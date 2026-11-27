import csv
import json

import pytest

from wand_core.testing.datasets import write_synthetic_dataset
from wand_train import definitions
from wand_train.cli import main
from wand_train.data import builder, gestureset
from wand_train.explore import runs
from wand_train.explore.explorer import build_explorer
from wand_train.trainers.base import Hyperparameter, Trainer, TrainResult
from wand_train.trainers.fake import (
    register_fake_family,
    unregister_fake_family,
)
from wand_train.trainers.registry import register_trainer, unregister_trainer

SHARPNESS = [0.01, 1.0, 5.0, 50.0]


def definition_data(name="fake-grid", direction="max", values=SHARPNESS):
    return {
        "formatVersion": 1,
        "name": name,
        "family": "fake",
        "validation": {"scheme": "kFold", "folds": 3},
        "comparator": {
            "name": "byMetric",
            "settings": {"metric": "accuracy", "direction": direction},
        },
        "hyperparameters": {"sharpness": values},
    }


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    root = tmp_path_factory.mktemp("runs")
    write_synthetic_dataset(
        root / "data" / "ann", authors=("ann", "bob"), samples_per_shape=10
    )
    builder.build([root / "data" / "ann"], root / "training-data", root=root)
    return root


@pytest.fixture(autouse=True)
def fake_family():
    register_fake_family()
    yield
    unregister_fake_family()


def write_definition(root, data=None):
    data = data or definition_data()
    path = root / f"{data['name']}.json"
    path.write_text(json.dumps(data))
    return path


def run_cli(world, tmp_path, *extra, name="fake-grid"):
    path = write_definition(tmp_path, definition_data(name))
    reports = tmp_path / "reports"
    code = main(
        [
            "explore",
            str(path),
            "--training-data",
            str(world / "training-data"),
            "--reports",
            str(reports),
            *extra,
        ]
    )
    return code, reports


def only_run(reports):
    (folder,) = (reports / "fake" / "exploration").iterdir()
    return folder


def test_a_run_leaves_the_three_files(world, tmp_path, capsys):
    code, reports = run_cli(world, tmp_path, "--seed", "7")
    assert code == 0
    folder = only_run(reports)
    assert folder.name.endswith("-fake-grid")
    assert json.loads((folder / "definition.json").read_text()) == (
        definition_data()
    )
    info = json.loads((folder / "run.json").read_text())
    assert info["seed"] == 7 and info["testFraction"] == 0.2
    full = gestureset.load(world / "training-data")
    assert info["trainingDataFingerprint"] == full.info.fingerprint
    assert info["candidateCount"] == 4 and info["finishedAt"]
    with open(folder / "results.csv") as stream:
        rows = list(csv.DictReader(stream))
    assert list(rows[0])[:3] == ["candidate", "fold", "sharpness"]
    assert {"accuracy", "macro_f1", "log_loss", "train_seconds"} <= set(rows[0])
    assert len(rows) == 4 * 3
    assert "Stored in" in capsys.readouterr().out


def test_reloading_gives_the_same_answers(world, tmp_path, capsys):
    code, reports = run_cli(world, tmp_path)
    folder = only_run(reports)
    stored = runs.ExplorerFactory.from_run(folder)
    assert stored.complete and stored.finished_candidates == 4
    ranking = stored.ranking()
    accuracies = [r.mean["accuracy"] for r in ranking]
    assert accuracies == sorted(accuracies, reverse=True)
    assert stored.best().number == ranking[0].number
    assert [r.number for r in stored.top(2)] == [r.number for r in ranking[:2]]
    one = stored.metrics(2)
    assert len(one.fold_metrics) == 3
    assert one.hyperparameters == {"sharpness": 1.0}
    effect = dict(stored.effect("sharpness", "accuracy"))
    assert set(effect) == set(SHARPNESS)
    assert effect[1.0] == pytest.approx(stored.metrics(2).mean["accuracy"])
    # What the command printed at the end matches the reloaded ranking.
    printed = capsys.readouterr().out
    assert f"{ranking[0].mean['accuracy']:.4f}" in printed


def test_a_run_ranks_like_the_explorer_that_made_it(world, tmp_path):
    full = gestureset.load(world / "training-data")
    training, _ = full.train_test_split(0.2, 42)
    explorer = build_explorer(definitions.parse(definition_data()))
    ranked = explorer.explore(training, 42)
    _, reports = run_cli(world, tmp_path)
    stored = runs.ExplorerFactory.from_run(only_run(reports))
    assert [r.number for r in stored.ranking()] == [r.number for r in ranked]
    for stored_result, result in zip(stored.ranking(), ranked):
        for name in ("accuracy", "macro_f1", "log_loss"):
            assert stored_result.mean[name] == pytest.approx(result.mean[name])
            assert stored_result.std[name] == pytest.approx(result.std[name])


