import numpy as np
import pandas as pd
import pytest

from wand_core.testing.datasets import write_synthetic_dataset
from wand_train import evaluate
from wand_train.data import builder, gestureset
from wand_train.data.gestureset import RawPositions
from wand_train.evaluate import (
    BACKWARD,
    PREDICTION_COLUMNS,
    SPELL,
    measures_from_predictions,
)
from wand_train.trainers.fake import FakeTrainer

LABELS = ("a", "b", "c")


def table(spell, backward):
    """Predictions from (correct label, probabilities) and backward
    probabilities."""
    rows = []
    for number, (correct, probabilities) in enumerate(spell):
        rows.append(case(f"s{number}", SPELL, correct, probabilities))
    for number, probabilities in enumerate(backward):
        rows.append(case(f"s{number}", BACKWARD, None, probabilities))
    return pd.DataFrame(rows, columns=list(PREDICTION_COLUMNS))


def case(sample_id, kind, correct, probabilities):
    probabilities = np.asarray(probabilities, dtype=float)
    best = int(np.argmax(probabilities))
    return {
        "sampleId": sample_id,
        "kind": kind,
        "correctLabel": correct,
        "predictedLabel": LABELS[best],
        "confidence": float(probabilities[best]),
        "probabilities": probabilities,
        "timeMs": 1.0,
    }


MIXED_SPELL = [
    ("a", [0.7, 0.2, 0.1]),
    ("a", [0.4, 0.5, 0.1]),  # wrong: predicted b
    ("b", [0.1, 0.8, 0.1]),
    ("b", [0.2, 0.6, 0.2]),
    ("c", [0.1, 0.2, 0.7]),
    ("c", [0.3, 0.5, 0.2]),  # wrong: predicted b
]
MIXED_BACKWARD = [[0.4, 0.3, 0.3], [0.5, 0.25, 0.25]]


@pytest.fixture
def mixed():
    return measures_from_predictions(table(MIXED_SPELL, MIXED_BACKWARD), LABELS)


def test_reversing_a_gesture():
    raw = RawPositions(
        "x",
        np.array([0.0, 0.1, 0.3]),
        np.array([0.1, 0.2, 0.5]),
        np.array([0.4, 0.3, 0.1]),
        (640, 480),
    )
    time_s, horizontal, vertical = evaluate.reverse_positions(raw)
    np.testing.assert_allclose(time_s, [0.0, 0.2, 0.3])
    np.testing.assert_allclose(horizontal, [0.5, 0.2, 0.1])
    np.testing.assert_allclose(vertical, [0.1, 0.3, 0.4])
    # A backward spell lasts as long as the original.
    assert evaluate.backward_gesture(raw)[-1] == pytest.approx(0.3)


def test_threshold_free_measures_on_a_mixed_table(mixed):
    measures = mixed.measures
    assert measures["accuracy"] == pytest.approx(4 / 6)
    assert measures["macro_f1"] == pytest.approx(2 / 3)
    expected_loss = -np.mean(np.log([0.7, 0.4, 0.8, 0.6, 0.7, 0.2]))
    assert measures["log_loss"] == pytest.approx(expected_loss)
    assert mixed.label_auc["a"] == 1.0
    assert mixed.label_auc["b"] == 1.0
    # c: the positives score .7 and .2; the negatives .1, .1, .1, .2.
    assert mixed.label_auc["c"] == pytest.approx((4 + 3.5) / 8)
    assert measures["label_auc_mean"] == pytest.approx((1 + 1 + 0.9375) / 3)
    # Spell confidences .7 .5 .8 .6 .7 .5 against backward .4 and .5.
    assert measures["rejection_auc"] == pytest.approx(11 / 12)
    assert mixed.skipped_labels == []


def test_confusion_matrix_and_per_label_measures(mixed):
    assert mixed.confusion.to_numpy().tolist() == [
        [1, 1, 0],
        [0, 2, 0],
        [0, 1, 1],
    ]
    assert mixed.per_label["precision"].tolist() == [1.0, 0.5, 1.0]
    assert mixed.per_label["recall"].tolist() == [0.5, 1.0, 0.5]


def test_curve_data(mixed):
    curve = mixed.curve.set_index("threshold")
    assert len(curve) == 101
    at_zero = curve.loc[0.0]
    assert at_zero["recognition_rate"] == pytest.approx(4 / 6)  # accuracy
    assert at_zero["misrecognition_rate"] == pytest.approx(2 / 6)
    assert at_zero["missed_rate"] == 0
    assert at_zero["backward_false_trigger_rate"] == 1.0
    half = curve.loc[0.5]
    assert half["backward_false_trigger_rate"] == 0.5
    assert half["missed_rate"] == 0
    above = curve.loc[0.51]
    assert above["recognition_rate"] == pytest.approx(4 / 6)
    assert above["misrecognition_rate"] == 0
    assert above["missed_rate"] == pytest.approx(2 / 6)
    assert above["backward_false_trigger_rate"] == 0
    assert curve.loc[0.8]["recognition_rate"] == pytest.approx(1 / 6)
    top = curve.loc[1.0]
    assert top["recognition_rate"] == 0 and top["missed_rate"] == 1
    sums = (
        curve["recognition_rate"]
        + curve["misrecognition_rate"]
        + curve["missed_rate"]
    )
    np.testing.assert_allclose(sums, 1.0)


