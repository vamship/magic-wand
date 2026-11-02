import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from wand_core.dataset import (
    ChangeKind,
    DatasetError,
    DatasetStore,
    Handedness,
    PositionColumns,
    SampleNotFoundError,
    SampleRecord,
    SampleStatus,
    SessionEndedError,
    SessionNotFoundError,
    VideoRecord,
    append_sample,
    make_sample_id,
    open_data_folder,
    read_samples,
    split_sample_id,
)
from wand_core.dataset.models import CameraRecord, Mode
from wand_core.settings import MotionSettings, VisionSettings

TZ = timezone(timedelta(hours=-4))


class Clock:
    def __init__(self):
        self.now = datetime(2026, 11, 1, 16, 0, 0, tzinfo=TZ)

    def __call__(self):
        self.now += timedelta(seconds=1)
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def store(tmp_path, clock):
    return DatasetStore.open(tmp_path / "data", create=True, clock=clock)


@pytest.fixture
def session(store):
    return store.create_session(
        "vamship",
        Handedness.RIGHT,
        name="desk",
        notes="lamp",
        camera=CameraRecord(
            device="cam",
            index=0,
            requested=Mode(width=640, height=480, fps=30),
            actual=Mode(width=640, height=480, fps=29.8),
        ),
        vision_settings=VisionSettings(hue_center=22),
        motion_settings=MotionSettings(start_speed=0.3),
        profile="p",
    )


def make_sample(store, session, clip=False, label="circle", number=None):
    number = number or store.next_sample_number(session.session_id)
    sample_id = make_sample_id(session.session_id, number)
    if clip:
        path = store.clip_path(sample_id)
        path.write_bytes(b"video")
    return SampleRecord(
        sample_id=sample_id,
        session_id=session.session_id,
        captured_at=datetime(2026, 11, 1, 14, 30, tzinfo=TZ),
        updated_at=datetime(2026, 11, 1, 14, 30, tzinfo=TZ),
        label=label,
        handedness=session.handedness,
        frame_size=(640, 480),
        positions=PositionColumns(
            time_s=[0.0, 0.1], horizontal=[0.4, 0.5], vertical=[0.5, 0.5]
        ),
        video=(
            VideoRecord(
                file=DatasetStore.clip_reference(sample_id), gesture_start_s=2.0
            )
            if clip
            else None
        ),
    )


# --- Identifiers ------------------------------------------------------------


def test_session_ids_are_uuid_version_4_and_folders_are_named_by_them(
    store, session
):
    parsed = uuid.UUID(session.session_id)
    assert parsed.version == 4
    assert str(parsed) == session.session_id
    folder = store.path / "sessions" / session.session_id
    assert (folder / "session.json").is_file()
    assert (folder / "samples.jsonl").read_bytes() == b""
    assert (folder / "videos").is_dir()


def test_sample_ids_pad_to_at_least_four_digits():
    sid = "3f8c1d2e-9a4b-4c7e-8f10-5b6d7e8f9a0b"
    assert make_sample_id(sid, 1) == f"{sid}-0001"
    assert make_sample_id(sid, 42) == f"{sid}-0042"
    assert make_sample_id(sid, 12345) == f"{sid}-12345"
    assert split_sample_id(f"{sid}-0042") == (sid, 42)
    with pytest.raises(SampleNotFoundError):
        split_sample_id("nonsense")


def test_new_session_records_everything_needed(store, session):
    loaded = store.get_session(session.session_id)
    assert loaded == session
    assert loaded.author == "vamship"
    assert loaded.name == "desk"
    assert loaded.notes == "lamp"
    assert loaded.ended_at is None
    assert loaded.highest_sample_number == 0
    assert loaded.camera.actual.fps == 29.8
    assert loaded.vision_settings.hue_center == 22
    assert loaded.motion_settings.start_speed == 0.3
    assert loaded.profile == "p"
    assert loaded.started_at.utcoffset() is not None


