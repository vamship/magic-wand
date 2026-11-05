"""DC-V1: the whole application, run through its HTTP interface.

A recorded video stands in for the camera. A gate lets the test release the
video's frames a few at a time, so each gesture arrives when the application
is ready for it (the countdown runs on the wall clock, the video on its own).
"""

import asyncio
import json
import shutil
import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from wand_collect.app import build_application
from wand_collect.state import CaptureStatus
from wand_collect.wiring import assemble
from wand_core.sources import (
    CameraInfo,
    Frame,
    FrameSource,
    VideoFileSource,
)
from wand_core.testing.synthetic import circle_path, write_video

REPO_CONFIG = Path(__file__).resolve().parents[2] / "config"
COUNTDOWN_S = 0.3
PADDING_S = 0.3
FPS = 30
TRAIL = 30  # idle frames after a movement: end hold, post padding, margin


class Timeline:
    """The positions of the disk, frame by frame, built segment by segment."""

    def __init__(self, start=(0.5, 0.5)):
        self.points = [start]
        self.marks = {}

    def _mark(self, name, first):
        self.marks[name] = (first, len(self.points))

    def still(self, name, frames):
        first = len(self.points)
        self.points += [self.points[-1]] * frames
        self._mark(name, first)

    def circle(self, name, frames, radius=0.25):
        """A whole circle that starts and ends where the disk is."""
        first = len(self.points)
        x, y = self.points[-1]
        center = (x - radius * 0.75, y)
        ring = circle_path(frames, center, radius)
        self.points += [tuple(p) for p in ring[1:]] + [self.points[-1]]
        self._mark(name, first)

    def line(self, name, frames, dx):
        first = len(self.points)
        x, y = self.points[-1]
        out = [
            (x + dx * i / (frames // 2), y) for i in range(1, frames // 2 + 1)
        ]
        back = list(reversed(out[:-1])) + [(x, y)]
        self.points += out + back
        self._mark(name, first)

    def write(self, file):
        write_video(np.array(self.points), file, fps=FPS)


class GatedSource(FrameSource):
    """Frames of a recorded video, handed out only as far as released."""

    def __init__(self, path):
        self._inner = VideoFileSource(path)
        self.released = 0
        self.read_count = 0

    def open(self):
        self._inner.open()

    def close(self):
        self._inner.close()

    @property
    def frame_size(self):
        return self._inner.frame_size

    @property
    def nominal_fps(self):
        return self._inner.nominal_fps

    def read(self) -> Frame | None:
        if self.read_count >= self.released:
            time.sleep(0.003)
            return None
        frame = self._inner.read()
        self.read_count += 1
        return frame

    def release(self, frames):
        self.released += frames

    @property
    def caught_up(self):
        return self.read_count >= self.released


def wait_until(condition, what, timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = condition()
        if value:
            return value
        time.sleep(0.01)
    raise AssertionError(f"timed out waiting for {what}")


class Run:
    """One start of the application, on a video, with a test client."""

    def __init__(self, tmp_path, video, device=None):
        self.source = GatedSource(video)
        self.config = tmp_path / "config"
        self.application = build_application(
            self.config,
            tmp_path / "data",
            open_camera=False,
            camera_factory=lambda *args: self.source,
        )
        self.device = device
        self.assembled = assemble(
            self.application,
            camera_lister=lambda: (
                [CameraInfo(0, self.device, self.device)] if self.device else []
            ),
            static_dir=None,
        )
        self.state = self.application.state
        self.history = []  # (monotonic time, capture state) per change
        self.state.subscribe(
            lambda s: self.history.append((time.monotonic(), s.capture.state))
        )
        self.client = TestClient(self.assembled.app)

    def __enter__(self):
        self.client.__enter__()
        return self

    def __exit__(self, *exc):
        self.client.__exit__(*exc)

    def open_camera(self):
        self.application.engine.open_camera(0, 640, 480, 30).result(5)
        self.device = self.state.snapshot.camera.device

    def play(self, frames):
        self.source.release(frames)
        wait_until(lambda: self.source.caught_up, "the frames to be read")

    def status(self):
        return self.state.snapshot.capture.state

    def api(self, method, path, expect=(200, 201, 204), **kwargs):
        response = self.client.request(method, "/api" + path, **kwargs)
        assert response.status_code in expect, (path, response.text)
        return response

    def wait_ready(self):
        """Wait for READY in the state and in what the test has recorded."""
        wait_until(lambda: self.status() is CaptureStatus.READY, "READY")
        wait_until(
            lambda: self.states()[-1] is CaptureStatus.READY, "READY seen"
        )

    def states(self):
        """The capture states visited, one entry per change."""
        seen = []
        for _, state in self.history:
            if not seen or seen[-1] != state:
                seen.append(state)
        return seen


@pytest.fixture
def config(tmp_path):
    shutil.copytree(REPO_CONFIG, tmp_path / "config")
    path = tmp_path / "config" / "data-collection.yaml"
    text = path.read_text()
    text = text.replace("countdownS: 3.0", f"countdownS: {COUNTDOWN_S}")
    text = text.replace("preS: 2.0", f"preS: {PADDING_S}")
    text = text.replace("postS: 2.0", f"postS: {PADDING_S}")
    text = text.replace("mirrorPreview: true", "mirrorPreview: false")
    path.write_text(text)
    return tmp_path


def sample_lines(run, session_id):
    path = run.application.store.session_dir(session_id) / "samples.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


def drain(hub, client):
    """The events waiting for one browser (run on the server's own loop)."""
    events = []
    while True:
        event = asyncio.run_coroutine_threadsafe(
            client.next(0.02), hub._loop
        ).result(5)
        if event is None:
            return events
        events.append(event)


def last_state(events):
    states = [json.loads(data) for name, data in events if name == "state"]
    return states[-1] if states else None


def settle(run, quiet=0.15):
    """Wait until the state has not changed for a moment."""
    last = None
    stable_since = time.time()
    while time.time() - stable_since < quiet:
        now = run.state.snapshot
        if now != last:
            last, stable_since = now, time.time()
        time.sleep(0.01)


def test_the_whole_flow_through_the_http_interface(config):
    tmp_path = config
    first = Timeline()
    first.still("pre", 30)
    first.circle("g1", 45)
    first.still("t1", TRAIL)
    first.line("d1", 4, 0.3)  # a quick flick: too short
    first.still("t2", TRAIL)
    first.circle("g2", 45)
    first.still("t3", TRAIL)
    first.circle("d2", 12, radius=0.03)  # a tiny circle: too small
    first.still("t4", TRAIL)
    first.circle("g3", 45)
    first.still("t5", TRAIL)
    first.write(tmp_path / "first.avi")

    second = Timeline()
    second.still("pre", 20)
    second.circle("g4", 45)
    second.still("t1", TRAIL)
    second.write(tmp_path / "second.avi")

    def span(timeline, *names):
        return sum(timeline.marks[n][1] - timeline.marks[n][0] for n in names)

    # --- The first run: calibrate, record, review -------------------------
    with Run(tmp_path, tmp_path / "first.avi") as run:
        hub = run.assembled.app.state.hub
        watcher_one, watcher_two = hub.connect(), hub.connect()
        run.open_camera()
        run.play(span(first, "pre"))
        before = run.state.snapshot.settings.vision

        # Calibrate on the frozen frame by clicking the disk.
        assert run.api("POST", "/calibration/freeze").status_code == 200
        clicked = run.api(
            "POST",
            "/calibration/clicks",
            json={"points": [{"horizontal": 0.5, "vertical": 0.5}]},
        ).json()
        assert clicked["tip"]["found"] is True
        calibrated = run.state.snapshot.settings.vision
        assert calibrated != before
        run.api("PUT", "/settings", json={"vision": {"blurSize": 3}})
        calibrated = run.state.snapshot.settings.vision
        assert calibrated.blur_size == 3

        # Start the session; settings become locked.
        started = run.api(
            "POST",
            "/sessions",
            json={"author": "tester", "handedness": "right", "name": "v1"},
        ).json()
        session_id = started["id"]
        assert run.state.snapshot.session.role.value == "capture"
        locked = run.api(
            "PUT", "/settings", json={"vision": {}}, expect=(400, 409)
        )
        assert locked.status_code in (400, 409)
        assert (
            run.client.post(
                "/api/sessions", json={"author": "x", "handedness": "left"}
            ).status_code
            == 409
        )

        # Start capturing: a countdown, then ready.
        run.api("PUT", "/recording/label", json={"label": "spell_one"})
        wait_until(
            lambda: run.state.snapshot.active_label == "spell_one", "label"
        )
        run.api("POST", "/recording/start")
        run.wait_ready()
        assert run.states()[-3:] == [
            CaptureStatus.STOPPED,
            CaptureStatus.COUNTDOWN,
            CaptureStatus.READY,
        ]
        assert last_state(drain(hub, watcher_one)) is not None
        drain(hub, watcher_two)

        def finish_gesture(index):
            run.play(span(first, f"t{index}"))
            wait_until(
                lambda: (
                    run.state.snapshot.latest_sample is not None
                    and not run.state.snapshot.latest_sample.saving
                ),
                "the sample to be saved",
            )
            run.wait_ready()

        def finish_discard(index, reason):
            run.play(span(first, f"t{index}"))
            wait_until(
                lambda: (
                    run.state.snapshot.last_discard is not None
                    and run.state.snapshot.last_discard.reason.value == reason
                ),
                f"the {reason} discard",
            )
            run.wait_ready()

        # Gesture 1.
        mark = len(run.history)
        run.play(span(first, "g1"))
        finish_gesture(1)
        assert run.states()[-4:] == [
            CaptureStatus.READY,
            CaptureStatus.RECORDING,
            CaptureStatus.COUNTDOWN,
            CaptureStatus.READY,
        ]
        assert run.state.snapshot.counts["spell_one"] == 1
        # N2: a cycle takes about the countdown (the replayed gesture is fast).
        entered = [
            t for t, s in run.history[mark:] if s is CaptureStatus.COUNTDOWN
        ]
        ready = [t for t, s in run.history[mark:] if s is CaptureStatus.READY]
        took = ready[0] - entered[0]
        assert COUNTDOWN_S * 0.9 <= took <= COUNTDOWN_S + 3.0

        # A discard creates nothing.
        run.play(span(first, "d1"))
        finish_discard(2, "too_short")
        assert len(sample_lines(run, session_id)) == 1
        assert run.state.snapshot.counts["spell_one"] == 1

        # Gesture 2, a discard, gesture 3.
        run.play(span(first, "g2"))
        finish_gesture(3)
        run.play(span(first, "d2"))
        finish_discard(4, "too_small")
        run.play(span(first, "g3"))
        finish_gesture(5)

        lines = sample_lines(run, session_id)
        assert len(lines) == 3  # three gestures; the two discards left nothing
        assert [line["label"] for line in lines] == ["spell_one"] * 3
        assert {line["status"] for line in lines} == {"accepted"}
        assert {line["handedness"] for line in lines} == {"right"}
        assert all(len(line["positions"]["horizontal"]) > 20 for line in lines)
        session_dir = run.application.store.session_dir(session_id)
        for line in lines:
            assert (session_dir / line["video"]["file"]).stat().st_size > 1000
            assert line["video"]["gestureStartS"] >= 0
        assert lines[1]["sampleId"].endswith("-0002")
        assert run.state.snapshot.counts["spell_one"] == 3

        settle(run)
        one, two = drain(hub, watcher_one), drain(hub, watcher_two)
        assert last_state(one) == last_state(two)
        assert last_state(one) == json.loads(run.state.snapshot.to_json())

        # Pause, then review: reject one sample and relabel another.
        run.api("POST", "/recording/pause")
        wait_until(lambda: run.status() is CaptureStatus.PAUSED, "PAUSED")
        listed = run.api(
            "GET", f"/samples?session={session_id}&order=capture"
        ).json()["items"]
        assert [i["label"] for i in listed] == ["spell_one"] * 3
        revision = run.state.snapshot.samples_revision
        run.api(
            "PATCH", f"/samples/{listed[1]['id']}", json={"status": "rejected"}
        )
        run.api(
            "PATCH", f"/samples/{listed[2]['id']}", json={"label": "spell_two"}
        )
        stored = {x["sampleId"]: x for x in sample_lines(run, session_id)}
        assert stored[listed[1]["id"]]["status"] == "rejected"
        assert stored[listed[2]["id"]]["label"] == "spell_two"
        assert stored[listed[0]["id"]]["status"] == "accepted"
        assert run.state.snapshot.samples_revision > revision
        assert dict(run.state.snapshot.counts) == {
            "spell_one": 1,
            "spell_two": 1,
        }
        overlay = run.api(
            "GET", f"/samples/{listed[0]['id']}/image?mode=overlay"
        )
        assert overlay.headers["content-type"] == "image/png"

        # Resume with a different label: nothing is lost, capture carries on.
        run.api("PUT", "/recording/label", json={"label": "spell_three"})
        run.api("POST", "/recording/resume")
        run.wait_ready()
        assert run.state.snapshot.active_label == "spell_three"
        settle(run)
        one, two = drain(hub, watcher_one), drain(hub, watcher_two)
        assert last_state(one) == last_state(two)
        assert last_state(one)["capture"]["state"] == "READY"
        recorded_vision = run.state.snapshot.settings.vision
        # The application stops mid-session; the session stays open on disk.
    assert run.application.store.get_session(session_id).ended_at is None

    # --- The second run: resume the open session --------------------------
    with Run(tmp_path, tmp_path / "second.avi", device=run.device) as again:
        listed = again.api("GET", "/sessions").json()
        assert [(s["id"], s["open"], s["sampleCount"]) for s in listed] == [
            (session_id, True, 3)
        ]
        assert again.state.snapshot.settings.vision != recorded_vision
        resumed = again.api(
            "POST", f"/sessions/{session_id}/load?mode=resume"
        ).json()
        assert resumed["role"] == "capture" and resumed["warnings"] == []
        assert (
            again.state.snapshot.settings.vision == recorded_vision
        )  # the recorded
        again.play(span(second, "pre"))
        again.api("PUT", "/recording/label", json={"label": "spell_three"})
        wait_until(lambda: again.state.snapshot.active_label, "label")
        again.api("POST", "/recording/start")
        again.wait_ready()
        again.play(span(second, "g4"))
        again.play(span(second, "t1"))
        wait_until(
            lambda: (
                again.state.snapshot.latest_sample is not None
                and not again.state.snapshot.latest_sample.saving
            ),
            "the sample after the resume",
        )
        lines = sample_lines(again, session_id)
        assert len(lines) == 4
        assert lines[3]["sampleId"].endswith("-0004")  # numbering continued
        assert lines[3]["label"] == "spell_three"
        assert (
            again.application.store.get_session(
                session_id
            ).highest_sample_number
            == 4
        )

        # End the session: resume is refused, review works, edits still work.
        again.api("POST", "/sessions/current/end")
        assert again.state.snapshot.session is None
        assert again.status() is CaptureStatus.STOPPED
        assert again.application.store.get_session(session_id).ended_at
        refused = again.client.post(
            f"/api/sessions/{session_id}/load?mode=resume"
        )
        assert refused.status_code == 409
        assert refused.json()["error"]["code"] == "session_ended"
        review = again.api(
            "POST", f"/sessions/{session_id}/load?mode=review"
        ).json()
        assert review["role"] == "review"
        sample = again.api("GET", f"/samples?session={session_id}").json()[
            "items"
        ][0]
        again.api(
            "PATCH", f"/samples/{sample['id']}", json={"status": "rejected"}
        )
        assert (
            again.application.store.get_sample(sample["id"]).status.value
            == "rejected"
        )
