import json

import numpy as np
import pytest

from wand_core import classifiers
from wand_core.testing.datasets import write_synthetic_dataset
from wand_train.data import builder, gestureset
from wand_train.trainers import metrics
from wand_train.trainers.base import (
    Hyperparameter,
    HyperparameterError,
    Trainer,
)
from wand_train.trainers.fake import (
    FakeTrainer,
    register_fake_family,
    unregister_fake_family,
)
from wand_train.trainers.registry import (
    UnknownFamilyError,
    get_trainer,
    register_trainer,
    trainer_families,
    unregister_trainer,
)


@pytest.fixture(scope="module")
def sets(tmp_path_factory):
    root = tmp_path_factory.mktemp("trainers")
    write_synthetic_dataset(
        root / "data" / "ann", authors=("ann", "bob"), samples_per_shape=10
    )
    builder.build([root / "data" / "ann"], root / "td", root=root)
    return gestureset.load(root / "td").train_test_split(seed=1)


@pytest.fixture(autouse=True)
def fake_family():
    register_fake_family()
    yield
    unregister_fake_family()


# --- Metrics -----------------------------------------------------------


def test_metrics_against_hand_computed_values():
    true = ["a", "a", "b", "b", "c"]
    predicted = ["a", "b", "b", "b", "a"]
    assert metrics.accuracy(true, predicted) == pytest.approx(3 / 5)
    # a: tp1 fp1 fn1 -> 0.5 ; b: tp2 fp1 fn0 -> 0.8 ; c: tp0 -> 0
    assert metrics.macro_f1(true, predicted) == pytest.approx((0.5 + 0.8) / 3)
    probabilities = np.array(
        [
            [0.5, 0.25, 0.25],
            [0.2, 0.6, 0.2],
            [0.1, 0.8, 0.1],
            [0.25, 0.5, 0.25],
            [0.4, 0.4, 0.2],
        ]
    )
    expected = -np.mean(np.log([0.5, 0.2, 0.8, 0.5, 0.2]))
    assert metrics.log_loss(
        true, probabilities, ["a", "b", "c"]
    ) == pytest.approx(expected)


def test_macro_f1_skips_labels_absent_from_the_evaluation_set():
    assert metrics.macro_f1(["a", "a"], ["a", "a"]) == 1.0


def test_log_loss_is_clipped_and_handles_unknown_labels():
    probabilities = np.array([[1.0, 0.0]])
    assert np.isfinite(metrics.log_loss(["b"], probabilities, ["a", "b"]))
    assert np.isfinite(metrics.log_loss(["z"], probabilities, ["a", "b"]))


# --- Hyperparameters ---------------------------------------------------


def test_defaults_and_validation_errors():
    trainer = FakeTrainer()
    assert trainer.validate({}) == {"sharpness": 5.0}
    assert trainer.validate({"sharpness": 2}) == {"sharpness": 2}
    with pytest.raises(HyperparameterError, match="'colour'"):
        trainer.validate({"colour": 1})
    with pytest.raises(HyperparameterError, match="'sharpness'"):
        trainer.validate({"sharpness": "high"})
    with pytest.raises(HyperparameterError, match="'sharpness'"):
        trainer.validate({"sharpness": True})
    with pytest.raises(HyperparameterError, match="'sharpness'"):
        trainer.validate({"sharpness": 5000})
    with pytest.raises(HyperparameterError, match="'sharpness'"):
        trainer.validate({"sharpness": -1})


def test_each_kind_of_hyperparameter():
    integer = Hyperparameter("depth", "int", 3, minimum=1, maximum=10)
    assert integer.check(4) == 4
    for bad in (2.5, "x", True, 0, 11):
        with pytest.raises(HyperparameterError, match="depth"):
            integer.check(bad)
    choice = Hyperparameter(
        "kernel", "choice", "rbf", choices=("rbf", "linear")
    )
    assert choice.check("linear") == "linear"
    with pytest.raises(HyperparameterError, match="kernel"):
        choice.check("poly")
    flag = Hyperparameter("shrink", "bool", True)
    with pytest.raises(HyperparameterError, match="shrink"):
        flag.check(1)
    with pytest.raises(ValueError):
        Hyperparameter("depth", "int", 0, minimum=1)  # default out of range


# --- Training ----------------------------------------------------------