def test_session_needs_an_author(store):
    with pytest.raises(DatasetError, match="author"):
        store.create_session(" ", Handedness.LEFT)


def test_bad_session_ids_are_rejected_not_used_as_paths(store):
    for bad in ("../x", "abc", "", "3F8C1D2E-9A4B-4C7E-8F10-5B6D7E8F9A0B"):
        with pytest.raises(SessionNotFoundError):
            store.get_session(bad)
    with pytest.raises(SessionNotFoundError):
        store.get_session(str(uuid.uuid4()))


def test_list_sessions_oldest_first_skipping_folders_without_a_record(
    store, session
):
    second = store.create_session("someone", Handedness.LEFT)
    (store.path / "sessions" / str(uuid.uuid4())).mkdir()  # crash leftover
    assert [s.session_id for s in store.list_sessions()] == [
        session.session_id,
        second.session_id,
    ]


# --- Numbering --------------------------------------------------------------


def test_numbers_start_at_one_and_count_up(store, session):
    assert store.next_sample_number(session.session_id) == 1
    store.add_sample(make_sample(store, session))
    assert store.next_sample_number(session.session_id) == 2
    assert store.new_sample_id(session.session_id).endswith("-0002")


def test_adding_appends_one_line_and_updates_the_highest_number(store, session):
    path = store.session_dir(session.session_id) / "samples.jsonl"
    store.add_sample(make_sample(store, session))
    assert path.read_bytes().count(b"\n") == 1
    assert store.get_session(session.session_id).highest_sample_number == 1
    store.add_sample(make_sample(store, session))
    assert path.read_bytes().count(b"\n") == 2
    assert store.get_session(session.session_id).highest_sample_number == 2


def test_a_deleted_highest_number_is_not_reused(store, session):
    first = store.add_sample(make_sample(store, session))
    second = store.add_sample(make_sample(store, session))
    store.delete_sample(second.sample_id)
    assert store.next_sample_number(session.session_id) == 3
    store.delete_sample(first.sample_id)
    assert store.next_sample_number(session.session_id) == 3


def test_a_crash_between_the_append_and_the_session_update_is_safe(
    store, session
):
    # The line reached the file but highestSampleNumber was not updated.
    path = store.session_dir(session.session_id) / "samples.jsonl"
    append_sample(path, make_sample(store, session, number=5))
    assert store.get_session(session.session_id).highest_sample_number == 0
    assert store.next_sample_number(session.session_id) == 6


def test_resume_continues_numbering_after_reopening(tmp_path, clock):
    store = DatasetStore.open(tmp_path / "d", create=True, clock=clock)
    session = store.create_session("a", Handedness.RIGHT)
    store.add_sample(make_sample(store, session))
    store.add_sample(make_sample(store, session))
    reopened = DatasetStore.open(tmp_path / "d", clock=clock)
    assert reopened.next_sample_number(session.session_id) == 3


def test_sample_ids_are_checked_on_add(store, session):
    other = store.create_session("b", Handedness.RIGHT)
    foreign = make_sample(store, other)
    wrong = foreign.model_copy(update={"session_id": session.session_id})
    with pytest.raises(DatasetError, match="does not belong"):
        store.add_sample(wrong)
    saved = store.add_sample(make_sample(store, session))
    with pytest.raises(DatasetError, match="already exists"):
        store.add_sample(saved)


# --- Update, delete, clips --------------------------------------------------


def test_update_rewrites_the_file_and_sets_updated_at(store, session):
    record = store.add_sample(make_sample(store, session))
    updated = store.update_sample(
        record.sample_id, label="line", status=SampleStatus.REJECTED
    )
    assert updated.label == "line"
    assert updated.status is SampleStatus.REJECTED
    assert updated.updated_at > record.updated_at
    assert updated.captured_at == record.captured_at
    assert store.get_sample(record.sample_id) == updated
    assert len(store.read_samples(session.session_id)) == 1


