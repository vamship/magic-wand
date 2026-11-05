"""Command-line entry point of the data collection application."""

import argparse
import sys
from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path

import uvicorn

from wand_collect.app import (
    build_application,
    default_config_dir,
    is_loopback,
)
from wand_collect.labels import LabelsError, load_labels
from wand_collect.wiring import assemble
from wand_core.dataset import (
    Action,
    DatasetError,
    Level,
    SampleFilter,
    SampleStatus,
    check_folder,
    export_samples,
    merge_folders,
)

SHUTDOWN_GRACE_S = 2  # seconds open connections get after Ctrl+C


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

    export = commands.add_parser(
        "export",
        help="write one JSON Lines file from data folders",
        description="Write every matching sample, with its session record "
        "and without video, to one JSON Lines file.",
    )
    export.add_argument("folders", nargs="+", type=Path, help="data folders")
    export.add_argument(
        "--output", "-o", type=Path, required=True, help="the file to write"
    )
    export.add_argument(
        "--status",
        choices=[s.value for s in SampleStatus],
        help="keep only samples with this status",
    )
    export.add_argument("--label", help="keep only this label id")
    export.add_argument("--session", help="keep only this session id")
    export.add_argument("--author", help="keep only this author")
    export.add_argument(
        "--from",
        dest="start",
        type=_time("--from"),
        help="keep samples captured at or after this ISO date or time",
    )
    export.add_argument(
        "--to",
        dest="end",
        type=_time("--to", end_of_day=True),
        help="keep samples captured at or before this ISO date or time "
        "(a date alone includes the whole day)",
    )

    merge = commands.add_parser(
        "merge",
        help="merge data folders into a target folder",
        description="Copy the sessions of the source folders into the "
        "target folder. Sources are never changed.",
    )
    merge.add_argument("sources", nargs="+", type=Path, help="source folders")
    merge.add_argument(
        "--target", "-t", type=Path, required=True, help="the target folder"
    )
    merge.add_argument(
        "--on-conflict",
        choices=["skip", "replace"],
        default="skip",
        help="what to do with a session that differs in the target "
        "(default: skip, which reports it and keeps the target's copy)",
    )
    merge.add_argument(
        "--skip-clips", action="store_true", help="do not copy video clips"
    )

    check = commands.add_parser(
        "check",
        help="run the consistency check on a data folder",
        description="Report problems in a data folder without changing "
        "anything. The exit status is 1 when there are errors.",
    )
    check.add_argument("folder", type=Path, help="the data folder")
    check.add_argument(
        "--config",
        type=Path,
        help="configuration folder whose labels.yaml gives the known labels "
        "(default: config/)",
    )
    return parser


def _time(option: str, end_of_day: bool = False):
    """An argparse type for an ISO date or time."""

    def parse(text: str) -> datetime:
        try:
            value = datetime.fromisoformat(text)
        except ValueError:
            raise argparse.ArgumentTypeError(
                f"{option}: {text!r} is not an ISO date or time "
                "(for example 2026-11-01 or 2026-11-01T14:30)"
            ) from None
        if value.tzinfo is None:
            value = value.astimezone()  # local time
        if end_of_day and len(text) == 10:
            value += timedelta(days=1) - timedelta(microseconds=1)
        return value

    return parse


def export(args: argparse.Namespace) -> int:
    keep = SampleFilter(
        status=SampleStatus(args.status) if args.status else None,
        label=args.label,
        session=args.session,
        author=args.author,
        start=args.start,
        end=args.end,
    )
    try:
        count = export_samples(args.folders, args.output, keep)
    except (DatasetError, OSError) as error:
        print(f"export failed: {error}", file=sys.stderr)
        return 1
    print(f"Wrote {count} samples to {args.output}")
    return 0


def merge(args: argparse.Namespace) -> int:
    try:
        result = merge_folders(
            args.sources,
            args.target,
            on_conflict=args.on_conflict,
            skip_clips=args.skip_clips,
        )
    except (DatasetError, OSError, ValueError) as error:
        print(f"merge failed: {error}", file=sys.stderr)
        return 1
    for session in result.sessions:
        print(session)
    summary = ", ".join(
        f"{result.count(action)} {action.value}"
        for action in Action
        if result.count(action)
    )
    print(f"Merged into {args.target}: {summary or 'nothing to merge'}")
    if result.has_conflicts:
        print(
            "Some sessions differ; run again with --on-conflict replace to "
            "use the sources' copies.",
            file=sys.stderr,
        )
    return 1 if result.count(Action.ERROR) else 0


def check(args: argparse.Namespace) -> int:
    labels = None
    config_dir = args.config or default_config_dir()
    try:
        labels = {label.id for label in load_labels(config_dir / "labels.yaml")}
    except LabelsError as error:
        print(f"note: labels are not checked ({error})", file=sys.stderr)
    report = check_folder(args.folder, labels)
    order = {Level.ERROR: 0, Level.WARNING: 1, Level.INFO: 2}
    for finding in sorted(report.findings, key=lambda f: order[f.level]):
        print(finding)
    print(
        f"Checked {report.sessions} sessions and {report.samples} samples: "
        f"{len(report.errors)} errors, {len(report.warnings)} warnings, "
        f"{len(report.info)} notes"
    )
    return 0 if report.ok else 1


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
    app = assemble(application).app
    print(f"Open http://{server.host}:{server.port}/ in a browser.")
    # The live view and the event stream never end on their own, so an open
    # browser tab would keep the server waiting after Ctrl+C. Give open
    # connections a moment, then close them.
    uvicorn.run(
        app,
        host=server.host,
        port=server.port,
        timeout_graceful_shutdown=SHUTDOWN_GRACE_S,
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    commands = {
        "serve": serve,
        "export": export,
        "merge": merge,
        "check": check,
    }
    if args.command in commands:
        return commands[args.command](args)
    parser.print_help()
    return 0
