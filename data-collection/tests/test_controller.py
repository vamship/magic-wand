from concurrent.futures import Future
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from wand_collect.clip_writer import ClipResult
from wand_collect.controller import (
    CaptureController,
    Clock,
    Pause,
    Resume,
    Start,
    Stop,
)
from wand_collect.engine import (
    BufferedFrame,
    GestureDiscarded,
    GestureFound,
    MotionStarted,
)
from wand_collect.server import create_app
from wand_collect.state import (
    ApplicationState,
    CameraState,
    CaptureStatus,
    Label,
    Owner,
    SessionInfo,
    SessionRole,
)
from wand_core.dataset import DatasetStore, Handedness
from wand_core.sources import CameraMode
from wand_core.types import (
    Discard,
    DiscardReason,
    Gesture,
    Position,
)

S = CaptureStatus
LABELS = [Label("circle", "Circle"), Label("zigzag", "Zigzag")]


class FakeClock(Clock):
    def __init__(self):
        self.t = 100.0

    def monotonic(self):
        return self.t

    def wall(self):
        return 1_700_000_000.0 + self.t

    def now(self):
        return datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)


class FakeEngine:
    def __init__(self):
        self.calls = []
        self.armed = False
        self.newest = 1000.0
        self.frames = [BufferedFrame(t / 10, b"jpeg") for t in range(0, 400)]

    def arm(self):
        self.calls.append("arm")
        self.armed = True

    def disarm(self):
        self.calls.append("disarm")
        self.armed = False

    def frames_between(self, start, end):
        return [f for f in self.frames if start <= f.timestamp_s <= end]

    def newest_frame_s(self):
        return self.newest


class FakeClips:
    def __init__(self):
        self.ok = True
        self.submitted = []

    def submit(self, frames, fps, path):
        self.submitted.append((list(frames), fps, path))
        future = Future()
        future.set_result(
            ClipResult(True, path=path)
            if self.ok
            else ClipResult(False, error="encoder missing")
        )
        return future


class FakeSessions:
    def __init__(self, store, session_id):
        self.store, self.session_id = store, session_id

    def next_sample_number(self):
        return self.store.next_sample_number(self.session_id)


def gesture(start=10.0, length=1.5):
    points = [
        Position(i * 0.1, 0.2 + i * 0.02, 0.5) for i in range(int(length * 10))
    ]
    return Gesture(points, start, start + length, 640, 480)


class Rig:
    def __init__(self, tmp_path):
        self.clock = FakeClock()
        self.state = ApplicationState()
        self.state.update(Owner.LABEL_SERVICE, labels=LABELS)
        self.state.update(
            Owner.CAPTURE_ENGINE,
            camera=CameraState(
                "cam", 0, CameraMode(640, 480, 30), CameraMode(640, 480, 25.0)
            ),
        )
        self.store = DatasetStore.open(tmp_path / "data", create=True)
        self.session = self.store.create_session("ada", Handedness.LEFT)
        self.state.update(
            Owner.SESSION_SERVICE,
            session=SessionInfo(
                self.session.session_id, "n", SessionRole.CAPTURE
            ),
        )
        self.engine = FakeEngine()
        self.clips = FakeClips()
        self.jobs = []
        self.controller = CaptureController(
            self.state,
            self.engine,
            FakeSessions(self.store, self.session.session_id),
            self.store,
            self.clips,
            countdown_s=3.0,
            clip_padding=(2.0, 2.0),
            clock=self.clock,
            run_job=self.jobs.append,
        )
        self.changes = []
        self.state.subscribe(lambda s: self.changes.append(s.capture))
        self.client = TestClient(
            create_app(
                self.state, routers=[self.controller.router], static_dir=None
            )
        )

    @property
    def status(self):
        return self.state.snapshot.capture.state

    def send(self, message):
        self.controller.handle(message)

    def advance(self, seconds):
        self.clock.t += seconds
        self.controller.tick()

    def label(self, label="circle"):
        self.controller.handle(
            __import__("wand_collect.controller").controller.SetLabel(label)
        )

    def to_ready(self):
        self.label()
        self.send(Start())
        self.advance(3.0)
        assert self.status is S.READY

    def to_recording(self):
        self.to_ready()
        self.send(MotionStarted(10.0))
        assert self.status is S.RECORDING

    def finish_jobs(self):
        """Run the pending save jobs, then deliver their completions."""
        jobs, self.jobs = self.jobs, []
        for job in jobs:
            job()
        while not self.controller._queue.empty():
            self.send(self.controller._queue.get())


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


