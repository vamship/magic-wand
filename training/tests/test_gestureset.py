import json
from collections import Counter

import numpy as np
import pytest

from wand_core.testing.datasets import write_synthetic_dataset
from wand_train.data import builder, gestureset
from wand_train.data.format import INFO_FILE, TrainingDataError


@pytest.fixture(scope="module")
def everything(tmp_path_factory):
    root = tmp_path_factory.mktemp("sets")
    write_synthetic_dataset(
        root / "data" / "ann", authors=("ann", "bob"), samples_per_shape=7
    )
    output = root / "training-data"
    builder.build([root / "data" / "ann"], output, root=root)
    return gestureset.load(output), output


@pytest.fixture
def full(everything):
    return everything[0]


def test_load_covers_every_row(full):
    assert len(full) > 0
    assert full.gestures.shape == (len(full), 190)
    counts = full.counts()
    assert sum(counts["label"].values()) == len(full)
    assert set(counts["author"]) == {"ann", "bob"}


def test_unknown_format_version_is_refused(everything, tmp_path):
    _, output = everything
    import shutil

    copy = tmp_path / "td"
    shutil.copytree(output, copy)
    info = json.loads((copy / INFO_FILE).read_text())
    info["formatVersion"] = 9
    (copy / INFO_FILE).write_text(json.dumps(info))
    with pytest.raises(TrainingDataError):
        gestureset.load(copy)


def test_select_by_value_and_list(full):
    one = full.select(author="ann")
    assert set(one.column("author")) == {"ann"}
    two = full.select(label=["circle", "line"])
    assert set(two.labels) == {"circle", "line"}
    both = full.select(author="ann", label="zigzag")
    assert set(both.labels) == {"zigzag"} and set(both.column("author")) == {
        "ann"
    }
    assert len(full.select(author="nobody")) == 0
    with pytest.raises(KeyError):
        full.select(colour="red")


def test_shuffle_is_deterministic_per_seed(full):
    first = full.shuffle(1).rows
    assert np.array_equal(first, full.shuffle(1).rows)
    assert not np.array_equal(first, full.shuffle(2).rows)
    assert sorted(first) == sorted(full.rows)


def test_split_partitions_and_is_deterministic(full):
    parts = full.split([0.6, 0.2, 0.2], seed=3)
    union = np.concatenate([part.rows for part in parts])
    assert len(union) == len(set(union)) == len(full)
    assert sorted(union) == sorted(full.rows)
    again = full.split([0.6, 0.2, 0.2], seed=3)
    assert all(np.array_equal(a.rows, b.rows) for a, b in zip(parts, again))
    other = full.split([0.6, 0.2, 0.2], seed=4)
    assert not np.array_equal(parts[0].rows, other[0].rows)


@pytest.mark.parametrize("fractions", [[0.8, 0.2], [0.5, 0.25, 0.25]])
def test_stratified_shares_are_within_one_row(full, fractions):
    parts = full.split(fractions, seed=5)
    totals = Counter(full.labels)
    for fraction, part in zip(fractions, parts):
        got = Counter(part.labels)
        for label, total in totals.items():
            assert abs(got[label] - fraction * total) <= 1


def test_unstratified_split_and_bad_fractions(full):
    parts = full.split([0.7, 0.3], seed=1, stratify=False)
    assert sum(len(part) for part in parts) == len(full)
    for bad in ([0.5, 0.4], [1.2, -0.2], []):
        with pytest.raises(ValueError):
            full.split(bad, seed=1)


def test_select_then_split_keeps_only_the_selected(full):
    chosen = full.select(author="bob")
    for part in chosen.split([0.5, 0.5], seed=2):
        assert set(part.column("author")) == {"bob"}


def test_concat_joins_the_folds(full):
    first, second = full.split([0.5, 0.5], seed=1)
    joined = gestureset.GestureSet.concat([first, second])
    assert sorted(joined.rows) == sorted(full.rows)
    with pytest.raises(ValueError):
        gestureset.GestureSet.concat([])


def test_batches_cover_every_row_once(full):
    batches = list(full.batches(10))
    assert sum(len(labels) for _, labels in batches) == len(full)
    assert all(len(labels) == 10 for _, labels in batches[:-1])
    assert len(batches[-1][1]) <= 10
    stacked = np.vstack([gestures for gestures, _ in batches])
    np.testing.assert_array_equal(stacked, full.gestures)
    assert batches[0][0].shape[1] == 190


def test_raw_positions_of_a_row(full):
    raw = full.raw(0)
    assert raw.sample_id == full.sample_ids[0]
    assert len(raw.time_s) == len(raw.horizontal) == len(raw.vertical)
    assert raw.frame_size == (640, 480)


def test_views_share_the_table(full):
    view = full.select(author="ann").shuffle(1)
    first, _ = full.split([0.5, 0.5], seed=1)
    assert view._loaded is full._loaded and first._loaded is full._loaded
    assert view._loaded.gestures is full._loaded.gestures
    assert np.shares_memory(view._loaded.gestures, first._loaded.gestures)


def test_default_train_test_split_is_80_20(full):
    training, test = full.train_test_split(seed=42)
    assert len(training) + len(test) == len(full)
    assert abs(len(test) - 0.2 * len(full)) <= len(set(full.labels))
    assert set(training.sample_ids).isdisjoint(test.sample_ids)
    again, _ = full.train_test_split(seed=42)
    assert np.array_equal(training.rows, again.rows)
    with pytest.raises(ValueError):
        full.train_test_split(fraction=1.5)
