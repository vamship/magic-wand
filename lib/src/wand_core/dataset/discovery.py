"""Datasets side by side in a data location (``docs/data-handling.md`` 3).

A data location is a folder such as ``data/`` whose subfolders are data
folders, one for each dataset. This module lists them, creates a new one, and
finds the sessions that exist in more than one of several data folders with
different content.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from wand_core.dataset.fileio import (
    DATASET_FILE,
    SAMPLES_FILE,
    SESSION_FILE,
    SESSIONS_FOLDER,
    TEMP_SUFFIX,
    open_data_folder,
    read_dataset_info,
    read_session,
    split_complete_lines,
)
from wand_core.dataset.merge import _same_content
from wand_core.dataset.models import DatasetError, SessionRecord

NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class InvalidDatasetNameError(DatasetError):
    """A dataset name that is not a lowercase slug."""


class DatasetExistsError(DatasetError):
    """A dataset (or any folder) with that name already exists."""


class SessionConflictError(DatasetError):
    """The same session has different content in different data folders."""


@dataclass(frozen=True)
class DatasetSummary:
    """One dataset found in a data location."""

    name: str
    path: Path
    format_version: int | None
    sessions: int
    samples: int
    error: str | None = None  # set when dataset.json could not be read


def is_valid_dataset_name(name: str) -> bool:
    """A lowercase slug: letters, digits, hyphen and underscore."""
    return bool(NAME_PATTERN.match(name))


def session_dirs(folder: Path) -> list[tuple[Path, SessionRecord]]:
    """The sessions of a data folder, oldest first. Reads only."""
    sessions_dir = Path(folder) / SESSIONS_FOLDER
    found = []
    if sessions_dir.is_dir():
        for session_dir in sorted(sessions_dir.iterdir()):
            if (
                session_dir.is_dir()
                and not session_dir.name.endswith(TEMP_SUFFIX)
                and (session_dir / SESSION_FILE).is_file()
            ):
                found.append(
                    (session_dir, read_session(session_dir / SESSION_FILE))
                )
    return sorted(found, key=lambda pair: pair[1].started_at)


def _count_samples(session_dir: Path) -> int:
    try:
        raw = (session_dir / SAMPLES_FILE).read_bytes()
    except OSError:
        return 0
    lines, _ = split_complete_lines(raw)
    return sum(1 for line in lines if line.strip())


def _summarize(path: Path) -> DatasetSummary:
    try:
        info = read_dataset_info(path / DATASET_FILE)
    except (DatasetError, OSError) as error:
        return DatasetSummary(path.name, path, None, 0, 0, str(error))
    sessions = 0
    samples = 0
    sessions_dir = path / SESSIONS_FOLDER
    if sessions_dir.is_dir():
        for session_dir in sessions_dir.iterdir():
            if (
                session_dir.is_dir()
                and not session_dir.name.endswith(TEMP_SUFFIX)
                and (session_dir / SESSION_FILE).is_file()
            ):
                sessions += 1
                samples += _count_samples(session_dir)
    return DatasetSummary(
        path.name, path, info.format_version, sessions, samples
    )


def find_datasets(location: Path) -> list[DatasetSummary]:
    """The datasets in a data location, sorted by name.

    A dataset is a subfolder that contains a ``dataset.json``. Other files and
    folders, and folders whose name starts with a dot, are ignored. A dataset
    whose ``dataset.json`` cannot be read is listed with ``error`` set.
    """
    location = Path(location)
    if not location.is_dir():
        return []
    return [
        _summarize(child)
        for child in sorted(location.iterdir())
        if child.is_dir()
        and not child.name.startswith(".")
        and (child / DATASET_FILE).is_file()
    ]


def create_dataset(location: Path, name: str) -> Path:
    """Create the data folder ``<location>/<name>`` and return its path.

    The name must be a lowercase slug and must not exist yet.
    """
    if not is_valid_dataset_name(name):
        raise InvalidDatasetNameError(
            f"{name!r} is not a valid dataset name: use lowercase letters, "
            "digits, hyphens and underscores"
        )
    location = Path(location)
    path = location / name
    if path.exists():
        raise DatasetExistsError(f"{path} already exists")
    open_data_folder(path, create=True)
    return path


def session_conflicts(folders: Iterable[Path]) -> dict[str, list[Path]]:
    """Sessions in more than one folder whose content differs.

    Maps the session id to the session folders that hold it. Identical copies
    are not conflicts.
    """
    copies: dict[str, list[Path]] = {}
    for folder in folders:
        for session_dir, session in session_dirs(folder):
            copies.setdefault(session.session_id, []).append(session_dir)
    conflicts = {}
    for session_id, paths in copies.items():
        if len(paths) < 2:
            continue
        first = paths[0]
        try:
            same = all(_same_content(first, other) for other in paths[1:])
        except OSError:
            same = False
        if not same:
            conflicts[session_id] = paths
    return conflicts


__all__ = [
    "DatasetExistsError",
    "DatasetSummary",
    "InvalidDatasetNameError",
    "SessionConflictError",
    "create_dataset",
    "find_datasets",
    "is_valid_dataset_name",
    "session_conflicts",
    "session_dirs",
]
