"""Sample Library: finds and changes stored samples, and keeps the counts.

It serves review (the samples of one session) and browsing (the whole
dataset), makes the path images, and owns the ``counts`` and
``samples_revision`` fields of the Application State
(``data-collection/docs/design.md`` section 4.9).

An in-memory index holds one summary per sample. It is built once when the
library is created and then follows the Dataset Store's change
notifications, whoever caused them, so every change reaches the counts and
the revision by the same path.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import cv2
import numpy as np
from fastapi import APIRouter, Query, Response
from platformdirs import user_cache_dir
from pydantic import BaseModel

from wand_collect.server import InvalidRequestError, NotFoundError
from wand_collect.state import ApplicationState, Owner
from wand_core.casing import camel_keys
from wand_core.dataset import (
    DatasetStore,
    SampleNotFoundError,
    SampleRecord,
    SampleStatus,
    SessionNotFoundError,
    SessionRecord,
)
from wand_core.dataset.store import Change, ChangeKind
from wand_core.render import encode_png, render_path

logger = logging.getLogger(__name__)

THUMBNAIL_SIZE = (96, 72)
MAX_IMAGE_SIDE = 2000
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 500


def default_cache_dir() -> Path:
    """The operating system's cache location for thumbnails."""
    return Path(user_cache_dir("wand-collect")) / "thumbnails"


@dataclass(frozen=True)
class SampleSummary:
    sample_id: str
    session_id: str
    session_name: str | None
    author: str
    label: str
    status: SampleStatus
    captured_at: datetime
    has_clip: bool

    def to_json(self) -> dict[str, Any]:
        return camel_keys(
            {
                "id": self.sample_id,
                "session_id": self.session_id,
                "session_name": self.session_name,
                "author": self.author,
                "label": self.label,
                "status": self.status.value,
                "captured_at": self.captured_at.isoformat(),
                "has_clip": self.has_clip,
            }
        )


class PatchBody(BaseModel):
    label: str | None = None
    status: SampleStatus | None = None


