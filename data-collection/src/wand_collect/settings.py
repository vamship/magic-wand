"""Settings of the data collection application (data-collection.yaml).

See ``data-collection/docs/design.md`` section 5.4.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import model_validator

from wand_core.dataset import is_valid_dataset_name
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
    up: str = "ArrowUp"
    down: str = "ArrowDown"
    # One key or a list of keys; the first is shown on the button.
    reject: str | list[str] = [" ", "r"]
    delete: str = "Backspace"
    toggle_view: str = "v"
    scrub_open: str = "s"
    # The scrubbing view.
    scrub_play: str = " "
    scrub_back: str = "ArrowLeft"
    scrub_forward: str = "ArrowRight"
    scrub_back_many: str = "Shift+ArrowLeft"
    scrub_forward_many: str = "Shift+ArrowRight"
    scrub_start: str = "Home"
    scrub_end: str = "End"
    scrub_full_screen: str = "f"
    scrub_video: str = "v"
    scrub_close: str = "Escape"


class DataCollectionSettings(SettingsModel):
    data_location: str = "data"
    dataset: str = "default"
    server: ServerSettings = ServerSettings()
    camera: CameraSettings = CameraSettings()
    countdown_s: float = 3.0
    clip_padding: ClipPadding = ClipPadding()
    end_threshold_ratio: float = 0.6
    shortcuts: Shortcuts = Shortcuts()
    mirror_preview: bool = True

    @model_validator(mode="before")
    @classmethod
    def _old_keys(cls, data):
        if isinstance(data, dict) and "data_folder" in data:
            raise ValueError(
                "dataFolder is no longer used: set dataLocation (the folder "
                "that holds the datasets) and dataset (the name of the "
                "dataset to record into)"
            )
        return data

    @model_validator(mode="after")
    def _check(self) -> DataCollectionSettings:
        in_range("countdownS", self.countdown_s, 0, 60)
        in_range("endThresholdRatio", self.end_threshold_ratio, 0.01, 1)
        if not self.data_location:
            raise ValueError("dataLocation must not be empty")
        if not is_valid_dataset_name(self.dataset):
            raise ValueError(
                f"dataset {self.dataset!r} is not a valid name: use lowercase "
                "letters, digits, hyphens and underscores"
            )
        return self


def load_app_settings(config_dir: Path) -> DataCollectionSettings:
    """Load ``data-collection.yaml`` with its local override applied."""
    return load_settings(DataCollectionSettings, Path(config_dir) / FILE_NAME)
