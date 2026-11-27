"""The trainer base (``training/docs/design.md`` section 6).

A trainer trains a model of one family on the gesture set it is given and
evaluates it on another set it is given. It knows nothing about folds. A
subclass only fits the model, gives probabilities and writes its model file;
the base validates, times, scores and writes ``classifier.json``.
"""

from __future__ import annotations

import json
import math
import time
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

import numpy as np

from wand_core import normalize
from wand_core.casing import camel_keys
from wand_core.classifiers import Prediction
from wand_core.classifiers.files import CLASSIFIER_FILE, FORMAT_VERSION
from wand_train.data.gestureset import GestureSet
from wand_train.trainers import metrics

TIMING_SAMPLE = 200

KINDS = ("int", "float", "choice", "bool")


class HyperparameterError(ValueError):
    """An invalid hyperparameter; the message names it."""


@dataclass(frozen=True)
class Hyperparameter:
    """What a trainer accepts for one hyperparameter."""

    name: str
    kind: str  # "int", "float", "choice" or "bool"
    default: Any
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple = ()

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"{self.name}: unknown kind {self.kind!r}")
        self.check(self.default)

    def check(self, value: Any) -> Any:
        """Return the value if valid; raise ``HyperparameterError``."""
        if self.kind == "bool":
            if not isinstance(value, bool):
                raise self._error(value, "must be true or false")
            return value
        if self.kind == "choice":
            if value not in self.choices:
                raise self._error(value, f"must be one of {list(self.choices)}")
            return value
        number_ok = isinstance(value, (int, float)) and not isinstance(
            value, bool
        )
        if self.kind == "int" and not (
            isinstance(value, int) and not isinstance(value, bool)
        ):
            raise self._error(value, "must be an integer")
        if self.kind == "float" and not (number_ok and math.isfinite(value)):
            raise self._error(value, "must be a number")
        if self.minimum is not None and value < self.minimum:
            raise self._error(value, f"must be at least {self.minimum}")
        if self.maximum is not None and value > self.maximum:
            raise self._error(value, f"must be at most {self.maximum}")
        return value

    def _error(self, value: Any, problem: str) -> HyperparameterError:
        return HyperparameterError(
            f"hyperparameter {self.name!r} {problem} (got {value!r})"
        )


@dataclass
class TrainResult:
    """What ``train`` returns."""

    metrics: dict[str, float]
    hyperparameters: dict[str, Any]
    labels: tuple[str, ...]
    predictions: list[Prediction] | None = None
    sample_ids: list[str] = field(default_factory=list)


class Trainer(ABC):
    """Trains and evaluates one family; the base does the common work."""

    family: ClassVar[str]
    hyperparameter_specs: ClassVar[tuple[Hyperparameter, ...]] = ()

    def __init__(self) -> None:
        self.labels: tuple[str, ...] = ()
        self.hyperparameters: dict[str, Any] = {}
        self._trained = False

    # --- Hooks for a family ---------------------------------------------

    @abstractmethod
    def fit(
        self,
        features: np.ndarray,
        labels: np.ndarray,
        hyperparameters: dict[str, Any],
        seed: int,
    ) -> None:
        """Fit the model. ``self.labels`` already holds the label order."""

    @abstractmethod
    def predict_probabilities(self, features: np.ndarray) -> np.ndarray:
        """One row per gesture, one column per label of ``self.labels``."""

    @abstractmethod
    def write_model(self, folder: Path) -> None:
        """Write the model file(s) in the form the family's loader reads."""

    def extra_metrics(
        self,
        features: np.ndarray,
        labels: np.ndarray,
        probabilities: np.ndarray,
    ) -> dict[str, float]:
        """Further metrics of this family; none by default."""
        return {}

    # --- Hyperparameters ------------------------------------------------

    def validate(
        self, hyperparameters: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        """Fill in defaults; reject an unknown name, kind or range."""
        given = dict(hyperparameters or {})
        specs = {spec.name: spec for spec in self.hyperparameter_specs}
        for name in given:
            if name not in specs:
                accepted = ", ".join(sorted(specs)) or "none"
                raise HyperparameterError(
                    f"unknown hyperparameter {name!r} (accepted: {accepted})"
                )
        return {
            name: spec.check(given[name]) if name in given else spec.default
            for name, spec in specs.items()
        }

    # --- Training -------------------------------------------------------

    def train(
        self,
        training_set: GestureSet,
        evaluation_set: GestureSet,
        hyperparameters: Mapping[str, Any] | None = None,
        seed: int = 42,
        with_predictions: bool = False,
    ) -> TrainResult:
        """Train on ``training_set`` and evaluate on ``evaluation_set``.

        Only these two sets are used. Metrics are in the result, and so are
        the predictions when asked for.
        """
        values = self.validate(hyperparameters)
        if len(training_set) == 0:
            raise ValueError("the training set is empty")
        if len(evaluation_set) == 0:
            raise ValueError("the evaluation set is empty")
        train_features = training_set.gestures
        train_labels = training_set.labels
        self.labels = tuple(sorted(set(train_labels)))
        self.hyperparameters = values

        started = time.perf_counter()
        self.fit(train_features, train_labels, values, seed)
        train_seconds = time.perf_counter() - started
        self._trained = True

        features = evaluation_set.gestures
        true_labels = evaluation_set.labels
        probabilities = self._probabilities(features)
        predicted = metrics.predicted_labels(probabilities, self.labels)
        result_metrics = {
            "accuracy": metrics.accuracy(true_labels, predicted),
            "macro_f1": metrics.macro_f1(true_labels, predicted),
            "log_loss": metrics.log_loss(
                true_labels, probabilities, self.labels
            ),
            "time_per_gesture_ms": self._time_per_gesture_ms(features),
            "train_seconds": train_seconds,
        }
        result_metrics.update(
            self.extra_metrics(features, true_labels, probabilities)
        )
        predictions = None
        if with_predictions:
            predictions = [
                Prediction(
                    self.labels[best],
                    float(row[best]),
                    row,
                )
                for row, best in zip(
                    probabilities, np.argmax(probabilities, axis=1)
                )
            ]
        return TrainResult(
            metrics=result_metrics,
            hyperparameters=values,
            labels=self.labels,
            predictions=predictions,
            sample_ids=[str(sample) for sample in evaluation_set.sample_ids],
        )

    def _probabilities(self, features: np.ndarray) -> np.ndarray:
        probabilities = np.asarray(
            self.predict_probabilities(features), dtype=float
        )
        if probabilities.shape != (len(features), len(self.labels)):
            raise ValueError(
                "the model returned probabilities of the wrong shape"
            )
        return probabilities

    def _time_per_gesture_ms(self, features: np.ndarray) -> float:
        sample = features[:TIMING_SAMPLE]
        started = time.perf_counter()
        for row in sample:
            self.predict_probabilities(row[None, :])
        return (time.perf_counter() - started) * 1000 / len(sample)

    # --- Saving ---------------------------------------------------------

    def save(
        self, folder: str | Path, extra_fields: Mapping[str, Any] | None = None
    ) -> Path:
        """Write the trained model and ``classifier.json`` into ``folder``."""
        if not self._trained:
            raise RuntimeError("train a model before saving it")
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        self.write_model(folder)
        description = {
            "format_version": FORMAT_VERSION,
            "family": self.family,
            "labels": list(self.labels),
            "normalization": normalize.settings(),
            "hyperparameters": self.hyperparameters,
        }
        description.update(extra_fields or {})
        (folder / CLASSIFIER_FILE).write_text(
            json.dumps(camel_keys(description), indent=2) + "\n",
            encoding="utf-8",
        )
        return folder
