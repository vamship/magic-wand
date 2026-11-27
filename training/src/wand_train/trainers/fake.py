"""A fake family for tests of the framework.

It stores the mean normalized gesture of each label and predicts with a
softmax of the negative distances to the means. Call ``register_fake_family``
to make it available to the trainer registry and the library's loader.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from wand_core import classifiers
from wand_core.classifiers import Classifier
from wand_core.classifiers.files import ClassifierDescription
from wand_train.trainers.base import Hyperparameter, Trainer
from wand_train.trainers.registry import register_trainer, unregister_trainer

FAMILY = "fake"
MEANS_FILE = "means.npy"
MODEL_FILE = "model.json"


def probabilities_from_means(
    features: np.ndarray, means: np.ndarray, sharpness: float
) -> np.ndarray:
    """Softmax of ``-sharpness * distance`` to each mean.

    The last number of a normalized gesture is its duration in seconds, which
    would swamp the steps, so the distance leaves it out.
    """
    features, means = features[:, :-1], means[:, :-1]
    distances = np.linalg.norm(features[:, None, :] - means[None, :, :], axis=2)
    scores = -sharpness * distances
    scores -= scores.max(axis=1, keepdims=True)
    weights = np.exp(scores)
    return weights / weights.sum(axis=1, keepdims=True)


class FakeTrainer(Trainer):
    family = FAMILY
    hyperparameter_specs = (
        Hyperparameter("sharpness", "float", 5.0, minimum=0.0, maximum=1000.0),
    )

    def fit(
        self,
        features: np.ndarray,
        labels: np.ndarray,
        hyperparameters: dict[str, Any],
        seed: int,
    ) -> None:
        self.means = np.vstack(
            [features[labels == label].mean(axis=0) for label in self.labels]
        )

    def predict_probabilities(self, features: np.ndarray) -> np.ndarray:
        return probabilities_from_means(
            features, self.means, self.hyperparameters["sharpness"]
        )

    def write_model(self, folder: Path) -> None:
        np.save(folder / MEANS_FILE, self.means)
        (folder / MODEL_FILE).write_text(
            json.dumps({"sharpness": self.hyperparameters["sharpness"]})
        )


class FakeClassifier(Classifier):
    """The library side of the fake family."""

    def __init__(self, means, sharpness, labels, points, info):
        super().__init__(labels, points, info)
        self.means = means
        self.sharpness = sharpness

    def predict_probabilities(self, gestures: np.ndarray) -> np.ndarray:
        return probabilities_from_means(gestures, self.means, self.sharpness)


def load_fake(folder: Path, description: ClassifierDescription) -> Classifier:
    means = np.load(folder / MEANS_FILE)
    sharpness = json.loads((folder / MODEL_FILE).read_text())["sharpness"]
    return FakeClassifier(
        means,
        sharpness,
        description.labels,
        description.points,
        description.extra,
    )


def register_fake_family() -> None:
    register_trainer(FakeTrainer)
    classifiers.register_family(FAMILY, load_fake)


def unregister_fake_family() -> None:
    unregister_trainer(FAMILY)
    classifiers.unregister_family(FAMILY)
