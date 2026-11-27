"""The standard metrics (``training/docs/design.md`` section 6).

Labels are label ids. ``probabilities`` has one row per gesture and one column
per label of ``classifier_labels``.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

LOG_LOSS_CLIP = 1e-15

STANDARD_METRICS = (
    "accuracy",
    "macro_f1",
    "log_loss",
    "time_per_gesture_ms",
    "train_seconds",
)


def accuracy(true_labels: Sequence[str], predicted: Sequence[str]) -> float:
    """The share of gestures given the right label."""
    true_array = np.asarray(true_labels)
    if len(true_array) == 0:
        raise ValueError("cannot score an empty set")
    return float(np.mean(true_array == np.asarray(predicted)))


def macro_f1(true_labels: Sequence[str], predicted: Sequence[str]) -> float:
    """F1 averaged over the labels that occur in ``true_labels``.

    A label absent from the evaluation set is skipped. A label with no true
    and no predicted gestures cannot occur, so no division by zero arises: a
    present label with no correct prediction scores 0.
    """
    true_array = np.asarray(true_labels)
    predicted_array = np.asarray(predicted)
    scores = []
    for label in np.unique(true_array):
        true_positive = np.sum(
            (true_array == label) & (predicted_array == label)
        )
        false_positive = np.sum(
            (true_array != label) & (predicted_array == label)
        )
        false_negative = np.sum(
            (true_array == label) & (predicted_array != label)
        )
        denominator = 2 * true_positive + false_positive + false_negative
        scores.append(2 * true_positive / denominator if denominator else 0.0)
    return float(np.mean(scores))


def log_loss(
    true_labels: Sequence[str],
    probabilities: np.ndarray,
    classifier_labels: Sequence[str],
) -> float:
    """Mean negative log probability given to the right label.

    Probabilities are clipped to at least ``LOG_LOSS_CLIP``. A true label the
    classifier does not know gets that smallest probability.
    """
    column = {label: index for index, label in enumerate(classifier_labels)}
    chosen = np.array(
        [
            probabilities[row, column[label]] if label in column else 0.0
            for row, label in enumerate(true_labels)
        ]
    )
    return float(-np.mean(np.log(np.clip(chosen, LOG_LOSS_CLIP, 1.0))))


def predicted_labels(
    probabilities: np.ndarray, classifier_labels: Sequence[str]
) -> np.ndarray:
    """The most probable label of each row."""
    return np.asarray(classifier_labels)[np.argmax(probabilities, axis=1)]
