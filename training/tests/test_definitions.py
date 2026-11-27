import copy
import json

import numpy as np
import pytest

from wand_train import definitions
from wand_train.definitions import DefinitionError, Range
from wand_train.explore.enumerate import (
    candidate_count,
    check_against_trainer,
    enumerate_candidates,
    range_values,
)
from wand_train.trainers.base import HyperparameterError
from wand_train.trainers.fake import FakeTrainer

SVM = {
    "formatVersion": 1,
    "name": "svm-coarse",
    "family": "svm",
    "validation": {"scheme": "kFold", "folds": 5},
    "comparator": {
        "name": "byMetric",
        "settings": {"metric": "accuracy", "direction": "max"},
    },
    "hyperparameters": {
        "kernel": ["rbf"],
        "c": {"min": 0.1, "max": 100, "count": 4, "type": "log"},
        "gamma": ["scale", "auto"],
    },
}

MLP = {
    "formatVersion": 1,
    "name": "mlp-grid",
    "family": "mlp",
    "validation": {"scheme": "singleSplit"},
    "comparator": {"name": "byMetric"},
    "hyperparameters": {
        "hiddenLayers": [1, 2, 3],
        "hiddenUnits": [100, 120, 150],
        "learningRate": {"min": 0.0001, "max": 0.01, "count": 5, "type": "log"},
    },
}


def write(tmp_path, data, name=None):
    path = tmp_path / f"{name or data['name']}.json"
    path.write_text(json.dumps(data))
    return path


def changed(base, *path, value):
    data = copy.deepcopy(base)
    target = data
    for key in path[:-1]:
        target = target[key]
    if value is KeyError:
        del target[path[-1]]
    else:
        target[path[-1]] = value
    return data


def test_the_examples_load(tmp_path):
    svm = definitions.load(write(tmp_path, SVM))
    assert svm.family == "svm" and svm.validation.folds == 5
    assert svm.comparator.settings == {"metric": "accuracy", "direction": "max"}
    assert len(enumerate_candidates(svm)) == 1 * 4 * 2
    mlp = definitions.load(write(tmp_path, MLP))
    assert list(mlp.hyperparameters) == [
        "hidden_layers",
        "hidden_units",
        "learning_rate",
    ]
    assert mlp.validation.scheme == "singleSplit"
    assert mlp.validation.fraction == 0.2 and mlp.validation.folds == 5
    assert mlp.comparator.settings == {}
    assert candidate_count(mlp) == 45
    assert len(enumerate_candidates(mlp)) == 45


def test_range_values():
    assert range_values(Range(0, 10, 5, "linear")) == [0, 2.5, 5, 7.5, 10]
    log = range_values(Range(0.1, 100, 4, "log"))
    np.testing.assert_allclose(log, [0.1, 1, 10, 100])
    assert log[0] == 0.1 and log[-1] == 100
    assert range_values(Range(3, 9, 1, "linear")) == [3.0]
    assert range_values(Range(1, 10, 4, "linear", integer=True)) == [
        1,
        4,
        7,
        10,
    ]
    # 1, 1.5, 2, 2.5 round half up to 1, 2, 2, 3 -> duplicates removed.
    assert range_values(Range(1, 2.5, 4, "linear", integer=True)) == [1, 2, 3]
    assert all(
        isinstance(value, int)
        for value in range_values(Range(1, 10, 4, "linear", integer=True))
    )


def test_enumeration_order_and_repeatability(tmp_path):
    definition = definitions.parse(
        {
            **SVM,
            "hyperparameters": {
                "a": [1, 2],
                "b": ["x", "y", "z"],
                "c": [True, False],
            },
        },
        expected_name="svm-coarse",
    )
    candidates = enumerate_candidates(definition)
    assert len(candidates) == 12
    assert candidates[0] == {"a": 1, "b": "x", "c": True}
    assert candidates[1] == {"a": 1, "b": "x", "c": False}  # last is fastest
    assert candidates[2] == {"a": 1, "b": "y", "c": True}
    assert candidates[-1] == {"a": 2, "b": "z", "c": False}
    assert candidates == enumerate_candidates(definition)


