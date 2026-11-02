"""Capture Engine: the only owner of the camera.

One thread runs a loop that turns frames into tip detections and gestures,
keeps recent frames for video clips and publishes what the rest of the
application needs. See ``data-collection/docs/design.md`` section 4.6.

Commands (open a camera, arm, ...) arrive on a queue and take effect between
frames. Settings are not commands: the engine reads them from the Application
State at the start of every frame.

Callbacks (the receiver of results, motion listeners) run on the engine
thread and must not block; the consumers of frames wait on a condition and
never delay the loop.
"""

from __future__ import annotations

import bisect
import logging
import queue
import threading
from collections import deque
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from wand_collect.state import (
    ApplicationState,
    CameraState,
    Owner,
)
from wand_core.motion import Segmenter
from wand_core.sources import (
    CameraMode,
    CameraSource,
    Frame,
    FrameSource,
    FrameSourceError,
    VideoFileSource,
    camera_name,
)
from wand_core.types import (
    Discard,
    Gesture,
    SegmenterState,
    SegmenterUpdate,
    TipDetection,
)
from wand_core.vision import Tracker

logger = logging.getLogger(__name__)

VIEWS = ("camera", "mask")
FPS_MEASURE_SECONDS = 2.0
IDLE_WAIT_S = 0.05
JPEG_QUALITY = 85


# --- Messages and readings --------------------------------------------------


@dataclass(frozen=True)
class MotionStarted:
    timestamp_s: float


@dataclass(frozen=True)
class GestureFound:
    gesture: Gesture


@dataclass(frozen=True)
class GestureDiscarded:
    discard: Discard


@dataclass(frozen=True)
class MotionReading:
    """Published for every frame (speeds in frame-heights per second)."""

    timestamp_s: float
    speed: float
    moving: bool
    state: SegmenterState
    start_speed: float
    end_speed: float


@dataclass(frozen=True)
class BufferedFrame:
    timestamp_s: float
    jpeg: bytes


# --- Ring buffer ------------------------------------------------------------


class RingBuffer:
    """Recent JPEG-compressed frames with their timestamps."""

    def __init__(self, max_seconds: float) -> None:
        self._max_seconds = max_seconds
        self._frames: deque[BufferedFrame] = deque()
        self._lock = threading.Lock()

    @property
    def max_seconds(self) -> float:
        return self._max_seconds

    def set_max_seconds(self, seconds: float) -> None:
        with self._lock:
            self._max_seconds = seconds
            self._trim()

    def add(self, timestamp_s: float, jpeg: bytes) -> None:
        with self._lock:
            self._frames.append(BufferedFrame(timestamp_s, jpeg))
            self._trim()

    def clear(self) -> None:
        with self._lock:
            self._frames.clear()

    def __len__(self) -> int:
        return len(self._frames)

    def frames_between(
        self, start_s: float, end_s: float
    ) -> list[BufferedFrame]:
        """Frames with ``start_s <= timestamp <= end_s``, oldest first."""
        with self._lock:
            frames = list(self._frames)
        stamps = [f.timestamp_s for f in frames]
        low = bisect.bisect_left(stamps, start_s)
        high = bisect.bisect_right(stamps, end_s)
        return frames[low:high]

    def _trim(self) -> None:
        if not self._frames:
            return
        newest = self._frames[-1].timestamp_s
        while (
            len(self._frames) > 1
            and newest - self._frames[0].timestamp_s > self._max_seconds
        ):
            self._frames.popleft()


# --- Publishing frames ------------------------------------------------------


