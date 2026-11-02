import queue
import threading
import time

import cv2
import numpy as np
import pytest

from wand_collect.engine import (
    CaptureEngine,
    GestureDiscarded,
    GestureFound,
    MotionStarted,
    RingBuffer,
)
from wand_collect.state import (
    ApplicationState,
    Owner,
    SettingsState,
)
from wand_core.settings import MotionSettings, VisionSettings
from wand_core.sources import (
    CameraMode,
    CameraOpenError,
    Frame,
    FrameSource,
    VideoFileSource,
)
from wand_core.testing.synthetic import (
    SceneStyle,
    circle_path,
    line_path,
    render_frame,
    write_video,
)
from wand_core.types import SegmenterState

FPS = 30.0
STYLE = SceneStyle()


class QueueSource(FrameSource):
    """A frame source fed by the test, one frame at a time."""

    def __init__(self, size=(640, 480), fps=FPS):
        self.frames: queue.Queue = queue.Queue()
        self._size = size
        self._fps = fps
        self.opened = False
        self.closed = 0

    def open(self):
        self.opened = True

    def read(self):
        try:
            return self.frames.get(timeout=0.02)
        except queue.Empty:
            return None

    def close(self):
        self.closed += 1

    @property
    def frame_size(self):
        return self._size

    @property
    def nominal_fps(self):
        return self._fps

    def push(self, image, timestamp_s):
        self.frames.put(Frame(image, timestamp_s))


class Rig:
    """An engine with a queue source and a recorder of its messages."""

    def __init__(self, **engine_args):
        self.state = ApplicationState()
        self.messages = []
        self.readings = []
        self.engine = CaptureEngine(
            self.state, receiver=self.messages.append, **engine_args
        )
        self.engine.add_motion_listener(self.readings.append)
        self.source = QueueSource()
        self.t = 0.0
        self.engine.start()
        self.engine.open_source(self.source, "test", 0).result(2)

    def feed(self, center, count=1):
        for _ in range(count):
            self.source.push(render_frame(STYLE, center), self.t)
            self.t += 1 / FPS

    def feed_path(self, points):
        for point in points:
            self.feed((float(point[0]), float(point[1])))

    def wait_frames(self, number, timeout=5):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.engine.latest_frame()[0] >= number:
                return
            time.sleep(0.005)
        raise AssertionError(
            f"engine stopped at frame {self.engine.latest_frame()[0]}"
        )

    def close(self):
        self.engine.stop()


@pytest.fixture
def rig():
    rig = Rig()
    yield rig
    rig.close()


# --- Ring buffer ------------------------------------------------------------


def test_ring_buffer_keeps_the_recent_window_and_returns_ranges():
    buffer = RingBuffer(max_seconds=8.0)
    for i in range(600):  # 20 seconds at 30 fps
        buffer.add(i / FPS, b"x")
    assert 8 * FPS <= len(buffer) <= 8 * FPS + 2
    frames = buffer.frames_between(15.0, 16.0)
    stamps = [f.timestamp_s for f in frames]
    assert stamps[0] == pytest.approx(15.0, abs=1 / FPS)
    assert stamps[-1] == pytest.approx(16.0, abs=1 / FPS)
    assert stamps == sorted(stamps)
    assert buffer.frames_between(0.0, 5.0) == []  # already dropped
    buffer.set_max_seconds(2.0)
    assert len(buffer) <= 2 * FPS + 2


def test_buffer_size_follows_padding_and_max_duration(rig):
    rig.feed((0.5, 0.5))
    rig.wait_frames(1)
    assert rig.engine.buffer.max_seconds == pytest.approx(2.0 + 4.0 + 2.0)
    rig.state.update(
        Owner.CALIBRATION_SERVICE,
        settings=SettingsState(motion=MotionSettings(max_duration_s=6.0)),
    )
    rig.feed((0.5, 0.5))
    rig.wait_frames(2)
    assert rig.engine.buffer.max_seconds == pytest.approx(10.0)


