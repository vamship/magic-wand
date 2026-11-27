import json

import numpy as np
import pytest

from wand_core import classifiers
from wand_core.classifiers import (
    Classifier,
    InvalidClassifierFileError,
    MissingClassifierFileError,
    MissingDependencyError,
    NormalizationMismatchError,
    Prediction,
    UnknownFamilyError,
    UnsupportedFormatVersionError,
)
from wand_core.normalize import output_size

LABELS = ["alohomora", "reparo", "silencio"]


class FakeClassifier(Classifier):
    """Predicts from the distance to stored class means."""

    def __init__(self, means, labels, points, info):
        super().__init__(labels, points, info)
        self.means = means

    def predict_probabilities(self, gestures):
        distances = np.linalg.norm(
            gestures[:, None, :] - self.means[None, :, :], axis=2
        )
        scores = np.exp(-distances)
        return scores / scores.sum(axis=1, keepdims=True)


def load_fake(folder, description):
    means = np.load(folder / "means.npy")
    return FakeClassifier(
        means, description.labels, description.points, description.extra
    )


@pytest.fixture(autouse=True)
def fake_family():
    classifiers.register_family("fake", load_fake)
    yield
    classifiers.unregister_family("fake")


def description(**changes):
    data = {
        "formatVersion": 1,
        "family": "fake",
        "labels": LABELS,
        "normalization": {"points": 64, "version": 1},
    }
    data.update(changes)
    return data


@pytest.fixture
def means():
    generator = np.random.default_rng(1)
    return generator.normal(size=(3, output_size()))


def write(folder, data, means=None):
    folder.mkdir(exist_ok=True)
    (folder / "classifier.json").write_text(json.dumps(data))
    if means is not None:
        np.save(folder / "means.npy", means)
    return folder


def test_load_and_predict(tmp_path, means):
    folder = write(tmp_path / "c", description(), means)
    classifier = classifiers.load(folder)
    prediction = classifier.predict(means[1] + 0.01)
    assert isinstance(prediction, Prediction)
    assert prediction.label == "reparo"
    assert prediction.probabilities.sum() == pytest.approx(1.0)
    assert prediction.confidence == prediction.probabilities.max()
    assert classifier.labels == tuple(LABELS)


def test_batch_agrees_with_single(tmp_path, means):
    classifier = classifiers.load(write(tmp_path / "c", description(), means))
    gestures = means + 0.05
    batch = classifier.predict(gestures)
    assert len(batch) == 3
    for gesture, from_batch in zip(gestures, batch):
        single = classifier.predict(gesture)
        assert single.label == from_batch.label
        np.testing.assert_allclose(
            single.probabilities, from_batch.probabilities
        )


@pytest.mark.parametrize(
    "changes, error",
    [
        ({"formatVersion": 2}, UnsupportedFormatVersionError),
        (
            {"normalization": {"points": 32, "version": 1}},
            NormalizationMismatchError,
        ),
        (
            {"normalization": {"points": 64, "version": 2}},
            NormalizationMismatchError,
        ),
        ({"family": "nope"}, UnknownFamilyError),
        ({"labels": []}, InvalidClassifierFileError),
    ],
)
def test_rejected_files(tmp_path, means, changes, error):
    folder = write(tmp_path / "c", description(**changes), means)
    with pytest.raises(error):
        classifiers.load(folder)


def test_missing_and_malformed_file(tmp_path):
    with pytest.raises(MissingClassifierFileError):
        classifiers.load(tmp_path)
    (tmp_path / "classifier.json").write_text("{not json")
    with pytest.raises(InvalidClassifierFileError):
        classifiers.load(tmp_path)


def test_missing_optional_dependency_is_named(tmp_path):
    def loader(folder, description):
        import not_a_real_module_for_tests  # noqa: F401

    classifiers.register_family("heavy", loader)
    try:
        folder = write(tmp_path / "c", description(family="heavy"))
        with pytest.raises(MissingDependencyError, match="not_a_real_module"):
            classifiers.load(folder)
    finally:
        classifiers.unregister_family("heavy")


def test_extra_fields_are_ignored(tmp_path, means):
    data = description(modelId="fake-1", hyperparameters={"depth": 3})
    classifier = classifiers.load(write(tmp_path / "c", data, means))
    assert classifier.info["model_id"] == "fake-1"
    assert classifier.predict(means[0]).label == "alohomora"


def test_wrong_gesture_size_is_rejected(tmp_path, means):
    classifier = classifiers.load(write(tmp_path / "c", description(), means))
    with pytest.raises(ValueError, match="190"):
        classifier.predict(np.zeros(10))


def test_library_does_not_need_training_code():
    import pathlib

    import wand_core

    root = pathlib.Path(wand_core.__file__).parent
    for path in root.rglob("*.py"):
        assert "wand_train" not in path.read_text(), path
