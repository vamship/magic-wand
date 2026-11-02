"""Calibration Service: prepares the settings for a session.

It owns the ``settings`` field of the Application State: the working vision
and motion settings and the loaded profile. It chooses the camera, derives the
vision settings from clicks on a frozen frame, proposes motion thresholds from
a guided measurement, and saves and loads profiles. While a session is loaded
for capture it refuses every change (``data-collection/docs/design.md``
section 4.4).

Mirroring: when the live view is mirrored, the frozen frame is sent to the
browser mirrored too, and clicks arrive in that mirrored picture. The service
turns them back before using the real frame, so the calibration is always
done on what the camera saw.
"""

from __future__ import annotations

import base64
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

import cv2
import numpy as np
from fastapi import APIRouter, Response
from pydantic import BaseModel

from wand_collect.engine import CaptureEngine
from wand_collect.server import (
    ConflictError,
    InvalidRequestError,
    NotFoundError,
)
from wand_collect.settings import DataCollectionSettings
from wand_collect.state import (
    ApplicationState,
    Owner,
    SettingsState,
    settings_locked,
)
from wand_core.calibration import (
    ColorCalibrator,
    MotionCalibrationError,
    UnusableColorError,
    calibrate_motion,
)
from wand_core.casing import camel_keys
from wand_core.settings import (
    MotionSettings,
    SettingsError,
    VisionSettings,
    WorkingSettings,
    load_profile,
    profile_path,
    save_profile,
    validate,
)
from wand_core.sources import CameraInfo, list_cameras
from wand_core.types import TipDetection

STILL_SECONDS = 3.0
WAVE_SECONDS = 5.0
SETTLE_SECONDS = 0.5  # at the start of a phase, while the user gets ready
OPEN_CAMERA_TIMEOUT_S = 15.0
JPEG_QUALITY = 85


class SettingsBody(BaseModel):
    """A partial change: only the keys given are changed (camel case)."""

    vision: dict[str, Any] | None = None
    motion: dict[str, Any] | None = None


class CameraBody(BaseModel):
    index: int


class Click(BaseModel):
    horizontal: float
    vertical: float


class ClicksBody(BaseModel):
    points: list[Click] = []
    tolerance: float | None = None


class MeasureBody(BaseModel):
    phase: Literal["still", "wave"]


