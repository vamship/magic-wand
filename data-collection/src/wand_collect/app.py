"""Starting the application: loading configuration and wiring the parts.

The order is the one in ``tasks.md`` DC-A2: configuration, the data folder,
the labels, the Application State, then the Capture Engine, which opens the
preview camera if there is one. The application still starts without a
camera.
"""

from __future__ import annotations

import ipaddress
import logging
from dataclasses import dataclass
from pathlib import Path

from wand_collect.engine import CameraFactory, CaptureEngine
from wand_collect.labels import load_labels
from wand_collect.settings import DataCollectionSettings, load_app_settings
from wand_collect.state import ApplicationState, Owner, SettingsState
from wand_core.dataset import DatasetStore
from wand_core.settings import resolve_settings

logger = logging.getLogger(__name__)

PREVIEW_OPEN_TIMEOUT_S = 15.0


@dataclass
class Application:
    """The running parts, created once at startup."""

    config_dir: Path
    settings: DataCollectionSettings
    state: ApplicationState
    store: DatasetStore
    engine: CaptureEngine
    camera_error: str | None = None

    def shutdown(self) -> None:
        self.engine.stop()


def default_config_dir() -> Path:
    """``config/`` in the working folder, else the repository's own."""
    here = Path.cwd() / "config"
    if here.is_dir():
        return here
    return Path(__file__).resolve().parents[3] / "config"


def is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def build_application(
    config_dir: Path | None = None,
    data_folder: Path | None = None,
    open_camera: bool = True,
    camera_factory: CameraFactory | None = None,
) -> Application:
    """Create the state, the data folder and the engine, in order."""
    config_dir = Path(config_dir) if config_dir else default_config_dir()
    settings = load_app_settings(config_dir)

    folder = Path(data_folder) if data_folder else Path(settings.data_folder)
    if not folder.is_absolute():
        folder = config_dir.parent / folder  # relative to the repository root
    store = DatasetStore.open(folder, create=True)

    state = ApplicationState()
    state.update(
        Owner.LABEL_SERVICE, labels=load_labels(config_dir / "labels.yaml")
    )
    working = resolve_settings(config_dir)
    state.update(
        Owner.CALIBRATION_SERVICE,
        settings=SettingsState(vision=working.vision, motion=working.motion),
    )

    padding = settings.clip_padding
    engine = CaptureEngine(
        state,
        clip_padding=(padding.pre_s, padding.post_s),
        camera_factory=camera_factory,
    )
    engine.start()
    application = Application(config_dir, settings, state, store, engine)
    if open_camera:
        camera = settings.camera
        try:
            engine.open_camera(
                camera.index, camera.width, camera.height, camera.fps
            ).result(PREVIEW_OPEN_TIMEOUT_S)
        except Exception as error:  # noqa: BLE001 - the server starts anyway
            application.camera_error = str(error)
            logger.warning("no camera available: %s", error)
    return application
