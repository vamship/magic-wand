"""Session Service: starting, ending, listing, loading and resuming sessions.

It owns the ``session`` field of the Application State and supplies the next
sample number to the Capture Controller (``data-collection/docs/design.md``
sections 3.2 and 4.5). The session is only recorded in the state after every
earlier step has succeeded, so a failed start or resume changes nothing.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, Protocol

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from wand_collect.cameras import CameraCatalog, as_catalog
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
from wand_core.casing import camel_keys, to_camel
from wand_core.dataset import (
    Action,
    CameraRecord,
    DatasetError,
    DatasetExistsError,
    DatasetStore,
    Handedness,
    InvalidDatasetNameError,
    SessionNotFoundError,
    SessionRecord,
    create_dataset,
    find_datasets,
    is_valid_dataset_name,
    merge_folders,
)
from wand_core.dataset.fileio import DATASET_FILE
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


class DetailsBody(BaseModel):
    """New name and/or notes; an empty text clears the field."""

    name: str | None = None
    notes: str | None = None


class NameBody(BaseModel):
    name: str


class MergeBody(BaseModel):
    """Datasets to merge, and into which dataset (which may be new)."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    sources: list[str]
    target: str
    on_conflict: Literal["skip", "replace"] = "skip"
    skip_clips: bool = False


