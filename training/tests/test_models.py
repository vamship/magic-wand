import json
import shutil
import subprocess
import sys
import textwrap
from datetime import datetime, timedelta

import pandas as pd
import pytest

from wand_core import classifiers
from wand_core.testing.datasets import write_synthetic_dataset
from wand_train import models
from wand_train.cli import main
from wand_train.data import builder, gestureset
from wand_train.trainers.fake import (
    FakeTrainer,
    register_fake_family,
    unregister_fake_family,
)

CLOCK = datetime(2026, 12, 1, 9, 0, 0).astimezone()


@pytest.fixture(autouse=True)
def fake_family():
    register_fake_family()
    yield
    unregister_fake_family()


@pytest.fixture
def world(tmp_path):
    write_synthetic_dataset(
        tmp_path / "data" / "ann", authors=("ann", "bob"), samples_per_shape=10
    )
    builder.build(
        [tmp_path / "data" / "ann"], tmp_path / "training-data", root=tmp_path
    )
    return tmp_path


@pytest.fixture
def ticking(monkeypatch):
    """Every call to ``models.now`` is one second later."""
    state = {"moment": CLOCK}

    def tick():
        state["moment"] += timedelta(seconds=1)
        return state["moment"]

    monkeypatch.setattr(models, "now", tick)


def definition(name="fake-grid"):
    return {
        "formatVersion": 1,
        "name": name,
        "family": "fake",
        "validation": {"scheme": "kFold", "folds": 3},
        "comparator": {
            "name": "byMetric",
            "settings": {"metric": "accuracy", "direction": "max"},
        },
        "hyperparameters": {"sharpness": [0.5, 5.0, 50.0]},
    }


def explore(world, seed=7):
    path = world / "fake-grid.json"
    path.write_text(json.dumps(definition()))
    code = main(
        [
            "explore",
            str(path),
            "--seed",
            str(seed),
            "--training-data",
            str(world / "training-data"),
            "--reports",
            str(world / "reports"),
        ]
    )
    assert code == 0
    (run,) = (world / "reports" / "fake" / "exploration").iterdir()
    return run


def train(world, *args):
    return main(
        [
            "train",
            *args,
            "--training-data",
            str(world / "training-data"),
            "--reports",
            str(world / "reports"),
            "--models",
            str(world / "models"),
        ]
    )


def only(folder):
    (child,) = folder.iterdir()
    return child


def test_train_from_a_run_writes_every_file(world, ticking, capsys):
    run = explore(world)
    capsys.readouterr()
    assert train(world, run.name) == 0
    out = capsys.readouterr().out
    report = only(world / "reports" / "fake" / "training")
    model = only(world / "models" / "fake")
    assert str(report) in out and str(model) in out
    assert {p.name for p in report.iterdir()} == {
        "source.json",
        "metrics.csv",
        "predictions.parquet",
        "report.md",
        "figures",
    }
    source = json.loads((report / "source.json").read_text())
    assert source["explorationRunId"] == run.name
    assert source["candidate"] in (1, 2, 3)
    assert source["seed"] == 7 and source["testFraction"] == 0.2
    assert source["hyperparameters"]["sharpness"] in (0.5, 5.0, 50.0)
    metrics = pd.read_csv(report / "metrics.csv")
    assert set(metrics["section"]) >= {
        "measure",
        "label_auc",
        "precision",
        "recall",
        "confusion",
        "threshold_info",
        "curve",
    }
    assert len(metrics[metrics["name"] == "recognition_rate"]) == 101
    predictions = pd.read_parquet(report / "predictions.parquet")
    assert len(predictions) % 2 == 0
    assert len(predictions["probabilities"].iloc[0]) == 3


def test_classifier_json_has_the_stated_fields_and_no_threshold(world, ticking):
    run = explore(world)
    assert train(world, run.name) == 0
    model = only(world / "models" / "fake")
    data = json.loads((model / "classifier.json").read_text())
    assert {
        "formatVersion",
        "family",
        "labels",
        "normalization",
        "modelId",
        "hyperparameters",
        "metrics",
        "trainingDataFingerprint",
        "reportPath",
    } <= set(data)
    assert set(data["metrics"]) == {
        "accuracy",
        "macroF1",
        "logLoss",
        "labelAucMean",
        "rejectionAuc",
    }
    assert data["modelId"] == model.name
    # The temporary reports folder is outside the repository, so the path is
    # absolute here; inside the repository it is relative to the root.
    assert data["reportPath"].endswith(f"reports/fake/training/{model.name}")
    assert models._relative(world / "reports" / "x", world) == "reports/x"
    assert not any("threshold" in key.lower() for key in data)
    assert classifiers.load(model).labels == tuple(data["labels"])


def test_the_model_loads_with_the_library_alone(world, ticking):
    run = explore(world)
    assert train(world, run.name) == 0
    model = only(world / "models" / "fake")
    script = textwrap.dedent(
        f"""
        import json, sys
        import numpy as np
        from wand_core import classifiers
        from wand_core.classifiers import Classifier

        class Loaded(Classifier):
            def __init__(self, means, sharpness, labels, points, info):
                super().__init__(labels, points, info)
                self.means, self.sharpness = means, sharpness

            def predict_probabilities(self, gestures):
                distance = np.linalg.norm(
                    gestures[:, None, :] - self.means[None], axis=2)
                score = -self.sharpness * distance
                score -= score.max(axis=1, keepdims=True)
                weight = np.exp(score)
                return weight / weight.sum(axis=1, keepdims=True)

        def load(folder, description):
            means = np.load(folder / "means.npy")
            sharpness = json.loads(
                (folder / "model.json").read_text())["sharpness"]
            return Loaded(means, sharpness, description.labels,
                          description.points, description.extra)

        classifiers.register_family("fake", load)
        classifier = classifiers.load({str(model)!r})
        classifier.predict(np.zeros(190))
        assert "wand_train" not in sys.modules
        print("ok")
        """
    )
    done = subprocess.run(
        [sys.executable, "-I", "-c", script],
        capture_output=True,
        text=True,
    )
    assert done.stdout.strip() == "ok", done.stderr


