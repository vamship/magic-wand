import json
import shutil

import numpy as np
import pandas.testing as pdt
import pytest

from wand_core import normalize
from wand_core.dataset import DatasetStore, SampleStatus, SessionConflictError
from wand_core.testing.datasets import write_synthetic_dataset
from wand_train.cli import main
from wand_train.data import builder
from wand_train.data.format import (
    COLUMNS,
    INFO_FILE,
    TrainingDataError,
    read_info,
    read_table,
)


@pytest.fixture
def data(tmp_path):
    location = tmp_path / "data"
    write_synthetic_dataset(location / "ann", authors=("ann",), seed=1)
    write_synthetic_dataset(location / "bob", authors=("bob",), seed=2)
    return location


def build(data, tmp_path, names=(), name="out"):
    folders = builder.select_datasets(data, names)
    output = tmp_path / name
    builder.build(folders, output, root=tmp_path)
    return output


def test_table_has_every_column_and_library_values(data, tmp_path):
    table = read_table(build(data, tmp_path))
    assert list(table.columns) == list(COLUMNS)
    row = table.iloc[0]
    expected = normalize.normalize(
        row.rawTimeS,
        row.rawX,
        row.rawY,
        (row.frameWidth, row.frameHeight),
    )
    assert len(row.steps) == 189
    np.testing.assert_allclose(np.append(row.steps, row.durationS), expected)
    assert set(table.author) == {"ann", "bob"}


def test_rejected_samples_are_left_out(data, tmp_path):
    table = read_table(build(data, tmp_path))
    samples = [
        sample
        for folder in data.iterdir()
        for store in [DatasetStore.open(folder)]
        for session in store.list_sessions()
        for sample in store.read_samples(session.session_id)
    ]
    total = len(samples)
    rejected = sum(s.status is SampleStatus.REJECTED for s in samples)
    assert rejected > 0
    assert len(table) == total - rejected
    assert set(table.label) == {"circle", "line", "zigzag"}


def test_rows_are_ordered_by_session_then_sample(data, tmp_path):
    table = read_table(build(data, tmp_path))
    keys = list(zip(table.sessionId, table.sampleId))
    assert keys == sorted(keys)


def test_building_twice_and_argument_order(data, tmp_path):
    first = read_table(build(data, tmp_path, ["ann", "bob"], "a"))
    second = read_table(build(data, tmp_path, ["bob", "ann"], "b"))
    third = read_table(build(data, tmp_path, [], "c"))
    for other in (second, third):
        pdt.assert_frame_equal(
            first.drop(columns=["steps", "rawTimeS", "rawX", "rawY"]),
            other.drop(columns=["steps", "rawTimeS", "rawX", "rawY"]),
        )
        np.testing.assert_array_equal(
            np.vstack(first.steps), np.vstack(other.steps)
        )


def test_info_fields_and_fingerprint(data, tmp_path):
    output = build(data, tmp_path)
    info = read_info(output)
    assert info.format_version == 1
    assert info.normalization == {"points": 64, "version": 1}
    assert info.datasets == ["data/ann", "data/bob"]
    assert info.sample_count == len(read_table(output))
    assert len(info.fingerprint) == 64
    assert info.source_commit == ""  # tmp_path is not a repository


def test_fingerprint_follows_label_and_status_not_time(data, tmp_path):
    folders = builder.select_datasets(data)
    _, lines = builder.build_table(folders)
    from wand_train.data.format import fingerprint

    base = fingerprint(lines)
    assert fingerprint(list(reversed(lines))) == base
    relabelled = [(lines[0][0], "other", lines[0][2]), *lines[1:]]
    restatused = [(lines[0][0], lines[0][1], "rejected"), *lines[1:]]
    assert fingerprint(relabelled) != base
    assert fingerprint(restatused) != base
    first = builder.build(folders, tmp_path / "x", root=tmp_path)
    second = builder.build(folders, tmp_path / "y", root=tmp_path)
    assert first.fingerprint == second.fingerprint


def test_a_session_in_two_datasets_is_used_once(data, tmp_path):
    session = next((data / "ann" / "sessions").iterdir())
    copy = data / "copy"
    shutil.copytree(data / "ann", copy)
    for other in (copy / "sessions").iterdir():
        if other.name != session.name:
            shutil.rmtree(other)
    once = read_table(build(data, tmp_path, ["ann", "bob"], "a"))
    twice = read_table(build(data, tmp_path, ["ann", "bob", "copy"], "b"))
    assert len(once) == len(twice)


def test_differing_copies_stop_the_build(data, tmp_path):
    session = next((data / "ann" / "sessions").iterdir())
    copy = data / "copy"
    shutil.copytree(data / "ann", copy)
    samples = copy / "sessions" / session.name / "samples.jsonl"
    lines = samples.read_text().splitlines()
    samples.write_text("\n".join(lines[:-1]) + "\n")
    with pytest.raises(SessionConflictError, match=session.name):
        build(data, tmp_path, ["ann", "copy"])


def test_check_matches_then_detects_a_change(data, tmp_path, capsys):
    output = build(data, tmp_path)
    args = ["training-data", "check", "--data-location", str(data)]
    assert main([*args, "--output", str(output)]) == 0
    folder = next((data / "ann" / "sessions").iterdir())
    samples = folder / "samples.jsonl"
    lines = samples.read_text().splitlines()
    first = json.loads(lines[0])
    first["label"] = "changed"
    lines[0] = json.dumps(first)
    samples.write_text("\n".join(lines) + "\n")
    assert main([*args, "--output", str(output)]) == 1
    assert "fingerprint" in capsys.readouterr().err


def test_unknown_format_version_is_refused(data, tmp_path, capsys):
    output = build(data, tmp_path)
    info = json.loads((output / INFO_FILE).read_text())
    info["formatVersion"] = 2
    (output / INFO_FILE).write_text(json.dumps(info))
    with pytest.raises(TrainingDataError):
        read_table(output)
    assert main(["training-data", "summary", "--output", str(output)]) == 1
    assert (
        main(
            ["training-data", "check", "--output", str(output)]
            + ["--data-location", str(data)]
        )
        == 1
    )


def test_summary_prints_counts(data, tmp_path, capsys):
    output = build(data, tmp_path)
    assert main(["training-data", "summary", "--output", str(output)]) == 0
    text = capsys.readouterr().out
    assert "circle" in text and "ann" in text and "bob" in text


def test_build_command(data, tmp_path, capsys):
    output = tmp_path / "built"
    code = main(
        ["training-data", "build", "ann", "--data-location", str(data)]
        + ["--output", str(output)]
    )
    assert code == 0
    assert set(read_table(output).author) == {"ann"}


def test_source_commit_in_a_repository(tmp_path):
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "x",
        ],
        cwd=tmp_path,
        check=True,
    )
    assert len(builder.short_commit(tmp_path)) >= 7
    assert builder.short_commit(tmp_path / "missing") == ""
