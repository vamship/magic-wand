import json
import re
import shutil
from datetime import datetime, timedelta

import pandas as pd
import pytest

from wand_core.testing.datasets import write_synthetic_dataset
from wand_train import models
from wand_train.cli import main
from wand_train.data import builder
from wand_train.reports import exploration, index, training
from wand_train.trainers.fake import (
    register_fake_family,
    unregister_fake_family,
)

CLOCK = datetime(2026, 12, 1, 9, 0, 0).astimezone()
LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


@pytest.fixture(autouse=True)
def fake_family():
    register_fake_family()
    yield
    unregister_fake_family()


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    root = tmp_path_factory.mktemp("reports-world")
    write_synthetic_dataset(
        root / "data" / "ann", authors=("ann", "bob"), samples_per_shape=10
    )
    builder.build([root / "data" / "ann"], root / "training-data", root=root)
    return root


@pytest.fixture
def ticking(monkeypatch):
    state = {"moment": CLOCK}

    def tick():
        state["moment"] += timedelta(seconds=1)
        return state["moment"]

    monkeypatch.setattr(models, "now", tick)


def definition(name="fake-grid", scheme=None):
    return {
        "formatVersion": 1,
        "name": name,
        "family": "fake",
        "validation": scheme or {"scheme": "kFold", "folds": 3},
        "comparator": {
            "name": "byMetric",
            "settings": {"metric": "accuracy", "direction": "max"},
        },
        "hyperparameters": {"sharpness": [0.5, 5.0, 50.0]},
    }


def explore(world, reports, name="fake-grid", scheme=None):
    path = world / f"{name}.json"
    path.write_text(json.dumps(definition(name, scheme)))
    code = main(
        [
            "explore",
            str(path),
            "--training-data",
            str(world / "training-data"),
            "--reports",
            str(reports),
        ]
    )
    assert code == 0
    return sorted((reports / "fake" / "exploration").iterdir())[-1]


def train(world, reports, models_folder, run):
    code = main(
        [
            "train",
            run.name,
            "--training-data",
            str(world / "training-data"),
            "--reports",
            str(reports),
            "--models",
            str(models_folder),
        ]
    )
    assert code == 0
    return sorted((reports / "fake" / "training").iterdir())[-1]


@pytest.fixture
def made(world, tmp_path, ticking):
    """An exploration, a model trained from it, and their reports."""
    reports = tmp_path / "reports"
    run = explore(world, reports)
    model = train(world, reports, tmp_path / "models", run)
    return reports, run, model


def links(report):
    return LINK.findall(report.read_text(encoding="utf-8"))


def test_explore_and_train_write_reports_figures_and_index(made):
    reports, run, model = made
    for path in (
        run / "report.md",
        model / "report.md",
        reports / "index.md",
        run / "figures" / "effect-sharpness.png",
        model / "figures" / "rates-against-threshold.png",
        model / "figures" / "rejection-roc.png",
    ):
        assert path.is_file(), path


def test_every_relative_link_points_to_a_file(made):
    reports, run, model = made
    for report in (
        run / "report.md",
        model / "report.md",
        reports / "index.md",
    ):
        found = links(report)
        assert found
        for target in found:
            assert (report.parent / target).resolve().is_file(), target


def test_the_exploration_report_ranks_the_candidates(made):
    _, run, _ = made
    text = (run / "report.md").read_text(encoding="utf-8")
    assert "by accuracy" in text
    assert "k-fold, 3 folds" in text
    fingerprint = json.loads((run / "run.json").read_text())[
        "trainingDataFingerprint"
    ]
    assert fingerprint in text
    rows = [
        line
        for line in text.splitlines()
        if re.match(r"\| \d+ \| \d+ \|", line)
    ]
    assert len(rows) == 3
    stored = exploration.runs.ExplorerFactory.from_run(run)
    ranked = stored.ranking()
    assert [int(row.split("|")[2]) for row in rows] == [
        r.number for r in ranked
    ]
    header = next(
        line for line in text.splitlines() if line.startswith("| Rank")
    )
    for column in (
        "sharpness",
        "accuracy mean",
        "accuracy std",
        "macro_f1 mean",
    ):
        assert column in header


def test_no_chart_for_a_hyperparameter_with_one_value(world, tmp_path):
    reports = tmp_path / "reports"
    data = definition("one")
    data["hyperparameters"] = {"sharpness": [5.0]}
    path = world / "one.json"
    path.write_text(json.dumps(data))
    assert (
        main(
            [
                "explore",
                str(path),
                "--training-data",
                str(world / "training-data"),
                "--reports",
                str(reports),
            ]
        )
        == 0
    )
    (run,) = (reports / "fake" / "exploration").iterdir()
    assert (
        not list((run / "figures").glob("*.png"))
        if (run / "figures").exists()
        else True
    )
    assert "Effect of each hyperparameter" not in (run / "report.md").read_text(
        encoding="utf-8"
    )


