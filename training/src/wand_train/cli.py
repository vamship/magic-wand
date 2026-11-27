"""Command line of the training tool (`wand-train`)."""

import argparse
import sys
from collections.abc import Sequence

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
        subparsers.add_parser(name, help=summary, description=summary)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return NOT_IMPLEMENTED_STATUS
    print(f"wand-train {args.command}: not implemented yet", file=sys.stderr)
    return NOT_IMPLEMENTED_STATUS


if __name__ == "__main__":
    sys.exit(main())
