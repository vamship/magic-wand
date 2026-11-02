import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from wand_core.dataset import (
    DatasetError,
    DatasetInfo,
    Handedness,
    NotADatasetError,
    PositionColumns,
    SampleRecord,
    SampleStatus,
    SessionRecord,
    UnsupportedFormatError,
    VideoRecord,
    append_sample,
    fileio,
    from_disk,
    open_data_folder,
    read_samples,
    read_session,
    replace_file,
    to_disk,
    write_record,
    write_samples,
)
from wand_core.dataset.models import CameraRecord, Mode
from wand_core.settings import VisionSettings

TZ = timezone(timedelta(hours=-4))
SESSION_ID = "3f8c1d2e-9a4b-4c7e-8f10-5b6d7e8f9a0b"


def session_record(**changes):
    values = {
        "session_id": SESSION_ID,
        "name": "Vamshi evening desk",
        "author": "vamshi",
        "handedness": Handedness.RIGHT,
        "started_at": datetime(2026, 11, 1, 14, 15, 2, tzinfo=TZ),
        "notes": "desk lamp, white wall",
        "camera": CameraRecord(
            device="FaceTime HD Camera",
            index=0,
            requested=Mode(width=640, height=480, fps=30),
            actual=Mode(width=640, height=480, fps=29.8),
        ),
        "vision_settings": VisionSettings(hue_center=20),
        "highest_sample_number": 42,
        "profile": "desk-evening",
    }
    values.update(changes)
    return SessionRecord(**values)


def sample_record(number=42, **changes):
    values = {
        "sample_id": f"{SESSION_ID}-{number:04d}",
        "session_id": SESSION_ID,
        "captured_at": datetime(2026, 11, 1, 14, 15, 30, tzinfo=TZ),
        "updated_at": datetime(2026, 11, 1, 14, 15, 30, tzinfo=TZ),
        "label": "circle",
        "status": SampleStatus.ACCEPTED,
        "handedness": Handedness.RIGHT,
        "frame_size": (640, 480),
        "positions": PositionColumns(
            time_s=[0.0, 0.033, 0.066],
            horizontal=[0.41, 0.42, 0.44],
            vertical=[0.52, 0.50, 0.47],
        ),
        "video": VideoRecord(
            file=f"videos/{SESSION_ID}-{number:04d}.mp4", gesture_start_s=2.0
        ),
    }
    values.update(changes)
    return SampleRecord(**values)


# --- Records and formats ----------------------------------------------------


def test_session_and_sample_round_trip_through_disk_data(tmp_path):
    session = session_record()
    sample = sample_record()
    path = tmp_path / "session.json"
    write_record(path, session)
    assert read_session(path) == session
    samples = tmp_path / "samples.jsonl"
    append_sample(samples, sample)
    assert read_samples(samples) == [sample]


def test_keys_are_camel_case_on_disk_and_utf8(tmp_path):
    path = tmp_path / "session.json"
    write_record(path, session_record(name="Café — ünïcode ✓"))
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    assert data["sessionId"] == SESSION_ID
    assert data["formatVersion"] == 1
    assert data["highestSampleNumber"] == 42
    assert data["camera"]["requested"] == {
        "width": 640,
        "height": 480,
        "fps": 30,
    }
    assert data["visionSettings"]["hueCenter"] == 20
    assert data["clipPadding"] == {"preS": 2.0, "postS": 2.0}
    assert data["endedAt"] is None
    assert data["startedAt"] == "2026-11-01T14:15:02-04:00"
    assert "Café — ünïcode ✓" in text  # raw UTF-8, not \u escapes
    assert not any("_" in key for key in data)


def test_sample_line_is_compact_camel_case_single_line(tmp_path):
    samples = tmp_path / "samples.jsonl"
    append_sample(samples, sample_record())
    raw = samples.read_bytes()
    assert raw.endswith(b"\n")
    assert raw.count(b"\n") == 1
    data = json.loads(raw)
    assert data["sampleId"].endswith("-0042")
    assert data["frameSize"] == [640, 480]
    assert data["positions"]["timeS"] == [0.0, 0.033, 0.066]
    assert data["video"]["gestureStartS"] == 2.0
    assert data["status"] == "accepted"


def test_sample_without_video_round_trips(tmp_path):
    sample = sample_record(video=None)
    samples = tmp_path / "samples.jsonl"
    append_sample(samples, sample)
    assert json.loads(samples.read_text())["video"] is None
    assert read_samples(samples) == [sample]


def test_record_validation_names_the_problem():
    with pytest.raises(ValueError, match="slug"):
        sample_record(label="Not A Slug")
    with pytest.raises(ValueError, match="differ in length"):
        PositionColumns(time_s=[0.0], horizontal=[0.1, 0.2], vertical=[0.1])
    with pytest.raises(ValueError, match="UTC offset"):
        session_record(started_at=datetime(2026, 11, 1, 14, 15, 2))
    data = to_disk(sample_record())
    data["label"] = "Bad Label"
    with pytest.raises(DatasetError, match="label"):
        from_disk(SampleRecord, data, source="x.jsonl")
    data = to_disk(sample_record())
    data["surprise"] = 1
    with pytest.raises(DatasetError, match="surprise"):
        from_disk(SampleRecord, data)