def test_the_training_report_shows_every_item(made):
    _, run, model = made
    text = (model / "report.md").read_text(encoding="utf-8")
    source = json.loads((model / "source.json").read_text())
    for expected in (
        model.name,
        run.name,
        "candidate",
        str(source["seed"]),
        source["trainingDataFingerprint"],
        "Training gestures",
        "Test gestures",
        "Hyperparameters",
        "sharpness",
        "Accuracy",
        "Macro F1",
        "Log loss",
        "Mean label AUC",
        "Rejection AUC",
        "## Label AUC",
        "| circle |",
        "| line |",
        "| zigzag |",
        "## Precision and recall",
        "## Confusion matrix",
        "correct \\ predicted",
        "## Timing",
        "95th percentile",
        "rates-against-threshold.png",
        "rejection-roc.png",
        "Training chooses no threshold",
    ):
        assert expected in text, expected


def test_the_training_report_links_to_the_exploration_report(made):
    _, run, model = made
    assert "../../exploration/" + run.name + "/report.md" in (
        model / "report.md"
    ).read_text(encoding="utf-8")


def test_the_confusion_matrix_in_the_report_matches_the_files(made):
    _, _, model = made
    stored = training.read_metrics(model / "metrics.csv")
    predictions = pd.read_parquet(model / "predictions.parquet")
    spell = predictions[predictions["kind"] == "spell"]
    assert int(stored.confusion.to_numpy().sum()) == len(spell)
    assert stored.measures["accuracy"] == pytest.approx(
        (spell["correctLabel"] == spell["predictedLabel"]).mean()
    )


def test_the_index_lists_explorations_and_models_by_family(made):
    reports, run, model = made
    text = (reports / "index.md").read_text(encoding="utf-8")
    assert "## fake" in text
    assert f"[{run.name}](fake/exploration/{run.name}/report.md)" in text
    assert f"[{model.name}](fake/training/{model.name}/report.md)" in text
    assert "2026-12-01" in text
    assert re.search(r"accuracy \d\.\d{4}", text)
    assert "Rejection AUC" in text


def test_the_index_follows_new_runs_and_deleted_folders(
    world, tmp_path, ticking
):
    reports = tmp_path / "reports"
    first = explore(world, reports)
    second = explore(world, reports, "fake-grid-two", {"scheme": "singleSplit"})
    text = (reports / "index.md").read_text(encoding="utf-8")
    assert f"exploration/{first.name}/" in text
    assert f"exploration/{second.name}/" in text

    shutil.rmtree(first)
    assert main(["index", "--reports", str(reports)]) == 0
    text = (reports / "index.md").read_text(encoding="utf-8")
    assert f"exploration/{first.name}/" not in text
    assert f"exploration/{second.name}/" in text


def test_a_model_stays_in_the_index_when_its_run_is_deleted(made):
    reports, run, model = made
    shutil.rmtree(run)
    index.write(reports)
    text = (reports / "index.md").read_text(encoding="utf-8")
    assert run.name not in text
    assert model.name in text
    training.write(model)  # still works from its own files
    assert "../../exploration" not in (model / "report.md").read_text(
        encoding="utf-8"
    )


def test_an_empty_reports_folder_gets_an_index(tmp_path):
    reports = tmp_path / "reports"
    assert main(["index", "--reports", str(reports)]) == 0
    assert "No explorations or models yet" in (reports / "index.md").read_text(
        encoding="utf-8"
    )


def test_reports_are_rebuilt_from_stored_files_alone(made, monkeypatch):
    reports, run, model = made
    before = (model / "report.md").read_text(encoding="utf-8")
    # Training must not be needed: break it, then rebuild everything.
    monkeypatch.setattr(
        "wand_train.trainers.base.Trainer.train",
        lambda *a, **k: pytest.fail("trained"),
    )
    (model / "report.md").unlink()
    (run / "report.md").unlink()
    exploration.write(run)
    training.write(model)
    assert (model / "report.md").read_text(encoding="utf-8") == before


def test_a_model_trained_from_values_has_no_run_to_link(
    world, tmp_path, ticking
):
    reports = tmp_path / "reports"
    values = tmp_path / "values.json"
    values.write_text(json.dumps({"sharpness": 5.0}))
    code = main(
        [
            "train",
            "--family",
            "fake",
            "--values",
            str(values),
            "--training-data",
            str(world / "training-data"),
            "--reports",
            str(reports),
            "--models",
            str(tmp_path / "models"),
        ]
    )
    assert code == 0
    (model,) = (reports / "fake" / "training").iterdir()
    text = (model / "report.md").read_text(encoding="utf-8")
    assert "given directly" in text


def test_a_failing_report_keeps_the_results_and_says_so(
    world, tmp_path, monkeypatch, capsys
):
    def broken(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(
        "wand_train.cli.report_writer.write_exploration_report", broken
    )
    path = world / "fake-grid.json"
    path.write_text(json.dumps(definition()))
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
    assert "disk full" in capsys.readouterr().err
    (run,) = (tmp_path / "reports" / "fake" / "exploration").iterdir()
    assert (run / "results.csv").is_file()