class SampleLibrary:
    def __init__(
        self,
        state: ApplicationState,
        store: DatasetStore,
        cache_dir: Path | None = None,
    ) -> None:
        self._state = state
        self._store = store
        self._cache_dir = Path(cache_dir) if cache_dir else default_cache_dir()
        self._lock = threading.RLock()
        self._samples: dict[str, SampleSummary] = {}
        self._sessions: dict[str, tuple[str | None, str]] = {}  # name, author
        self._accepted: Counter[str] = Counter()
        self._rebuild()
        store.subscribe(self._on_change)

        self.router = APIRouter()
        add = self.router.add_api_route
        add("/samples", self.get_samples, methods=["GET"])
        add("/samples/{sample_id}", self.get_sample, methods=["GET"])
        add("/samples/{sample_id}", self.patch_sample, methods=["PATCH"])
        add(
            "/samples/{sample_id}",
            self.delete_sample,
            methods=["DELETE"],
            status_code=204,
        )
        add("/samples/{sample_id}/image", self.get_image, methods=["GET"])
        add(
            "/samples/{sample_id}/thumbnail",
            self.get_thumbnail,
            methods=["GET"],
        )

    # --- The index -------------------------------------------------------

    def _rebuild(self) -> None:
        with self._lock:
            self._samples.clear()
            self._sessions.clear()
            for session in self._store.list_sessions():
                self._sessions[session.session_id] = (
                    session.name,
                    session.author,
                )
                for record in self._store.read_samples(session.session_id):
                    self._add(record)
        self._state.update(
            Owner.SAMPLE_LIBRARY, counts=dict(self._accepted_counts())
        )

    def _summary(self, record: SampleRecord) -> SampleSummary:
        name, author = self._sessions.get(record.session_id, (None, ""))
        return SampleSummary(
            record.sample_id,
            record.session_id,
            name,
            author,
            record.label,
            record.status,
            record.captured_at,
            self._store.has_clip(record),
        )

    def _add(self, record: SampleRecord) -> None:
        summary = self._summary(record)
        self._samples[record.sample_id] = summary
        if summary.status is SampleStatus.ACCEPTED:
            self._accepted[summary.label] += 1

    def _remove(self, sample_id: str) -> None:
        old = self._samples.pop(sample_id, None)
        if old is not None and old.status is SampleStatus.ACCEPTED:
            self._accepted[old.label] -= 1

    def _accepted_counts(self) -> dict[str, int]:
        return {k: v for k, v in self._accepted.items() if v > 0}

    def _on_change(self, change: Change) -> None:
        with self._lock:
            if change.kind is ChangeKind.SESSION_WRITTEN:
                try:
                    session = self._store.get_session(change.session_id)
                except SessionNotFoundError:
                    return
                self._refresh_session(session)
            elif change.sample_id is not None:
                self._remove(change.sample_id)
                if change.kind is not ChangeKind.SAMPLE_DELETED:
                    try:
                        record = self._store.get_sample(change.sample_id)
                    except SampleNotFoundError:
                        record = None
                    if record is not None:
                        self._add(record)
            else:
                return
            counts = self._accepted_counts()
        self._state.modify(
            Owner.SAMPLE_LIBRARY,
            lambda s: {
                "counts": counts,
                "samples_revision": s.samples_revision + 1,
            },
        )

    def _refresh_session(self, session: SessionRecord) -> None:
        new = (session.name, session.author)
        if self._sessions.get(session.session_id) == new:
            return
        self._sessions[session.session_id] = new
        for sample_id, summary in list(self._samples.items()):
            if summary.session_id == session.session_id:
                self._samples[sample_id] = SampleSummary(
                    **{
                        **summary.__dict__,
                        "session_name": session.name,
                        "author": session.author,
                    }
                )

    def label_use_count(self, label: str) -> int:
        """How many samples (of any status) have this label."""
        with self._lock:
            return sum(1 for s in self._samples.values() if s.label == label)

    # --- Queries ---------------------------------------------------------

    def query(
        self,
        label: str | None = None,
        session: str | None = None,
        author: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        status: SampleStatus | None = None,
        order: Literal["capture", "newest"] = "capture",
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> tuple[list[SampleSummary], int]:
        """One page of the matching samples, and the total that match."""
        with self._lock:
            found = [
                s
                for s in self._samples.values()
                if (label is None or s.label == label)
                and (session is None or s.session_id == session)
                and (author is None or s.author == author)
                and (start is None or s.captured_at >= start)
                and (end is None or s.captured_at <= end)
                and (status is None or s.status is status)
            ]
        # The id breaks ties, so pages are stable.
        found.sort(
            key=lambda s: (s.captured_at, s.sample_id),
            reverse=order == "newest",
        )
        first = (page - 1) * page_size
        return found[first : first + page_size], len(found)

    def get_samples(
        self,
        label: str | None = None,
        session: str | None = None,
        author: str | None = None,
        from_: str | None = Query(None, alias="from"),
        to: str | None = None,
        status: SampleStatus | None = None,
        order: Literal["capture", "newest"] = "capture",
        page: int = Query(1, ge=1),
        page_size: int = Query(
            DEFAULT_PAGE_SIZE, alias="pageSize", ge=1, le=MAX_PAGE_SIZE
        ),
    ) -> dict[str, Any]:
        if session == "current":
            current = self._state.snapshot.session
            if current is None:
                raise InvalidRequestError("no session is loaded")
            session = current.id
        items, total = self.query(
            label,
            session,
            author,
            _parse_time(from_, "from"),
            _parse_time(to, "to", end_of_day=True),
            status,
            order,
            page,
            page_size,
        )
        return {
            "items": [item.to_json() for item in items],
            "total": total,
            "page": page,
            "pageSize": page_size,
        }

    # --- One sample ------------------------------------------------------

    def _record(self, sample_id: str) -> SampleRecord:
        try:
            return self._store.get_sample(sample_id)
        except (SampleNotFoundError, SessionNotFoundError) as error:
            raise NotFoundError(str(error)) from error

    def get_sample(self, sample_id: str) -> dict[str, Any]:
        return self._details(self._record(sample_id))

    def _details(self, record: SampleRecord) -> dict[str, Any]:
        data = camel_keys(record.model_dump(mode="json"))
        data["id"] = data.pop("sampleId")
        data["hasClip"] = self._store.has_clip(record)
        return data

    def patch_sample(self, sample_id: str, body: PatchBody) -> dict[str, Any]:
        if body.label is None and body.status is None:
            raise InvalidRequestError("give a label, a status or both")
        self._record(sample_id)  # 404 when there is no such sample
        if body.label is not None and body.label not in {
            label.id for label in self._state.snapshot.labels
        }:
            raise InvalidRequestError(f"no such label: {body.label!r}")
        try:
            updated = self._store.update_sample(
                sample_id, label=body.label, status=body.status
            )
        except SampleNotFoundError as error:
            raise NotFoundError(str(error)) from error
        return self._details(updated)

    def delete_sample(self, sample_id: str) -> None:
        self._record(sample_id)
        try:
            self._store.delete_sample(sample_id)
        except SampleNotFoundError as error:
            raise NotFoundError(str(error)) from error
        for stale in self._cache_dir.glob(f"{sample_id}-*.png"):
            stale.unlink(missing_ok=True)

    # --- Images ----------------------------------------------------------

    def get_image(
        self,
        sample_id: str,
        mode: Literal["path", "overlay"] = "path",
        width: int | None = Query(None, ge=1, le=MAX_IMAGE_SIDE),
    ) -> Response:
        record = self._record(sample_id)
        frame_width, frame_height = record.frame_size
        width = width or frame_width
        size = (width, max(1, round(width * frame_height / frame_width)))
        frame = None
        if mode == "overlay":
            frame = self._clip_frame(record)
            if frame is None:
                raise NotFoundError(f"sample {sample_id} has no clip")
        image = render_path(_positions(record), size, frame)
        return Response(encode_png(image), media_type="image/png")

    def get_thumbnail(self, sample_id: str) -> Response:
        record = self._record(sample_id)
        digest = hashlib.sha1(
            json.dumps(
                [record.positions.horizontal, record.positions.vertical]
            ).encode()
        ).hexdigest()[:16]
        cached = self._cache_dir / f"{sample_id}-{digest}.png"
        try:
            png = cached.read_bytes()
        except OSError:
            png = encode_png(render_path(_positions(record), THUMBNAIL_SIZE))
            try:
                self._cache_dir.mkdir(parents=True, exist_ok=True)
                cached.write_bytes(png)
            except OSError:
                logger.warning("thumbnail cache is not writable: %s", cached)
        return Response(
            png,
            media_type="image/png",
            headers={"Cache-Control": "max-age=3600"},
        )

    def _clip_frame(self, record: SampleRecord) -> np.ndarray | None:
        """The clip's frame at the gesture start, or ``None`` without a clip."""
        if not self._store.has_clip(record):
            return None
        path = self._store.session_dir(record.session_id) / record.video.file
        capture = cv2.VideoCapture(str(path))
        try:
            if not capture.isOpened():
                return None
            # Read forward to the gesture start: a short clip, and exact.
            fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
            wanted = max(0, round(record.video.gesture_start_s * fps))
            frame = None
            for _ in range(wanted + 1):
                ok, image = capture.read()
                if not ok:
                    break  # the start is past the end: keep the last frame
                frame = image
            return frame
        except cv2.error as error:
            logger.warning("cannot read clip %s: %s", path, error)
            return None
        finally:
            capture.release()


def _positions(record: SampleRecord) -> list[tuple[float, float]]:
    columns = record.positions
    return list(zip(columns.horizontal, columns.vertical))


def _parse_time(
    value: str | None, name: str, end_of_day: bool = False
) -> datetime | None:
    """An ISO date or date and time. A date alone as an end covers its day."""
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise InvalidRequestError(f"{name} is not an ISO date: {value!r}")
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()  # local time
    if end_of_day and len(value) == 10:
        parsed += timedelta(days=1) - timedelta(microseconds=1)
    return parsed


__all__ = ["SampleLibrary", "SampleSummary"]