def test_buffered_frames_are_jpegs_with_timestamps(rig):
    rig.feed((0.5, 0.5), count=5)
    rig.wait_frames(5)
    frames = rig.engine.frames_between(0.0, 10.0)
    assert len(frames) == 5
    image = cv2.imdecode(
        np.frombuffer(frames[0].jpeg, np.uint8), cv2.IMREAD_COLOR
    )
    assert image.shape == (480, 640, 3)
    assert frames[1].timestamp_s == pytest.approx(1 / FPS)


# --- Publishing -------------------------------------------------------------


def test_annotated_and_mask_frames_are_published_with_numbers(rig):
    rig.feed((0.5, 0.5))
    rig.wait_frames(1)
    number, annotated = rig.engine.latest_frame("camera")
    mask_number, mask = rig.engine.latest_frame("mask")
    assert number == mask_number == 1
    assert annotated.shape == (480, 640, 3)
    # The tip marker is drawn on a copy: the disk's ring is green.
    assert tuple(annotated[240 - 19, 320]) != tuple(
        render_frame(STYLE, (0.5, 0.5))[240 - 19, 320]
    )
    assert mask.shape == (480, 640, 3)
    assert set(np.unique(mask)) <= {0, 255}
    assert mask[240, 320].tolist() == [255, 255, 255]


def test_caller_can_wait_for_a_newer_frame(rig):
    assert rig.engine.wait_for_frame("camera", after=0, timeout=0.05) is None
    rig.feed((0.5, 0.5))
    result = rig.engine.wait_for_frame("camera", after=0, timeout=2)
    assert result[0] == 1
    assert rig.engine.wait_for_frame("camera", after=1, timeout=0.05) is None
    rig.feed((0.5, 0.5))
    assert rig.engine.wait_for_frame("camera", after=1, timeout=2)[0] == 2


def test_a_motion_reading_is_published_for_every_frame(rig):
    rig.feed_path(circle_path(20))
    rig.wait_frames(20)
    assert len(rig.readings) == 20
    reading = rig.readings[-1]
    assert reading.start_speed == 0.25
    assert reading.end_speed == 0.15
    assert reading.timestamp_s == pytest.approx(19 / FPS)
    assert rig.engine.latest_motion == reading
    assert max(r.speed for r in rig.readings) > 0.25


def test_a_slow_consumer_never_delays_the_loop(rig):
    started = threading.Event()

    def slow_consumer():
        started.set()
        rig.engine.wait_for_frame("camera", after=0, timeout=2)
        time.sleep(1.5)  # holds the frame; the loop must carry on

    consumer = threading.Thread(target=slow_consumer)
    consumer.start()
    started.wait()
    begin = time.time()
    rig.feed_path(circle_path(90))
    rig.wait_frames(90, timeout=1.2)
    assert time.time() - begin < 1.2
    consumer.join()


# --- Arming, messages -------------------------------------------------------


def still_then_circle(rig, turns_seconds=1.5):
    rig.feed((0.3125 + 0.1875, 0.5), count=10)
    rig.feed_path(circle_path(round(turns_seconds * FPS), center=(0.3125, 0.5)))
    rig.feed((0.5, 0.5), count=int(1.2 * FPS))


def test_nothing_is_reported_until_armed_but_speed_always_is(rig):
    still_then_circle(rig)
    rig.wait_frames(10 + 45 + 36)
    assert rig.messages == []
    assert max(r.speed for r in rig.readings) > 0.25
    assert all(r.state is SegmenterState.IDLE for r in rig.readings)


def test_armed_engine_reports_motion_start_then_the_gesture(rig):
    rig.engine.arm().result(2)
    still_then_circle(rig)
    rig.wait_frames(10 + 45 + 36)
    kinds = [type(m) for m in rig.messages]
    assert kinds == [MotionStarted, GestureFound]
    gesture = rig.messages[1].gesture
    assert 40 <= len(gesture.positions) <= 50
    assert (gesture.frame_width, gesture.frame_height) == (640, 480)
    assert rig.messages[0].timestamp_s < gesture.end_timestamp_s


