import dataclasses
import json
import threading

import pytest
from pydantic import ValidationError

from wand_collect.state import (
    ApplicationState,
    CameraState,
    CaptureState,
    CaptureStatus,
    Label,
    LatestSample,
    Owner,
    OwnershipError,
    SessionInfo,
    SessionRole,
    SettingsState,
    settings_locked,
)
from wand_core.settings import MotionSettings, VisionSettings
from wand_core.sources import CameraMode
from wand_core.types import Discard, DiscardReason


def test_new_instance_starts_with_defaults():
    snapshot = ApplicationState().snapshot
    assert snapshot.session is None
    assert snapshot.counts == {}
    assert snapshot.labels == ()
    assert snapshot.capture.state is CaptureStatus.STOPPED
    assert snapshot.settings.profile is None
    assert (
        snapshot.settings.vision.model_dump() == VisionSettings().model_dump()
    )
    assert (
        snapshot.settings.motion.model_dump() == MotionSettings().model_dump()
    )
    assert snapshot.samples_revision == 0
    assert snapshot.active_label is None
    assert snapshot.latest_sample is None
    assert snapshot.last_discard is None


def test_instances_are_independent():
    a, b = ApplicationState(), ApplicationState()
    a.update(Owner.SAMPLE_LIBRARY, samples_revision=5)
    assert a.snapshot.samples_revision == 5
    assert b.snapshot.samples_revision == 0


def test_snapshot_is_immutable():
    state = ApplicationState()
    state.update(Owner.SAMPLE_LIBRARY, counts={"a": 1})
    snapshot = state.snapshot
    with pytest.raises(dataclasses.FrozenInstanceError):
        snapshot.samples_revision = 3
    with pytest.raises(TypeError):
        snapshot.counts["a"] = 2
    with pytest.raises(ValidationError):
        snapshot.settings.vision.hue_center = 50
    with pytest.raises(dataclasses.FrozenInstanceError):
        snapshot.settings.profile = "x"


def test_snapshot_does_not_change_when_the_supplied_data_does():
    state = ApplicationState()
    counts = {"a": 1}
    vision = VisionSettings()
    state.update(Owner.SAMPLE_LIBRARY, counts=counts)
    state.update(
        Owner.CALIBRATION_SERVICE,
        settings=SettingsState(vision=vision, motion=MotionSettings()),
    )
    counts["a"] = 99
    vision.hue_center = 90
    assert state.snapshot.counts == {"a": 1}
    assert state.snapshot.settings.vision.hue_center == 15


def test_update_replaces_the_snapshot_and_notifies_listeners():
    state = ApplicationState()
    seen_a, seen_b = [], []
    state.subscribe(seen_a.append)
    state.subscribe(seen_b.append)
    before = state.snapshot
    returned = state.update(Owner.LABEL_SERVICE, labels=[Label("x", "X")])
    assert state.snapshot is returned
    assert before.labels == ()
    assert returned.labels == (Label("x", "X"),)
    assert seen_a == [returned] == seen_b


def test_unsubscribe_and_unchanged_update():
    state = ApplicationState()
    seen = []
    cancel = state.subscribe(seen.append)
    state.update(Owner.SAMPLE_LIBRARY, samples_revision=1)
    state.update(Owner.SAMPLE_LIBRARY, samples_revision=1)  # no change
    assert len(seen) == 1
    cancel()
    cancel()
    state.update(Owner.SAMPLE_LIBRARY, samples_revision=2)
    assert len(seen) == 1


def test_failing_listener_does_not_stop_others_or_the_update():
    state = ApplicationState()
    seen = []

    def bad(_):
        raise RuntimeError("boom")

    state.subscribe(bad)
    state.subscribe(seen.append)
    state.update(Owner.SAMPLE_LIBRARY, samples_revision=1)
    assert len(seen) == 1
    assert state.snapshot.samples_revision == 1


def test_listener_that_updates_keeps_order():
    state = ApplicationState()
    seen = []

    def follow_up(snapshot):
        seen.append(snapshot.samples_revision)
        if snapshot.samples_revision == 1:
            state.update(Owner.SAMPLE_LIBRARY, samples_revision=2)

    state.subscribe(follow_up)
    state.update(Owner.SAMPLE_LIBRARY, samples_revision=1)
    assert seen == [1, 2]


@pytest.mark.parametrize(
    ("owner", "field", "value"),
    [
        (Owner.SESSION_SERVICE, "settings", SettingsState()),
        (Owner.CAPTURE_ENGINE, "capture", CaptureState()),
        (Owner.CAPTURE_CONTROLLER, "labels", ()),
        (Owner.SAMPLE_LIBRARY, "active_label", "a"),
        (Owner.LABEL_SERVICE, "counts", {}),
        (Owner.CALIBRATION_SERVICE, "session", None),
    ],
)
def test_writing_a_field_you_do_not_own_is_rejected(owner, field, value):
    state = ApplicationState()
    before = state.snapshot
    seen = []
    state.subscribe(seen.append)
    with pytest.raises(OwnershipError, match=field):
        state.update(owner, **{field: value})
    assert state.snapshot is before
    assert not seen


def test_a_mixed_update_is_rejected_whole():
    state = ApplicationState()
    with pytest.raises(OwnershipError):
        state.update(
            Owner.CAPTURE_CONTROLLER,
            active_label="a",
            counts={"a": 1},  # not the controller's
        )
    assert state.snapshot.active_label is None


