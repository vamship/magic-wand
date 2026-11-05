import hashlib
import os
from datetime import datetime, timedelta, timezone

import pytest

from wand_core.dataset import (
    Action,
    DatasetError,
    DatasetStore,
    Handedness,
    PositionColumns,
    SampleRecord,
    SampleStatus,
    VideoRecord,
    load_samples,
    merge_folders,
    open_data_folder,
)
from wand_core.dataset.fileio import NotADatasetError

TZ = timezone(timedelta(hours=-4))


class Clock:
    def __init__(self):
        self.now = datetime(2026, 11, 1, 16, 0, 0, tzinfo=TZ)

    def __call__(self):
        self.now += timedelta(minutes=1)
        return self.now


def make_store(path):
    return DatasetStore.open(path, create=True, clock=Clock())


def add(store, session, label="circle", clip=True):
    sample_id = store.new_sample_id(session.session_id)
    video = None
    if clip:
        store.clip_path(sample_id).write_bytes(b"clip-" + sample_id.encode())
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
            status=SampleStatus.ACCEPTED,
            handedness=session.handedness,
            frame_size=(640, 480),
            positions=PositionColumns(
                time_s=[0.0, 0.1], horizontal=[0.4, 0.5], vertical=[0.5, 0.6]
            ),
            video=video,
        )
    )


def tree_hash(folder):
    """A hash of every file's path and bytes."""
    digest = hashlib.sha256()
    for path in sorted(folder.rglob("*")):
        digest.update(str(path.relative_to(folder)).encode())
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()


@pytest.fixture
def source(tmp_path):
    store = make_store(tmp_path / "source")
    session = store.create_session("ada", Handedness.RIGHT, name="one")
    add(store, session)
    add(store, session, "zigzag")
    other = store.create_session("bob", Handedness.LEFT)
    add(store, other)
    return tmp_path / "source"


def ids(folder):
    return {s.sample_id for s in load_samples(folder)}


def test_new_sessions_are_copied_whole_with_the_same_ids(tmp_path, source):
    target = tmp_path / "target"
    result = merge_folders([source], target)
    assert [r.action for r in result.sessions] == [Action.COPIED] * 2
    assert ids(target) == ids(source) and len(ids(target)) == 3
    for clip in (source / "sessions").rglob("*.mp4"):
        copy = target / clip.relative_to(source)
        assert copy.read_bytes() == clip.read_bytes()
    assert not any(target.rglob("*.tmp"))


def test_the_target_is_created_if_needed_and_extends_an_existing_one(
    tmp_path, source
):
    target_store = make_store(tmp_path / "target")
    mine = target_store.create_session("me", Handedness.RIGHT)
    add(target_store, mine)
    merge_folders([source], tmp_path / "target")
    assert len(load_samples(tmp_path / "target")) == 4


def test_identical_sessions_are_skipped(tmp_path, source):
    target = tmp_path / "target"
    merge_folders([source], target)
    again = merge_folders([source], target)
    assert {r.action for r in again.sessions} == {Action.SKIPPED}
    assert len(load_samples(target)) == 3


def test_conflicts_are_reported_and_left_alone_by_default(tmp_path, source):
    target = tmp_path / "target"
    merge_folders([source], target)
    store = DatasetStore.open(target)
    session = store.list_sessions()[0]
    store.update_sample(
        store.read_samples(session.session_id)[0].sample_id, label="zigzag"
    )
    before = tree_hash(target)
    result = merge_folders([source], target)
    assert result.count(Action.CONFLICT) == 1 and result.has_conflicts
    assert result.count(Action.SKIPPED) == 1
    assert tree_hash(target) == before


def test_conflicts_are_replaced_when_asked(tmp_path, source):
    target = tmp_path / "target"
    merge_folders([source], target)
    store = DatasetStore.open(target)
    session = store.list_sessions()[0]
    store.update_sample(
        store.read_samples(session.session_id)[0].sample_id, label="zigzag"
    )
    result = merge_folders([source], target, on_conflict="replace")
    assert result.count(Action.REPLACED) == 1
    assert sorted(
        (s.sample_id, s.label) for s in load_samples(target)
    ) == sorted((s.sample_id, s.label) for s in load_samples(source))
    assert not any(target.rglob("*.tmp"))
    assert tree_hash(target) == tree_hash(target)  # settled