def test_the_split_equals_the_explorations(world, ticking):
    run = explore(world, seed=11)
    assert train(world, run.name) == 0
    report = only(world / "reports" / "fake" / "training")
    predictions = pd.read_parquet(report / "predictions.parquet")
    tested = set(predictions["sampleId"])
    _, test = gestureset.load(world / "training-data").train_test_split(0.2, 11)
    assert tested == {str(sample) for sample in test.sample_ids}


def test_the_trainer_gets_disjoint_training_and_test_sets(
    world, ticking, monkeypatch
):
    run = explore(world)
    calls = []
    original = FakeTrainer.train

    def spy(self, training_set, evaluation_set, *args, **kwargs):
        calls.append((set(training_set.rows), set(evaluation_set.rows)))
        return original(self, training_set, evaluation_set, *args, **kwargs)

    monkeypatch.setattr(FakeTrainer, "train", spy)
    assert train(world, run.name) == 0
    ((training, test),) = calls
    assert training.isdisjoint(test)
    total = len(gestureset.load(world / "training-data"))
    assert len(training) + len(test) == total


def test_a_changed_fingerprint_stops_before_training(
    world, ticking, monkeypatch, capsys
):
    run = explore(world)
    shutil.rmtree(world / "training-data")
    write_synthetic_dataset(
        world / "data" / "carl", authors=("carl",), samples_per_shape=3, seed=9
    )
    builder.build(
        [world / "data" / "ann", world / "data" / "carl"],
        world / "training-data",
        root=world,
    )
    calls = []
    monkeypatch.setattr(FakeTrainer, "train", lambda *a, **k: calls.append(1))
    capsys.readouterr()
    assert train(world, run.name) == 1
    assert "changed" in capsys.readouterr().err
    assert calls == []
    assert not (world / "models").exists()


def test_models_never_share_an_id_or_overwrite(world, ticking):
    run = explore(world)
    assert train(world, run.name) == 0
    assert train(world, run.name) == 0
    reports = sorted((world / "reports" / "fake" / "training").iterdir())
    models_ = sorted((world / "models" / "fake").iterdir())
    assert len(reports) == len(models_) == 2
    assert [p.name for p in reports] == [p.name for p in models_]
    # The same second again is refused and changes nothing.
    source = models.source_from_run(run.name, world / "reports")
    before = (models_[0] / "classifier.json").read_text()
    with pytest.raises(models.ModelExistsError):
        models.train_model(
            source,
            world / "training-data",
            world / "reports",
            world / "models",
            moment=datetime.strptime(
                models_[0].name.split("fake-")[1], "%Y%m%d-%H%M%S"
            ).astimezone(),
        )
    assert (models_[0] / "classifier.json").read_text() == before


def test_deleting_the_exploration_leaves_the_model_intact(world, ticking):
    run = explore(world)
    assert train(world, run.name) == 0
    shutil.rmtree(run)
    report = only(world / "reports" / "fake" / "training")
    model = only(world / "models" / "fake")
    assert (report / "source.json").is_file()
    assert classifiers.load(model).labels


def test_values_file_without_an_exploration(world, ticking):
    values = world / "values.json"
    values.write_text(json.dumps({"sharpness": 3.0}))
    assert (
        train(world, "--family", "fake", "--values", str(values), "--seed", "5")
        == 0
    )
    source = json.loads(
        (
            only(world / "reports" / "fake" / "training") / "source.json"
        ).read_text()
    )
    assert source["explorationRunId"] is None and source["candidate"] is None
    assert source["hyperparameters"] == {"sharpness": 3.0}
    assert source["seed"] == 5


def test_a_chosen_candidate(world, ticking):
    run = explore(world)
    assert train(world, run.name, "--candidate", "3") == 0
    source = json.loads(
        (
            only(world / "reports" / "fake" / "training") / "source.json"
        ).read_text()
    )
    assert source["candidate"] == 3
    assert source["hyperparameters"] == {"sharpness": 50.0}


def test_clear_errors(world, ticking, capsys):
    run = explore(world)
    capsys.readouterr()
    assert train(world, run.name, "--candidate", "9") == 1
    assert "candidate 9" in capsys.readouterr().err
    assert train(world, "no-such-run") == 1
    assert "no-such-run" in capsys.readouterr().err
    values = world / "values.json"
    values.write_text("{}")
    assert train(world, "--family", "nope", "--values", str(values)) == 1
    assert "nope" in capsys.readouterr().err
    assert train(world) == 1
    assert train(world, run.name, "--values", str(values)) == 1
    assert train(world, "--values", str(values)) == 1  # needs --family
    values.write_text(json.dumps({"sharpness": 5000}))
    assert train(world, "--family", "fake", "--values", str(values)) == 1
    assert "sharpness" in capsys.readouterr().err
    assert not (world / "models").exists()