# --- Start, countdown and arming ----------------------------------------------


def test_start_enters_a_countdown_with_an_end_time(rig):
    rig.label()
    rig.send(Start())
    capture = rig.state.snapshot.capture
    assert capture.state is S.COUNTDOWN
    assert capture.countdown_ends_at == pytest.approx(1_700_000_103.0)
    assert rig.engine.armed is False


def test_ready_only_after_the_countdown_and_the_engine_is_armed_then(rig):
    rig.label()
    rig.send(Start())
    rig.advance(2.9)
    assert rig.status is S.COUNTDOWN and not rig.engine.armed
    rig.advance(0.2)
    assert rig.status is S.READY and rig.engine.armed
    assert rig.engine.calls[-1] == "arm"
    assert rig.state.snapshot.capture.countdown_ends_at is None


def test_no_state_updates_during_the_countdown(rig):
    rig.label()
    rig.send(Start())
    before = len(rig.changes)
    for _ in range(12):
        rig.advance(0.25)
    # one change only: READY at the end
    assert len(rig.changes) - before == 1


def test_start_is_ignored_when_already_running(rig):
    rig.to_ready()
    rig.send(Start())
    assert rig.status is S.READY


def test_motion_start_enters_recording(rig):
    rig.to_ready()
    rig.send(MotionStarted(5.0))
    assert rig.status is S.RECORDING
    rig.advance(1.0)  # no countdown is running
    assert rig.status is S.RECORDING


def test_the_engine_is_never_armed_during_a_countdown(rig):
    rig.to_recording()
    rig.send(GestureDiscarded(Discard(DiscardReason.TOO_SHORT, 11.0)))
    assert rig.status is S.COUNTDOWN
    assert rig.engine.armed is False


# --- Discards -----------------------------------------------------------------


def test_a_discard_records_the_reason_and_creates_nothing(rig):
    rig.to_recording()
    discard = Discard(DiscardReason.TOO_LONG, 12.0)
    rig.send(GestureDiscarded(discard))
    assert rig.state.snapshot.last_discard == discard
    assert rig.status is S.COUNTDOWN
    assert rig.jobs == []
    assert rig.store.read_samples(rig.session.session_id) == []
    assert rig.state.snapshot.latest_sample is None


# --- Gestures -----------------------------------------------------------------


def test_a_gesture_makes_one_accepted_sample_and_counts_down_at_once(rig):
    rig.to_recording()
    rig.label("zigzag")  # a label change applies to the next gesture
    g = gesture()
    rig.send(GestureFound(g))
    assert rig.status is S.COUNTDOWN
    latest = rig.state.snapshot.latest_sample
    assert latest.saving is True and latest.label == "zigzag"
    assert len(rig.jobs) == 1

    rig.finish_jobs()
    samples = rig.store.read_samples(rig.session.session_id)
    assert len(samples) == 1
    sample = samples[0]
    assert sample.sample_id == latest.id
    assert sample.label == "zigzag" and sample.status.value == "accepted"
    assert sample.handedness is Handedness.LEFT
    assert sample.frame_size == (640, 480)
    assert sample.positions.time_s[:3] == pytest.approx([0.0, 0.1, 0.2])
    assert len(sample.positions.horizontal) == len(g.positions)
    # the clip runs from preS before to postS after the gesture
    frames, fps, path = rig.clips.submitted[0]
    assert fps == 25.0
    assert frames[0].timestamp_s == pytest.approx(8.0, abs=0.11)
    assert frames[-1].timestamp_s == pytest.approx(13.5, abs=0.11)
    assert sample.video.file == f"videos/{sample.sample_id}.mp4"
    assert sample.video.gesture_start_s == pytest.approx(
        10.0 - frames[0].timestamp_s
    )
    done = rig.state.snapshot.latest_sample
    assert done.saving is False and done.clip_available is True


def test_ready_waits_for_both_the_countdown_and_the_save(rig):
    rig.to_recording()
    rig.send(GestureFound(gesture()))
    rig.advance(3.5)  # the countdown is over, the sample is not saved
    assert rig.status is S.COUNTDOWN and not rig.engine.armed
    rig.finish_jobs()
    assert rig.status is S.READY and rig.engine.armed
    assert len(rig.store.read_samples(rig.session.session_id)) == 1


def test_ready_waits_for_the_countdown_when_the_save_is_quick(rig):
    rig.to_recording()
    rig.send(GestureFound(gesture()))
    rig.finish_jobs()
    assert rig.status is S.COUNTDOWN  # saved, but the countdown still runs
    rig.advance(3.0)
    assert rig.status is S.READY