class CalibrationService:
    def __init__(
        self,
        state: ApplicationState,
        engine: CaptureEngine,
        config_dir: Path,
        app_settings: DataCollectionSettings | None = None,
        camera_lister: Callable[[], list[CameraInfo]] = list_cameras,
        still_s: float = STILL_SECONDS,
        wave_s: float = WAVE_SECONDS,
        settle_s: float = SETTLE_SECONDS,
    ) -> None:
        self._state = state
        self._engine = engine
        self._config_dir = Path(config_dir)
        self._app = app_settings or DataCollectionSettings()
        self._list_cameras = camera_lister
        self._still_s = still_s
        self._wave_s = wave_s
        self._settle_s = settle_s

        self._frozen: np.ndarray | None = None  # in memory only
        self._colors = ColorCalibrator()
        self._measured: dict[str, list[TipDetection]] = {}

        self.router = APIRouter()
        add = self.router.add_api_route
        add("/cameras", self.get_cameras, methods=["GET"])
        add("/camera", self.put_camera, methods=["PUT"], status_code=204)
        add("/settings", self.put_settings, methods=["PUT"], status_code=204)
        add("/calibration/freeze", self.freeze, methods=["POST"])
        add("/calibration/clicks", self.clicks, methods=["POST"])
        add("/calibration/measure", self.measure, methods=["POST"])
        add("/profiles", self.get_profiles, methods=["GET"])
        add(
            "/profiles/{name}",
            self.put_profile,
            methods=["PUT"],
            status_code=204,
        )
        add(
            "/profiles/{name}/load",
            self.post_profile_load,
            methods=["POST"],
            status_code=204,
        )
        add(
            "/profiles/{name}",
            self.delete_profile,
            methods=["DELETE"],
            status_code=204,
        )

    # --- Helpers ---------------------------------------------------------

    def _require_unlocked(self) -> None:
        if settings_locked(self._state.snapshot):
            raise ConflictError(
                "session_active",
                "settings cannot change while a session is loaded for "
                "capture; end the session first",
            )

    @property
    def _mirror(self) -> bool:
        return self._app.mirror_preview

    def _write(self, **changes: Any) -> None:
        """Replace parts of the settings in the state."""

        def change(snapshot):
            current = snapshot.settings
            return {
                "settings": SettingsState(
                    vision=changes.get("vision", current.vision),
                    motion=changes.get("motion", current.motion),
                    profile=changes.get("profile", current.profile),
                )
            }

        self._state.modify(Owner.CALIBRATION_SERVICE, change)

    def apply_recorded_settings(
        self,
        vision: VisionSettings,
        motion: MotionSettings,
        profile: str | None = None,
    ) -> None:
        """Take the settings recorded in a session (used when it resumes).

        This is allowed even though a session is about to be loaded for
        capture: the Session Service calls it before recording the session.
        """
        self._write(vision=vision, motion=motion, profile=profile)

    # --- Cameras ---------------------------------------------------------

    def get_cameras(self) -> list[dict[str, Any]]:
        found = list(self._list_cameras())
        cameras = [
            {
                "index": c.index,
                "name": c.name,
                "deviceId": c.device_id,
                "modes": [
                    {"width": m.width, "height": m.height, "fps": m.fps}
                    for m in c.modes
                ],
            }
            for c in found
        ]
        # The camera in use may not open a second time to be probed, so make
        # sure it is listed.
        current = self._state.snapshot.camera
        if current.index is not None and all(
            c["index"] != current.index for c in cameras
        ):
            cameras.append(
                {
                    "index": current.index,
                    "name": current.device,
                    "deviceId": current.device,
                    "modes": [],
                }
            )
        return sorted(cameras, key=lambda c: c["index"])

    def put_camera(self, body: CameraBody) -> None:
        self._require_unlocked()
        camera = self._app.camera
        try:
            self._engine.open_camera(
                body.index, camera.width, camera.height, camera.fps
            ).result(OPEN_CAMERA_TIMEOUT_S)
        except Exception as error:  # noqa: BLE001 - reported to the user
            raise ConflictError("camera_unavailable", str(error)) from error

    # --- Settings --------------------------------------------------------

    def put_settings(self, body: SettingsBody) -> None:
        self._require_unlocked()
        current = self._state.snapshot.settings
        changes: dict[str, Any] = {}
        if body.vision:
            merged = {**camel_keys(current.vision.model_dump()), **body.vision}
            changes["vision"] = self._validated(VisionSettings, merged)
        if body.motion:
            partial = dict(body.motion)
            if "startSpeed" in partial and "endSpeed" not in partial:
                # The end threshold follows the start at a fixed ratio.
                ratio = self._app.end_threshold_ratio
                partial["endSpeed"] = round(partial["startSpeed"] * ratio, 3)
            merged = {**camel_keys(current.motion.model_dump()), **partial}
            changes["motion"] = self._validated(MotionSettings, merged)
        if changes:
            self._write(**changes)

    @staticmethod
    def _validated(model_class, data):
        try:
            return validate(model_class, data)
        except SettingsError as error:
            raise InvalidRequestError(str(error)) from error

    # --- Color calibration -----------------------------------------------

    def freeze(self) -> Response:
        """Keep the current frame for calibration and return it as a JPEG."""
        self._require_unlocked()
        raw = self._engine.latest_raw
        if raw is None:
            raise ConflictError(
                "camera_unavailable", "there is no camera frame to freeze"
            )
        self._frozen = raw.image.copy()
        self._colors = ColorCalibrator(self._state.snapshot.settings.vision)
        shown = cv2.flip(self._frozen, 1) if self._mirror else self._frozen
        ok, jpeg = cv2.imencode(
            ".jpg", shown, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
        )
        return Response(content=jpeg.tobytes(), media_type="image/jpeg")

    def clicks(self, body: ClicksBody) -> dict[str, Any]:
        self._require_unlocked()
        if self._frozen is None:
            raise InvalidRequestError("freeze a frame first")
        if not body.points and body.tolerance is None:
            raise InvalidRequestError("give at least one point or a tolerance")
        self._colors.base = self._state.snapshot.settings.vision
        points = [
            (1 - p.horizontal if self._mirror else p.horizontal, p.vertical)
            for p in body.points
        ]
        try:
            if points:
                if body.tolerance is not None:
                    self._colors.tolerance = body.tolerance
                result = self._colors.add_clicks(self._frozen, points)
            else:
                result = self._colors.calibrate(
                    self._frozen, tolerance=body.tolerance
                )
        except UnusableColorError as error:
            raise InvalidRequestError(str(error)) from error
        except ValueError as error:  # for example a point outside the frame
            raise InvalidRequestError(str(error)) from error
        self._write(vision=result.settings)

        mask = cv2.cvtColor(result.mask, cv2.COLOR_GRAY2BGR)
        if self._mirror:
            mask = cv2.flip(mask, 1)
        tip = result.detection
        horizontal = tip.horizontal
        if tip.found and self._mirror:
            horizontal = 1 - horizontal
        return {
            "mask": _png_data_url(mask),
            "tip": {
                "found": tip.found,
                "horizontal": horizontal,
                "vertical": tip.vertical,
                "radius": tip.radius,
            },
            "otherRegions": result.other_regions,
            "sampleCount": result.sample_count,
            "tolerance": self._colors.tolerance,
        }

    # --- Guided motion measurement ---------------------------------------

    def measure(self, body: MeasureBody) -> dict[str, Any]:
        """Collect tip positions for a fixed time (a phase).

        After both phases, propose and write motion thresholds.
        """
        self._require_unlocked()
        seconds = self._still_s if body.phase == "still" else self._wave_s
        self._measured[body.phase] = self._collect(seconds)
        response: dict[str, Any] = {"phase": body.phase, "complete": False}
        if len(self._measured) < 2:
            return response

        snapshot = self._state.snapshot
        actual = snapshot.camera.actual
        aspect = actual.width / actual.height if actual else 4 / 3
        try:
            proposal = calibrate_motion(
                self._measured["still"],
                self._measured["wave"],
                snapshot.settings.motion,
                aspect,
            )
        except MotionCalibrationError as error:
            raise InvalidRequestError(str(error)) from error
        self._write(motion=proposal.settings)
        response.update(
            complete=True,
            proposal={
                "startSpeed": proposal.settings.start_speed,
                "endSpeed": proposal.settings.end_speed,
                "idleCeiling": proposal.idle_ceiling,
                "typicalGestureSpeed": proposal.typical_gesture_speed,
                "peakCount": proposal.peak_count,
            },
        )
        return response

    def _collect(self, seconds: float) -> list[TipDetection]:
        """The detections over ``seconds`` of the camera's own time.

        The first moments are dropped: the user is still moving from the
        last position into this one, and that would skew the measurement.
        """
        seconds = seconds + self._settle_s
        collected: list[TipDetection] = []
        done = threading.Event()

        def listener(detection: TipDetection) -> None:
            collected.append(detection)
            if detection.timestamp_s - collected[0].timestamp_s >= seconds:
                done.set()

        self._engine.add_detection_listener(listener)
        try:
            done.wait(timeout=seconds * 3 + 2)
        finally:
            self._engine.remove_detection_listener(listener)
        if not collected:
            raise ConflictError(
                "camera_unavailable", "the camera is delivering no frames"
            )
        start = collected[0].timestamp_s + self._settle_s
        return [d for d in collected if d.timestamp_s >= start]

    # --- Profiles --------------------------------------------------------

    def get_profiles(self) -> list[dict[str, str]]:
        folder = self._config_dir / "profiles"
        names = (
            sorted(p.stem for p in folder.glob("*.yaml"))
            if folder.is_dir()
            else []
        )
        return [{"name": name} for name in names]

    def put_profile(self, name: str) -> None:
        """Save the current settings as a profile."""
        current = self._state.snapshot.settings
        try:
            save_profile(
                self._config_dir,
                name,
                WorkingSettings(vision=current.vision, motion=current.motion),
            )
        except SettingsError as error:
            raise InvalidRequestError(str(error)) from error

    def post_profile_load(self, name: str) -> None:
        self._require_unlocked()
        try:
            path = profile_path(self._config_dir, name)
        except SettingsError as error:
            raise InvalidRequestError(str(error)) from error
        if not path.exists():
            raise NotFoundError(f"no profile named {name!r}")
        try:
            working = load_profile(self._config_dir, name)
        except SettingsError as error:
            raise InvalidRequestError(str(error)) from error
        self._write(vision=working.vision, motion=working.motion, profile=name)

    def delete_profile(self, name: str) -> None:
        try:
            path = profile_path(self._config_dir, name)
        except SettingsError as error:
            raise InvalidRequestError(str(error)) from error
        if not path.exists():
            raise NotFoundError(f"no profile named {name!r}")
        path.unlink()
        current = self._state.snapshot.settings
        if current.profile == name:
            self._write(profile=None)


def _png_data_url(image: np.ndarray) -> str:
    ok, png = cv2.imencode(".png", image)
    return "data:image/png;base64," + base64.b64encode(png.tobytes()).decode()


__all__ = ["CalibrationService"]
