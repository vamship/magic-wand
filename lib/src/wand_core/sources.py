"""Frame sources: objects that deliver video frames with timestamps.

A frame is a BGR image (a NumPy array) and a timestamp in seconds that
increases steadily. A live camera and a recorded file implement the same
interface, so everything downstream runs identically on both
(``lib/docs/design.md`` section 5).

Cameras are opened through ``cv2.VideoCapture``. Both ``CameraSource`` and
``list_cameras`` accept a ``capture_factory`` so tests can substitute a
stand-in and never touch real hardware.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

DEFAULT_WIDTH, DEFAULT_HEIGHT, DEFAULT_FPS = 640, 480, 30
MAX_CAMERA_INDEX = 10
LINUX_CAMERA_NAMES = Path("/sys/class/video4linux")
PROBE_SIZES = ((640, 480), (1280, 720), (1920, 1080))

CaptureFactory = Callable[[Any], Any]  # index or path -> VideoCapture-like


class FrameSourceError(RuntimeError):
    """A frame source could not be opened or used."""


class CameraOpenError(FrameSourceError):
    """A camera could not be opened (missing, busy or not permitted)."""


class VideoOpenError(FrameSourceError):
    """A video file could not be opened or has no usable frame rate."""


@dataclass(frozen=True)
class Frame:
    """An image and the time it was captured, in seconds."""

    image: np.ndarray
    timestamp_s: float


@dataclass(frozen=True)
class CameraMode:
    """A resolution and frame rate. ``fps`` is 0 when it is not reported."""

    width: int
    height: int
    fps: float


@dataclass(frozen=True)
class CameraInfo:
    """A camera found on this machine.

    ``device_id`` is the name when known, otherwise ``index:<N>``; it is what
    a session stores. ``modes`` is empty when the supported modes are not
    known.
    """

    index: int
    name: str | None
    device_id: str
    modes: tuple[CameraMode, ...] = ()


class FrameSource(ABC):
    """Common interface of all frame sources.

    Use as a context manager, or call ``open`` and ``close``. ``read``
    returns the next frame, or ``None`` when there is none (the end of a
    file, or a failed grab from a camera).
    """

    @abstractmethod
    def open(self) -> None:
        """Open the source. Raises ``FrameSourceError`` on failure."""

    @abstractmethod
    def read(self) -> Frame | None:
        """Return the next frame, or ``None``."""

    @abstractmethod
    def close(self) -> None:
        """Release the source. Closing twice is safe."""

    @property
    @abstractmethod
    def frame_size(self) -> tuple[int, int]:
        """The frame width and height in pixels."""

    @property
    @abstractmethod
    def nominal_fps(self) -> float:
        """The frame rate of the source (0 when unknown)."""

    def __enter__(self) -> FrameSource:
        self.open()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def __iter__(self) -> Iterator[Frame]:
        while (frame := self.read()) is not None:
            yield frame


class VideoFileSource(FrameSource):
    """Frames of a video file, in order.

    Timestamps follow the file's own timeline: they start at 0 and advance by
    the file's frame interval.
    """

    def __init__(
        self, path: str | Path, capture_factory: CaptureFactory | None = None
    ) -> None:
        self.path = Path(path)
        self._factory = capture_factory or cv2.VideoCapture
        self._capture: Any = None
        self._fps = 0.0
        self._size = (0, 0)
        self._index = 0

    def open(self) -> None:
        if self._capture is not None:
            return
        if not self.path.exists():
            raise VideoOpenError(f"video file not found: {self.path}")
        capture = self._factory(str(self.path))
        if not capture.isOpened():
            capture.release()
            raise VideoOpenError(f"cannot open video file: {self.path}")
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        if not fps > 0:
            capture.release()
            raise VideoOpenError(f"video has no frame rate: {self.path}")
        self._fps = fps
        self._size = (
            int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        )
        self._index = 0
        self._capture = capture

    def read(self) -> Frame | None:
        if self._capture is None:
            raise FrameSourceError("the video source is not open")
        ok, image = self._capture.read()
        if not ok:
            return None
        frame = Frame(image, self._index / self._fps)
        self._index += 1
        return frame

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    @property
    def frame_size(self) -> tuple[int, int]:
        return self._size

    @property
    def nominal_fps(self) -> float:
        return self._fps


class CameraSource(FrameSource):
    """Frames from a live camera.

    The requested mode is a request only: ``actual`` is what the camera
    reports after opening. A frame's timestamp is taken from a monotonic
    clock when the frame is grabbed, between the grab and the decode.
    """

    def __init__(
        self,
        index: int = 0,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        fps: float = DEFAULT_FPS,
        capture_factory: CaptureFactory | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.index = index
        self.requested = CameraMode(width, height, fps)
        self.actual: CameraMode | None = None
        self._factory = capture_factory or cv2.VideoCapture
        self._clock = clock
        self._capture: Any = None

    def open(self) -> None:
        if self._capture is not None:
            return
        capture = self._factory(self.index)
        if not capture.isOpened():
            capture.release()
            raise CameraOpenError(f"cannot open camera {self.index}")
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.requested.width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.requested.height)
        capture.set(cv2.CAP_PROP_FPS, self.requested.fps)
        self.actual = CameraMode(
            int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            float(capture.get(cv2.CAP_PROP_FPS)),
        )
        self._capture = capture

    def read(self) -> Frame | None:
        if self._capture is None:
            raise FrameSourceError("the camera is not open")
        if not self._capture.grab():
            return None
        timestamp = self._clock()
        ok, image = self._capture.retrieve()
        if not ok:
            return None
        return Frame(image, timestamp)

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    @property
    def frame_size(self) -> tuple[int, int]:
        mode = self.actual or self.requested
        return (mode.width, mode.height)

    @property
    def nominal_fps(self) -> float:
        return (self.actual or self.requested).fps


# --- Listing cameras --------------------------------------------------------


def camera_name(index: int, names_dir: Path = LINUX_CAMERA_NAMES) -> str | None:
    """The operating system's name for a camera, when it provides one.

    On Linux this is read from ``/sys/class/video4linux``. macOS gives no
    names through OpenCV, so the index identifies the camera there.
    """
    try:
        name = (names_dir / f"video{index}" / "name").read_text().strip()
    except OSError:
        return None
    return name or None


def list_cameras(
    max_index: int = MAX_CAMERA_INDEX,
    capture_factory: CaptureFactory | None = None,
    names_dir: Path = LINUX_CAMERA_NAMES,
    probe_modes: bool = False,
) -> list[CameraInfo]:
    """Find the cameras on this machine by trying indices from 0.

    Returns an empty list when there are none. With ``probe_modes`` it also
    tries a few common resolutions, which is slower and opens each camera
    longer.
    """
    factory = capture_factory or cv2.VideoCapture
    cameras = []
    for index in range(max_index):
        try:
            capture = factory(index)
        except Exception:  # noqa: BLE001 - a bad backend must not stop the scan
            continue
        try:
            if not capture.isOpened():
                continue
            modes = _probe_modes(capture) if probe_modes else ()
        finally:
            capture.release()
        name = camera_name(index, names_dir)
        cameras.append(CameraInfo(index, name, name or f"index:{index}", modes))
    return cameras


def _probe_modes(capture: Any) -> tuple[CameraMode, ...]:
    modes: list[CameraMode] = []
    for width, height in PROBE_SIZES:
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        mode = CameraMode(
            int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            float(capture.get(cv2.CAP_PROP_FPS)),
        )
        if mode not in modes and mode.width and mode.height:
            modes.append(mode)
    return tuple(modes)
