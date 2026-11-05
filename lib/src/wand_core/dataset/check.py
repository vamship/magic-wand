"""The consistency check of a data folder (``docs/data-handling.md`` 7.1).

It only reads. It reports leftover temporary files, incomplete last lines,
clips with no sample, unsupported format versions, damaged files and samples
with an unknown label. A sample whose clip is missing is information, not an
error, because clips are optional.
"""

from __future__ import annotations

import json
from collections.abc import Collection
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from wand_core.dataset.fileio import (
    DATASET_FILE,
    SAMPLES_FILE,
    SESSION_FILE,
    SESSIONS_FOLDER,
    TEMP_SUFFIX,
    VIDEOS_FOLDER,
    read_dataset_info,
    read_session,
    split_complete_lines,
)
from wand_core.dataset.models import (
    DatasetError,
    SampleRecord,
    UnsupportedFormatError,
    from_disk,
)


class Level(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class Finding:
    level: Level
    code: str
    path: Path
    message: str

    def __str__(self) -> str:
        return f"{self.level.value}: {self.path}: {self.message}"


@dataclass
class CheckReport:
    findings: list[Finding] = field(default_factory=list)
    sessions: int = 0
    samples: int = 0

    def add(self, level: Level, code: str, path: Path, message: str) -> None:
        self.findings.append(Finding(level, code, path, message))

    def of(self, level: Level) -> list[Finding]:
        return [f for f in self.findings if f.level is level]

    @property
    def errors(self) -> list[Finding]:
        return self.of(Level.ERROR)

    @property
    def warnings(self) -> list[Finding]:
        return self.of(Level.WARNING)

    @property
    def info(self) -> list[Finding]:
        return self.of(Level.INFO)

    @property
    def ok(self) -> bool:
        return not self.errors

    def codes(self) -> set[str]:
        return {f.code for f in self.findings}


def check_folder(
    folder: Path, labels: Collection[str] | None = None
) -> CheckReport:
    """Check a data folder. Never writes. ``labels`` are the known ids."""
    folder = Path(folder)
    report = CheckReport()
    if not (folder / DATASET_FILE).is_file():
        report.add(
            Level.ERROR, "not_a_dataset", folder, f"no {DATASET_FILE} here"
        )
        return report
    try:
        read_dataset_info(folder / DATASET_FILE)
    except UnsupportedFormatError as error:
        report.add(
            Level.ERROR, "unsupported_format", folder / DATASET_FILE, str(error)
        )
    except DatasetError as error:
        report.add(Level.ERROR, "damaged_file", folder / DATASET_FILE, str(error))

    for temp in sorted(folder.rglob(f"*{TEMP_SUFFIX}")):
        report.add(
            Level.WARNING,
            "temporary_file",
            temp,
            "a leftover temporary file (it is removed when the folder opens)",
        )

    sessions_dir = folder / SESSIONS_FOLDER
    if sessions_dir.is_dir():
        for session_dir in sorted(p for p in sessions_dir.iterdir() if p.is_dir()):
            if session_dir.name.endswith(TEMP_SUFFIX):
                continue  # reported above as a temporary file
            _check_session(session_dir, labels, report)
    return report


def _check_session(
    session_dir: Path, labels: Collection[str] | None, report: CheckReport
) -> None:
    session_file = session_dir / SESSION_FILE
    try:
        session = read_session(session_file)
    except UnsupportedFormatError as error:
        report.add(Level.ERROR, "unsupported_format", session_file, str(error))
        return
    except FileNotFoundError:
        report.add(Level.ERROR, "missing_file", session_file, "no session.json")
        return
    except DatasetError as error:
        report.add(Level.ERROR, "damaged_file", session_file, str(error))
        return
    report.sessions += 1
    if session.session_id != session_dir.name:
        report.add(
            Level.ERROR,
            "session_id_mismatch",
            session_file,
            f"the folder is named {session_dir.name} but the session id is "
            f"{session.session_id}",
        )

    sample_ids: set[str] = set()
    for sample, number in _read_samples(session_dir, report):
        report.samples += 1
        sample_ids.add(sample.sample_id)
        if sample.session_id != session.session_id:
            report.add(
                Level.ERROR,
                "session_id_mismatch",
                session_dir / SAMPLES_FILE,
                f"sample {sample.sample_id} (line {number}) belongs to "
                f"session {sample.session_id}",
            )
        if labels is not None and sample.label not in labels:
            report.add(
                Level.ERROR,
                "unknown_label",
                session_dir / SAMPLES_FILE,
                f"sample {sample.sample_id} has the unknown label "
                f"{sample.label!r}",
            )
        if sample.video is not None and not (
            session_dir / sample.video.file
        ).is_file():
            report.add(
                Level.INFO,
                "missing_clip",
                session_dir / sample.video.file,
                f"sample {sample.sample_id} has no clip file",
            )

    videos = session_dir / VIDEOS_FOLDER
    if videos.is_dir():
        for clip in sorted(videos.iterdir()):
            if clip.suffix == TEMP_SUFFIX or not clip.is_file():
                continue
            if clip.stem not in sample_ids:
                report.add(
                    Level.WARNING,
                    "orphan_clip",
                    clip,
                    "a clip with no sample",
                )


def _read_samples(session_dir: Path, report: CheckReport):
    """Yield ``(record, line number)``; report damaged and incomplete lines."""
    path = session_dir / SAMPLES_FILE
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        report.add(Level.ERROR, "missing_file", path, "no samples.jsonl")
        return
    lines, incomplete = split_complete_lines(raw)
    if incomplete:
        report.add(
            Level.WARNING,
            "incomplete_last_line",
            path,
            "the last line is incomplete (a crash while saving); it is "
            "removed when the folder opens",
        )
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            data = json.loads(line.decode("utf-8"))
            record = from_disk(SampleRecord, data, f"{path} line {number}")
        except UnsupportedFormatError as error:
            report.add(Level.ERROR, "unsupported_format", path, str(error))
        except (ValueError, DatasetError) as error:
            last = number == len(lines) and not incomplete
            code = "incomplete_last_line" if last else "damaged_line"
            level = Level.WARNING if last else Level.ERROR
            report.add(level, code, path, f"line {number}: {error}")
        else:
            yield record, number
