"""The evaluator (design sections 9.2 and 9.3).

It builds the test cases from the test set (each spell sample, and the same
sample drawn backward), runs a trained model over them one gesture at a time,
and computes the measures. Every measure is computed from the table of
predictions alone, so any of them can be recomputed from the stored table.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from wand_core import normalize
from wand_train.data.gestureset import GestureSet, RawPositions
from wand_train.trainers import metrics

PredictFunction = Callable[[np.ndarray], np.ndarray]

SPELL = "spell"
BACKWARD = "backward"
PREDICTION_COLUMNS = (
    "sampleId",
    "kind",
    "correctLabel",
    "predictedLabel",
    "confidence",
    "probabilities",
    "timeMs",
)
THRESHOLDS = np.round(np.linspace(0.0, 1.0, 101), 2)
DEFAULT_MAX_FALSE_TRIGGER = 0.05
CURVE_COLUMNS = (
    "threshold",
    "recognition_rate",
    "misrecognition_rate",
    "missed_rate",
    "backward_false_trigger_rate",
)


@dataclass
class Evaluation:
    """The predictions and every measure computed from them.

    ``measures`` holds ``accuracy``, ``macro_f1``, ``log_loss``,
    ``label_auc_mean``, ``rejection_auc``, ``time_mean_ms`` and
    ``time_p95_ms``; a measure that cannot be computed is ``None``.
    ``label_auc`` maps each label to its AUC, or ``None`` when it was skipped
    (no positives or no negatives). ``threshold`` is the lowest threshold at
    which the backward false trigger rate is at or below
    ``max_false_trigger``, or ``None`` when none is.
    """

    predictions: pd.DataFrame
    labels: tuple[str, ...]
    measures: dict[str, float | None]
    label_auc: dict[str, float | None]
    skipped_labels: list[str]
    confusion: pd.DataFrame  # rows: correct label, columns: predicted label
    per_label: pd.DataFrame  # precision and recall of each label
    curve: pd.DataFrame
    threshold: float | None
    max_false_trigger: float


def reverse_positions(
    raw: RawPositions,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The positions listed from last to first, with the times measured from
    the new first position (``t' = last_time - t``)."""
    return (
        raw.time_s[-1] - raw.time_s[::-1],
        raw.horizontal[::-1].copy(),
        raw.vertical[::-1].copy(),
    )


def backward_gesture(raw: RawPositions) -> np.ndarray:
    """The normalized gesture of the sample drawn backward."""
    time_s, horizontal, vertical = reverse_positions(raw)
    return normalize.normalize(time_s, horizontal, vertical, raw.frame_size)


def evaluate(
    predict: PredictFunction,
    labels: Sequence[str],
    test_set: GestureSet,
    max_false_trigger: float = DEFAULT_MAX_FALSE_TRIGGER,
) -> Evaluation:
    """Evaluate a trained model on the test set.

    ``predict`` returns the probability of every label (in the order of
    ``labels``) for a batch of normalized gestures. Nothing beyond the test
    set is used.
    """
    if len(test_set) == 0:
        raise ValueError("the test set is empty")
    labels = tuple(labels)
    rows = []
    spell_gestures = test_set.gestures
    for position in range(len(test_set)):
        sample_id = str(test_set.sample_ids[position])
        correct = str(test_set.labels[position])
        rows.append(
            _case(
                predict,
                labels,
                sample_id,
                SPELL,
                correct,
                spell_gestures[position],
            )
        )
        rows.append(
            _case(
                predict,
                labels,
                sample_id,
                BACKWARD,
                None,
                backward_gesture(test_set.raw(position)),
            )
        )
    table = pd.DataFrame(rows, columns=list(PREDICTION_COLUMNS))
    return measures_from_predictions(table, labels, max_false_trigger)


def _case(predict, labels, sample_id, kind, correct, gesture) -> dict:
    started = time.perf_counter()
    probabilities = np.asarray(predict(gesture[None, :]), dtype=float)[0]
    elapsed = (time.perf_counter() - started) * 1000
    best = int(np.argmax(probabilities))
    return {
        "sampleId": sample_id,
        "kind": kind,
        "correctLabel": correct,
        "predictedLabel": labels[best],
        "confidence": float(probabilities[best]),
        "probabilities": probabilities,
        "timeMs": elapsed,
    }


# --- Measures, from the predictions table alone --------------------------


