"""Settings of the data collection application (data-collection.yaml).

See ``data-collection/docs/design.md`` section 5.4.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import model_validator

from wand_core.settings import (
    SettingsModel,
    in_range,
    load_settings,
    positive,
)

FILE_NAME = "data-collection.yaml"


class ServerSettings(SettingsModel):
    host: str = "127.0.0.1"
    port: int = 8000

    @model_validator(mode="after")
    def _check(self) -> ServerSettings:
        in_range("server.port", self.port, 1, 65535)
        return self


class CameraSettings(SettingsModel):
    index: int = 0
    width: int = 640
    height: int = 480
    fps: int = 30

    @model_validator(mode="after")
    def _check(self) -> CameraSettings:
        in_range("camera.index", self.index, 0, 1000)
        positive("camera.width", self.width)
        positive("camera.height", self.height)
        positive("camera.fps", self.fps)
        return self


class ClipPadding(SettingsModel):
    pre_s: float = 2.0
    post_s: float = 2.0

    @model_validator(mode="after")
    def _check(self) -> ClipPadding:
        in_range("clipPadding.preS", self.pre_s, 0, 60)
        in_range("clipPadding.postS", self.post_s, 0, 60)
        return self


class Shortcuts(SettingsModel):
    pause: str = "Escape"
    previous: str = "ArrowLeft"
    next: str = "ArrowRight"
    reject: str = "r"
    delete: str = "Backspace"
    toggle_view: str = "p"


class DataCollectionSettings(SettingsModel):
    data_folder: str = "data"
    server: ServerSettings = ServerSettings()
    camera: CameraSettings = CameraSettings()
    countdown_s: float = 3.0
    clip_padding: ClipPadding = ClipPadding()
    end_threshold_ratio: float = 0.6
    shortcuts: Shortcuts = Shortcuts()

    @model_validator(mode="after")
    def _check(self) -> DataCollectionSettings:
        in_range("countdownS", self.countdown_s, 0, 60)
        in_range("endThresholdRatio", self.end_threshold_ratio, 0.01, 1)
        if not self.data_folder:
            raise ValueError("dataFolder must not be empty")
        return self


def load_app_settings(config_dir: Path) -> DataCollectionSettings:
    """Load ``data-collection.yaml`` with its local override applied."""
    return load_settings(DataCollectionSettings, Path(config_dir) / FILE_NAME)