class SessionService:
    def __init__(
        self,
        state: ApplicationState,
        engine: CaptureEngine,
        store: DatasetStore,
        calibration: CalibrationService,
        app_settings: DataCollectionSettings | None = None,
        camera_lister: Callable[[], list[CameraInfo]] | CameraCatalog = (
            list_cameras
        ),
        data_location: Path | None = None,
        dataset: str | None = None,
    ) -> None:
        self._state = state
        self._engine = engine
        self._store = store
        self._calibration = calibration
        self._app = app_settings or DataCollectionSettings()
        self._cameras = as_catalog(camera_lister)
        self._controller: CaptureControllerPort | None = None
        self._lock = threading.Lock()  # one start, load or end at a time
        # The datasets live side by side in the data location; by default
        # the one the store was opened on is one of them.
        self._location = Path(data_location or store.path.parent)
        self._dataset = dataset or store.path.name
        state.update(Owner.SESSION_SERVICE, dataset=self._dataset)

        self.router = APIRouter()
        add = self.router.add_api_route
        add("/datasets", self.get_datasets, methods=["GET"])
        add("/datasets", self.post_dataset, methods=["POST"])
        add("/datasets/merge", self.merge_datasets, methods=["POST"])
        add("/dataset", self.put_dataset, methods=["PUT"], status_code=204)
        add("/sessions", self.get_sessions, methods=["GET"])
        add("/sessions", self.post_session, methods=["POST"])
        add("/sessions/{session_id}/load", self.load, methods=["POST"])
        add(
            "/sessions/current/end", self.end, methods=["POST"], status_code=204
        )
        add(
            "/sessions/{session_id}/end",
            self.end_session,
            methods=["POST"],
            status_code=204,
        )
        add(
            "/sessions/current/hold",
            self.hold,
            methods=["POST"],
            status_code=204,
        )
        add(
            "/sessions/current/camera/confirm",
            self.confirm_camera,
            methods=["POST"],
            status_code=204,
        )
        add(
            "/sessions/{session_id}",
            self.patch,
            methods=["PATCH"],
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
                    "notes": record.notes,
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

    # --- Datasets --------------------------------------------------------

    def get_datasets(self) -> list[dict[str, Any]]:
        """The datasets in the data location, and which one is in use."""
        return [
            {
                "name": found.name,
                "sessions": found.sessions,
                "samples": found.samples,
                "inUse": found.name == self._dataset,
                **({"error": found.error} if found.error else {}),
            }
            for found in find_datasets(self._location)
        ]

    def post_dataset(self, body: NameBody) -> dict[str, Any]:
        """Create a new, empty dataset."""
        with self._lock:
            self._require_no_session()
            name = body.name.strip()
            try:
                create_dataset(self._location, name)
            except InvalidDatasetNameError as error:
                raise InvalidRequestError(str(error)) from error
            except DatasetExistsError as error:
                raise ConflictError("dataset_exists", str(error)) from error
        return {"name": name}

    def put_dataset(self, body: NameBody) -> None:
        """Choose the dataset in use: sessions and samples come from it."""
        with self._lock:
            self._require_no_session()
            name = body.name.strip()
            path = self._existing_dataset(name)
            try:
                self._store.switch_to(path)
            except DatasetError as error:
                raise InvalidRequestError(str(error)) from error
            self._dataset = name
            self._state.update(Owner.SESSION_SERVICE, dataset=name)

    def merge_datasets(self, body: MergeBody) -> dict[str, Any]:
        """Merge datasets into a target dataset, which is created if new.

        Sources are only read. The result lists what happened to each session.
        """
        with self._lock:
            self._require_no_session()
            if not body.sources:
                raise InvalidRequestError("give at least one source dataset")
            sources = [self._existing_dataset(n) for n in body.sources]
            target = body.target.strip()
            if not is_valid_dataset_name(target):
                raise InvalidRequestError(
                    f"{target!r} is not a valid dataset name"
                )
            if target in body.sources:
                raise InvalidRequestError(
                    "a dataset cannot be merged into itself"
                )
            try:
                result = merge_folders(
                    sources,
                    self._location / target,
                    on_conflict=body.on_conflict,
                    skip_clips=body.skip_clips,
                )
            except (DatasetError, OSError, ValueError) as error:
                raise InvalidRequestError(str(error)) from error
            if target == self._dataset:
                self._store.switch_to(self._location / target)  # reindex
        return {
            "target": target,
            "sessions": [
                {
                    "sessionId": s.session_id,
                    "source": s.source.parent.parent.name,
                    "action": s.action.value,
                    "message": s.message,
                }
                for s in result.sessions
            ],
            "counts": {
                action.value: result.count(action)
                for action in Action
                if result.count(action)
            },
        }

    def _existing_dataset(self, name: str) -> Path:
        if not is_valid_dataset_name(name):
            raise InvalidRequestError(f"{name!r} is not a valid dataset name")
        path = self._location / name
        if not (path / DATASET_FILE).is_file():
            raise NotFoundError(f"there is no dataset named {name!r}")
        return path

    def _require_no_session(self) -> None:
        if self._state.snapshot.session is not None:
            raise ConflictError(
                "session_active",
                "a session is loaded; end it or put it on hold first",
            )

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
        index = self._find_camera(record.camera.device, record.camera.index)
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
        # The camera that opened may not be the one the session used (a
        # camera cannot always be told from another), so the user checks it
        # before capturing; see ``confirm_camera``.
        self._record(record, SessionRole.CAPTURE, camera_check=True)
        summary = _summary(record, SessionRole.CAPTURE)
        summary["cameraCheck"] = True
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

    def _find_camera(self, device: str | None, index: int | None) -> int:
        """The camera to open for a resumed session: the recorded one when it
        can be found, otherwise the best available.

        A camera is not always told from another (macOS gives no names, so a
        camera is only "the one at position N"), and the user checks the
        camera in any case, so this never refuses because the recorded camera
        is missing. It refuses only when there is no camera at all.
        """
        current = self._state.snapshot.camera
        if (
            device is not None
            and current.device == device
            and current.index is not None
        ):
            return current.index  # in use, so it may not probe again
        listed = self._cameras.get()
        if device is not None and not any(
            c.device_id == device for c in listed
        ):
            # Not in the list read earlier: it may have been plugged in since.
            listed = self._cameras.get(refresh=True)
        for camera in listed:
            if device is not None and camera.device_id == device:
                return camera.index
        if index is not None and any(c.index == index for c in listed):
            return index
        if current.index is not None:
            return current.index
        if listed:
            return listed[0].index
        raise ConflictError(
            "camera_unavailable",
            f"no camera is available to resume the session (it was recorded "
            f"with {device}); connect one and try again",
        )

    # --- Camera check ----------------------------------------------------

    def confirm_camera(self) -> None:
        """The user has checked the camera of a resumed session.

        The session record takes the camera that is now in use (the user may
        have changed it), and capture can start.
        """
        with self._lock:
            session = self._state.snapshot.session
            if (
                session is None
                or session.role is not SessionRole.CAPTURE
                or not session.camera_check
            ):
                raise ConflictError(
                    "no_camera_check", "there is no camera to check"
                )
            camera = self._state.snapshot.camera
            if camera.device is None:
                raise ConflictError(
                    "camera_unavailable", "there is no camera in use"
                )
            record = self._store.update_session(
                session.id,
                camera=CameraRecord(
                    device=camera.device,
                    index=camera.index,
                    requested=_mode_record(camera.requested),
                    actual=_mode_record(camera.actual),
                ),
            )
            self._record(record, SessionRole.CAPTURE)

    # --- End -------------------------------------------------------------

    def end(self) -> None:
        """End the loaded session for good: it accepts no more samples.

        A session loaded for review is only closed, and stays as it was (this
        is how the Web UI closes a review).
        """
        self._leave(finish=True)

    def end_session(self, session_id: str) -> None:
        """End any open session, loaded or not, for good.

        If it is the loaded session, in either role, capturing stops and the
        session is unloaded. Ending another session leaves the loaded one
        alone. An ended session is refused.
        """
        with self._lock:
            try:
                record = self._store.get_session(session_id)
            except SessionNotFoundError as error:
                raise NotFoundError(str(error)) from error
            if record.ended_at is not None:
                raise ConflictError(
                    "session_ended", "the session has already ended"
                )
            loaded = self._state.snapshot.session
            is_loaded = loaded is not None and loaded.id == session_id
            if (
                is_loaded
                and loaded.role is SessionRole.CAPTURE
                and self._controller is not None
            ):
                # Stop first, so that no sample is saved after the end.
                self._controller.stop()
            self._store.end_session(session_id)
            if is_loaded:
                self._state.update(Owner.SESSION_SERVICE, session=None)

    def hold(self) -> None:
        """Put the loaded session on hold: capturing stops and the session
        is unloaded, but it stays open on disk, as when the application is
        closed. It can be resumed later, and another session can be started
        or loaded meanwhile."""
        self._leave(finish=False)

    def _leave(self, finish: bool) -> None:
        with self._lock:
            session = self._state.snapshot.session
            if session is None:
                raise ConflictError("no_session", "no session is loaded")
            if session.role is SessionRole.CAPTURE:
                # Stop first, so that no sample is saved after the end.
                if self._controller is not None:
                    self._controller.stop()
                if finish:
                    self._store.end_session(session.id)
            self._state.update(Owner.SESSION_SERVICE, session=None)

    # --- Delete ----------------------------------------------------------

    def patch(self, session_id: str, body: DetailsBody) -> dict[str, Any]:
        """Change the name and/or notes of any session, open or ended.

        These are descriptions, not settings, so they can change while the
        session is loaded, and after it has ended.
        """
        changes = {
            field: (getattr(body, field) or "").strip() or None
            for field in ("name", "notes")
            if field in body.model_fields_set
        }
        if not changes:
            raise InvalidRequestError("give a name, notes or both")
        with self._lock:
            try:
                record = self._store.update_session(session_id, **changes)
            except SessionNotFoundError as error:
                raise NotFoundError(str(error)) from error
            loaded = self._state.snapshot.session
            if loaded is not None and loaded.id == session_id:
                self._record(record, loaded.role, loaded.camera_check)
        return {
            "id": record.session_id,
            "name": record.name,
            "notes": record.notes,
        }

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

    def _record(
        self,
        record: SessionRecord,
        role: SessionRole,
        camera_check: bool = False,
    ) -> None:
        self._state.update(
            Owner.SESSION_SERVICE,
            session=SessionInfo(
                record.session_id,
                record.name or record.author,
                role,
                camera_check,
                record.camera.device if camera_check else None,
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
