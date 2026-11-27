"""Command line of the training tool (`wand-train`)."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from wand_core.dataset import DatasetError
from wand_train.data import builder
from wand_train.data.format import TrainingDataError

NOT_IMPLEMENTED_STATUS = 2

COMMANDS = {
    "training-data": "Build, check and summarize the training data.",
    "explore": "Run a hyperparameter exploration.",
    "show": "Print the results of an exploration.",
    "train": "Train a final model.",
    "index": "Rebuild the index of reports.",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wand-train",
        description="Train and evaluate wand gesture classifiers.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    for name, summary in COMMANDS.items():
        command = subparsers.add_parser(name, help=summary, description=summary)
        if name == "training-data":
            add_training_data_commands(command)
    return parser


def add_training_data_commands(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="action", metavar="action")
    for action, summary in (
        ("build", "Build training-data/ from the datasets."),
        ("check", "Compare training-data/ with the datasets."),
        ("summary", "Print the counts per label and author."),
    ):
        command = actions.add_parser(action, help=summary, description=summary)
        command.add_argument(
            "--output",
            type=Path,
            help="the training data folder (default: training-data/)",
        )
        if action != "summary":
            command.add_argument(
                "datasets",
                nargs="*",
                help="dataset names (default: every dataset in the data "
                "location)",
            )
            command.add_argument(
                "--data-location",
                type=Path,
                help="the folder that holds the datasets (default: data/)",
            )


def training_data(args: argparse.Namespace) -> int:
    root = builder.repository_root()
    output = args.output or root / "training-data"
    try:
        if args.action == "summary":
            print(builder.summary(output))
            return 0
        location = args.data_location or root / "data"
        folders = builder.select_datasets(location, args.datasets)
        if args.action == "build":
            info = builder.build(folders, output, root)
            print(
                f"Built {output}: {info.sample_count} samples from "
                f"{len(info.session_ids)} sessions "
                f"(fingerprint {info.fingerprint[:12]})"
            )
            return 0
        problems = builder.check(folders, output)
    except (DatasetError, TrainingDataError) as error:
        print(f"wand-train: {error}", file=sys.stderr)
        return 1
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    print(f"{output} matches the datasets")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return NOT_IMPLEMENTED_STATUS
    if args.command == "training-data":
        if args.action is None:
            parser.parse_args(["training-data", "--help"])
        return training_data(args)
    print(f"wand-train {args.command}: not implemented yet", file=sys.stderr)
    return NOT_IMPLEMENTED_STATUS


if __name__ == "__main__":
    sys.exit(main())