def test_discards_are_reported(rig):
    rig.engine.arm().result(2)
    rig.feed((0.3, 0.5), count=10)
    rig.feed_path(line_path(3, (0.3, 0.5), (0.6, 0.5)))  # a flick
    rig.feed((0.6, 0.5), count=30)
    rig.wait_frames(43)
    assert [type(m) for m in rig.messages] == [MotionStarted, GestureDiscarded]
    assert rig.messages[1].discard.reason.value == "too_short"


def test_disarm_stops_reporting(rig):
    rig.engine.arm().result(2)
    rig.engine.disarm().result(2)
    still_then_circle(rig)
    rig.wait_frames(91)
    assert rig.messages == []


def test_a_failing_receiver_does_not_stop_the_loop():
    rig = Rig()
    rig.engine.set_receiver(lambda m: 1 / 0)
    rig.engine.arm().result(2)
    still_then_circle(rig)
    rig.wait_frames(91)
    assert len(rig.readings) == 91
    rig.close()


# --- Settings ---------------------------------------------------------------


def test_new_vision_settings_apply_from_the_next_frame(rig):
    rig.feed((0.5, 0.5))
    rig.wait_frames(1)
    assert rig.engine.latest_detection.found
    blue = VisionSettings(hue_center=105, hue_half_width=10)
    rig.state.update(
        Owner.CALIBRATION_SERVICE, settings=SettingsState(vision=blue)
    )
    rig.feed((0.5, 0.5))
    rig.wait_frames(2)
    assert not rig.engine.latest_detection.found


def test_new_motion_settings_reset_the_segmenter(rig):
    rig.engine.arm().result(2)
    rig.feed((0.3, 0.5), count=5)
    rig.feed_path(line_path(10, (0.3, 0.5), (0.8, 0.5)))
    rig.wait_frames(15)
    assert rig.readings[-1].state is SegmenterState.MOTION
    rig.state.update(
        Owner.CALIBRATION_SERVICE,
        settings=SettingsState(motion=MotionSettings(start_speed=0.5)),
    )
    rig.feed((0.8, 0.5))
    rig.wait_frames(16)
    assert rig.readings[-1].state is SegmenterState.IDLE
    assert rig.readings[-1].start_speed == 0.5


# --- Camera and the state ---------------------------------------------------


def test_opening_writes_the_camera_to_the_state(rig):
    camera = rig.state.snapshot.camera
    assert camera.device == "test"
    assert camera.index == 0
    assert camera.actual == CameraMode(640, 480, FPS)


def test_measured_frame_rate_is_written_after_a_couple_of_seconds():
    rig = Rig()
    # Frames arrive every 1/25 s of timestamp, whatever the camera claimed.
    for i in range(80):
        rig.source.push(render_frame(STYLE, (0.5, 0.5)), i / 25.0)
    rig.wait_frames(80)
    assert rig.state.snapshot.camera.actual.fps == pytest.approx(25.0)
    assert rig.state.snapshot.camera.requested.fps == FPS
    rig.close()


def test_a_camera_that_cannot_open_returns_the_error_and_clears_the_state():
    attempts = []

    def factory(index, width, height, fps):
        attempts.append(index)
        raise CameraOpenError(f"cannot open camera {index}")

    rig = Rig(camera_factory=factory)
    assert rig.state.snapshot.camera.device == "test"
    with pytest.raises(CameraOpenError, match="camera 7"):
        rig.engine.open_camera(7).result(2)
    assert rig.state.snapshot.camera.device is None
    assert rig.source.closed >= 1  # the old source was released
    # The engine keeps running and can open another source.
    other = QueueSource()
    rig.engine.open_source(other, "second", 1).result(2)
    assert rig.state.snapshot.camera.device == "second"
    other.push(render_frame(STYLE, (0.5, 0.5)), 0.0)
    rig.wait_frames(1)
    rig.close()
    assert attempts == [7]