def test_unknown_format_version_is_refused(tmp_path):
    data = to_disk(session_record())
    data["formatVersion"] = 99
    path = tmp_path / "session.json"
    path.write_text(json.dumps(data))
    with pytest.raises(UnsupportedFormatError, match="99"):
        read_session(path)
    line = to_disk(sample_record())
    line["formatVersion"] = 2
    with pytest.raises(UnsupportedFormatError):
        from_disk(SampleRecord, line)


def test_unreadable_json_gives_a_dataset_error(tmp_path):
    path = tmp_path / "session.json"
    path.write_text("{not json")
    with pytest.raises(DatasetError, match="session.json"):
        read_session(path)
    path.write_text("[1, 2]")
    with pytest.raises(DatasetError, match="JSON object"):
        read_session(path)


# --- The replace routine ----------------------------------------------------


def test_replace_flushes_file_renames_then_flushes_the_folder(
    tmp_path, monkeypatch
):
    log = []
    real_fsync, real_replace, real_open = os.fsync, os.replace, os.open
    folder_fds = set()

    def spy_open(path, *args, **kwargs):
        fd = real_open(path, *args, **kwargs)
        if Path(path) == tmp_path:
            folder_fds.add(fd)
        return fd

    def spy_fsync(fd):
        log.append("fsync-folder" if fd in folder_fds else "fsync-file")
        return real_fsync(fd)

    def spy_replace(src, dst):
        log.append("replace")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "open", spy_open)
    monkeypatch.setattr(os, "fsync", spy_fsync)
    monkeypatch.setattr(os, "replace", spy_replace)
    target = tmp_path / "file.json"
    replace_file(target, b"new")
    assert log == ["fsync-file", "replace", "fsync-folder"]
    assert target.read_bytes() == b"new"
    assert [p.name for p in tmp_path.iterdir()] == ["file.json"]


