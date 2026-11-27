"""Final training and saving models (design sections 9 and 10).

Phase 3: train the chosen hyperparameter candidate on the whole training set,
evaluate it once on the test set, and write the report files and the model.
The test set is never used to train: the saved model is the one evaluated.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from wand_core import classifiers
from wand_core.casing import camel_keys, snake_keys
from wand_train import evaluate as evaluation
from wand_train.data import gestureset
from wand_train.evaluate import Evaluation
from wand_train.explore import runs
from wand_train.trainers.registry import get_trainer

SOURCE_FILE = "source.json"
METRICS_FILE = "metrics.csv"
PREDICTIONS_FILE = "predictions.parquet"
TRAINING_FOLDER = "training"
DEFAULT_SEED = 42
DEFAULT_TEST_FRACTION = 0.2
SUMMARY_METRICS = (
    "accuracy",
    "macro_f1",
    "log_loss",
    "label_auc_mean",
    "rejection_auc",
)
VERIFY_TOLERANCE = 1e-9


class FingerprintMismatchError(ValueError):
    """The training data differs from the data the exploration used."""


class ModelMismatchError(RuntimeError):
    """The saved classifier does not predict as the evaluated model did."""


class ModelExistsError(FileExistsError):
    """A report or model folder with the model id already exists."""


@dataclass(frozen=True)
class Source:
    """Where the hyperparameters of a final training came from."""

    family: str
    hyperparameters: dict[str, Any]
    seed: int
    test_fraction: float
    fingerprint: str | None  # the exploration's; None for given values
    run_id: str | None = None
    candidate: int | None = None


@dataclass(frozen=True)
class TrainedModel:
    model_id: str
    report_folder: Path
    model_folder: Path
    evaluation: Evaluation


def now() -> datetime:
    return datetime.now().astimezone()


def make_model_id(family: str, moment: datetime | None = None) -> str:
    """``<family>-<yyyymmdd-HHMMSS>`` in local time."""
    return f"{family}-{(moment or now()):%Y%m%d-%H%M%S}"


# --- Reading the source ---------------------------------------------------


def source_from_run(
    reference: str, reports: Path, candidate: int | None = None
) -> Source:
    """The hyperparameters of a candidate of a stored exploration.

    The default candidate is the best by the stored ranking. The seed, the
    test fraction and the training data fingerprint come from the run.
    """
    stored = runs.ExplorerFactory.from_run(runs.find_run(reference, reports))
    if candidate is None:
        if stored.finished_candidates == 0:
            raise ValueError(
                f"run {stored.info.run_id} has no finished candidates"
            )
        result = stored.best()
    else:
        try:
            result = stored.metrics(candidate)
        except KeyError:
            raise ValueError(
                f"run {stored.info.run_id} has no finished candidate "
                f"{candidate} (it has {stored.finished_candidates} of "
                f"{stored.info.candidate_count})"
            ) from None
    return Source(
        family=stored.definition.family,
        hyperparameters=dict(result.hyperparameters),
        seed=stored.info.seed,
        test_fraction=stored.info.test_fraction,
        fingerprint=stored.info.training_data_fingerprint,
        run_id=stored.info.run_id,
        candidate=result.number,
    )


def source_from_values(
    family: str, values_file: Path, seed: int, test_fraction: float
) -> Source:
    """Hyperparameter values from a JSON file (camel case keys)."""
    try:
        data = json.loads(Path(values_file).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"cannot read {values_file}: {error}") from error
    if not isinstance(data, dict):
        raise ValueError(f"{values_file} must hold an object of values")
    return Source(family, snake_keys(data), seed, test_fraction, None)


# --- Training --------------------------------------------------------------


def train_model(
    source: Source,
    training_data: Path,
    reports: Path,
    models: Path,
    max_false_trigger: float = evaluation.DEFAULT_MAX_FALSE_TRIGGER,
    moment: datetime | None = None,
    root: Path | None = None,
) -> TrainedModel:
    """Train, evaluate, write the report files and save the model."""
    trainer = get_trainer(source.family)  # an unknown family stops here
    hyperparameters = trainer.validate(source.hyperparameters)
    full = gestureset.load(training_data)
    current = full.info.fingerprint
    if source.fingerprint is not None and source.fingerprint != current:
        raise FingerprintMismatchError(
            "the training data changed since the exploration: it has "
            f"fingerprint {current[:12]}, the exploration used "
            f"{source.fingerprint[:12]}; explore again, or train from values"
        )
    training_set, test_set = full.train_test_split(
        source.test_fraction, source.seed
    )
    trainer.train(training_set, test_set, hyperparameters, source.seed)
    result = evaluation.evaluate(
        trainer.predict_probabilities,
        trainer.labels,
        test_set,
        max_false_trigger,
    )

    model_id = make_model_id(source.family, moment)
    report_folder = Path(reports) / source.family / TRAINING_FOLDER / model_id
    model_folder = Path(models) / source.family / model_id
    for folder in (report_folder, model_folder):
        if folder.exists():
            raise ModelExistsError(f"{folder} already exists")

    report_folder.mkdir(parents=True)
    _write_source(
        report_folder,
        source,
        hyperparameters,
        current,
        len(training_set),
        len(test_set),
    )
    _write_metrics(report_folder, result)
    _write_predictions(report_folder, result)
    trainer.save(
        model_folder,
        {
            "model_id": model_id,
            "hyperparameters": hyperparameters,
            "metrics": {
                name: result.measures[name] for name in SUMMARY_METRICS
            },
            "training_data_fingerprint": current,
            "report_path": _relative(report_folder, root),
        },
    )
    _verify(model_folder, test_set, result)
    return TrainedModel(model_id, report_folder, model_folder, result)


def _relative(path: Path, root: Path | None) -> str:
    if root is not None:
        try:
            return Path(path).resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            pass
    return Path(path).as_posix()


def _write_source(
    folder: Path,
    source: Source,
    hyperparameters: dict[str, Any],
    fingerprint: str,
    training_gestures: int,
    test_gestures: int,
) -> None:
    data = {
        "exploration_run_id": source.run_id,
        "candidate": source.candidate,
        "family": source.family,
        "hyperparameters": hyperparameters,
        "seed": source.seed,
        "test_fraction": source.test_fraction,
        "training_data_fingerprint": fingerprint,
        "training_gestures": training_gestures,
        "test_gestures": test_gestures,
    }
    (folder / SOURCE_FILE).write_text(
        json.dumps(camel_keys(data), indent=2) + "\n", encoding="utf-8"
    )


def metric_rows(result: Evaluation) -> list[tuple[str, str, str, Any]]:
    """The rows of ``metrics.csv``: (section, name, threshold, value).

    The measures that need no threshold come first, then the curve data with
    one row per threshold and measure.
    """
    rows: list[tuple[str, str, str, Any]] = []
    for name, value in result.measures.items():
        rows.append(("measure", name, "", value))
    for label, value in result.label_auc.items():
        rows.append(("label_auc", label, "", value))
    for label in result.labels:
        rows.append(
            ("precision", label, "", result.per_label.loc[label, "precision"])
        )
        rows.append(
            ("recall", label, "", result.per_label.loc[label, "recall"])
        )
    for correct in result.labels:
        for guess in result.labels:
            rows.append(
                (
                    "confusion",
                    f"{correct}>{guess}",
                    "",
                    result.confusion.loc[correct, guess],
                )
            )
    rows.append(
        ("threshold_info", "max_false_trigger", "", result.max_false_trigger)
    )
    rows.append(("threshold_info", "lowest_threshold", "", result.threshold))
    for _, point in result.curve.iterrows():
        for name in evaluation.CURVE_COLUMNS[1:]:
            rows.append(("curve", name, point["threshold"], point[name]))
    return rows


def _write_metrics(folder: Path, result: Evaluation) -> None:
    with open(
        folder / METRICS_FILE, "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.writer(stream)
        writer.writerow(["section", "name", "threshold", "value"])
        for section, name, threshold, value in metric_rows(result):
            missing = value is None or (
                isinstance(value, float) and np.isnan(value)
            )
            writer.writerow(
                [section, name, threshold, "" if missing else value]
            )


def _write_predictions(folder: Path, result: Evaluation) -> None:
    table = result.predictions.copy()
    table["probabilities"] = table["probabilities"].apply(
        lambda row: [float(value) for value in row]
    )
    table.to_parquet(folder / PREDICTIONS_FILE, index=False)


def _verify(
    model_folder: Path, test_set: gestureset.GestureSet, result: Evaluation
) -> None:
    """The saved classifier must predict what the evaluated model did."""
    classifier = classifiers.load(model_folder)
    spell = result.predictions[result.predictions["kind"] == evaluation.SPELL]
    expected = np.vstack(spell["probabilities"].to_numpy())
    predictions = classifier.predict(test_set.gestures)
    loaded = np.vstack([prediction.probabilities for prediction in predictions])
    if loaded.shape != expected.shape or not np.allclose(
        loaded, expected, atol=VERIFY_TOLERANCE
    ):
        raise ModelMismatchError(
            f"the classifier saved in {model_folder} does not predict as the "
            "evaluated model did"
        )