def test_unknown_or_no_field_is_rejected():
    state = ApplicationState()
    with pytest.raises(OwnershipError, match="unknown"):
        state.update(Owner.SAMPLE_LIBRARY, nonsense=1)
    with pytest.raises(OwnershipError, match="at least one"):
        state.update(Owner.SAMPLE_LIBRARY)


def test_each_owner_can_write_its_fields():
    state = ApplicationState()
    state.update(
        Owner.SESSION_SERVICE,
        session=SessionInfo("s1", "Desk", SessionRole.CAPTURE),
    )
    state.update(Owner.CALIBRATION_SERVICE, settings=SettingsState(profile="p"))
    state.update(Owner.CAPTURE_ENGINE, camera=CameraState(device="cam"))
    state.update(
        Owner.CAPTURE_CONTROLLER,
        capture=CaptureState(CaptureStatus.READY),
        active_label="spell_one",
        latest_sample=LatestSample("n1", "spell_one", "accepted", True),
        last_discard=Discard(DiscardReason.TOO_SHORT, 2.5),
    )
    state.update(
        Owner.SAMPLE_LIBRARY, counts={"spell_one": 1}, samples_revision=1
    )
    state.update(Owner.LABEL_SERVICE, labels=[Label("spell_one", "One")])
    snap = state.snapshot
    assert snap.session.id == "s1"
    assert snap.settings.profile == "p"
    assert snap.capture.state is CaptureStatus.READY
    assert snap.last_discard.reason is DiscardReason.TOO_SHORT


def test_settings_locked_only_while_loaded_for_capture():
    state = ApplicationState()
    assert not settings_locked(state.snapshot)
    state.update(
        Owner.SESSION_SERVICE,
        session=SessionInfo("s", "n", SessionRole.CAPTURE),
    )
    assert settings_locked(state.snapshot)
    state.update(
        Owner.SESSION_SERVICE,
        session=SessionInfo("s", "n", SessionRole.REVIEW),
    )
    assert not settings_locked(state.snapshot)
    state.update(Owner.SESSION_SERVICE, session=None)
    assert not settings_locked(state.snapshot)


def test_json_uses_camel_case_and_keeps_data_keys():
    state = ApplicationState()
    state.update(
        Owner.SESSION_SERVICE,
        session=SessionInfo("s1", "Desk", SessionRole.CAPTURE),
    )
    state.update(
        Owner.CAPTURE_ENGINE,
        camera=CameraState(
            "cam", 0, CameraMode(640, 480, 30), CameraMode(1280, 720, 30.0)
        ),
    )
    state.update(
        Owner.CAPTURE_CONTROLLER,
        capture=CaptureState(CaptureStatus.COUNTDOWN, countdown_ends_at=12.5),
        active_label="spell_one",
        last_discard=Discard(DiscardReason.TOO_LONG, 4.0),
    )
    state.update(
        Owner.SAMPLE_LIBRARY, counts={"spell_one": 3}, samples_revision=7
    )
    text = state.snapshot.to_json()
    data = json.loads(text)
    assert data["session"] == {"id": "s1", "name": "Desk", "role": "capture"}
    assert data["capture"] == {
        "state": "COUNTDOWN",
        "countdownEndsAt": 12.5,
        "remainingS": None,
    }
    assert data["activeLabel"] == "spell_one"
    assert data["samplesRevision"] == 7
    assert data["counts"] == {"spell_one": 3}  # data keys untouched
    assert data["lastDiscard"] == {"reason": "too_long", "timestampS": 4.0}
    assert data["camera"]["actual"] == {
        "width": 1280,
        "height": 720,
        "fps": 30.0,
    }
    assert data["settings"]["vision"]["hueCenter"] == 15
    assert data["settings"]["motion"]["startSpeed"] == 0.25
    assert data["settings"]["profile"] is None
    assert data["latestSample"] is None
    assert "_" not in "".join(k for k in data if k != "counts")


def test_concurrent_updates_are_never_lost_and_arrive_in_order():
    state = ApplicationState()
    seen = []
    state.subscribe(lambda snapshot: seen.append(snapshot.samples_revision))
    threads, per_thread = 8, 250

    def work():
        for _ in range(per_thread):
            state.modify(
                Owner.SAMPLE_LIBRARY,
                lambda s: {"samples_revision": s.samples_revision + 1},
            )

    pool = [threading.Thread(target=work) for _ in range(threads)]
    for t in pool:
        t.start()
    for t in pool:
        t.join()
    total = threads * per_thread
    assert state.snapshot.samples_revision == total
    assert seen == list(range(1, total + 1))


def test_readers_never_see_a_half_applied_update():
    state = ApplicationState()
    stop = threading.Event()
    bad = []

    def reader():
        while not stop.is_set():
            snap = state.snapshot
            # The two fields are always written together as a pair.
            if (snap.active_label is None) != (snap.latest_sample is None):
                bad.append(snap)
            if snap.latest_sample and (
                snap.latest_sample.label != snap.active_label
            ):
                bad.append(snap)

    readers = [threading.Thread(target=reader) for _ in range(3)]
    for t in readers:
        t.start()
    for i in range(500):
        label = f"label{i}"
        state.update(
            Owner.CAPTURE_CONTROLLER,
            active_label=label,
            latest_sample=LatestSample(f"id{i}", label, "accepted", False),
        )
    stop.set()
    for t in readers:
        t.join()
    assert not bad