def test_update_only_what_is_given(store, session):
    record = store.add_sample(make_sample(store, session))
    updated = store.update_sample(
        record.sample_id, status=SampleStatus.REJECTED
    )
    assert updated.label == "circle"
    again = store.update_sample(record.sample_id, label="zigzag")
    assert again.status is SampleStatus.REJECTED


def test_update_is_atomic_and_leaves_other_samples_alone(store, session):
    first = store.add_sample(make_sample(store, session))
    second = store.add_sample(make_sample(store, session))
    store.update_sample(second.sample_id, label="x")
    assert store.get_sample(first.sample_id) == first
    folder = store.session_dir(session.session_id)
    assert not list(folder.glob("*.tmp")) and not list(folder.glob(".*.tmp"))


@pytest.mark.parametrize("bad", ["Circle", "two words", "dash-ed", "", "é"])
def test_labels_must_be_lowercase_slugs(store, session, bad):
    record = store.add_sample(make_sample(store, session))
    with pytest.raises(ValueError, match="slug"):
        store.update_sample(record.sample_id, label=bad or " ")
    assert store.get_sample(record.sample_id).label == "circle"


def test_adding_a_bad_label_is_rejected_by_the_record(store, session):
    with pytest.raises(ValueError, match="slug"):
        make_sample(store, session, label="Bad Label")


def test_delete_removes_the_record_and_the_clip(store, session):
    record = store.add_sample(make_sample(store, session, clip=True))
    clip = store.clip_path(record.sample_id)
    assert clip.exists() and store.has_clip(record)
    store.delete_sample(record.sample_id)
    assert not clip.exists()
    assert store.read_samples(session.session_id) == []
    with pytest.raises(SampleNotFoundError):
        store.get_sample(record.sample_id)


def test_deleting_with_a_missing_clip_is_not_an_error(store, session):
    record = store.add_sample(make_sample(store, session, clip=True))
    store.clip_path(record.sample_id).unlink()
    store.delete_sample(record.sample_id)
    assert store.read_samples(session.session_id) == []


def test_unknown_samples_raise_not_found(store, session):
    ghost = make_sample_id(session.session_id, 9)
    with pytest.raises(SampleNotFoundError):
        store.update_sample(ghost, label="x")
    with pytest.raises(SampleNotFoundError):
        store.delete_sample(ghost)
    with pytest.raises(SampleNotFoundError):
        store.get_sample(ghost)


def test_a_sample_without_a_clip_reference_or_file_has_no_clip(store, session):
    none = store.add_sample(make_sample(store, session, clip=False))
    assert none.video is None and not store.has_clip(none)
    with_clip = store.add_sample(make_sample(store, session, clip=True))
    assert store.has_clip(with_clip)
    store.clip_path(with_clip.sample_id).unlink()  # referenced but absent
    assert with_clip.video is not None
    assert not store.has_clip(with_clip)
    empty_ref = none.model_copy(
        update={"video": VideoRecord(file="", gesture_start_s=0.0)}
    )
    assert not store.has_clip(empty_ref)


# --- Ended sessions ---------------------------------------------------------


def test_ended_sessions_accept_no_samples_but_can_be_edited(store, session):
    record = store.add_sample(make_sample(store, session, clip=True))
    ended = store.end_session(session.session_id)
    assert ended.ended_at is not None
    assert store.end_session(session.session_id).ended_at == ended.ended_at
    with pytest.raises(SessionEndedError):
        store.add_sample(make_sample(store, session))
    assert len(store.read_samples(session.session_id)) == 1
    store.update_sample(record.sample_id, label="line")
    assert store.get_sample(record.sample_id).label == "line"
    store.delete_sample(record.sample_id)
    assert store.read_samples(session.session_id) == []


def test_update_session_changes_fields(store, session):
    updated = store.update_session(
        session.session_id, notes="new", profile=None
    )
    assert updated.notes == "new" and updated.profile is None
    assert store.get_session(session.session_id) == updated
    with pytest.raises(ValueError):
        store.update_session(session.session_id, no_such_field=1)


