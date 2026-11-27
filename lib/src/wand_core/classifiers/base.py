"""The classifier interface (``lib/docs/design.md`` section 13).

A classifier predicts from normalized gestures (``wand_core.normalize``). It
is only loaded and used here; training and saving belong to the training tool.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from wand_core.classifiers.errors import ClassifierError
from wand_core.normalize import output_size

SUM_TOLERANCE = 1e-6


@dataclass(frozen=True)
class Prediction:
    """The result for one gesture.

    ``label`` is the most probable label id, ``confidence`` its probability and
    ``probabilities`` has one probability per label in the classifier's label
    order.
    """

    label: str
    confidence: float
    probabilities: np.ndarray


class Classifier(ABC):
    """A trained model of one family, loaded from a folder."""

    def __init__(self, labels: Sequence[str], points: int, info: dict):
        if not labels:
            raise ValueError("a classifier needs at least one label")
        self.labels = tuple(labels)
        self.points = points
        self.info = info

    @abstractmethod
    def predict_probabilities(self, gestures: np.ndarray) -> np.ndarray:
        """Probabilities for a 2-D array of normalized gestures.

        Returns an array with one row per gesture and one column per label.
        """

    def predict(self, gestures: np.ndarray) -> Prediction | list[Prediction]:
        """Predict one gesture (a 1-D array) or a batch (a 2-D array).

        One gesture gives a ``Prediction``; a batch gives a list of them, in
        order, equal to predicting each gesture alone.
        """
        array = np.asarray(gestures, dtype=float)
        if array.ndim not in (1, 2):
            raise ValueError("gestures must be a 1-D or a 2-D array")
        batch = array.reshape(1, -1) if array.ndim == 1 else array
        expected = output_size(self.points)
        if batch.shape[1] != expected:
            raise ValueError(
                f"a normalized gesture has {expected} numbers, "
                f"got {batch.shape[1]}"
            )
        probabilities = np.asarray(
            self.predict_probabilities(batch), dtype=float
        )
        if probabilities.shape != (len(batch), len(self.labels)):
            raise ClassifierError(
                "the model returned probabilities of the wrong shape"
            )
        if not np.allclose(probabilities.sum(axis=1), 1.0, atol=SUM_TOLERANCE):
            raise ClassifierError("the probabilities do not sum to 1")
        predictions = []
        for row in probabilities:
            best = int(np.argmax(row))
            predictions.append(
                Prediction(self.labels[best], float(row[best]), row)
            )
        return predictions[0] if array.ndim == 1 else predictions
