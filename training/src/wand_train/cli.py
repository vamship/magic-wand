"""Command line of the training tool (`wand-train`)."""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from wand_core.casing import to_snake
from wand_core.dataset import DatasetError
from wand_train import definitions, models
from wand_train.data import builder, gestureset
from wand_train.data.format import TrainingDataError
from wand_train.explore import runs
from wand_train.explore.enumerate import candidate_count
from wand_train.explore.explorer import build_explorer
from wand_train.trainers.base import HyperparameterError
from wand_train.trainers.registry import UnknownFamilyError

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
        elif name == "explore":
            add_explore_options(command)
        elif name == "show":
            add_show_options(command)
        elif name == "train":
            add_train_options(command)
    return parser


def add_explore_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("definition", type=Path, help="the definition file")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--test-fraction", type=float, default=0.2)
    parser.add_argument(
        "--training-data",
        type=Path,
        help="the training data folder (default: training-data/)",
    )
    parser.add_argument(
        "--reports",
        type=Path,
        help="the reports folder (default: reports/)",
    )


def add_train_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "run", nargs="?", help="an exploration run id, or its folder"
    )
    parser.add_argument(
        "--candidate",
        type=int,
        help="the hyperparameter candidate (default: the best)",
    )
    parser.add_argument("--family", help="the family, with --values")
    parser.add_argument(
        "--values", type=Path, help="a JSON file of hyperparameter values"
    )
    parser.add_argument("--seed", type=int, help="default 42; from a run")
    parser.add_argument(
        "--test-fraction", type=float, help="default 0.2; from a run"
    )
    parser.add_argument("--training-data", type=Path)
    parser.add_argument("--reports", type=Path)
    parser.add_argument("--models", type=Path)
    parser.add_argument("--max-false-trigger", type=float, default=0.05)


def add_show_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("run", help="a run id, or the run folder")
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--effect", help="a hyperparameter to examine")
    parser.add_argument(
        "--metric", default="accuracy", help="the metric for --effect"
    )
    parser.add_argument(
        "--reports",
        type=Path,
        help="the reports folder (default: reports/)",
    )


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


def explore(args: argparse.Namespace) -> int:
    root = builder.repository_root()
    reports = args.reports or root / "reports"
    training_data = args.training_data or root / "training-data"
    try:
        text = args.definition.read_text(encoding="utf-8")
        definition = definitions.load(args.definition)
        explorer = build_explorer(definition)
        explorer.check_candidates()
        full = gestureset.load(training_data)
        training_set, _ = full.train_test_split(args.test_fraction, args.seed)
        writer = runs.RunWriter.start(
            reports,
            explorer,
            json.loads(text),
            args.seed,
            args.test_fraction,
            full.info.fingerprint,
        )
    except (
        OSError,
        ValueError,
        DatasetError,
        TrainingDataError,
        UnknownFamilyError,
        HyperparameterError,
        FileExistsError,
    ) as error:
        print(f"wand-train: {error}", file=sys.stderr)
        return 1
    print(
        f"{definition.name}: {candidate_count(definition)} candidates, "
        f"{len(training_set)} training gestures (the test set is not used)"
    )

    def progress(done: int, total: int) -> None:
        print(f"\r  fold {done} of {total}", end="", flush=True)

    try:
        ranked = explorer.explore(
            training_set,
            args.seed,
            progress=progress,
            on_candidate=writer.on_candidate,
        )
    except BaseException:
        writer.close()
        print(f"\nwand-train: interrupted; partial results in {writer.folder}")
        raise
    writer.finish()
    print(f"\nStored in {writer.folder}")
    print(runs_table(ranked[:5], explorer))
    return 0


def runs_table(results, explorer) -> str:
    metric = getattr(explorer.comparator, "metric", "accuracy")
    lines = [f"{'#':>5}  {metric:<14} {'+/-':<8} hyperparameters"]
    for result in results:
        lines.append(
            f"{result.number:>5}  {result.mean[metric]:<14.4f} "
            f"{result.std[metric]:<8.4f} {result.hyperparameters}"
        )
    return "\n".join(lines)


def train(args: argparse.Namespace) -> int:
    root = builder.repository_root()
    reports = args.reports or root / "reports"
    try:
        if args.run and args.values:
            raise ValueError("give a run or --values, not both")
        if args.run:
            if (
                args.family
                or args.seed is not None
                or (args.test_fraction is not None)
            ):
                raise ValueError(
                    "the family, seed and test fraction come from the run"
                )
            source = models.source_from_run(args.run, reports, args.candidate)
        elif args.values:
            if not args.family:
                raise ValueError("--values needs --family")
            if args.candidate is not None:
                raise ValueError("--candidate needs an exploration run")
            source = models.source_from_values(
                args.family,
                args.values,
                models.DEFAULT_SEED if args.seed is None else args.seed,
                models.DEFAULT_TEST_FRACTION
                if args.test_fraction is None
                else args.test_fraction,
            )
        else:
            raise ValueError(
                "give an exploration run or --values with --family"
            )
        trained = models.train_model(
            source,
            args.training_data or root / "training-data",
            reports,
            args.models or root / "models",
            args.max_false_trigger,
            root=root,
        )
    except (
        OSError,
        ValueError,
        KeyError,
        RuntimeError,
        DatasetError,
        TrainingDataError,
        UnknownFamilyError,
        HyperparameterError,
    ) as error:
        print(f"wand-train: {error}", file=sys.stderr)
        return 1
    result = trained.evaluation
    print(f"Model {trained.model_id}")
    print(f"  report: {trained.report_folder}")
    print(f"  model:  {trained.model_folder}")
    for name in models.SUMMARY_METRICS:
        value = result.measures[name]
        print(f"  {name}: {'n/a' if value is None else f'{value:.4f}'}")
    if result.threshold is None:
        print(
            "  no threshold keeps the backward false trigger rate at or "
            f"below {result.max_false_trigger}"
        )
    else:
        print(
            f"  lowest threshold with backward false triggers at or below "
            f"{result.max_false_trigger}: {result.threshold:.2f}"
        )
    return 0


def show(args: argparse.Namespace) -> int:
    root = builder.repository_root()
    try:
        folder = runs.find_run(args.run, args.reports or root / "reports")
        stored = runs.ExplorerFactory.from_run(folder)
        print(
            f"Run {stored.info.run_id}: {stored.finished_candidates} of "
            f"{stored.info.candidate_count} candidates finished"
        )
        if not stored.complete:
            print("The run is incomplete; only finished candidates are ranked.")
        print(runs_table(stored.top(args.top), stored.explorer))
        if args.effect:
            name = to_snake(args.effect)
            print(f"\nMean {args.metric} at each value of {name}:")
            for value, mean in stored.effect(name, args.metric):
                print(f"  {value!s:<12} {mean:.4f}")
    except (OSError, KeyError, ValueError) as error:
        print(f"wand-train: {error}", file=sys.stderr)
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return NOT_IMPLEMENTED_STATUS
    if args.command == "explore":
        return explore(args)
    if args.command == "show":
        return show(args)
    if args.command == "train":
        return train(args)
    if args.command == "training-data":
        if args.action is None:
            parser.parse_args(["training-data", "--help"])
        return training_data(args)
    print(f"wand-train {args.command}: not implemented yet", file=sys.stderr)
    return NOT_IMPLEMENTED_STATUS


if __name__ == "__main__":
    sys.exit(main())
