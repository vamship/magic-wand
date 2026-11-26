import hashlib
import shutil
from datetime import datetime, timedelta, timezone

import pytest

from wand_core.dataset import (
    DatasetExistsError,
    DatasetStore,
    Handedness,
    InvalidDatasetNameError,
    PositionColumns,
    SampleRecord,
    SampleStatus,
    SessionConflictError,
    check_folder,
    check_folders,
    create_dataset,
    find_datasets,
    is_valid_dataset_name,
    load_samples,
    merge_folders,
    session_conflicts,
)

TZ = timezone(timedelta(hours=-4))


class Clock:
    def __init__(self):
        self.now = datetime(2026, 11, 1, 16, 0, 0, tzinfo=TZ)

    def __call__(self):
        self.now += timedelta(minutes=1)
        return self.now


def make_store(path):
    return DatasetStore.open(path, create=True, clock=Clock())


def add(store, session, label="circle"):
    sample_id = store.new_sample_id(session.session_id)
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
            video=None,
        )
    )


def tree_hash(folder):
    digest = hashlib.sha256()
    for path in sorted(folder.rglob("*")):
        digest.update(str(path.relative_to(folder)).encode())
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()


@pytest.fixture
def location(tmp_path):
    return tmp_path / "data"


def fill(location, name, author, sessions=1, samples=2, end=True):
    store = make_store(location / name)
    for _ in range(sessions):
        session = store.create_session(author, Handedness.RIGHT)
        for _ in range(samples):
            add(store, session)
        if end:
            store.end_session(session.session_id)
    return store


# --- Names -------------------------------------------------------------------


@pytest.mark.parametrize(
    "name", ["vamship", "a1", "two-words", "x_y", "9lives"]
)
def test_valid_names(name):
    assert is_valid_dataset_name(name)


@pytest.mark.parametrize(
    "name", ["", "Upper", "has space", "a/b", "-start", "_start", "dot.", ".."]
)
def test_invalid_names(name):
    assert not is_valid_dataset_name(name)


# --- Finding datasets ---------------------------------------------------------


def test_a_location_lists_exactly_its_datasets(location):
    fill(location, "mrunal", "mrunal", sessions=2, samples=3)
    fill(location, "vamship", "vamship", sessions=1, samples=4)
    fill(location, "wen", "wen", sessions=3, samples=1)
    (location / "notes.txt").write_text("stray file")
    (location / "empty-folder").mkdir()
    (location / ".hidden").mkdir()
    shutil.copytree(location / "wen", location / ".hidden" / "wen")

    found = find_datasets(location)

    assert [d.name for d in found] == ["mrunal", "vamship", "wen"]
    assert [(d.sessions, d.samples) for d in found] == [(2, 6), (1, 4), (3, 3)]
    assert all(d.format_version == 1 and d.error is None for d in found)
    assert found[0].path == location / "mrunal"


def test_a_missing_location_has_no_datasets(tmp_path):
    assert find_datasets(tmp_path / "nowhere") == []


def test_a_dataset_that_cannot_be_read_is_listed_with_its_error(location):
    fill(location, "good", "ada")
    fill(location, "bad", "bob")
    (location / "bad" / "dataset.json").write_text("{not json")

    found = {d.name: d for d in find_datasets(location)}

    assert found["good"].error is None
    assert found["bad"].error is not None and found["bad"].sessions == 0


def test_a_session_still_being_written_is_not_double_counted(location):
    store = fill(location, "ada", "ada", samples=2)
    folder = store.session_dir(store.list_sessions()[0].session_id)
    with open(folder / "samples.jsonl", "ab") as handle:
        handle.write(b'{"sampleId": "half')  # an incomplete last line
    assert find_datasets(location)[0].samples == 2


# --- Creating a dataset -------------------------------------------------------


def test_a_created_dataset_opens_and_passes_the_check(location):
    path = create_dataset(location, "new-one")

    assert path == location / "new-one"
    assert check_folder(path).ok
    assert [d.name for d in find_datasets(location)] == ["new-one"]
    store = make_store(path)
    assert store.list_sessions() == []