def test_the_fake_family_beats_chance(sets):
    training, test = sets
    result = FakeTrainer().train(training, test, seed=1)
    assert result.metrics["accuracy"] > 0.5  # chance is 1/3
    for name in metrics.STANDARD_METRICS:
        assert name in result.metrics
    assert result.metrics["train_seconds"] >= 0
    assert result.metrics["time_per_gesture_ms"] > 0
    assert result.labels == ("circle", "line", "zigzag")


def test_predictions_on_request(sets):
    training, test = sets
    assert FakeTrainer().train(training, test).predictions is None
    result = FakeTrainer().train(training, test, with_predictions=True)
    assert len(result.predictions) == len(test)
    for prediction in result.predictions:
        assert prediction.probabilities.sum() == pytest.approx(1.0)
        assert prediction.confidence == prediction.probabilities.max()
        assert (
            prediction.label
            == result.labels[int(np.argmax(prediction.probabilities))]
        )
    assert result.sample_ids == [str(i) for i in test.sample_ids]


class Recording(FakeTrainer):
    """Records everything the model is given, and learns a scaling."""

    family = "recording"

    def fit(self, features, labels, hyperparameters, seed):
        self.fitted_features = features.copy()
        self.scale = features.std()
        super().fit(features, labels, hyperparameters, seed)


def test_a_trainer_uses_only_the_two_sets_it_is_given(sets):
    training, test = sets
    trainer = Recording()
    trainer.train(training, test)
    np.testing.assert_array_equal(trainer.fitted_features, training.gestures)
    assert len(trainer.fitted_features) == len(training)
    # Nothing from the evaluation set reached the fit.
    held_out = {tuple(row) for row in test.gestures}
    assert not held_out & {tuple(row) for row in trainer.fitted_features}


def test_learned_values_come_from_the_training_set_only(sets):
    training, test = sets
    first, second = Recording(), Recording()
    first.train(training, test)
    second.train(training, test.select(label="circle"))
    assert first.scale == second.scale == pytest.approx(training.gestures.std())


def test_an_empty_set_is_refused(sets):
    training, test = sets
    with pytest.raises(ValueError, match="empty"):
        FakeTrainer().train(training, test.select(author="nobody"))


def test_extra_metrics_are_returned_beside_the_standard_ones(sets):
    class Extra(FakeTrainer):
        family = "extra"

        def extra_metrics(self, features, labels, probabilities):
            return {"mean_confidence": float(probabilities.max(axis=1).mean())}

    training, test = sets
    result = Extra().train(training, test)
    assert "mean_confidence" in result.metrics
    assert "accuracy" in result.metrics


# --- Saving ------------------------------------------------------------


def test_saved_model_loads_in_the_library_with_equal_predictions(
    sets, tmp_path
):
    training, test = sets
    trainer = FakeTrainer()
    result = trainer.train(
        training, test, {"sharpness": 3.0}, with_predictions=True
    )
    folder = trainer.save(tmp_path / "model", {"model_id": "fake-1"})
    description = json.loads((folder / "classifier.json").read_text())
    assert description["formatVersion"] == 1
    assert description["family"] == "fake"
    assert description["labels"] == ["circle", "line", "zigzag"]
    assert description["normalization"] == {"points": 64, "version": 1}
    assert description["modelId"] == "fake-1"
    loaded = classifiers.load(folder)
    predictions = loaded.predict(test.gestures)
    for saved, trained in zip(predictions, result.predictions):
        assert saved.label == trained.label
        np.testing.assert_allclose(saved.probabilities, trained.probabilities)


def test_saving_before_training_is_an_error(tmp_path):
    with pytest.raises(RuntimeError):
        FakeTrainer().save(tmp_path / "x")


# --- Registry ----------------------------------------------------------


def test_registry_and_adding_a_family(sets):
    assert "fake" in trainer_families()
    assert isinstance(get_trainer("fake"), FakeTrainer)
    with pytest.raises(UnknownFamilyError, match="nope"):
        get_trainer("nope")

    class Another(FakeTrainer):
        family = "another"

    register_trainer(Another)
    try:
        assert isinstance(get_trainer("another"), Another)
        assert "fake" in trainer_families()  # others are unaffected
    finally:
        unregister_trainer("another")
    assert issubclass(Another, Trainer)