def test_a_clip_failure_still_saves_the_sample_without_a_clip(rig):
    rig.clips.ok = False
    rig.to_recording()
    rig.send(GestureFound(gesture()))
    rig.finish_jobs()
    sample = rig.store.read_samples(rig.session.session_id)[0]
    assert sample.video is None
    assert rig.state.snapshot.latest_sample.clip_available is False
    assert rig.state.snapshot.latest_sample.saving is False


def test_no_buffered_frames_saves_without_a_clip(rig):
    rig.engine.frames = []
    rig.to_recording()
    rig.send(GestureFound(gesture()))
    rig.finish_jobs()
    assert rig.store.read_samples(rig.session.session_id)[0].video is None
    assert rig.clips.submitted == []


def test_a_failed_save_clears_the_latest_sample_and_carries_on(rig):
    rig.store.end_session(rig.session.session_id)  # the save will be refused
    rig.to_recording()
    rig.send(GestureFound(gesture()))
    rig.finish_jobs()
    assert rig.state.snapshot.latest_sample is None
    rig.advance(3.0)
    assert rig.status is S.READY


def test_sample_numbers_are_never_given_twice(rig):
    session_id = rig.session.session_id
    first = rig.controller._reserve_number(session_id)
    second = rig.controller._reserve_number(session_id)  # nothing saved yet
    assert (first, second) == (1, 2)
    rig.to_recording()
    rig.send(GestureFound(gesture()))
    rig.finish_jobs()
    sample = rig.store.read_samples(session_id)[0]
    assert sample.sample_id.endswith("0003")


def test_a_gesture_with_no_label_is_dropped_safely(rig):
    rig.to_recording()
    rig.state.update(Owner.CAPTURE_CONTROLLER, active_label=None)
    rig.send(GestureFound(gesture()))
    assert rig.jobs == [] and rig.status is S.COUNTDOWN


def test_results_in_other_states_are_ignored(rig):
    rig.label()
    rig.send(GestureFound(gesture()))
    rig.send(MotionStarted(1.0))
    assert rig.status is S.STOPPED and rig.jobs == []


# --- Pause and resume ---------------------------------------------------------


def test_pause_during_a_countdown_freezes_the_remaining_time(rig):
    rig.label()
    rig.send(Start())
    rig.advance(1.0)
    rig.send(Pause())
    capture = rig.state.snapshot.capture
    assert capture.state is S.PAUSED
    assert capture.remaining_s == pytest.approx(2.0)
    assert rig.engine.armed is False
    rig.advance(10.0)  # time passes while paused
    assert rig.status is S.PAUSED
    rig.send(Resume())
    assert rig.status is S.COUNTDOWN
    rig.advance(1.9)
    assert rig.status is S.COUNTDOWN
    rig.advance(0.2)
    assert rig.status is S.READY


def test_pause_while_ready_resumes_with_a_fresh_countdown(rig):
    rig.to_ready()
    rig.send(Pause())
    assert rig.status is S.PAUSED and not rig.engine.armed
    assert rig.state.snapshot.capture.remaining_s is None
    rig.send(Resume())
    capture = rig.state.snapshot.capture
    assert capture.state is S.COUNTDOWN
    assert capture.countdown_ends_at == pytest.approx(1_700_000_103.0)
    rig.advance(3.0)
    assert rig.status is S.READY


def test_pause_during_recording_waits_for_the_result(rig):
    rig.to_recording()
    rig.send(Pause())
    assert rig.status is S.RECORDING  # not yet
    rig.send(GestureFound(gesture()))
    assert rig.status is S.PAUSED
    assert rig.state.snapshot.capture.remaining_s == pytest.approx(3.0)
    assert len(rig.jobs) == 1  # the gesture was still kept
    rig.send(Resume())
    assert rig.status is S.COUNTDOWN


def test_pause_during_recording_then_a_discard(rig):
    rig.to_recording()
    rig.send(Pause())
    rig.send(GestureDiscarded(Discard(DiscardReason.TOO_SMALL, 11.0)))
    assert rig.status is S.PAUSED
    assert rig.state.snapshot.last_discard.reason is DiscardReason.TOO_SMALL


def test_pause_and_resume_in_other_states_do_nothing(rig):
    rig.send(Pause())
    rig.send(Resume())
    assert rig.status is S.STOPPED


