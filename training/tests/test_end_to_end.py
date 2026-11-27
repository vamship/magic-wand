"""The whole flow on a small synthetic dataset with the fake family (TR-V1).

Build the training data, explore (k-fold and single split), train, report,
and load the model with the library alone. No camera, no real data.
"""

import json
import shutil
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from wand_core import classifiers
from wand_core.testing.datasets import write_synthetic_dataset
from wand_train import models
from wand_train.cli import main
from wand_train.data import gestureset
from wand_train.explore import runs
from wand_train.explore.explorer import build_explorer
from wand_train.trainers.fake import (
    register_fake_family,
    unregister_fake_family,
)

SEED = 13
TEST_FRACTION = 0.2
TIMING_COLUMNS = ("time_per_gesture_ms", "train_seconds")
CLOCK = datetime(2026, 12, 1, 9, 0, 0).astimezone()


@pytest.fixture(autouse=True)
def fake_family():
    register_fake_family()
    yield
    unregister_fake_family()


@pytest.fixture(autouse=True)
def ticking(monkeypatch):
    """Run ids and model ids are one second apart, so they never collide."""
    state = {"moment": CLOCK}

    def tick():
        state["moment"] += timedelta(seconds=1)
        return state["moment"]

    monkeypatch.setattr(models, "now", tick)
    monkeypatch.setattr(runs, "now", tick)


def definition(name, scheme):
    return {
        "formatVersion": 1,
        "name": name,
        "family": "fake",
        "validation": scheme,
        "comparator": {
            "name": "byMetric",
            "settings": {"metric": "accuracy", "direction": "max"},
        },
        "hyperparameters": {"sharpness": [0.5, 5.0, 50.0]},
    }


class Flow:
    """The command line functions, run in a temporary project."""

    def __init__(self, root):
        self.root = root
        self.reports = root / "reports"
        self.models = root / "models"
        self.training_data = root / "training-data"

    def run(self, *args):
        assert main([str(arg) for arg in args]) == 0

    def build(self):
        write_synthetic_dataset(
            self.root / "data" / "ann",
            authors=("ann", "bob"),
            samples_per_shape=10,
        )
        self.run(
            "training-data",
            "build",
            "ann",
            "--data-location",
            self.root / "data",
            "--output",
            self.training_data,
        )

    def explore(self, name, scheme):
        path = self.root / f"{name}.json"
        path.write_text(json.dumps(definition(name, scheme)))
        self.run(
            "explore",
            path,
            "--seed",
            SEED,
            "--test-fraction",
            TEST_FRACTION,
            "--training-data",
            self.training_data,
            "--reports",
            self.reports,
        )
        (folder,) = [
            item
            for item in (self.reports / "fake" / "exploration").iterdir()
            if item.name.endswith(f"-{name}")
        ]
        return folder

    def train(self, run):
        before = set(self.trainings())
        self.run(
            "train",
            run.name,
            "--training-data",
            self.training_data,
            "--reports",
            self.reports,
            "--models",
            self.models,
        )
        (new,) = set(self.trainings()) - before
        return new

    def trainings(self):
        folder = self.reports / "fake" / "training"
        return list(folder.iterdir()) if folder.is_dir() else []


@pytest.fixture
def flow(tmp_path):
    flow = Flow(tmp_path)
    flow.build()
    return flow


def results_without_timing(run):
    table = pd.read_csv(run / "results.csv")
    return table.drop(columns=list(TIMING_COLUMNS))


def test_the_whole_flow_leaves_every_file(flow):
    kfold = flow.explore("grid-kfold", {"scheme": "kFold", "folds": 3})
    single = flow.explore(
        "grid-single", {"scheme": "singleSplit", "fraction": 0.25}
    )
    report = flow.train(kfold)
    model = next((flow.models / "fake").iterdir())

    for run in (kfold, single):
        assert {item.name for item in run.iterdir()} == {
            "definition.json",
            "run.json",
            "results.csv",
            "report.md",
            "figures",
        }
    assert {item.name for item in report.iterdir()} == {
        "source.json",
        "metrics.csv",
        "predictions.parquet",
        "report.md",
        "figures",
    }
    assert {item.name for item in model.iterdir()} >= {"classifier.json"}
    assert model.name == report.name
    assert (flow.reports / "index.md").is_file()
    index = (flow.reports / "index.md").read_text(encoding="utf-8")
    for name in (kfold.name, single.name, report.name):
        assert name in index
    assert {item.name for item in flow.training_data.iterdir()} >= {
        "gestures.parquet",
        "gestures.json",
    }

    description = json.loads((model / "classifier.json").read_text())
    assert description["modelId"] == model.name
    assert description["family"] == "fake"
    assert description["reportPath"].endswith(f"{report.name}")


