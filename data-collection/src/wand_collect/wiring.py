"""Putting the application together: the services and the web application.

``serve`` and the whole-application test both start from here, so the test
exercises the same wiring as the real application.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI

from wand_collect.app import Application
from wand_collect.clip_writer import ClipWriter
from wand_collect.controller import CaptureController
from wand_collect.server import STATIC_DIR, create_app
from wand_collect.services.calibration import CalibrationService
from wand_collect.services.labels import LabelService
from wand_collect.services.library import SampleLibrary
from wand_collect.services.session import SessionService
from wand_collect.stream import StreamService
from wand_core.sources import CameraInfo, list_cameras


@dataclass
class Assembled:
    """The web application and the parts a test may want to reach."""

    app: FastAPI
    application: Application
    calibration: CalibrationService
    sessions: SessionService
    library: SampleLibrary
    labels: LabelService
    controller: CaptureController
    clips: ClipWriter

    def shutdown(self) -> None:
        self.controller.shutdown()
        self.clips.close()
        self.labels.stop()
        self.application.shutdown()


def assemble(
    application: Application,
    camera_lister: Callable[[], list[CameraInfo]] = list_cameras,
    static_dir: Path | None = STATIC_DIR,
) -> Assembled:
    """Create every service and the web application, and start the loops."""
    state, engine = application.state, application.engine
    calibration = CalibrationService(
        state,
        engine,
        application.config_dir,
        application.settings,
        camera_lister=camera_lister,
    )
    sessions = SessionService(
        state,
        engine,
        application.store,
        calibration,
        application.settings,
        camera_lister=camera_lister,
    )
    library = SampleLibrary(
        state,
        application.store,
        mirror=application.settings.mirror_preview,
    )
    clips = ClipWriter()
    padding = application.settings.clip_padding
    controller = CaptureController(
        state,
        engine,
        sessions,
        application.store,
        clips,
        countdown_s=application.settings.countdown_s,
        clip_padding=(padding.pre_s, padding.post_s),
    )
    sessions.set_controller(controller)
    engine.set_receiver(controller.on_engine_message)
    controller.start_loop()
    labels = LabelService(
        state,
        application.config_dir / "labels.yaml",
        library.label_use_count,
    )
    labels.start()

    assembled = Assembled(
        None,  # set below, once the shutdown hook can refer to this object
        application,
        calibration,
        sessions,
        library,
        labels,
        controller,
        clips,
    )
    assembled.app = create_app(
        state,
        engine,
        routers=[
            StreamService(engine, state).router,
            calibration.router,
            sessions.router,
            library.router,
            labels.router,
            controller.router,
        ],
        static_dir=static_dir,
        on_shutdown=assembled.shutdown,
        app_settings=application.settings,
    )
    return assembled
