"""Command-line entry point of the data collection application."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import uvicorn

from wand_collect.app import build_application, is_loopback
from wand_collect.server import create_app
from wand_collect.services.calibration import CalibrationService
from wand_collect.labels import LabelsError
from wand_collect.services.labels import LabelService
from wand_collect.services.library import SampleLibrary
from wand_collect.services.session import SessionService
from wand_collect.stream import StreamService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wand-collect",
        description="Record and label wand gestures.",
    )
    commands = parser.add_subparsers(dest="command")
    serve = commands.add_parser("serve", help="start the application")
    serve.add_argument(
        "--config", type=Path, help="configuration folder (default: config/)"
    )
    serve.add_argument(
        "--data-folder", type=Path, help="where datasets are stored"
    )
    return parser


def serve(args: argparse.Namespace) -> int:
    try:
        application = build_application(args.config, args.data_folder)
    except LabelsError as error:
        print(f"Cannot start: {error}", file=sys.stderr)
        return 1
    server = application.settings.server
    if not is_loopback(server.host):
        print(
            f"WARNING: the server listens on {server.host}, not only on this "
            "computer. Anyone who can reach this address can use the "
            "application and see the camera.",
            file=sys.stderr,
        )
    if application.camera_error:
        print(
            f"No camera available ({application.camera_error}). "
            "The application starts without a live view.",
            file=sys.stderr,
        )
    calibration = CalibrationService(
        application.state,
        application.engine,
        application.config_dir,
        application.settings,
    )
    sessions = SessionService(
        application.state,
        application.engine,
        application.store,
        calibration,
        application.settings,
    )
    library = SampleLibrary(application.state, application.store)
    labels = LabelService(
        application.state,
        application.config_dir / "labels.yaml",
        library.label_use_count,
    )
    labels.start()

    def shutdown() -> None:
        labels.stop()
        application.shutdown()

    app = create_app(
        application.state,
        application.engine,
        routers=[
            StreamService(application.engine, application.state).router,
            calibration.router,
            sessions.router,
            library.router,
            labels.router,
        ],
        on_shutdown=shutdown,
        app_settings=application.settings,
    )
    print(f"Open http://{server.host}:{server.port}/ in a browser.")
    uvicorn.run(app, host=server.host, port=server.port)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "serve":
        return serve(args)
    parser.print_help()
    return 0