# --- Notifications ----------------------------------------------------------


def test_every_change_is_reported_with_kind_and_ids(store):
    changes = []
    store.subscribe(changes.append)
    session = store.create_session("a", Handedness.RIGHT)
    sample = store.add_sample(make_sample(store, session))
    store.update_sample(sample.sample_id, label="line")
    store.delete_sample(sample.sample_id)
    store.end_session(session.session_id)
    assert [(c.kind, c.session_id, c.sample_id) for c in changes] == [
        (ChangeKind.SESSION_WRITTEN, session.session_id, None),
        (ChangeKind.SAMPLE_ADDED, session.session_id, sample.sample_id),
        (ChangeKind.SAMPLE_UPDATED, session.session_id, sample.sample_id),
        (ChangeKind.SAMPLE_DELETED, session.session_id, sample.sample_id),
        (ChangeKind.SESSION_WRITTEN, session.session_id, None),
    ]


def test_subscribers_see_the_change_already_on_disk(store, session):
    seen = []

    def check(change):
        seen.append(
            [r.sample_id for r in store.read_samples(change.session_id)]
        )

    store.subscribe(check)
    sample = store.add_sample(make_sample(store, session))
    store.delete_sample(sample.sample_id)
    assert seen == [[sample.sample_id], []]


def test_failed_changes_are_not_reported(store, session):
    changes = []
    store.subscribe(changes.append)
    store.end_session(session.session_id)
    changes.clear()
    with pytest.raises(SessionEndedError):
        store.add_sample(make_sample(store, session))
    with pytest.raises(SampleNotFoundError):
        store.delete_sample(make_sample_id(session.session_id, 7))
    assert changes == []


def test_unsubscribe_and_failing_subscriber(store):
    seen = []
    cancel = store.subscribe(seen.append)

    def bad(change):
        raise RuntimeError("boom")

    store.subscribe(bad)
    store.create_session("a", Handedness.RIGHT)
    assert len(seen) == 1
    cancel()
    cancel()
    store.create_session("b", Handedness.RIGHT)
    assert len(seen) == 1


def test_a_subscriber_may_read_the_store_back(store):
    sessions = []
    store.subscribe(lambda change: sessions.append(len(store.list_sessions())))
    store.create_session("a", Handedness.RIGHT)
    store.create_session("b", Handedness.RIGHT)
    assert sessions == [1, 2]


def test_concurrent_adds_keep_every_sample(store, session):
    errors = []

    def work():
        try:
            for _ in range(10):
                with store._lock:  # one writer reserves a number and saves
                    store.add_sample(make_sample(store, session))
        except Exception as error:  # noqa: BLE001
            errors.append(error)

    pool = [threading.Thread(target=work) for _ in range(4)]
    for t in pool:
        t.start()
    for t in pool:
        t.join()
    assert not errors
    numbers = sorted(
        split_sample_id(r.sample_id)[1]
        for r in store.read_samples(session.session_id)
    )
    assert numbers == list(range(1, 41))
    assert store.get_session(session.session_id).highest_sample_number == 40


# --- Opening ----------------------------------------------------------------


def test_opening_cleans_up_after_a_crash_during_an_append(tmp_path, clock):
    store = DatasetStore.open(tmp_path / "d", create=True, clock=clock)
    session = store.create_session("a", Handedness.RIGHT)
    store.add_sample(make_sample(store, session))
    path = store.session_dir(session.session_id) / "samples.jsonl"
    with open(path, "ab") as handle:
        handle.write(b'{"sampleId": "half')
    reopened = DatasetStore.open(tmp_path / "d", clock=clock)
    assert reopened.folder.report.truncated_files == [path]
    assert len(reopened.read_samples(session.session_id)) == 1
    assert reopened.next_sample_number(session.session_id) == 2
    assert len(read_samples(path)) == 1
    assert open_data_folder(tmp_path / "d").info == reopened.folder.info