def test_no_hyperparameters_gives_one_empty_candidate():
    definition = definitions.parse({**SVM, "hyperparameters": {}})
    assert enumerate_candidates(definition) == [{}]


INVALID = {
    "unknown top-level key": (changed(SVM, "colour", value="red"), "colour"),
    "unknown nested key": (
        changed(SVM, "validation", "shuffle", value=True),
        "shuffle",
    ),
    "unknown range key": (
        changed(SVM, "hyperparameters", "c", "step", value=1),
        "step",
    ),
    "missing family": (changed(SVM, "family", value=KeyError), "family"),
    "missing comparator": (
        changed(SVM, "comparator", value=KeyError),
        "comparator",
    ),
    "missing comparator name": (
        changed(SVM, "comparator", "name", value=KeyError),
        "name",
    ),
    "wrong format version": (
        changed(SVM, "formatVersion", value=2),
        "formatVersion",
    ),
    "bad scheme": (
        changed(SVM, "validation", "scheme", value="loo"),
        "validation.scheme",
    ),
    "folds below 2": (
        changed(SVM, "validation", "folds", value=1),
        "validation.folds",
    ),
    "fraction of zero": (
        changed(SVM, "validation", "fraction", value=0),
        "validation.fraction",
    ),
    "fraction of one": (
        changed(SVM, "validation", "fraction", value=1),
        "validation.fraction",
    ),
    "min above max": (
        changed(SVM, "hyperparameters", "c", "min", value=500),
        "hyperparameters.c",
    ),
    "count below 1": (
        changed(SVM, "hyperparameters", "c", "count", value=0),
        "hyperparameters.c.count",
    ),
    "log range from zero": (
        changed(SVM, "hyperparameters", "c", "min", value=0),
        "hyperparameters.c.min",
    ),
    "bad range type": (
        changed(SVM, "hyperparameters", "c", "type", value="exp"),
        "hyperparameters.c.type",
    ),
    "range without count": (
        changed(SVM, "hyperparameters", "c", "count", value=KeyError),
        "count",
    ),
    "empty list": (
        changed(SVM, "hyperparameters", "kernel", value=[]),
        "hyperparameters.kernel",
    ),
    "scalar entry": (
        changed(SVM, "hyperparameters", "kernel", value="rbf"),
        "hyperparameters.kernel",
    ),
}


@pytest.mark.parametrize("case", list(INVALID))
def test_invalid_definitions_name_the_key(case):
    data, key = INVALID[case]
    with pytest.raises(DefinitionError, match=key):
        definitions.parse(data)


def test_name_must_match_the_file_name(tmp_path):
    path = write(tmp_path, SVM, name="other")
    with pytest.raises(DefinitionError, match="file name"):
        definitions.load(path)


def test_unreadable_and_malformed_files(tmp_path):
    with pytest.raises(DefinitionError):
        definitions.load(tmp_path / "missing.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{nope")
    with pytest.raises(DefinitionError, match="JSON"):
        definitions.load(bad)


def test_hyperparameters_are_checked_against_the_trainer():
    ok = definitions.parse(
        {**SVM, "hyperparameters": {"sharpness": [1.0, 2.0]}}
    )
    check_against_trainer(ok, FakeTrainer())
    unknown = definitions.parse({**SVM, "hyperparameters": {"depth": [1]}})
    with pytest.raises(HyperparameterError, match="depth"):
        check_against_trainer(unknown, FakeTrainer())
    out_of_range = definitions.parse(
        {**SVM, "hyperparameters": {"sharpness": [1.0, 5000.0]}}
    )
    with pytest.raises(HyperparameterError, match="sharpness"):
        check_against_trainer(out_of_range, FakeTrainer())
