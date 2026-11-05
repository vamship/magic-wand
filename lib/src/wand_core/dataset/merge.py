"""Merge data folders into a target (``docs/data-handling.md`` 7.3).

Sources are only read. A session the target lacks is copied whole, with its
clips (unless skipped), keeping all ids. A session in both with identical
content is skipped; with different content it is a conflict, reported and left
alone unless the caller asks to replace it. A session is copied to a temporary
folder and renamed into place, so an interrupted merge leaves no half-copied
session.
"""

from __future__ import annotations

import hashlib
import shutil
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Literal

from wand_core.dataset.fileio import (
    DATASET_FILE,
    SAMPLES_FILE,
    SESSION_FILE,
    SESSIONS_FOLDER,
    TEMP_SUFFIX,
    VIDEOS_FOLDER,
    NotADatasetError,
    _fsync_folder,
    open_data_folder,
    read_dataset_info,
    read_session,
)
from wand_core.dataset.models import DatasetError


class Action(str, Enum):
    COPIED = "copied"
    SKIPPED = "skipped"
    REPLACED = "replaced"
    CONFLICT = "conflict"
    ERROR = "error"


@dataclass(frozen=True)
class SessionResult:
    session_id: str
    source: Path
    action: Action
    message: str = ""

    def __str__(self) -> str:
        extra = f" ({self.message})" if self.message else ""
        return f"{self.session_id}: {self.action.value}{extra}"


@dataclass
class MergeResult:
    sessions: list[SessionResult] = field(default_factory=list)

    def count(self, action: Action) -> int:
        return sum(1 for s in self.sessions if s.action is action)

    @property
    def has_conflicts(self) -> bool:
        return self.count(Action.CONFLICT) > 0


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _same_content(a: Path, b: Path) -> bool:
    """Identical when the session file and the samples file match."""
    return all(
        _digest(a / name) == _digest(b / name)
        for name in (SESSION_FILE, SAMPLES_FILE)
    )


def _copy_session(source: Path, destination: Path, skip_clips: bool) -> None:
    ignore = shutil.ignore_patterns(f"*{TEMP_SUFFIX}")
    shutil.copytree(source, destination, ignore=ignore)
    if skip_clips:
        shutil.rmtree(destination / VIDEOS_FOLDER, ignore_errors=True)
        (destination / VIDEOS_FOLDER).mkdir()
    _fsync_folder(destination)


def merge_folders(
    sources: list[Path],
    target: Path,
    on_conflict: Literal["skip", "replace"] = "skip",
    skip_clips: bool = False,
) -> MergeResult:
    """Merge ``sources`` into ``target`` (created if it does not exist)."""
    if on_conflict not in ("skip", "replace"):
        raise ValueError("on_conflict must be 'skip' or 'replace'")
    target = Path(target)
    sources = [Path(s) for s in sources]
    for source in sources:
        if not (source / DATASET_FILE).is_file():
            raise NotADatasetError(f"{source} is not a dataset folder")
        read_dataset_info(source / DATASET_FILE)  # refuses unknown versions
        if source.resolve() == target.resolve():
            raise DatasetError("a folder cannot be merged into itself")
    folder = open_data_folder(target, create=True)
    result = MergeResult()
    for source in sources:
        sessions_dir = source / SESSIONS_FOLDER
        if not sessions_dir.is_dir():
            continue
        for session_dir in sorted(p for p in sessions_dir.iterdir() if p.is_dir()):
            if session_dir.name.endswith(TEMP_SUFFIX):
                continue
            result.sessions.append(
                _merge_session(
                    session_dir, folder.sessions_dir, on_conflict, skip_clips
                )
            )
    return result


def _merge_session(
    source: Path,
    sessions_dir: Path,
    on_conflict: str,
    skip_clips: bool,
) -> SessionResult:
    try:
        session = read_session(source / SESSION_FILE)
        (source / SAMPLES_FILE).read_bytes()
    except (DatasetError, OSError) as error:
        return SessionResult(source.name, source, Action.ERROR, str(error))
    session_id = session.session_id
    existing = sessions_dir / session_id
    root = sessions_dir.parent

    if not existing.exists():
        _place(source, existing, root, skip_clips)
        return SessionResult(session_id, source, Action.COPIED)
    try:
        identical = _same_content(source, existing)
    except OSError:
        identical = False
    if identical:
        return SessionResult(session_id, source, Action.SKIPPED, "identical")
    if on_conflict == "skip":
        return SessionResult(
            session_id,
            source,
            Action.CONFLICT,
            "the target has a different copy; it was left unchanged",
        )
    old = root / f".merge-old-{uuid.uuid4().hex}{TEMP_SUFFIX}"
    existing.rename(old)
    try:
        _place(source, existing, root, skip_clips)
    except BaseException:
        old.rename(existing)  # put the target's copy back
        raise
    shutil.rmtree(old, ignore_errors=True)
    return SessionResult(session_id, source, Action.REPLACED)


def _place(source: Path, destination: Path, root: Path, skip_clips: bool) -> None:
    """Copy to a temporary folder beside the target's files, then rename."""
    temp = root / f".merge-{uuid.uuid4().hex}{TEMP_SUFFIX}"
    try:
        _copy_session(source, temp, skip_clips)
        temp.rename(destination)
    except BaseException:
        shutil.rmtree(temp, ignore_errors=True)
        raise
    _fsync_folder(destination.parent)
