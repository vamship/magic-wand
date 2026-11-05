"""Export and load: samples from data folders or an export file.

The export is one JSON Lines file: each line is a sample record with its
session record embedded under ``session``, without video (``docs/
data-handling.md`` 7.2). ``load_samples`` reads either a data folder or such a
file into the same in-memory form, with the same filters, for the classifier.
Reading never writes to the folders.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from wand_core.dataset.fileio import (
    DATASET_FILE,
    SAMPLES_FILE,
    SESSION_FILE,
    SESSIONS_FOLDER,
    TEMP_SUFFIX,
    NotADatasetError,
    dump_line,
    read_dataset_info,
    read_samples,
    read_session,
)
from wand_core.dataset.models import (
    DatasetError,
    Handedness,
    SampleRecord,
    SampleStatus,
    SessionRecord,
    from_disk,
    to_disk,
)


@dataclass(frozen=True)
class SampleFilter:
    """Which samples to keep. Unset fields keep everything."""

    status: SampleStatus | None = None
    label: str | None = None
    session: str | None = None
    author: str | None = None
    start: datetime | None = None  # captured at or after
    end: datetime | None = None  # captured at or before

    def keeps(self, sample: SampleRecord, session: SessionRecord) -> bool:
        return (
            (self.status is None or sample.status is self.status)
            and (self.label is None or sample.label == self.label)
            and (self.session is None or session.session_id == self.session)
            and (self.author is None or session.author == self.author)
            and (self.start is None or sample.captured_at >= self.start)
            and (self.end is None or sample.captured_at <= self.end)
        )


@dataclass(frozen=True)
class LoadedSample:
    """A sample as plain Python data, with its session."""

    sample_id: str
    session_id: str
    label: str
    status: SampleStatus
    handedness: Handedness
    frame_size: tuple[int, int]
    captured_at: datetime
    time_s: list[float]
    horizontal: list[float]
    vertical: list[float]
    session: SessionRecord

    @classmethod
    def of(cls, sample: SampleRecord, session: SessionRecord) -> LoadedSample:
        return cls(
            sample.sample_id,
            sample.session_id,
            sample.label,
            sample.status,
            sample.handedness,
            sample.frame_size,
            sample.captured_at,
            list(sample.positions.time_s),
            list(sample.positions.horizontal),
            list(sample.positions.vertical),
            session,
        )


def iter_folder(
    folder: Path, keep: SampleFilter | None = None
) -> Iterator[tuple[SampleRecord, SessionRecord]]:
    """Samples of a data folder with their sessions, oldest session first.

    Reads only: nothing is cleaned up or repaired.
    """
    folder = Path(folder)
    if not (folder / DATASET_FILE).is_file():
        raise NotADatasetError(f"{folder} is not a dataset folder")
    read_dataset_info(folder / DATASET_FILE)  # refuses unknown versions
    sessions = []
    sessions_dir = folder / SESSIONS_FOLDER
    for session_dir in (
        sorted(sessions_dir.iterdir()) if sessions_dir.is_dir() else []
    ):
        if session_dir.name.endswith(TEMP_SUFFIX):
            continue
        if (session_dir / SESSION_FILE).is_file():
            sessions.append(
                (session_dir, read_session(session_dir / SESSION_FILE))
            )
    for session_dir, session in sorted(sessions, key=lambda s: s[1].started_at):
        for sample in read_samples(session_dir / SAMPLES_FILE):
            if keep is None or keep.keeps(sample, session):
                yield sample, session


def export_samples(
    folders: Iterable[Path],
    output: Path,
    keep: SampleFilter | None = None,
) -> int:
    """Write the export file, line by line. Returns the number of samples."""
    count = 0
    with open(output, "w", encoding="utf-8") as out:
        for folder in folders:
            for sample, session in iter_folder(folder, keep):
                data = to_disk(sample.model_copy(update={"video": None}))
                data["session"] = to_disk(session)
                out.write(dump_line(data) + "\n")
                count += 1
    return count


def _iter_export(
    path: Path, keep: SampleFilter | None
) -> Iterator[tuple[SampleRecord, SessionRecord]]:
    with open(path, encoding="utf-8") as lines:
        for number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            source = f"{path} line {number}"
            try:
                data = json.loads(line)
            except ValueError as error:
                raise DatasetError(f"{source} is not valid JSON") from error
            if not isinstance(data, dict) or "session" not in data:
                raise DatasetError(f"{source} has no session")
            session = from_disk(SessionRecord, data.pop("session"), source)
            sample = from_disk(SampleRecord, data, source)
            if keep is None or keep.keeps(sample, session):
                yield sample, session


def load_samples(
    source: Path | Iterable[Path], keep: SampleFilter | None = None
) -> list[LoadedSample]:
    """Load a data folder, an export file, or several folders.

    A file is read as an export, a folder as a data folder.
    """
    paths = (
        [Path(source)]
        if isinstance(source, (str, Path))
        else [Path(p) for p in source]
    )
    loaded: list[LoadedSample] = []
    for path in paths:
        if path.is_dir():
            pairs = iter_folder(path, keep)
        elif path.is_file():
            pairs = _iter_export(path, keep)
        else:
            raise NotADatasetError(f"{path} does not exist")
        loaded.extend(LoadedSample.of(s, ss) for s, ss in pairs)
    return loaded