def test_a_failed_replace_leaves_the_old_file_and_no_temp_file(
    tmp_path, monkeypatch
):
    target = tmp_path / "file.json"
    target.write_bytes(b"old")

    def broken_replace(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", broken_replace)
    with pytest.raises(OSError, match="disk full"):
        replace_file(target, b"new")
    assert target.read_bytes() == b"old"
    assert [p.name for p in tmp_path.iterdir()] == ["file.json"]


# --- The append routine -----------------------------------------------------


def test_append_writes_line_and_newline_in_one_write_then_flushes(
    tmp_path, monkeypatch
):
    calls = []
    real_write, real_fsync = os.write, os.fsync

    def spy_write(fd, data):
        calls.append(("write", bytes(data)))
        return real_write(fd, data)

    def spy_fsync(fd):
        calls.append(("fsync", None))
        return real_fsync(fd)

    monkeypatch.setattr(os, "write", spy_write)
    monkeypatch.setattr(os, "fsync", spy_fsync)
    samples = tmp_path / "samples.jsonl"
    append_sample(samples, sample_record())
    assert [c[0] for c in calls] == ["write", "fsync"]
    written = calls[0][1]
    assert written.endswith(b"\n") and written.count(b"\n") == 1
    assert samples.read_bytes() == written


def test_appends_accumulate_in_order(tmp_path):
    samples = tmp_path / "samples.jsonl"
    for number in (1, 2, 3):
        append_sample(samples, sample_record(number))
    ids = [s.sample_id[-4:] for s in read_samples(samples)]
    assert ids == ["0001", "0002", "0003"]


def test_write_samples_replaces_the_whole_file(tmp_path):
    samples = tmp_path / "samples.jsonl"
    for number in (1, 2, 3):
        append_sample(samples, sample_record(number))
    write_samples(samples, [sample_record(1), sample_record(3)])
    ids = [s.sample_id[-4:] for s in read_samples(samples)]
    assert ids == ["0001", "0003"]
    write_samples(samples, [])
    assert read_samples(samples) == []


# --- Reading damaged files --------------------------------------------------


def test_reading_ignores_a_last_line_without_its_newline(tmp_path):
    samples = tmp_path / "samples.jsonl"
    append_sample(samples, sample_record(1))
    line = fileio.sample_to_line(sample_record(2))
    with open(samples, "ab") as handle:
        handle.write(line.encode())  # complete JSON but no newline
    ids = [s.sample_id[-4:] for s in read_samples(samples)]
    assert ids == ["0001"]


def test_reading_ignores_an_invalid_last_line(tmp_path):
    samples = tmp_path / "samples.jsonl"
    append_sample(samples, sample_record(1))
    with open(samples, "ab") as handle:
        handle.write(b'{"sampleId": "x", "labe\n')
    assert len(read_samples(samples)) == 1


def test_an_invalid_line_in_the_middle_is_an_error(tmp_path):
    samples = tmp_path / "samples.jsonl"
    append_sample(samples, sample_record(1))
    with open(samples, "ab") as handle:
        handle.write(b"garbage\n")
    append_sample(samples, sample_record(2))
    with pytest.raises(DatasetError, match="line 2"):
        read_samples(samples)


def test_reading_a_missing_samples_file_gives_nothing(tmp_path):
    assert read_samples(tmp_path / "nope.jsonl") == []


# --- Opening a data folder --------------------------------------------------


def test_a_missing_folder_is_created_only_when_asked(tmp_path):
    folder = tmp_path / "data"
    with pytest.raises(NotADatasetError):
        open_data_folder(folder)
    assert not folder.exists()
    opened = open_data_folder(folder, create=True)
    assert opened.report.created
    assert (folder / "dataset.json").exists()
    assert (folder / "sessions").is_dir()
    assert opened.info.format_version == 1
    reopened = open_data_folder(folder)
    assert not reopened.report.created
    assert reopened.info == opened.info
    assert isinstance(reopened.info, DatasetInfo)


def test_a_non_empty_folder_without_dataset_json_is_not_taken_over(tmp_path):
    (tmp_path / "photos.jpg").write_bytes(b"x")
    with pytest.raises(NotADatasetError, match="not empty"):
        open_data_folder(tmp_path, create=True)
    assert not (tmp_path / "dataset.json").exists()


def test_unknown_dataset_version_is_refused(tmp_path):
    open_data_folder(tmp_path / "d", create=True)
    path = tmp_path / "d" / "dataset.json"
    data = json.loads(path.read_text())
    data["formatVersion"] = 7
    path.write_text(json.dumps(data))
    with pytest.raises(UnsupportedFormatError, match="7"):
        open_data_folder(tmp_path / "d")


def make_session_folder(root):
    folder = root / "sessions" / SESSION_ID
    (folder / "videos").mkdir(parents=True)
    write_record(folder / "session.json", session_record())
    return folder


def test_crash_leftover_temp_file_is_removed_on_open(tmp_path):
    open_data_folder(tmp_path, create=True)
    folder = make_session_folder(tmp_path)
    leftovers = [
        folder / ".session.json.abc123.tmp",
        folder / "videos" / ".clip.mp4.def456.tmp",
        tmp_path / ".dataset.json.ghi789.tmp",
    ]
    for leftover in leftovers:
        leftover.write_bytes(b"half")
    opened = open_data_folder(tmp_path)
    assert sorted(opened.report.removed_temp_files) == sorted(leftovers)
    assert not any(p.exists() for p in leftovers)
    assert (folder / "session.json").exists()  # real files untouched


def test_crash_truncated_last_line_is_cut_on_open(tmp_path):
    open_data_folder(tmp_path, create=True)
    folder = make_session_folder(tmp_path)
    samples = folder / "samples.jsonl"
    append_sample(samples, sample_record(1))
    good = samples.read_bytes()
    with open(samples, "ab") as handle:
        handle.write(fileio.sample_to_line(sample_record(2)).encode()[:60])
    opened = open_data_folder(tmp_path)
    assert opened.report.truncated_files == [samples]
    assert samples.read_bytes() == good
    append_sample(samples, sample_record(2))  # appending works again
    assert len(read_samples(samples)) == 2


def test_crash_invalid_last_line_with_newline_is_cut_on_open(tmp_path):
    open_data_folder(tmp_path, create=True)
    folder = make_session_folder(tmp_path)
    samples = folder / "samples.jsonl"
    append_sample(samples, sample_record(1))
    good = samples.read_bytes()
    with open(samples, "ab") as handle:
        handle.write(b'{"sampleId": "broken\n')
    open_data_folder(tmp_path)
    assert samples.read_bytes() == good


def test_a_healthy_folder_is_left_alone(tmp_path):
    open_data_folder(tmp_path, create=True)
    folder = make_session_folder(tmp_path)
    samples = folder / "samples.jsonl"
    append_sample(samples, sample_record(1))
    before = samples.read_bytes()
    opened = open_data_folder(tmp_path)
    assert opened.report.removed_temp_files == []
    assert opened.report.truncated_files == []
    assert samples.read_bytes() == before


def test_truncating_handles_empty_and_missing_files(tmp_path):
    empty = tmp_path / "samples.jsonl"
    empty.write_bytes(b"")
    assert not fileio.truncate_damaged_tail(empty)
    assert not fileio.truncate_damaged_tail(tmp_path / "none.jsonl")
    only_partial = tmp_path / "partial.jsonl"
    only_partial.write_bytes(b'{"a"')
    assert fileio.truncate_damaged_tail(only_partial)
    assert only_partial.read_bytes() == b""
