"""Building the training data from datasets (``training/docs/design.md`` 5.2).

Reads accepted samples from data folders, normalizes each gesture with the
library's normalizer and writes the table and its description. Rebuilding
gives the same content; only ``builtAt`` differs.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import pandas as pd

from wand_core import normalize
from wand_core.dataset import (
    SampleFilter,
    SampleStatus,
    SessionConflictError,
    find_datasets,
    iter_folder,
    session_conflicts,
)
from wand_train.data.format import (
    COLUMNS,
    TrainingDataError,
    TrainingDataInfo,
    fingerprint,
    read_info,
    read_table,
    write_info,
    write_table,
)


def repository_root(start: Path | None = None) -> Path:
    """The workspace root: the nearest folder above with a ``uv.lock``."""
    start = (start or Path.cwd()).resolve()
    for folder in (start, *start.parents):
        if (folder / "uv.lock").is_file():
            return folder
    return start


def short_commit(folder: Path) -> str:
    """The short git commit of the repository, or an empty string."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=folder,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return result.stdout.strip()


def select_datasets(location: Path, names: Sequence[str] = ()) -> list[Path]:
    """The dataset folders to use: the named ones, or all in ``location``."""
    if names:
        folders = []
        for name in names:
            folder = Path(location) / name
            if not folder.is_dir():
                raise TrainingDataError(
                    f"dataset {name!r} not found in {location}"
                )
            folders.append(folder)
        return folders
    found = find_datasets(location)
    for dataset in found:
        if dataset.error:
            raise TrainingDataError(f"{dataset.path}: {dataset.error}")
    if not found:
        raise TrainingDataError(f"no datasets found in {location}")
    return [dataset.path for dataset in found]


def build_table(
    folders: Sequence[Path],
) -> tuple[pd.DataFrame, list[tuple[str, str, str]]]:
    """The table of accepted samples and the fingerprint lines.

    A session that is in several folders is used once; copies that differ stop
    the build. The fingerprint lines cover the accepted samples.
    """
    folders = sorted(Path(folder) for folder in folders)
    conflicts = session_conflicts(folders)
    if conflicts:
        names = ", ".join(sorted(conflicts))
        raise SessionConflictError(
            f"session(s) {names} differ between datasets; "
            "resolve them (for example with a merge) and build again"
        )
    seen: set[str] = set()
    rows = []
    lines = []
    keep = SampleFilter(status=SampleStatus.ACCEPTED)
    for folder in folders:
        used: set[str] = set()
        for sample, session in iter_folder(folder, keep, exclude_sessions=seen):
            used.add(session.session_id)
            positions = sample.positions
            gesture = normalize.normalize(
                positions.time_s,
                positions.horizontal,
                positions.vertical,
                sample.frame_size,
            )
            rows.append(
                {
                    "sampleId": sample.sample_id,
                    "sessionId": sample.session_id,
                    "author": session.author,
                    "handedness": session.handedness.value,
                    "label": sample.label,
                    "durationS": float(gesture[-1]),
                    "frameWidth": sample.frame_size[0],
                    "frameHeight": sample.frame_size[1],
                    "rawTimeS": list(positions.time_s),
                    "rawX": list(positions.horizontal),
                    "rawY": list(positions.vertical),
                    "steps": gesture[:-1],
                }
            )
            lines.append((sample.sample_id, sample.label, sample.status.value))
        seen.update(used)
    table = pd.DataFrame(rows, columns=list(COLUMNS))
    table = table.sort_values(["sessionId", "sampleId"], kind="stable")
    return table.reset_index(drop=True), lines


def describe(
    table: pd.DataFrame,
    lines: list[tuple[str, str, str]],
    folders: Sequence[Path],
    root: Path,
) -> TrainingDataInfo:
    def name(folder: Path) -> str:
        try:
            return Path(folder).resolve().relative_to(root).as_posix()
        except ValueError:
            return Path(folder).as_posix()

    return TrainingDataInfo(
        built_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        datasets=sorted(name(folder) for folder in folders),
        source_commit=short_commit(root),
        session_ids=sorted(set(table["sessionId"])),
        sample_count=len(table),
        fingerprint=fingerprint(lines),
        normalization=normalize.settings(),
    )


def build(
    folders: Sequence[Path], output: Path, root: Path | None = None
) -> TrainingDataInfo:
    """Build the training data into ``output`` and return its description."""
    root = root or repository_root()
    table, lines = build_table(folders)
    info = describe(table, lines, folders, root)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    write_table(output, table)
    write_info(output, info)
    return info


def check(folders: Sequence[Path], training_data: Path) -> list[str]:
    """What differs between the datasets and the committed training data.

    Returns messages; an empty list means they match. Nothing is written.
    """
    info = read_info(training_data)
    _, lines = build_table(folders)
    problems = []
    current = fingerprint(lines)
    if current != info.fingerprint:
        problems.append(
            f"the fingerprint differs: datasets give {current[:12]}, "
            f"{training_data} has {info.fingerprint[:12]}"
        )
    if len(lines) != info.sample_count:
        problems.append(
            f"the sample count differs: datasets have {len(lines)}, "
            f"{training_data} has {info.sample_count}"
        )
    if info.normalization != normalize.settings():
        problems.append(
            f"the normalization differs: library {normalize.settings()}, "
            f"{training_data} has {info.normalization}"
        )
    return problems


def summary(training_data: Path) -> str:
    """Counts per label and per author of the committed table."""
    table = read_table(training_data)
    parts = [f"{len(table)} samples"]
    for column, title in (("label", "Label"), ("author", "Author")):
        counts = table[column].value_counts().sort_index()
        parts.append(f"\n{title:<16}Samples")
        parts.extend(f"{key:<16}{count}" for key, count in counts.items())
    return "\n".join(parts)