def test_open_camera_uses_the_factory_with_the_requested_mode():
    seen = []

    def factory(index, width, height, fps):
        seen.append((index, width, height, fps))
        return QueueSource((width, height), fps)

    rig = Rig(camera_factory=factory)
    rig.engine.open_camera(2, 1280, 720, 24).result(2)
    assert seen == [(2, 1280, 720, 24)]
    assert rig.state.snapshot.camera.index == 2
    rig.close()


def test_close_camera_clears_the_state(rig):
    rig.engine.close_camera().result(2)
    assert rig.state.snapshot.camera.device is None
    assert rig.source.closed >= 1


def test_stop_releases_the_source():
    rig = Rig()
    rig.close()
    assert rig.source.closed >= 1
    assert rig.state.snapshot.camera.device is None


# --- A recorded video -------------------------------------------------------


def test_runs_on_a_recorded_video(tmp_path):
    path = np.vstack(
        [
            np.tile([0.5, 0.5], (10, 1)),
            circle_path(45, center=(0.3125, 0.5)),
            np.tile([0.5, 0.5], (36, 1)),
        ]
    )
    file = tmp_path / "clip.avi"
    write_video(path, file, STYLE, fps=FPS)
    state = ApplicationState()
    messages = []
    engine = CaptureEngine(state, receiver=messages.append)
    engine.start()
    engine.arm().result(2)
    engine.open_source(VideoFileSource(file), "clip.avi").result(2)
    assert engine.finished.wait(10)
    engine.stop()
    assert [type(m) for m in messages] == [MotionStarted, GestureFound]
    assert state.snapshot.camera.device is None  # released at stop


# --- Mirrored preview -------------------------------------------------------


def disk_columns(image):
    """The columns where the orange disk (or its white mask) is, as a mean.

    Only rows below the label text are looked at.
    """
    image = image[60:]
    orange = (image[:, :, 2] > 150) & (image[:, :, 1] < 200)
    white = image.min(axis=2) > 200
    hits = orange | white
    return np.nonzero(hits.any(axis=0))[0].mean() / image.shape[1]


def test_the_preview_is_not_mirrored_by_default(rig):
    rig.feed((0.2, 0.5))
    rig.wait_frames(1)
    assert disk_columns(rig.engine.latest_frame("camera")[1]) < 0.3
    assert disk_columns(rig.engine.latest_frame("mask")[1]) < 0.3


def test_a_mirrored_preview_flips_the_picture_and_the_mask_only():
    rig = Rig(mirror_preview=True)
    rig.feed((0.2, 0.5))
    rig.wait_frames(1)
    # What is shown: the disk on the right, as in a mirror.
    assert disk_columns(rig.engine.latest_frame("camera")[1]) > 0.7
    assert disk_columns(rig.engine.latest_frame("mask")[1]) > 0.7
    # What is measured and kept: as the camera saw it.
    assert rig.engine.latest_detection.horizontal == pytest.approx(
        0.2, abs=0.01
    )
    stored = rig.engine.frames_between(0.0, 1.0)[0]
    image = cv2.imdecode(np.frombuffer(stored.jpeg, np.uint8), cv2.IMREAD_COLOR)
    assert disk_columns(image) < 0.3
    rig.close()


def test_the_marker_follows_the_mirrored_disk():
    rig = Rig(mirror_preview=True)
    rig.feed((0.2, 0.5))
    rig.wait_frames(1)
    shown = rig.engine.latest_frame("camera")[1]
    green = (
        (shown[:, :, 1] > 200) & (shown[:, :, 2] < 80) & (shown[:, :, 0] < 80)
    )
    assert np.nonzero(green.any(axis=0))[0].mean() / 640 > 0.7
    rig.close()


def test_mirroring_does_not_mirror_the_label_text():
    plain, mirrored = Rig(), Rig(mirror_preview=True)
    for rig in (plain, mirrored):
        rig.feed(None)  # no ball: nothing but the background and the label
        rig.wait_frames(1)
    # A flipped background is the same picture, so the images are equal only
    # if the text was drawn after the flip and still reads normally.
    assert np.array_equal(
        plain.engine.latest_frame("camera")[1],
        mirrored.engine.latest_frame("camera")[1],
    )
    plain.close()
    mirrored.close()