class FramePublisher:
    """The latest frame, with a number, and waiting for a newer one."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._number = 0
        self._image: np.ndarray | None = None

    def publish(self, image: np.ndarray) -> int:
        with self._condition:
            self._number += 1
            self._image = image
            self._condition.notify_all()
            return self._number

    def latest(self) -> tuple[int, np.ndarray | None]:
        with self._condition:
            return self._number, self._image

    def wait_newer(
        self, after: int, timeout: float | None = None
    ) -> tuple[int, np.ndarray] | None:
        """Block until a frame numbered above ``after`` exists."""
        with self._condition:
            ok = self._condition.wait_for(lambda: self._number > after, timeout)
            if not ok:
                return None
            return self._number, self._image


# --- The engine -------------------------------------------------------------

Receiver = Callable[[MotionStarted | GestureFound | GestureDiscarded], None]
CameraFactory = Callable[[int, int, int, float], FrameSource]


def _default_camera_factory(
    index: int, width: int, height: int, fps: float
) -> FrameSource:
    return CameraSource(index, width, height, fps)


class CaptureEngine:
    def __init__(
        self,
        state: ApplicationState,
        receiver: Receiver | None = None,
        clip_padding: tuple[float, float] = (2.0, 2.0),
        camera_factory: CameraFactory | None = None,
        mirror_preview: bool = False,
    ) -> None:
        self._state = state
        self._mirror = mirror_preview
        self._receiver = receiver
        self._motion_listeners: list[Callable[[MotionReading], None]] = []
        self._padding = clip_padding
        self._camera_factory = camera_factory or _default_camera_factory
        self._commands: queue.Queue[tuple[Callable[[], Any], Future]] = (
            queue.Queue()
        )
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.finished = threading.Event()  # a video file source ran out

        self._frames = {view: FramePublisher() for view in VIEWS}
        self.buffer = RingBuffer(sum(clip_padding) + 4.0)
        self.latest_motion: MotionReading | None = None
        self.latest_detection: TipDetection | None = None

        # Engine-thread state.
        self._source: FrameSource | None = None
        self._armed = False
        self._tracker: Tracker | None = None
        self._segmenter: Segmenter | None = None
        self._settings_seen: Any = None
        self._segmenter_state = SegmenterState.IDLE
        self._fps_stamps: list[float] = []
        self._fps_done = True

    # --- Lifecycle -------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="capture-engine", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the thread and release the camera."""
        if self._thread is None:
            return
        self._stop.set()
        self._thread.join(timeout=5)
        self._thread = None

    # --- Commands (take effect between frames) ---------------------------

    def _submit(self, work: Callable[[], Any]) -> Future:
        future: Future = Future()
        self._commands.put((work, future))
        return future

    def open_camera(
        self, index: int, width: int = 640, height: int = 480, fps: float = 30
    ) -> Future:
        """Open camera ``index``. The future holds the error on failure."""
        return self._submit(
            lambda: self._open(
                lambda: self._camera_factory(index, width, height, fps),
                camera_name(index) or f"index:{index}",
                index,
            )
        )

    def open_source(
        self,
        source: FrameSource,
        device: str = "video",
        index: int | None = None,
    ) -> Future:
        """Run on any frame source, such as a recorded video."""
        return self._submit(lambda: self._open(lambda: source, device, index))

    def close_camera(self) -> Future:
        return self._submit(self._close_source)

    def arm(self) -> Future:
        """Let the segmenter report gestures."""
        return self._submit(lambda: self._set_armed(True))

    def disarm(self) -> Future:
        """Stop the segmenter reporting; speed is still reported."""
        return self._submit(lambda: self._set_armed(False))

    def set_receiver(self, receiver: Receiver | None) -> None:
        self._receiver = receiver

    def add_motion_listener(
        self, listener: Callable[[MotionReading], None]
    ) -> None:
        self._motion_listeners.append(listener)

    # --- Reading what the engine publishes -------------------------------

    def latest_frame(
        self, view: str = "camera"
    ) -> tuple[int, np.ndarray | None]:
        return self._frames[view].latest()

    def wait_for_frame(
        self, view: str = "camera", after: int = 0, timeout: float | None = None
    ) -> tuple[int, np.ndarray] | None:
        """Wait for a frame newer than ``after`` (see ``latest_frame``)."""
        return self._frames[view].wait_newer(after, timeout)

    def frames_between(
        self, start_s: float, end_s: float
    ) -> list[BufferedFrame]:
        return self.buffer.frames_between(start_s, end_s)

    # --- The loop --------------------------------------------------------

    def _run(self) -> None:
        try:
            while not self._stop.is_set():
                waiting = self._source is None or self.finished.is_set()
                self._drain_commands(block=waiting)
                if self._source is None or self.finished.is_set():
                    continue
                try:
                    frame = self._source.read()
                except FrameSourceError:
                    frame = None
                if frame is None:
                    self._no_frame()
                    continue
                self._process(frame)
        finally:
            self._close_source()

    def _drain_commands(self, block: bool) -> None:
        try:
            item = self._commands.get(timeout=IDLE_WAIT_S if block else 0)
        except queue.Empty:
            return
        while True:
            work, future = item
            try:
                future.set_result(work())
            except Exception as error:  # noqa: BLE001 - goes to the caller
                future.set_exception(error)
            try:
                item = self._commands.get_nowait()
            except queue.Empty:
                return

    def _no_frame(self) -> None:
        if isinstance(self._source, VideoFileSource):
            self._finish_fps_measurement()
            self.finished.set()
        else:
            self._stop.wait(0.005)  # a failed grab: try again shortly

    # --- Command bodies (engine thread) ----------------------------------

    def _open(
        self,
        make_source: Callable[[], FrameSource],
        device: str,
        index: int | None,
    ) -> None:
        self._close_source()  # releases the old camera and clears the state
        source = make_source()
        source.open()
        self._source = source
        self.finished.clear()
        self._tracker = None
        self._segmenter = None
        self._settings_seen = None
        self._segmenter_state = SegmenterState.IDLE
        self.buffer.clear()
        self._fps_stamps = []
        self._fps_done = False
        width, height = source.frame_size
        actual = getattr(source, "actual", None) or CameraMode(
            width, height, source.nominal_fps
        )
        requested = getattr(source, "requested", None) or actual
        self._state.update(
            Owner.CAPTURE_ENGINE,
            camera=CameraState(device, index, requested, actual),
        )

    def _close_source(self) -> None:
        if self._source is not None:
            self._source.close()
            self._source = None
        self._tracker = None
        self._segmenter = None
        self._state.update(Owner.CAPTURE_ENGINE, camera=CameraState())

    def _set_armed(self, armed: bool) -> None:
        self._armed = armed
        if self._segmenter is not None:
            self._segmenter.set_enabled(armed)
        self._segmenter_state = SegmenterState.IDLE

    # --- Per frame -------------------------------------------------------

    def _apply_settings(self, frame: Frame) -> None:
        settings = self._state.snapshot.settings
        if settings is self._settings_seen and self._tracker is not None:
            return
        previous = self._settings_seen
        self._settings_seen = settings
        if self._tracker is None or previous is None:
            self._tracker = Tracker(settings.vision)
        elif settings.vision != previous.vision:
            self._tracker = Tracker(settings.vision)
        if (
            self._segmenter is None
            or previous is None
            or settings.motion != previous.motion
        ):
            height, width = frame.image.shape[:2]
            self._segmenter = Segmenter(
                settings.motion, frame_size=(width, height)
            )
            self._segmenter.set_enabled(self._armed)
            self._segmenter_state = SegmenterState.IDLE
        self.buffer.set_max_seconds(
            self._padding[0] + settings.motion.max_duration_s + self._padding[1]
        )

    def _process(self, frame: Frame) -> None:
        self._apply_settings(frame)
        detection = self._tracker.process(frame.image, frame.timestamp_s)
        update = self._segmenter.update(detection)
        self.latest_detection = detection

        ok, jpeg = cv2.imencode(
            ".jpg", frame.image, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
        )
        if ok:
            self.buffer.add(frame.timestamp_s, jpeg.tobytes())

        # Only what is shown is mirrored. Detections, the buffered frames
        # (and so the clips) stay as the camera saw them.
        self._frames["camera"].publish(
            _annotate(frame.image, detection, update, self._armed, self._mirror)
        )
        self._frames["mask"].publish(
            _mask_view(self._tracker.last_mask, self._mirror)
        )

        motion = self._state.snapshot.settings.motion
        reading = MotionReading(
            frame.timestamp_s,
            update.speed,
            update.moving,
            update.state,
            motion.start_speed,
            motion.end_speed,
        )
        self.latest_motion = reading
        for listener in self._motion_listeners:
            self._call(listener, reading)

        if (
            self._armed
            and self._segmenter_state is not SegmenterState.MOTION
            and update.state is SegmenterState.MOTION
        ):
            self._send(MotionStarted(frame.timestamp_s))
        self._segmenter_state = update.state
        if isinstance(update.result, Gesture):
            self._send(GestureFound(update.result))
        elif isinstance(update.result, Discard):
            self._send(GestureDiscarded(update.result))

        self._measure_fps(frame.timestamp_s)

    def _send(self, message: Any) -> None:
        if self._receiver is not None:
            self._call(self._receiver, message)

    @staticmethod
    def _call(callback: Callable[[Any], None], argument: Any) -> None:
        try:
            callback(argument)
        except Exception:  # noqa: BLE001 - a bad consumer must not stop capture
            logger.exception("engine callback failed")

    # --- Measured frame rate ---------------------------------------------

    def _measure_fps(self, timestamp_s: float) -> None:
        if self._fps_done:
            return
        self._fps_stamps.append(timestamp_s)
        if timestamp_s - self._fps_stamps[0] >= FPS_MEASURE_SECONDS:
            self._finish_fps_measurement()

    def _finish_fps_measurement(self) -> None:
        if self._fps_done:
            return
        self._fps_done = True
        stamps = self._fps_stamps
        if len(stamps) < 2 or stamps[-1] <= stamps[0]:
            return
        fps = (len(stamps) - 1) / (stamps[-1] - stamps[0])

        def with_measured_rate(snapshot):
            camera = snapshot.camera
            if camera.actual is None:
                return {"camera": camera}
            actual = CameraMode(camera.actual.width, camera.actual.height, fps)
            return {
                "camera": CameraState(
                    camera.device, camera.index, camera.requested, actual
                )
            }

        self._state.modify(Owner.CAPTURE_ENGINE, with_measured_rate)


