"""Command-line entry point of the data collection application."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import uvicorn

from wand_collect.app import build_application, is_loopback
from wand_collect.server import create_app


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
    application = build_application(args.config, args.data_folder)
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
    app = create_app(
        application.state,
        application.engine,
        on_shutdown=application.shutdown,
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