def test_a_changed_comparator_reranks_the_stored_results(world, tmp_path):
    _, reports = run_cli(world, tmp_path)
    folder = only_run(reports)
    before = runs.ExplorerFactory.from_run(folder).ranking()
    data = json.loads((folder / "definition.json").read_text())
    data["comparator"]["settings"]["direction"] = "min"
    (folder / "definition.json").write_text(json.dumps(data))
    after = runs.ExplorerFactory.from_run(folder).ranking()
    assert after[0].mean["accuracy"] == min(r.mean["accuracy"] for r in before)


def test_a_second_run_never_overwrites_the_first(world, tmp_path):
    explorer = build_explorer(definitions.parse(definition_data()))
    reports = tmp_path / "reports"
    runs.RunWriter.start(
        reports, explorer, definition_data(), 1, 0.2, "x", run_id="fixed"
    ).close()
    marker = reports / "fake" / "exploration" / "fixed" / "marker"
    marker.write_text("keep")
    with pytest.raises(runs.RunExistsError):
        runs.RunWriter.start(
            reports, explorer, definition_data(), 1, 0.2, "x", run_id="fixed"
        )
    assert marker.read_text() == "keep"


def test_an_invalid_definition_stops_before_training(world, tmp_path, capsys):
    data = definition_data(values=[1.0, 5000.0])
    path = write_definition(tmp_path, data)
    code = main(
        [
            "explore",
            str(path),
            "--training-data",
            str(world / "training-data"),
            "--reports",
            str(tmp_path / "reports"),
        ]
    )
    assert code == 1
    err = capsys.readouterr().err
    assert "sharpness" in err and "candidate 2" in err
    assert not (tmp_path / "reports").exists()  # no run was started
    bad = tmp_path / "other.json"
    bad.write_text(json.dumps({**data, "colour": "red"}))
    assert main(["explore", str(bad)]) == 1


class Dies(Trainer):
    """Raises on its third candidate, as a killed run would."""

    family = "dies"
    hyperparameter_specs = (Hyperparameter("a", "float", 1.0, minimum=0),)

    def fit(self, *args):
        raise NotImplementedError

    def predict_probabilities(self, features):
        raise NotImplementedError

    def write_model(self, folder):
        raise NotImplementedError

    def train(
        self,
        training_set,
        evaluation_set,
        hyperparameters=None,
        seed=42,
        with_predictions=False,
    ):
        values = self.validate(hyperparameters)
        if values["a"] >= 3:
            raise KeyboardInterrupt
        return TrainResult(
            {"accuracy": values["a"] / 10, "log_loss": 1.0}, values, ()
        )


def test_an_interrupted_run_keeps_what_finished(world, tmp_path, capsys):
    register_trainer(Dies)
    try:
        data = {
            **definition_data(),
            "family": "dies",
            "hyperparameters": {"a": [1, 2, 3, 4]},
        }
        data["name"] = "dies"
        (tmp_path / "dies.json").write_text(json.dumps(data))
        reports = tmp_path / "reports"
        with pytest.raises(KeyboardInterrupt):
            main(
                [
                    "explore",
                    str(tmp_path / "dies.json"),
                    "--training-data",
                    str(world / "training-data"),
                    "--reports",
                    str(reports),
                ]
            )
        folder = next((reports / "dies" / "exploration").iterdir())
        stored = runs.ExplorerFactory.from_run(folder)
        assert not stored.complete
        assert stored.finished_candidates == 2
        assert [r.number for r in stored.ranking()] == [2, 1]
        assert (
            json.loads((folder / "run.json").read_text())["finishedAt"] is None
        )
        capsys.readouterr()
        assert main(["show", str(folder)]) == 0
        assert "incomplete" in capsys.readouterr().out
    finally:
        unregister_trainer("dies")


def test_a_partly_written_candidate_is_left_out(world, tmp_path):
    _, reports = run_cli(world, tmp_path)
    folder = only_run(reports)
    lines = (folder / "results.csv").read_text().splitlines()
    (folder / "results.csv").write_text("\n".join(lines[:-1]) + "\n")
    stored = runs.ExplorerFactory.from_run(folder)
    assert stored.finished_candidates == 3 and not stored.complete


def test_show_by_run_id_with_top_and_effect(world, tmp_path, capsys):
    _, reports = run_cli(world, tmp_path)
    run_id = only_run(reports).name
    capsys.readouterr()
    code = main(
        [
            "show",
            run_id,
            "--reports",
            str(reports),
            "--top",
            "2",
            "--effect",
            "sharpness",
            "--metric",
            "accuracy",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "4 of 4 candidates finished" in out
    assert out.count("{'sharpness'") == 2
    for value in SHARPNESS:
        assert f"  {value!s:<12}" in out
    assert main(["show", "no-such-run", "--reports", str(reports)]) == 1


def test_explore_does_not_touch_the_test_set(world, tmp_path, monkeypatch):
    full = gestureset.load(world / "training-data")
    _, test = full.train_test_split(0.2, 42)
    seen = []
    original = gestureset.GestureSet.gestures.fget

    def spy(self):
        seen.append(set(self.rows))
        return original(self)

    monkeypatch.setattr(gestureset.GestureSet, "gestures", property(spy))
    run_cli(world, tmp_path)
    assert seen
    assert all(rows.isdisjoint(test.rows) for rows in seen)
