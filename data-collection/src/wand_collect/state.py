"""Application State: the shared record of what the application is doing.

One instance is created when the application starts and passed to every
component (never a module global). It holds one immutable snapshot. Readers
take the current snapshot with no lock; each field has one owner, the only
component allowed to write it. Every change builds a new snapshot, swaps it
in under a lock and notifies the listeners, one at a time and in order.
See ``data-collection/docs/design.md`` section 4.3.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import threading
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any

from pydantic import ConfigDict

from wand_core.casing import camel_keys, to_camel
from wand_core.settings import MotionSettings, VisionSettings
from wand_core.sources import CameraMode
from wand_core.types import Discard

logger = logging.getLogger(__name__)


# --- Frozen settings --------------------------------------------------------


class FrozenVisionSettings(VisionSettings):
    """Vision settings that cannot be changed once built."""

    model_config = ConfigDict(frozen=True)


class FrozenMotionSettings(MotionSettings):
    """Motion settings that cannot be changed once built."""

    model_config = ConfigDict(frozen=True)


# --- Snapshot ---------------------------------------------------------------


class SessionRole(str, Enum):
    CAPTURE = "capture"
    REVIEW = "review"


class CaptureStatus(str, Enum):
    STOPPED = "STOPPED"
    COUNTDOWN = "COUNTDOWN"
    READY = "READY"
    RECORDING = "RECORDING"
    PAUSED = "PAUSED"


@dataclass(frozen=True)
class SessionInfo:
    id: str
    name: str
    role: SessionRole


@dataclass(frozen=True)
class SettingsState:
    """The working vision and motion settings, and the loaded profile."""

    vision: VisionSettings = field(default_factory=FrozenVisionSettings)
    motion: MotionSettings = field(default_factory=FrozenMotionSettings)
    profile: str | None = None

    def __post_init__(self) -> None:
        # Always hold frozen copies, so the snapshot cannot be changed by
        # whoever supplied the settings.
        object.__setattr__(
            self,
            "vision",
            FrozenVisionSettings.model_validate(self.vision.model_dump()),
        )
        object.__setattr__(
            self,
            "motion",
            FrozenMotionSettings.model_validate(self.motion.model_dump()),
        )


@dataclass(frozen=True)
class CameraState:
    device: str | None = None
    index: int | None = None
    requested: CameraMode | None = None
    actual: CameraMode | None = None


@dataclass(frozen=True)
class CaptureState:
    """Where the capture cycle is.

    ``countdown_ends_at`` is set during a countdown, ``remaining_s`` when the
    countdown is paused.
    """

    state: CaptureStatus = CaptureStatus.STOPPED
    countdown_ends_at: float | None = None
    remaining_s: float | None = None


@dataclass(frozen=True)
class LatestSample:
    id: str
    label: str
    status: str
    clip_available: bool
    saving: bool = False


@dataclass(frozen=True)
class Label:
    id: str
    name: str


@dataclass(frozen=True)
class StateSnapshot:
    """Everything the application is doing at one moment. Immutable."""

    session: SessionInfo | None = None
    settings: SettingsState = field(default_factory=SettingsState)
    camera: CameraState = field(default_factory=CameraState)
    capture: CaptureState = field(default_factory=CaptureState)
    active_label: str | None = None
    latest_sample: LatestSample | None = None
    last_discard: Discard | None = None
    counts: Mapping[str, int] = field(
        default_factory=lambda: MappingProxyType({})
    )
    samples_revision: int = 0
    labels: tuple[Label, ...] = ()

    def to_json_dict(self) -> dict[str, Any]:
        """The snapshot as plain data with camel case keys."""
        return {
            to_camel(f.name): _jsonable(getattr(self, f.name))
            for f in dataclasses.fields(self)
        }

    def to_json(self) -> str:
        return json.dumps(self.to_json_dict())


def settings_locked(snapshot: StateSnapshot) -> bool:
    """Settings are locked while a session is loaded for capture."""
    return (
        snapshot.session is not None
        and snapshot.session.role is SessionRole.CAPTURE
    )


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (VisionSettings, MotionSettings)):
        return camel_keys(value.model_dump())
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            to_camel(f.name): _jsonable(getattr(value, f.name))
            for f in dataclasses.fields(value)
        }
    if isinstance(value, Mapping):  # keys are data (such as label ids)
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


# --- Ownership --------------------------------------------------------------


class Owner(str, Enum):
    SESSION_SERVICE = "session_service"
    CALIBRATION_SERVICE = "calibration_service"
    CAPTURE_ENGINE = "capture_engine"
    CAPTURE_CONTROLLER = "capture_controller"
    SAMPLE_LIBRARY = "sample_library"
    LABEL_SERVICE = "label_service"


FIELD_OWNERS: dict[str, Owner] = {
    "session": Owner.SESSION_SERVICE,
    "settings": Owner.CALIBRATION_SERVICE,
    "camera": Owner.CAPTURE_ENGINE,
    "capture": Owner.CAPTURE_CONTROLLER,
    "active_label": Owner.CAPTURE_CONTROLLER,
    "latest_sample": Owner.CAPTURE_CONTROLLER,
    "last_discard": Owner.CAPTURE_CONTROLLER,
    "counts": Owner.SAMPLE_LIBRARY,
    "samples_revision": Owner.SAMPLE_LIBRARY,
    "labels": Owner.LABEL_SERVICE,
}


class OwnershipError(PermissionError):
    """A component tried to write a field it does not own, or no field."""


Listener = Callable[[StateSnapshot], None]


class ApplicationState:
    """Holds the current snapshot and tells listeners when it changes.

    Listener callbacks run one at a time, in the order the changes were
    made, and must not block (the server's listener only enqueues).
    """

    def __init__(self) -> None:
        self._snapshot = StateSnapshot()
        self._lock = threading.Lock()
        self._listeners: list[Listener] = []
        self._pending: deque[StateSnapshot] = deque()
        self._delivering = False

    @property
    def snapshot(self) -> StateSnapshot:
        """The current snapshot. Safe to read from any thread, no lock."""
        return self._snapshot

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        """Call ``listener(snapshot)`` on every change. Returns a canceller."""
        with self._lock:
            self._listeners.append(listener)

        def cancel() -> None:
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return cancel

    def update(self, owner: Owner, **fields: Any) -> StateSnapshot:
        """Change the named fields, which ``owner`` must own."""
        return self.modify(owner, lambda _: fields)

    def modify(
        self,
        owner: Owner,
        change: Callable[[StateSnapshot], Mapping[str, Any]],
    ) -> StateSnapshot:
        """Change fields computed from the current snapshot, atomically.

        ``change`` runs under the lock, so a read-modify-write (such as
        increasing the samples revision) cannot lose an update. It must be
        quick and must not call back into this object.
        """
        with self._lock:
            fields = dict(change(self._snapshot))
            _check_ownership(owner, fields)
            new = dataclasses.replace(self._snapshot, **_prepare(fields))
            if new == self._snapshot:
                return self._snapshot
            self._snapshot = new
            self._pending.append(new)
            if self._delivering:
                return new
            self._delivering = True
        self._deliver()
        return new

    def _deliver(self) -> None:
        # One thread at a time drains the queue, outside the lock, so
        # listeners see snapshots in the order they were made.
        while True:
            with self._lock:
                if not self._pending:
                    self._delivering = False
                    return
                snapshot = self._pending.popleft()
                listeners = list(self._listeners)
            for listener in listeners:
                try:
                    listener(snapshot)
                except Exception:  # noqa: BLE001 - one listener must not stop others
                    logger.exception("state listener failed")


def _check_ownership(owner: Owner, fields: Mapping[str, Any]) -> None:
    if not fields:
        raise OwnershipError("an update must name at least one field")
    for name in fields:
        if name not in FIELD_OWNERS:
            raise OwnershipError(f"unknown state field: {name}")
        if FIELD_OWNERS[name] is not owner:
            raise OwnershipError(
                f"{owner.value} does not own {name} "
                f"(owner: {FIELD_OWNERS[name].value})"
            )


def _prepare(fields: Mapping[str, Any]) -> dict[str, Any]:
    prepared = dict(fields)
    if "counts" in prepared:
        prepared["counts"] = MappingProxyType(dict(prepared["counts"]))
    if "labels" in prepared:
        prepared["labels"] = tuple(prepared["labels"])
    return prepared
