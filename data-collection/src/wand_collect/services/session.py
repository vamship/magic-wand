"""Session Service: starting, ending, listing, loading and resuming sessions.

It owns the ``session`` field of the Application State and supplies the next
sample number to the Capture Controller (``data-collection/docs/design.md``
sections 3.2 and 4.5). The session is only recorded in the state after every
earlier step has succeeded, so a failed start or resume changes nothing.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any, Literal, Protocol

from fastapi import APIRouter
from pydantic import BaseModel

from wand_collect.engine import CaptureEngine
from wand_collect.server import (
    ConflictError,
    InvalidRequestError,
    NotFoundError,
)
from wand_collect.services.calibration import CalibrationService
from wand_collect.settings import DataCollectionSettings
from wand_collect.state import (
    ApplicationState,
    Owner,
    SessionInfo,
    SessionRole,
)
from wand_core.casing import camel_keys
from wand_core.dataset import (
    CameraRecord,
    DatasetError,
    DatasetStore,
    Handedness,
    SessionNotFoundError,
    SessionRecord,
)
from wand_core.dataset.models import ClipPadding, Mode
from wand_core.sources import CameraInfo, CameraMode, list_cameras

OPEN_CAMERA_TIMEOUT_S = 15.0


class CaptureControllerPort(Protocol):
    """What the Session Service needs from the Capture Controller."""

    def stop(self) -> None: ...


class StartBody(BaseModel):
    author: str
    handedness: Handedness
    name: str | None = None
    notes: str | None = None


class SessionService:
    def __init__(
        self,
        state: ApplicationState,
        engine: CaptureEngine,
        store: DatasetStore,
        calibration: CalibrationService,
        app_settings: DataCollectionSettings | None = None,
        camera_lister: Callable[[], list[CameraInfo]] = list_cameras,
    ) -> None:
        self._state = state
        self._engine = engine
        self._store = store
        self._calibration = calibration
        self._app = app_settings or DataCollectionSettings()
        self._list_cameras = camera_lister
        self._controller: CaptureControllerPort | None = None
        self._lock = threading.Lock()  # one start, load or end at a time

        self.router = APIRouter()
        add = self.router.add_api_route
        add("/sessions", self.get_sessions, methods=["GET"])
        add("/sessions", self.post_session, methods=["POST"])
        add("/sessions/{session_id}/load", self.load, methods=["POST"])
        add(
            "/sessions/current/end", self.end, methods=["POST"], status_code=204
        )
        add(
            "/sessions/{session_id}",
            self.delete,
            methods=["DELETE"],
            status_code=204,
        )

    def set_controller(self, controller: CaptureControllerPort) -> None:
        """Say who to stop when a session ends (the Capture Controller)."""
        self._controller = controller

    # --- Sample numbers --------------------------------------------------

    def next_sample_number(self) -> int:
        """The number for the next sample of the session loaded for capture."""
        session = self._state.snapshot.session
        if session is None or session.role is not SessionRole.CAPTURE:
            raise ConflictError(
                "no_session", "no session is loaded for capture"
            )
        return self._store.next_sample_number(session.id)

    # --- List ------------------------------------------------------------

    def get_sessions(self) -> list[dict[str, Any]]:
        listed = []
        for record in self._store.list_sessions():
            listed.append(
                {
                    "id": record.session_id,
                    "name": record.name,
                    "author": record.author,
                    "startedAt": record.started_at.isoformat(),
                    "endedAt": (
                        record.ended_at.isoformat() if record.ended_at else None
                    ),
                    "sampleCount": len(
                        self._store.read_samples(record.session_id)
                    ),
                    "open": record.ended_at is None,
                }
            )
        return listed

    # --- Start -----------------------------------------------------------

    def post_session(self, body: StartBody) -> dict[str, Any]:
        author = body.author.strip()
        if not author:
            raise InvalidRequestError("the author must not be empty")
        with self._lock:
            self._require_no_capture_session()
            snapshot = self._state.snapshot
            if snapshot.camera.device is None:
                raise ConflictError(
                    "camera_unavailable", "there is no camera in use"
                )
            camera = snapshot.camera
            padding = self._app.clip_padding
            try:
                record = self._store.create_session(
                    author=author,
                    handedness=body.handedness,
                    name=body.name or None,
                    notes=body.notes or None,
                    camera=CameraRecord(
                        device=camera.device,
                        index=camera.index,
                        requested=_mode_record(camera.requested),
                        actual=_mode_record(camera.actual),
                    ),
                    vision_settings=snapshot.settings.vision,
                    motion_settings=snapshot.settings.motion,
                    clip_padding=ClipPadding(
                        pre_s=padding.pre_s, post_s=padding.post_s
                    ),
                    profile=snapshot.settings.profile,
                )
            except DatasetError as error:
                raise InvalidRequestError(str(error)) from error
            self._record(record, SessionRole.CAPTURE)
            return _summary(record, SessionRole.CAPTURE)

    # --- Load and resume -------------------------------------------------

    def load(
        self, session_id: str, mode: Literal["review", "resume"]
    ) -> dict[str, Any]:
        with self._lock:
            self._require_no_capture_session()
            try:
                record = self._store.get_session(session_id)
            except SessionNotFoundError as error:
                raise NotFoundError(str(error)) from error
            if mode == "review":
                self._record(record, SessionRole.REVIEW)
                return _summary(record, SessionRole.REVIEW)
            return self._resume(record)

    def _resume(self, record: SessionRecord) -> dict[str, Any]:
        if record.ended_at is not None:
            raise ConflictError(
                "session_ended",
                "an ended session cannot be resumed; load it for review",
            )
        index = self._find_camera(record.camera.device)
        requested = record.camera.requested or record.camera.actual
        width, height, fps = (
            (requested.width, requested.height, requested.fps)
            if requested
            else (
                self._app.camera.width,
                self._app.camera.height,
                self._app.camera.fps,
            )
        )
        try:
            self._engine.open_camera(index, width, height, fps).result(
                OPEN_CAMERA_TIMEOUT_S
            )
        except Exception as error:  # noqa: BLE001 - reported to the user
            raise ConflictError("camera_unavailable", str(error)) from error
        self._calibration.apply_recorded_settings(
            record.vision_settings, record.motion_settings, record.profile
        )
        self._record(record, SessionRole.CAPTURE)
        summary = _summary(record, SessionRole.CAPTURE)
        actual = self._state.snapshot.camera.actual
        if record.camera.actual and not _same_mode(
            record.camera.actual, actual
        ):
            summary["warnings"].append(
                "the camera delivers a different mode than the one recorded "
                f"in the session ({_describe(record.camera.actual)}, now "
                f"{_describe(actual)})"
            )
        return summary

    def _find_camera(self, device: str | None) -> int:
        """The index of the camera with this device identifier."""
        if device is not None:
            current = self._state.snapshot.camera
            if current.device == device and current.index is not None:
                return current.index  # in use, so it may not probe again
            for camera in self._list_cameras():
                if camera.device_id == device:
                    return camera.index
        raise ConflictError(
            "camera_unavailable",
            f"the camera recorded in this session ({device}) is not "
            "available; connect it and try again",
        )

    # --- End -------------------------------------------------------------

    def end(self) -> None:
        with self._lock:
            session = self._state.snapshot.session
            if session is None:
                raise ConflictError("no_session", "no session is loaded")
            if session.role is SessionRole.CAPTURE:
                # Stop first, so that no sample is saved after the end.
                if self._controller is not None:
                    self._controller.stop()
                self._store.end_session(session.id)
            self._state.update(Owner.SESSION_SERVICE, session=None)

    # --- Delete ----------------------------------------------------------

    def delete(self, session_id: str) -> None:
        """Delete a session that is not loaded, with all its samples."""
        with self._lock:
            loaded = self._state.snapshot.session
            if loaded is not None and loaded.id == session_id:
                raise ConflictError(
                    "session_loaded",
                    "the session is loaded; end or close it first",
                )
            try:
                self._store.delete_session(session_id)
            except SessionNotFoundError as error:
                raise NotFoundError(str(error)) from error

    # --- Helpers ---------------------------------------------------------

    def _require_no_capture_session(self) -> None:
        session = self._state.snapshot.session
        if session is not None and session.role is SessionRole.CAPTURE:
            raise ConflictError(
                "session_active",
                "a session is already loaded for capture; end it first",
            )

    def _record(self, record: SessionRecord, role: SessionRole) -> None:
        self._state.update(
            Owner.SESSION_SERVICE,
            session=SessionInfo(
                record.session_id, record.name or record.author, role
            ),
        )


def _mode_record(mode: CameraMode | None) -> Mode | None:
    return None if mode is None else Mode(**vars(mode))


def _same_mode(recorded: Mode, actual: CameraMode | None) -> bool:
    return (
        actual is not None
        and recorded.width == actual.width
        and recorded.height == actual.height
    )


def _describe(mode: Mode | CameraMode | None) -> str:
    if mode is None:
        return "unknown"
    return f"{mode.width}x{mode.height} at {mode.fps:g} fps"


def _summary(record: SessionRecord, role: SessionRole) -> dict[str, Any]:
    return camel_keys(
        {
            "id": record.session_id,
            "name": record.name,
            "role": role.value,
            "warnings": [],
        }
    )