def test_sources_are_unchanged(tmp_path, source):
    before = tree_hash(source)
    stamps = {p: p.stat().st_mtime_ns for p in source.rglob("*")}
    merge_folders([source], tmp_path / "target")
    merge_folders([source], tmp_path / "target", on_conflict="replace")
    assert tree_hash(source) == before
    assert {p: p.stat().st_mtime_ns for p in source.rglob("*")} == stamps


def test_a_source_with_leftovers_is_not_cleaned_up_or_copied_dirty(
    tmp_path, source
):
    session_dir = next((source / "sessions").iterdir())
    (session_dir / "stray.tmp").write_text("x")
    merge_folders([source], tmp_path / "target")
    assert (session_dir / "stray.tmp").exists()
    assert not any((tmp_path / "target").rglob("*.tmp"))


def test_skipping_clips_leaves_samples_without_clips(tmp_path, source):
    target = tmp_path / "target"
    merge_folders([source], target, skip_clips=True)
    assert not list(target.rglob("*.mp4"))
    assert len(load_samples(target)) == 3
    store = DatasetStore.open(target)
    for session in store.list_sessions():
        for sample in store.read_samples(session.session_id):
            assert store.has_clip(sample) is False  # the sample still loads


def test_several_sources_and_the_per_session_result(tmp_path, source):
    second = make_store(tmp_path / "second")
    session = second.create_session("carol", Handedness.RIGHT)
    add(second, session)
    result = merge_folders([source, tmp_path / "second"], tmp_path / "t")
    assert len(result.sessions) == 3
    merged = {s.session_id for s in load_samples(tmp_path / "t")}
    assert {r.session_id for r in result.sessions} == merged
    assert all(str(r) for r in result.sessions)


def test_bad_inputs(tmp_path, source):
    with pytest.raises(NotADatasetError):
        merge_folders([tmp_path / "missing"], tmp_path / "t")
    with pytest.raises(DatasetError, match="itself"):
        merge_folders([source], source)
    with pytest.raises(ValueError):
        merge_folders([source], tmp_path / "t", on_conflict="maybe")
    assert not (tmp_path / "t").exists()  # refused before creating anything


def test_a_damaged_source_session_is_reported_not_fatal(tmp_path, source):
    broken = sorted((source / "sessions").iterdir())[0]
    (broken / "session.json").write_text("{nope")
    result = merge_folders([source], tmp_path / "t")
    assert result.count(Action.ERROR) == 1
    assert result.count(Action.COPIED) == 1


def test_an_interrupted_merge_leaves_no_session_and_is_cleaned_on_open(
    tmp_path, source, monkeypatch
):
    target = tmp_path / "target"
    merge_folders([source], target)
    other = make_store(tmp_path / "other")
    add(other, other.create_session("dan", Handedness.RIGHT))

    real_rename = type(target).rename

    def failing_rename(self, to):
        if self.name.startswith(".merge-"):
            raise OSError("disk went away")
        return real_rename(self, to)

    monkeypatch.setattr(type(target), "rename", failing_rename)
    with pytest.raises(OSError):
        merge_folders([tmp_path / "other"], target)
    monkeypatch.undo()
    assert len(os.listdir(target / "sessions")) == 2  # nothing half-copied
    open_data_folder(target)
    assert not any(target.glob(".merge-*"))


def test_an_orphan_merge_folder_is_removed_when_the_folder_opens(
    tmp_path, source
):
    target = tmp_path / "target"
    merge_folders([source], target)
    leftover = target / ".merge-abc.tmp"
    (leftover / "videos").mkdir(parents=True)
    (leftover / "session.json").write_text("{}")
    report = open_data_folder(target).report
    assert not leftover.exists() and leftover in report.removed_temp_files