def measures_from_predictions(
    table: pd.DataFrame,
    labels: Sequence[str],
    max_false_trigger: float = DEFAULT_MAX_FALSE_TRIGGER,
) -> Evaluation:
    """Compute every measure from a predictions table and the label order."""
    labels = tuple(labels)
    spell = table[table["kind"] == SPELL]
    backward = table[table["kind"] == BACKWARD]
    true = spell["correctLabel"].to_numpy()
    predicted = spell["predictedLabel"].to_numpy()
    probabilities = (
        np.vstack(spell["probabilities"].to_numpy())
        if len(spell)
        else np.zeros((0, len(labels)))
    )

    label_auc = {}
    for index, label in enumerate(labels):
        label_auc[label] = _auc(probabilities[:, index], true == label)
    computed = [value for value in label_auc.values() if value is not None]
    times = table["timeMs"].to_numpy(dtype=float)
    measures = {
        "accuracy": metrics.accuracy(true, predicted) if len(spell) else None,
        "macro_f1": metrics.macro_f1(true, predicted) if len(spell) else None,
        "log_loss": (
            metrics.log_loss(true, probabilities, labels)
            if len(spell)
            else None
        ),
        "label_auc_mean": float(np.mean(computed)) if computed else None,
        "rejection_auc": _auc(
            table["confidence"].to_numpy(dtype=float),
            (table["kind"] == SPELL).to_numpy(),
        ),
        "time_mean_ms": float(times.mean()) if len(times) else None,
        "time_p95_ms": float(np.percentile(times, 95)) if len(times) else None,
    }
    confusion, per_label = _confusion(true, predicted, labels)
    curve = _curve(spell, backward)
    return Evaluation(
        predictions=table.reset_index(drop=True),
        labels=labels,
        measures=measures,
        label_auc=label_auc,
        skipped_labels=[
            label for label, value in label_auc.items() if value is None
        ],
        confusion=confusion,
        per_label=per_label,
        curve=curve,
        threshold=_lowest_threshold(curve, max_false_trigger),
        max_false_trigger=max_false_trigger,
    )


def _auc(scores: np.ndarray, positive: np.ndarray) -> float | None:
    """Area under the ROC curve: the chance that a positive scores above a
    negative, counting a tie as a half. ``None`` without both kinds."""
    positive = np.asarray(positive, dtype=bool)
    count_positive = int(positive.sum())
    count_negative = len(positive) - count_positive
    if count_positive == 0 or count_negative == 0:
        return None
    ranks = pd.Series(scores).rank(method="average").to_numpy()
    rank_sum = ranks[positive].sum()
    return float(
        (rank_sum - count_positive * (count_positive + 1) / 2)
        / (count_positive * count_negative)
    )


def _confusion(
    true: np.ndarray, predicted: np.ndarray, labels: tuple[str, ...]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    index = {label: position for position, label in enumerate(labels)}
    matrix = np.zeros((len(labels), len(labels)), dtype=int)
    for correct, guess in zip(true, predicted):
        if correct in index and guess in index:
            matrix[index[correct], index[guess]] += 1
    confusion = pd.DataFrame(matrix, index=list(labels), columns=list(labels))
    true_positive = np.diag(matrix).astype(float)
    predicted_count = matrix.sum(axis=0)
    true_count = matrix.sum(axis=1)
    per_label = pd.DataFrame(
        {
            "precision": np.where(
                predicted_count > 0,
                true_positive / np.maximum(predicted_count, 1),
                np.nan,
            ),
            "recall": np.where(
                true_count > 0,
                true_positive / np.maximum(true_count, 1),
                np.nan,
            ),
        },
        index=list(labels),
    )
    return confusion, per_label


def _curve(spell: pd.DataFrame, backward: pd.DataFrame) -> pd.DataFrame:
    spell_confidence = spell["confidence"].to_numpy(dtype=float)
    right = (spell["predictedLabel"] == spell["correctLabel"]).to_numpy()
    backward_confidence = backward["confidence"].to_numpy(dtype=float)
    rows = []
    for threshold in THRESHOLDS:
        recognized = spell_confidence >= threshold
        rows.append(
            {
                "threshold": float(threshold),
                "recognition_rate": _share(recognized & right, len(spell)),
                "misrecognition_rate": _share(recognized & ~right, len(spell)),
                "missed_rate": _share(~recognized, len(spell)),
                "backward_false_trigger_rate": _share(
                    backward_confidence >= threshold, len(backward)
                ),
            }
        )
    return pd.DataFrame(rows, columns=list(CURVE_COLUMNS))


def _share(flags: np.ndarray, total: int) -> float:
    return float(flags.sum() / total) if total else float("nan")


def _lowest_threshold(curve: pd.DataFrame, limit: float) -> float | None:
    rates = curve["backward_false_trigger_rate"]
    qualifying = curve[rates <= limit]
    if qualifying.empty:
        return None
    return float(qualifying["threshold"].iloc[0])