def test_the_same_seed_gives_the_same_results_and_ranking(flow):
    scheme = {"scheme": "kFold", "folds": 3}
    first = flow.explore("grid-a", scheme)
    second = flow.explore("grid-b", scheme)
    pd.testing.assert_frame_equal(
        results_without_timing(first), results_without_timing(second)
    )
    ranks = [
        [
            result.number
            for result in runs.ExplorerFactory.from_run(run).ranking()
        ]
        for run in (first, second)
    ]
    assert ranks[0] == ranks[1]
    explorer = build_explorer(runs.ExplorerFactory.from_run(first).definition)
    training_set, _ = gestureset.load(flow.training_data).train_test_split(
        TEST_FRACTION, SEED
    )
    again = [
        fold.validation.rows.tolist()
        for fold in explorer.make_folds(training_set, SEED)
    ]
    assert again == [
        fold.validation.rows.tolist()
        for fold in explorer.make_folds(training_set, SEED)
    ]


@pytest.mark.parametrize(
    "scheme",
    [
        {"scheme": "kFold", "folds": 3},
        {"scheme": "singleSplit", "fraction": 0.25},
    ],
)
def test_the_test_set_is_in_no_fold_and_not_in_training(flow, scheme):
    run = flow.explore("grid", scheme)
    full = gestureset.load(flow.training_data)
    training_set, test_set = full.train_test_split(TEST_FRACTION, SEED)
    test_ids = {str(sample) for sample in test_set.sample_ids}
    assert test_ids
    assert test_ids.isdisjoint(str(s) for s in training_set.sample_ids)

    explorer = build_explorer(runs.ExplorerFactory.from_run(run).definition)
    folds = explorer.make_folds(training_set, SEED)
    assert folds
    for fold in folds:
        for part in (fold.training, fold.validation):
            assert test_ids.isdisjoint(str(s) for s in part.sample_ids)

    report = flow.train(run)
    predictions = pd.read_parquet(report / "predictions.parquet")
    assert set(predictions["sampleId"]) == test_ids


def test_the_saved_model_loads_with_the_library_and_predicts_the_same(flow):
    report = flow.train(flow.explore("grid", {"scheme": "kFold", "folds": 3}))
    classifier = classifiers.load(flow.models / "fake" / report.name)
    predictions = pd.read_parquet(report / "predictions.parquet")
    spell = predictions[predictions["kind"] == "spell"]
    _, test_set = gestureset.load(flow.training_data).train_test_split(
        TEST_FRACTION, SEED
    )
    by_id = dict(zip(map(str, test_set.sample_ids), test_set.gestures))
    gestures = np.vstack([by_id[sample] for sample in spell["sampleId"]])

    loaded = classifier.predict(gestures)

    assert [p.label for p in loaded] == list(spell["predictedLabel"])
    assert np.allclose(
        [p.confidence for p in loaded], spell["confidence"], atol=1e-9
    )
    assert np.allclose(
        np.vstack([p.probabilities for p in loaded]),
        np.vstack(spell["probabilities"].to_numpy()),
        atol=1e-9,
    )


def test_deleting_the_exploration_leaves_the_model_and_the_index_working(flow):
    run = flow.explore("grid", {"scheme": "kFold", "folds": 3})
    report = flow.train(run)
    shutil.rmtree(run)

    flow.run("index", "--reports", flow.reports)

    index = (flow.reports / "index.md").read_text(encoding="utf-8")
    assert run.name not in index
    assert report.name in index
    assert (report / "report.md").is_file()
    classifier = classifiers.load(flow.models / "fake" / report.name)
    assert classifier.labels == ("circle", "line", "zigzag")