def test_pausing_while_the_save_runs_keeps_the_sample_marked_saving(rig):
    rig.to_recording()
    rig.send(GestureFound(gesture()))
    rig.send(Pause())
    assert rig.status is S.PAUSED
    assert rig.state.snapshot.latest_sample.saving is True  # review waits
    rig.finish_jobs()
    assert rig.state.snapshot.latest_sample.saving is False
    assert rig.status is S.PAUSED


# --- Ending -------------------------------------------------------------------


@pytest.mark.parametrize(
    "where", ["stopped", "countdown", "ready", "recording", "paused"]
)
def test_the_end_of_the_session_stops_from_any_state(rig, where):
    rig.label()
    if where == "countdown":
        rig.send(Start())
    elif where == "ready":
        rig.to_ready()
    elif where == "recording":
        rig.to_recording()
    elif where == "paused":
        rig.to_ready()
        rig.send(Pause())
    done = Future()
    rig.send(Stop(done))
    assert rig.status is S.STOPPED and done.done()
    assert rig.engine.armed is False
    rig.advance(10.0)
    assert rig.status is S.STOPPED


def test_ending_waits_for_a_sample_being_saved_and_loses_nothing(rig):
    rig.to_recording()
    rig.send(GestureFound(gesture()))
    done = Future()
    rig.send(Stop(done))
    assert rig.status is S.STOPPED and not done.done()
    rig.finish_jobs()
    assert done.done()
    assert len(rig.store.read_samples(rig.session.session_id)) == 1
    assert rig.status is S.STOPPED  # a late save does not restart capture


def test_stop_called_without_the_loop_runs_directly(rig):
    rig.to_ready()
    rig.controller.stop()
    assert rig.status is S.STOPPED


# --- Requests -----------------------------------------------------------------


def test_the_label_must_exist(rig):
    assert (
        rig.client.put(
            "/api/recording/label", json={"label": "nope"}
        ).status_code
        == 400
    )
    ok = rig.client.put("/api/recording/label", json={"label": "zigzag"})
    assert ok.status_code == 204
    rig.controller.handle(rig.controller._queue.get())
    assert rig.state.snapshot.active_label == "zigzag"


def test_start_needs_a_capture_session_and_a_label(rig):
    rig.state.update(Owner.SESSION_SERVICE, session=None)
    refused = rig.client.post("/api/recording/start")
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "no_session"
    rig.state.update(
        Owner.SESSION_SERVICE,
        session=SessionInfo("x", "n", SessionRole.REVIEW),
    )
    assert rig.client.post("/api/recording/start").status_code == 409
    rig.state.update(
        Owner.SESSION_SERVICE,
        session=SessionInfo(rig.session.session_id, "n", SessionRole.CAPTURE),
    )
    assert rig.client.post("/api/recording/start").status_code == 400
    rig.label()
    assert rig.client.post("/api/recording/start").status_code == 204
    assert isinstance(rig.controller._queue.get(), Start)


def test_pause_and_resume_requests_check_the_state(rig):
    assert rig.client.post("/api/recording/pause").status_code == 409
    assert rig.client.post("/api/recording/resume").status_code == 409
    rig.to_ready()
    assert rig.client.post("/api/recording/start").status_code == 409
    assert rig.client.post("/api/recording/pause").status_code == 204
    rig.controller.handle(rig.controller._queue.get())
    assert rig.client.post("/api/recording/resume").status_code == 204
    assert isinstance(rig.controller._queue.get(), Resume)


def test_the_loop_runs_a_whole_cycle_on_a_real_thread(tmp_path):
    import time

    rig = Rig(tmp_path)
    rig.controller._countdown_s = 0.1
    rig.controller._clock = Clock()  # real time
    rig.controller._run_job = lambda work: work()  # saved at once
    rig.controller.start_loop()
    try:
        rig.controller.post(
            __import__("wand_collect.controller").controller.SetLabel("circle")
        )
        rig.controller.post(Start())
        deadline = time.time() + 3
        while rig.status is not S.READY and time.time() < deadline:
            time.sleep(0.01)
        assert rig.status is S.READY
        rig.controller.on_engine_message(MotionStarted(1.0))
        rig.controller.on_engine_message(GestureFound(gesture()))
        while rig.status is not S.READY and time.time() < deadline + 3:
            time.sleep(0.01)
        while not rig.store.read_samples(rig.session.session_id):
            assert time.time() < deadline + 3
            time.sleep(0.01)
        rig.controller.stop()
        assert rig.status is S.STOPPED
    finally:
        rig.controller.shutdown()
