import json
from datetime import datetime, timedelta, timezone

import pytest

from wand_collect.cli import main
from wand_core.dataset import (
    DatasetStore,
    Handedness,
    PositionColumns,
    SampleFilter,
    SampleRecord,
    SampleStatus,
    export_samples,
    load_samples,
)


def test_help_prints_usage(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])
    assert exit_info.value.code == 0
    assert "usage: wand-collect" in capsys.readouterr().out


# --- export, merge and check --------------------------------------------------

TZ = timezone(timedelta(hours=-4))


def make_folder(path, author="ada", labels=("spell_one", "spell_two")):
    clock = [datetime(2026, 11, 1, 16, 0, tzinfo=TZ)]

    def tick():
        clock[0] += timedelta(minutes=1)
        return clock[0]

    store = DatasetStore.open(path, create=True, clock=tick)
    session = store.create_session(author, Handedness.RIGHT)
    for i, label in enumerate(labels):
        now = tick()
        store.add_sample(
            SampleRecord(
                sample_id=store.new_sample_id(session.session_id),
                session_id=session.session_id,
                captured_at=now,
                updated_at=now,
                label=label,
                status=SampleStatus.ACCEPTED
                if i % 2 == 0
                else SampleStatus.REJECTED,
                handedness=Handedness.RIGHT,
                frame_size=(640, 480),
                positions=PositionColumns(
                    time_s=[0.0, 0.1],
                    horizontal=[0.1, 0.2],
                    vertical=[0.3, 0.4],
                ),
            )
        )
    return path


@pytest.fixture(autouse=True)
def no_camera_or_server(monkeypatch):
    """None of these commands may start the server or open a camera."""
    import wand_collect.cli as cli

    def forbidden(*args, **kwargs):
        raise AssertionError("the server or a camera was started")

    monkeypatch.setattr(cli.uvicorn, "run", forbidden)
    monkeypatch.setattr(cli, "build_application", forbidden)


def test_export_matches_the_library(tmp_path, capsys):
    folder = make_folder(tmp_path / "data")
    out = tmp_path / "e.jsonl"
    assert main(["export", str(folder), "--output", str(out)]) == 0
    assert "Wrote 2 samples" in capsys.readouterr().out
    expected = tmp_path / "expected.jsonl"
    export_samples([folder], expected)
    assert out.read_text() == expected.read_text()


def test_export_filters(tmp_path, capsys):
    folder = make_folder(tmp_path / "data")
    other = make_folder(tmp_path / "other", author="bob")
    out = tmp_path / "e.jsonl"
    code = main(
        [
            "export",
            str(folder),
            str(other),
            "-o",
            str(out),
            "--status",
            "accepted",
            "--author",
            "bob",
            "--label",
            "spell_one",
            "--from",
            "2026-11-01",
            "--to",
            "2026-11-01",
        ]
    )
    assert code == 0
    lines = out.read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["session"]["author"] == "bob"
    assert load_samples(out) == load_samples(
        other, SampleFilter(status=SampleStatus.ACCEPTED, label="spell_one")
    )


def test_export_with_a_missing_folder_is_a_clear_failure(tmp_path, capsys):
    code = main(["export", str(tmp_path / "nope"), "-o", str(tmp_path / "e")])
    assert code == 1
    assert "not a dataset folder" in capsys.readouterr().err


@pytest.mark.parametrize(
    "args",
    [
        ["export", "x"],  # no --output
        ["export", "x", "-o", "y", "--status", "maybe"],
        ["export", "x", "-o", "y", "--from", "yesterday"],
        ["merge", "x"],  # no --target
        ["merge", "x", "-t", "y", "--on-conflict", "overwrite"],
        ["check"],
    ],
)
def test_bad_options_exit_with_a_message(args, capsys):
    with pytest.raises(SystemExit) as info:
        main(args)
    assert info.value.code == 2
    assert capsys.readouterr().err


def test_merge_prints_a_result_per_session(tmp_path, capsys):
    source = make_folder(tmp_path / "source")
    target = tmp_path / "target"
    assert main(["merge", str(source), "--target", str(target)]) == 0
    out = capsys.readouterr().out
    assert "copied" in out and "1 copied" in out
    assert len(load_samples(target)) == 2
    assert main(["merge", str(source), "-t", str(target)]) == 0
    assert "skipped" in capsys.readouterr().out


def test_merge_conflicts_are_reported_then_replaced(tmp_path, capsys):
    source = make_folder(tmp_path / "source")
    target = tmp_path / "target"
    main(["merge", str(source), "-t", str(target)])
    store = DatasetStore.open(target)
    session = store.list_sessions()[0]
    sample = store.read_samples(session.session_id)[0]
    store.update_sample(sample.sample_id, label="spell_three")
    capsys.readouterr()
    assert main(["merge", str(source), "-t", str(target)]) == 0
    captured = capsys.readouterr()
    assert (
        "conflict" in captured.out and "--on-conflict replace" in captured.err
    )
    assert load_samples(target)[0].label == "spell_three"
    main(["merge", str(source), "-t", str(target), "--on-conflict", "replace"])
    assert "replaced" in capsys.readouterr().out
    assert load_samples(target)[0].label == "spell_one"


def test_merge_skip_clips_and_failures(tmp_path, capsys):
    source = make_folder(tmp_path / "source")
    assert (
        main(["merge", str(source), "-t", str(tmp_path / "t"), "--skip-clips"])
        == 0
    )
    assert (
        main(["merge", str(tmp_path / "nope"), "-t", str(tmp_path / "t")]) == 1
    )
    assert "not a dataset folder" in capsys.readouterr().err
    assert main(["merge", str(source), "-t", str(source)]) == 1


def test_check_reports_and_sets_the_exit_status(tmp_path, capsys):
    config = tmp_path / "config"
    config.mkdir()
    (config / "labels.yaml").write_text(
        "labels:\n  - id: spell_one\n    name: One\n"
    )
    clean = make_folder(tmp_path / "clean", labels=("spell_one",))
    assert main(["check", str(clean), "--config", str(config)]) == 0
    assert "0 errors" in capsys.readouterr().out

    bad = make_folder(tmp_path / "bad", labels=("spell_one", "mystery"))
    assert main(["check", str(bad), "--config", str(config)]) == 1
    out = capsys.readouterr().out
    assert "unknown label" in out and "1 errors" in out

    assert main(["check", str(tmp_path / "nope"), "--config", str(config)]) == 1
    assert "no dataset.json" in capsys.readouterr().out


def test_check_without_labels_still_runs(tmp_path, capsys):
    folder = make_folder(tmp_path / "data")
    assert main(["check", str(folder), "--config", str(tmp_path)]) == 0
    assert "labels are not checked" in capsys.readouterr().err


@pytest.mark.parametrize(
    "command, options",
    [
        (
            "export",
            [
                "--output",
                "--status",
                "--label",
                "--session",
                "--author",
                "--from",
                "--to",
            ],
        ),
        ("merge", ["--target", "--on-conflict", "--skip-clips"]),
        ("check", ["--config"]),
    ],
)
def test_help_documents_every_option(command, options, capsys):
    with pytest.raises(SystemExit):
        main([command, "--help"])
    text = capsys.readouterr().out
    for option in options:
        assert option in text