def test_threshold_information(mixed):
    assert mixed.threshold == pytest.approx(0.51)
    looser = measures_from_predictions(
        table(MIXED_SPELL, MIXED_BACKWARD), LABELS, max_false_trigger=0.6
    )
    assert looser.threshold == pytest.approx(0.41)
    # A backward case with confidence 1 can never be rejected.
    hopeless = measures_from_predictions(
        table(MIXED_SPELL, [[1.0, 0.0, 0.0]]), LABELS
    )
    assert hopeless.threshold is None
    assert hopeless.max_false_trigger == 0.05


def test_perfect_random_and_tied_classifiers():
    perfect = measures_from_predictions(
        table(
            [("a", [1, 0, 0]), ("b", [0, 1, 0]), ("c", [0, 0, 1])],
            [[0.4, 0.3, 0.3]] * 2,
        ),
        LABELS,
    )
    assert perfect.measures["accuracy"] == 1.0
    assert perfect.measures["rejection_auc"] == 1.0
    assert perfect.measures["label_auc_mean"] == 1.0
    curve = perfect.curve.set_index("threshold")
    assert curve.loc[1.0]["recognition_rate"] == 1.0  # confidence 1 counts
    assert curve.loc[1.0]["backward_false_trigger_rate"] == 0.0
    equal = measures_from_predictions(
        table(
            [("a", [0.5, 0.3, 0.2]), ("b", [0.2, 0.5, 0.3])],
            [[0.5, 0.25, 0.25]] * 2,
        ),
        LABELS,
    )
    assert equal.measures["rejection_auc"] == 0.5


def test_labels_without_both_kinds_are_skipped():
    only_a = measures_from_predictions(
        table(
            [("a", [0.9, 0.05, 0.05]), ("a", [0.6, 0.3, 0.1])],
            [[0.4, 0.3, 0.3]],
        ),
        LABELS,
    )
    assert only_a.skipped_labels == ["a", "b", "c"]
    assert only_a.label_auc == {"a": None, "b": None, "c": None}
    assert only_a.measures["label_auc_mean"] is None
    assert only_a.measures["accuracy"] == 1.0


def test_no_backward_cases_gives_no_rejection_auc():
    result = measures_from_predictions(
        table([("a", [0.9, 0.05, 0.05]), ("b", [0.1, 0.8, 0.1])], []), LABELS
    )
    assert result.measures["rejection_auc"] is None
    assert result.threshold is None  # no backward cases, no rates


# --- Evaluating a model ------------------------------------------------


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    root = tmp_path_factory.mktemp("evaluate")
    write_synthetic_dataset(
        root / "data" / "ann", authors=("ann", "bob"), samples_per_shape=10
    )
    builder.build([root / "data" / "ann"], root / "td", root=root)
    training, test = gestureset.load(root / "td").train_test_split(seed=3)
    trainer = FakeTrainer()
    trainer.train(training, test, {"sharpness": 5.0})
    return trainer, test


def test_evaluating_a_model(trained):
    trainer, test = trained
    result = evaluate.evaluate(
        trainer.predict_probabilities, trainer.labels, test
    )
    predictions = result.predictions
    assert list(predictions.columns) == list(PREDICTION_COLUMNS)
    assert len(predictions) == 2 * len(test)
    assert (predictions["kind"] == SPELL).sum() == len(test)
    assert (
        predictions[predictions["kind"] == BACKWARD]["correctLabel"]
        .isna()
        .all()
    )
    assert (predictions["timeMs"] > 0).all()
    assert result.measures["time_p95_ms"] >= result.measures["time_mean_ms"]
    curve = result.curve.set_index("threshold")
    assert curve.loc[0.0]["recognition_rate"] == pytest.approx(
        result.measures["accuracy"]
    )
    assert curve.loc[0.0]["backward_false_trigger_rate"] == 1.0
    confident = predictions["confidence"] == 1.0
    assert curve.loc[1.0]["backward_false_trigger_rate"] == pytest.approx(
        confident[predictions["kind"] == BACKWARD].mean()
    )


def test_everything_can_be_recomputed_from_the_table(trained):
    trainer, test = trained
    result = evaluate.evaluate(
        trainer.predict_probabilities, trainer.labels, test
    )
    # Through a round trip that keeps only the table's content.
    copy = result.predictions.copy()
    copy["probabilities"] = copy["probabilities"].apply(list).apply(np.array)
    again = measures_from_predictions(copy, trainer.labels)
    assert again.measures == result.measures
    pd.testing.assert_frame_equal(again.curve, result.curve)
    spell = copy[copy["kind"] == SPELL]
    assert result.measures["accuracy"] == pytest.approx(
        (spell["correctLabel"] == spell["predictedLabel"]).mean()
    )


def test_the_evaluator_uses_only_the_test_set(trained):
    trainer, test = trained
    seen = []

    def spy(batch):
        seen.append(batch.copy())
        return trainer.predict_probabilities(batch)

    evaluate.evaluate(spy, trainer.labels, test)
    assert all(batch.shape == (1, 190) for batch in seen)
    spell_inputs = np.vstack(seen[0::2])
    np.testing.assert_array_equal(spell_inputs, test.gestures)
    assert len(seen) == 2 * len(test)
    with pytest.raises(ValueError, match="empty"):
        evaluate.evaluate(spy, trainer.labels, test.select(author="nobody"))
