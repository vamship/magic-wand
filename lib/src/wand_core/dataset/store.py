"""The dataset store: sessions and samples in a data folder.

This is the one place that writes a data folder. It implements the rules of
``docs/data-handling.md``: identifiers and numbering (section 4), the folder
layout (section 3) and the crash-safe writes (section 6). Subscribers are
told about every change after it is on disk.

The application is the only writer of a data folder, so no file locking is
used; a lock inside the store keeps its own threads in order.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from wand_core.dataset.fileio import (
    SAMPLES_FILE,
    SESSION_FILE,
    VIDEOS_FOLDER,
    DataFolder,
    append_sample,
    open_data_folder,
    read_samples,
    read_session,
    write_record,
    write_samples,
)
from wand_core.dataset.models import (
    CameraRecord,
    ClipPadding,
    DatasetError,
    Handedness,
    SampleRecord,
    SampleStatus,
    SessionRecord,
)
from wand_core.settings import MotionSettings, VisionSettings

logger = logging.getLogger(__name__)

NUMBER_DIGITS = 4


class SessionNotFoundError(DatasetError):
    pass


class SampleNotFoundError(DatasetError):
    pass


class SessionEndedError(DatasetError):
    """An ended session accepts no new samples."""


class ChangeKind(str, Enum):
    SESSION_WRITTEN = "session_written"
    SAMPLE_ADDED = "sample_added"
    SAMPLE_UPDATED = "sample_updated"
    SAMPLE_DELETED = "sample_deleted"


@dataclass(frozen=True)
class Change:
    """What changed, reported to subscribers once it is on disk."""

    kind: ChangeKind
    session_id: str
    sample_id: str | None = None


Subscriber = Callable[[Change], None]


# --- Identifiers ------------------------------------------------------------


def make_sample_id(session_id: str, number: int) -> str:
    """``<session id>-<number>``, the number zero-padded to 4 digits or more."""
    return f"{session_id}-{number:0{NUMBER_DIGITS}d}"


def split_sample_id(sample_id: str) -> tuple[str, int]:
    """The session id and number of a sample id."""
    session_id, _, number = sample_id.rpartition("-")
    if not session_id or not number.isdigit():
        raise SampleNotFoundError(f"not a sample id: {sample_id!r}")
    return session_id, int(number)


def _check_session_id(session_id: str) -> str:
    try:
        parsed = uuid.UUID(session_id)
    except (ValueError, AttributeError, TypeError):
        raise SessionNotFoundError(
            f"not a session id: {session_id!r}"
        ) from None
    if str(parsed) != session_id:
        raise SessionNotFoundError(f"not a session id: {session_id!r}")
    return session_id


class DatasetStore:
    """Sessions and samples of one data folder."""

    def __init__(
        self,
        folder: DataFolder,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.folder = folder
        self._clock = clock or (lambda: datetime.now().astimezone())
        self._lock = threading.RLock()
        self._subscribers: list[Subscriber] = []

    @classmethod
    def open(
        cls,
        path: Path,
        create: bool = False,
        clock: Callable[[], datetime] | None = None,
    ) -> DatasetStore:
        """Open a data folder (cleaning up after a crash), or create it."""
        return cls(open_data_folder(path, create=create), clock)

    @property
    def path(self) -> Path:
        return self.folder.path

    # --- Notifications ---------------------------------------------------

    def subscribe(self, subscriber: Subscriber) -> Callable[[], None]:
        """Call ``subscriber(change)`` after each change; returns a cancel."""
        with self._lock:
            self._subscribers.append(subscriber)

        def cancel() -> None:
            with self._lock:
                if subscriber in self._subscribers:
                    self._subscribers.remove(subscriber)

        return cancel

    def _notify(self, change: Change) -> None:
        for subscriber in list(self._subscribers):
            try:
                subscriber(change)
            except Exception:  # noqa: BLE001 - one subscriber must not stop others
                logger.exception("dataset subscriber failed")

    # --- Paths -----------------------------------------------------------

    def session_dir(self, session_id: str) -> Path:
        return self.folder.sessions_dir / _check_session_id(session_id)

    def clip_path(self, sample_id: str) -> Path:
        """Where the clip of a sample is (or would be) stored."""
        session_id, _ = split_sample_id(sample_id)
        return self.session_dir(session_id) / VIDEOS_FOLDER / f"{sample_id}.mp4"

    @staticmethod
    def clip_reference(sample_id: str) -> str:
        """The ``video.file`` value for a sample's clip."""
        return f"{VIDEOS_FOLDER}/{sample_id}.mp4"

    def has_clip(self, record: SampleRecord) -> bool:
        """True if the sample has a clip: referenced, and the file exists."""
        if record.video is None or not record.video.file:
            return False
        return (
            self.session_dir(record.session_id) / record.video.file
        ).is_file()

    # --- Sessions --------------------------------------------------------

    def create_session(
        self,
        author: str,
        handedness: Handedness,
        name: str | None = None,
        notes: str | None = None,
        camera: CameraRecord | None = None,
        vision_settings: VisionSettings | None = None,
        motion_settings: MotionSettings | None = None,
        clip_padding: ClipPadding | None = None,
        profile: str | None = None,
    ) -> SessionRecord:
        """Create a session folder with its record, no samples and no clips."""
        if not author.strip():
            raise DatasetError("a session needs an author")
        with self._lock:
            session_id = str(uuid.uuid4())
            record = SessionRecord(
                session_id=session_id,
                name=name,
                author=author,
                handedness=handedness,
                started_at=self._clock(),
                notes=notes,
                camera=camera or CameraRecord(),
                vision_settings=vision_settings or VisionSettings(),
                motion_settings=motion_settings or MotionSettings(),
                clip_padding=clip_padding or ClipPadding(),
                profile=profile,
            )
            folder = self.session_dir(session_id)
            (folder / VIDEOS_FOLDER).mkdir(parents=True)
            write_samples(folder / SAMPLES_FILE, [])
            # The session exists once its record does, so it is written last.
            write_record(folder / SESSION_FILE, record)
            self._notify(Change(ChangeKind.SESSION_WRITTEN, session_id))
            return record

    def get_session(self, session_id: str) -> SessionRecord:
        path = self.session_dir(session_id) / SESSION_FILE
        if not path.exists():
            raise SessionNotFoundError(f"no session {session_id}")
        return read_session(path)

    def list_sessions(self) -> list[SessionRecord]:
        """All sessions, oldest first. Folders without a record are skipped."""
        sessions = []
        for folder in sorted(self.folder.sessions_dir.iterdir()):
            if (folder / SESSION_FILE).exists():
                sessions.append(read_session(folder / SESSION_FILE))
        return sorted(sessions, key=lambda s: s.started_at)

    def update_session(self, session_id: str, **changes: Any) -> SessionRecord:
        """Change fields of a session record (for example ``notes``)."""
        with self._lock:
            current = self.get_session(session_id)
            data = current.model_dump()
            data.update(changes)
            record = SessionRecord.model_validate(data)
            write_record(self.session_dir(session_id) / SESSION_FILE, record)
            self._notify(Change(ChangeKind.SESSION_WRITTEN, session_id))
            return record

    def end_session(self, session_id: str) -> SessionRecord:
        """Mark a session ended. It accepts no new samples afterwards."""
        with self._lock:
            current = self.get_session(session_id)
            if current.ended_at is not None:
                return current
            return self.update_session(session_id, ended_at=self._clock())

    # --- Samples ---------------------------------------------------------

    def read_samples(self, session_id: str) -> list[SampleRecord]:
        self.get_session(session_id)  # raises if there is no such session
        return read_samples(self.session_dir(session_id) / SAMPLES_FILE)

    def get_sample(self, sample_id: str) -> SampleRecord:
        session_id, _ = split_sample_id(sample_id)
        for record in self.read_samples(session_id):
            if record.sample_id == sample_id:
                return record
        raise SampleNotFoundError(f"no sample {sample_id}")

    def next_sample_number(self, session_id: str) -> int:
        """One more than the larger of the recorded and the seen maximum.

        The session records the highest number it has used, and the samples
        file may hold a higher one if a crash fell between the two writes.
        Numbers are never reused, even after a delete.
        """
        session = self.get_session(session_id)
        in_file = [
            split_sample_id(r.sample_id)[1]
            for r in self.read_samples(session_id)
        ]
        return max([session.highest_sample_number, *in_file]) + 1

    def new_sample_id(self, session_id: str) -> str:
        return make_sample_id(session_id, self.next_sample_number(session_id))

    def add_sample(self, record: SampleRecord) -> SampleRecord:
        """Save a new sample of an open session.

        The clip, if any, must already be in place (it is written first).
        The sample's line is appended, then ``highestSampleNumber`` is
        updated.
        """
        with self._lock:
            session = self.get_session(record.session_id)
            if session.ended_at is not None:
                raise SessionEndedError(
                    f"session {record.session_id} has ended"
                )
            session_id, number = split_sample_id(record.sample_id)
            if session_id != record.session_id:
                raise DatasetError(
                    f"sample id {record.sample_id} does not belong to "
                    f"session {record.session_id}"
                )
            folder = self.session_dir(record.session_id)
            existing = read_samples(folder / SAMPLES_FILE)
            if any(r.sample_id == record.sample_id for r in existing):
                raise DatasetError(f"sample {record.sample_id} already exists")
            append_sample(folder / SAMPLES_FILE, record)
            if number > session.highest_sample_number:
                write_record(
                    folder / SESSION_FILE,
                    session.model_copy(
                        update={"highest_sample_number": number}
                    ),
                )
            self._notify(
                Change(
                    ChangeKind.SAMPLE_ADDED, record.session_id, record.sample_id
                )
            )
            return record

    def update_sample(
        self,
        sample_id: str,
        label: str | None = None,
        status: SampleStatus | None = None,
    ) -> SampleRecord:
        """Change a sample's label and/or status. Allowed on ended sessions."""
        with self._lock:
            session_id, _ = split_sample_id(sample_id)
            records = self.read_samples(session_id)
            for index, record in enumerate(records):
                if record.sample_id == sample_id:
                    break
            else:
                raise SampleNotFoundError(f"no sample {sample_id}")
            changes: dict[str, Any] = {"updated_at": self._clock()}
            if label is not None:
                changes["label"] = label
            if status is not None:
                changes["status"] = status
            data = record.model_dump()
            data.update(changes)
            updated = SampleRecord.model_validate(data)  # checks the label
            records[index] = updated
            write_samples(self.session_dir(session_id) / SAMPLES_FILE, records)
            self._notify(
                Change(ChangeKind.SAMPLE_UPDATED, session_id, sample_id)
            )
            return updated

    def delete_sample(self, sample_id: str) -> None:
        """Permanently remove a sample and its clip. Allowed on ended sessions.

        The samples file is rewritten without the sample first, then the clip
        is removed; a missing clip is not an error.
        """
        with self._lock:
            session_id, _ = split_sample_id(sample_id)
            records = self.read_samples(session_id)
            kept = [r for r in records if r.sample_id != sample_id]
            if len(kept) == len(records):
                raise SampleNotFoundError(f"no sample {sample_id}")
            write_samples(self.session_dir(session_id) / SAMPLES_FILE, kept)
            self.clip_path(sample_id).unlink(missing_ok=True)
            self._notify(
                Change(ChangeKind.SAMPLE_DELETED, session_id, sample_id)
            )


__all__ = [
    "Change",
    "ChangeKind",
    "DatasetStore",
    "SampleNotFoundError",
    "SessionEndedError",
    "SessionNotFoundError",
    "make_sample_id",
    "split_sample_id",
]