# --- Drawing ----------------------------------------------------------------


def _annotate(
    image: np.ndarray,
    detection: TipDetection,
    update: SegmenterUpdate,
    armed: bool,
    mirror: bool = False,
) -> np.ndarray:
    """A copy of the frame with the tip marked and the motion state written.

    When ``mirror`` is true the picture is flipped left to right, like a
    mirror, and the marker is placed to match. The text is written after the
    flip, so it still reads normally.
    """
    canvas = cv2.flip(image, 1) if mirror else image.copy()
    height, width = canvas.shape[:2]
    if detection.found:
        horizontal = (
            1 - detection.horizontal if mirror else detection.horizontal
        )
        center = (
            round(horizontal * width),
            round(detection.vertical * height),
        )
        radius = max(2, round(detection.radius * height))
        cv2.circle(canvas, center, radius, (0, 255, 0), 2, cv2.LINE_AA)
        cv2.circle(canvas, center, 2, (0, 255, 0), -1, cv2.LINE_AA)
    if armed:
        label = update.state.value.upper()
    else:
        label = "MOVING" if update.moving else "IDLE"
    color = (0, 200, 255) if update.moving else (200, 200, 200)
    cv2.putText(
        canvas,
        label,
        (10, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        color,
        2,
        cv2.LINE_AA,
    )
    return canvas


def _mask_view(mask: np.ndarray | None, mirror: bool = False) -> np.ndarray:
    """The detection mask as a white-on-black color image."""
    if mask is None:
        return np.zeros((1, 1, 3), dtype=np.uint8)
    if mirror:
        mask = cv2.flip(mask, 1)
    return cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
