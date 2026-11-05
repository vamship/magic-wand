import json
from datetime import datetime, timedelta, timezone

import pytest

from wand_core.dataset import (
    DatasetError,
    DatasetStore,
    Handedness,
    PositionColumns,
    SampleFilter,
    SampleRecord,
    SampleStatus,
    VideoRecord,
    check_folder,
    export_samples,
    load_samples,
)
from wand_core.dataset.check import Level
from wand_core.dataset.fileio import NotADatasetError

TZ = timezone(timedelta(hours=-4))


class Clock:
    def __init__(self):
        self.now = datetime(2026, 11, 1, 16, 0, 0, tzinfo=TZ)

    def __call__(self):
        self.now += timedelta(minutes=1)
        return self.now


def add(store, session, label="circle", status="accepted", clip=False):
    sample_id = store.new_sample_id(session.session_id)
    video = None
    if clip:
        store.clip_path(sample_id).write_bytes(b"video")
        video = VideoRecord(
            file=store.clip_reference(sample_id), gesture_start_s=1.0
        )
    now = store._clock()
    return store.add_sample(
        SampleRecord(
            sample_id=sample_id,
            session_id=session.session_id,
            captured_at=now,
            updated_at=now,
            label=label,
            status=SampleStatus(status),
            handedness=session.handedness,
            frame_size=(640, 480),
            positions=PositionColumns(
                time_s=[0.0, 0.1], horizontal=[0.4, 0.5], vertical=[0.5, 0.6]
            ),
            video=video,
        )
    )


@pytest.fixture
def folder(tmp_path):
    return tmp_path / "data"


@pytest.fixture
def store(folder):
    return DatasetStore.open(folder, create=True, clock=Clock())


@pytest.fixture
def filled(store):
    ada = store.create_session("ada", Handedness.RIGHT, name="one")
    bob = store.create_session("bob", Handedness.LEFT, name="two")
    for label, status in [("circle", "accepted"), ("zigzag", "accepted"),
                          ("circle", "rejected")]:
        add(store, ada, label, status, clip=True)
    add(store, bob, "circle")
    add(store, bob, "zigzag", "rejected", clip=True)
    return store, ada, bob


# --- Check -------------------------------------------------------------------


def test_a_clean_folder_has_no_problems(folder, filled):
    report = check_folder(folder, {"circle", "zigzag"})
    assert report.ok and report.findings == []
    assert (report.sessions, report.samples) == (2, 5)


def test_each_problem_of_the_design_is_detected(folder, filled):
    store, ada, bob = filled
    ada_dir = store.session_dir(ada.session_id)
    bob_dir = store.session_dir(bob.session_id)
    # a leftover temporary file
    (ada_dir / ".session.json.abc.tmp").write_text("x")
    # an unknown label (added before the file gets a damaged tail)
    add(store, bob, "fireball")
    # an incomplete last line
    with open(bob_dir / "samples.jsonl", "ab") as handle:
        handle.write(b'{"sampleId": "half')
    # a clip with no sample
    (ada_dir / "videos" / "stray.mp4").write_bytes(b"x")
    # a sample whose clip is missing
    clips = sorted((ada_dir / "videos").glob("*-0001.mp4"))
    clips[0].unlink()

    report = check_folder(folder, {"circle", "zigzag"})
    assert report.codes() == {
        "temporary_file",
        "incomplete_last_line",
        "orphan_clip",
        "missing_clip",
        "unknown_label",
    }
    by_code = {f.code: f.level for f in report.findings}
    assert by_code["missing_clip"] is Level.INFO  # information, not an error
    assert by_code["unknown_label"] is Level.ERROR
    assert by_code["temporary_file"] is Level.WARNING
    assert not report.ok  # the unknown label is an error


def test_without_a_label_list_labels_are_not_checked(folder, filled):
    assert check_folder(folder).ok


def test_unsupported_format_versions_are_errors(folder, filled):
    store, ada, _ = filled
    path = store.session_dir(ada.session_id) / "session.json"
    data = json.loads(path.read_text())
    data["formatVersion"] = 99
    path.write_text(json.dumps(data))
    info = folder / "dataset.json"
    other = json.loads(info.read_text())
    other["formatVersion"] = 42
    info.write_text(json.dumps(other))
    report = check_folder(folder)
    assert not report.ok
    assert {f.code for f in report.errors} == {"unsupported_format"}
    assert len(report.errors) == 2


def test_a_damaged_line_in_the_middle_is_an_error(folder, filled):
    store, ada, _ = filled
    path = store.session_dir(ada.session_id) / "samples.jsonl"
    lines = path.read_text().splitlines()
    lines[0] = "{broken"
    path.write_text("\n".join(lines) + "\n")
    report = check_folder(folder)
    assert "damaged_line" in {f.code for f in report.errors}