def test_a_location_that_does_not_exist_is_created(tmp_path):
    create_dataset(tmp_path / "a" / "b", "first")
    assert (tmp_path / "a" / "b" / "first" / "dataset.json").is_file()


@pytest.mark.parametrize("name", ["", "Upper", "has space", "a/b", "../x"])
def test_invalid_names_are_refused(location, name):
    with pytest.raises(InvalidDatasetNameError):
        create_dataset(location, name)
    assert not location.exists() or not any(location.iterdir())


def test_existing_names_are_refused(location):
    fill(location, "taken", "ada")
    (location / "plain-folder").mkdir()
    with pytest.raises(DatasetExistsError):
        create_dataset(location, "taken")
    with pytest.raises(DatasetExistsError):
        create_dataset(location, "plain-folder")


# --- Several folders ----------------------------------------------------------


@pytest.fixture
def two(location):
    """Two datasets that share one session (identical) and have one each."""
    a = fill(location, "a", "ada")
    fill(location, "b", "bob")
    merge_folders([location / "a"], location / "b")  # b now has a's session
    return location / "a", location / "b", a


def sample_ids(loaded):
    return sorted(s.sample_id for s in loaded)


def test_a_shared_session_is_loaded_once(two):
    a, b, _ = two
    only_a = load_samples(a)
    only_b = load_samples(b)
    both = load_samples([a, b])
    assert len(both) == len(only_b) < len(only_a) + len(only_b)
    assert sample_ids(both) == sample_ids(only_b)


def test_differing_copies_fail_naming_the_session(two):
    a, b, store = two
    shared = store.list_sessions()[0].session_id
    DatasetStore.open(b, clock=Clock()).update_session(shared, name="changed")
    assert session_conflicts([a, b]).keys() == {shared}

    with pytest.raises(SessionConflictError, match=shared):
        load_samples([a, b])


def test_differing_copies_can_be_skipped(two):
    a, b, store = two
    shared = store.list_sessions()[0].session_id
    DatasetStore.open(b, clock=Clock()).update_session(shared, name="changed")

    loaded = load_samples([a, b], skip_conflicts=True)

    assert shared not in {s.session_id for s in loaded}
    assert {s.session_id for s in loaded} == {
        s.session_id for s in load_samples(b)
    } - {shared}


def test_one_folder_behaves_as_before(two):
    a, _, _ = two
    assert len(load_samples(a)) == 2
    assert len(load_samples([a])) == 2


def test_the_check_on_several_folders_lists_open_sessions_and_conflicts(
    location,
):
    a = fill(location, "a", "ada", end=False)
    fill(location, "b", "bob", end=True)
    merge_folders([location / "a"], location / "b")
    before = tree_hash(location)

    clean = check_folders([location / "a", location / "b"])
    assert clean.ok and clean.codes() == {"open_session"}
    assert all(f.level.value == "info" for f in clean.findings)
    assert len(clean.findings) == 2  # the shared open session, in both folders

    add(DatasetStore.open(location / "b", clock=Clock()), a.list_sessions()[0])
    conflicted = check_folders([location / "a", location / "b"])
    assert not conflicted.ok
    assert "session_conflict" in conflicted.codes()
    assert tree_hash(location) != before  # only because the test added a sample


def test_the_check_never_writes(location):
    fill(location, "a", "ada", end=False)
    fill(location, "b", "bob")
    before = tree_hash(location)
    check_folders([location / "a", location / "b"])
    assert tree_hash(location) == before


def test_the_check_of_one_folder_is_unchanged(location):
    fill(location, "a", "ada", end=False)
    assert check_folder(location / "a").findings == []


def test_a_missing_folder_is_reported_by_the_check(tmp_path):
    report = check_folders([tmp_path / "nothing"])
    assert report.codes() == {"not_a_dataset"} and not report.ok