def test_a_session_folder_with_the_wrong_name_is_an_error(folder, filled):
    store, ada, _ = filled
    old = store.session_dir(ada.session_id)
    old.rename(old.with_name("00000000-0000-4000-8000-000000000000"))
    report = check_folder(folder)
    assert "session_id_mismatch" in {f.code for f in report.errors}


def test_the_check_never_writes(folder, filled):
    store, ada, _ = filled
    (store.session_dir(ada.session_id) / "x.tmp").write_text("t")
    with open(store.session_dir(ada.session_id) / "samples.jsonl", "ab") as f:
        f.write(b"{half")

    def snapshot():
        return {
            str(p): (p.stat().st_mtime_ns, p.stat().st_size)
            for p in sorted(folder.rglob("*"))
        }

    before = snapshot()
    check_folder(folder, {"circle"})
    assert snapshot() == before


def test_not_a_dataset(tmp_path):
    report = check_folder(tmp_path / "nothing")
    assert report.codes() == {"not_a_dataset"} and not report.ok


# --- Export and load ------------------------------------------------------------


def test_export_writes_one_line_per_sample_with_the_session_and_no_video(
    folder, filled, tmp_path
):
    out = tmp_path / "export.jsonl"
    assert export_samples([folder], out) == 5
    lines = [json.loads(line) for line in out.read_text().splitlines()]
    assert len(lines) == 5
    first = lines[0]
    assert first["session"]["author"] == "ada"
    assert first["video"] is None
    assert set(first["positions"]) == {"timeS", "horizontal", "vertical"}


@pytest.mark.parametrize(
    "keep, expected",
    [
        (SampleFilter(status=SampleStatus.ACCEPTED), 3),
        (SampleFilter(label="circle"), 3),
        (SampleFilter(author="bob"), 2),
        (SampleFilter(label="circle", status=SampleStatus.ACCEPTED), 2),
        (SampleFilter(label="none"), 0),
    ],
)
def test_filters(folder, filled, tmp_path, keep, expected):
    out = tmp_path / "e.jsonl"
    assert export_samples([folder], out, keep) == expected
    assert len(load_samples(folder, keep)) == expected


def test_filter_by_session_and_dates(folder, filled, tmp_path):
    store, ada, bob = filled
    assert len(load_samples(folder, SampleFilter(session=bob.session_id))) == 2
    everything = load_samples(folder)
    times = sorted(s.captured_at for s in everything)
    window = SampleFilter(start=times[1], end=times[3])
    assert len(load_samples(folder, window)) == 3


def test_export_reads_several_folders(tmp_path, filled, folder):
    other = DatasetStore.open(tmp_path / "other", create=True, clock=Clock())
    carol = other.create_session("carol", Handedness.RIGHT)
    add(other, carol)
    out = tmp_path / "both.jsonl"
    assert export_samples([folder, tmp_path / "other"], out) == 6
    assert len(load_samples(out)) == 6
    assert len(load_samples([folder, tmp_path / "other"])) == 6


def test_loading_an_export_matches_loading_the_folders(folder, filled, tmp_path):
    out = tmp_path / "e.jsonl"
    keep = SampleFilter(status=SampleStatus.ACCEPTED)
    export_samples([folder], out, keep)
    assert load_samples(out, keep) == load_samples(folder, keep)
    assert load_samples(out) == load_samples(folder, keep)  # already filtered
    export_samples([folder], out)
    assert load_samples(out, SampleFilter(label="zigzag")) == load_samples(
        folder, SampleFilter(label="zigzag")
    )


def test_loaded_samples_expose_plain_data(folder, filled):
    sample = load_samples(folder)[0]
    assert sample.label == "circle" and sample.status is SampleStatus.ACCEPTED
    assert sample.handedness is Handedness.RIGHT
    assert sample.horizontal == [0.4, 0.5] and sample.time_s == [0.0, 0.1]
    assert sample.frame_size == (640, 480)
    assert sample.session.author == "ada" and sample.session.name == "one"


def test_loading_never_changes_the_folder(folder, filled):
    store, ada, _ = filled
    temp = store.session_dir(ada.session_id) / "left.tmp"
    temp.write_text("t")
    load_samples(folder)
    assert temp.exists()


def test_bad_inputs(tmp_path):
    with pytest.raises(NotADatasetError):
        load_samples(tmp_path / "missing")
    with pytest.raises(NotADatasetError):
        load_samples(tmp_path)  # a folder without dataset.json
    bad = tmp_path / "bad.jsonl"
    bad.write_text("not json\n")
    with pytest.raises(DatasetError):
        load_samples(bad)
    bad.write_text('{"sampleId": "x"}\n')
    with pytest.raises(DatasetError, match="no session"):
        load_samples(bad)
