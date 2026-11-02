"""Segmenter: decides when a gesture starts and ends.

It receives one tip detection at a time, uses no future data and keeps a
short history (``lib/docs/design.md`` section 8). Speeds are in
frame-heights per second, so the horizontal fraction is multiplied by the
frame's aspect ratio before distances are measured.
"""

import math
from collections import deque

from wand_core.settings import MotionSettings
from wand_core.types import (
    Discard,
    DiscardReason,
    Gesture,
    Position,
    SegmenterState,
    SegmenterUpdate,
    TipDetection,
)

_Point = tuple[float, float, float]  # timestamp_s, horizontal, vertical


class Segmenter:
    """Cuts a stream of tip detections into gestures.

    ``aspect_ratio`` is frame width over height. It may be omitted when
    ``frame_size`` (width, height) is given, which also fills the frame size
    of the gestures it reports.
    """

    def __init__(
        self,
        settings: MotionSettings | None = None,
        aspect_ratio: float | None = None,
        frame_size: tuple[int, int] | None = None,
    ) -> None:
        if aspect_ratio is None:
            aspect_ratio = (
                frame_size[0] / frame_size[1] if frame_size else 4 / 3
            )
        self.settings = settings or MotionSettings()
        self.aspect_ratio = aspect_ratio
        self.frame_size = frame_size
        self.enabled = True
        self._clear()

    # --- Control -------------------------------------------------------

    def apply_settings(self, settings: MotionSettings) -> None:
        """Use new settings and reset the state."""
        self.settings = settings
        self._clear()

    def set_enabled(self, enabled: bool) -> None:
        """Switch gesture reporting on or off.

        While off, speed and ``moving`` are still reported, but there are no
        gestures or discards and the state stays ``idle``.
        """
        self.enabled = enabled
        self._clear_motion()
        self.state = SegmenterState.IDLE

    def reset(self) -> None:
        self._clear()

    def _clear(self) -> None:
        self._recent: deque[_Point] = deque(
            maxlen=self.settings.start_frames + 2
        )
        self._window: deque[_Point] = deque(
            maxlen=self.settings.smoothing_frames
        )
        self._previous_smoothed: _Point | None = None
        self._last_found_s: float | None = None
        self._clear_motion()
        self.state = SegmenterState.IDLE

    def _clear_motion(self) -> None:
        self._pending: list[_Point] = []
        self._above_count = 0
        self._points: list[_Point] = []
        self._below_since: float | None = None

    # --- Updates -------------------------------------------------------

    def update(self, detection: TipDetection) -> SegmenterUpdate:
        """Take the next detection and report the speed, state and result."""
        if not detection.found:
            return self._update_lost(detection.timestamp_s)
        return self._update_found(
            (detection.timestamp_s, detection.horizontal, detection.vertical)
        )

    def _update_lost(self, now: float) -> SegmenterUpdate:
        result = None
        if self._above_count and self.state is SegmenterState.IDLE:
            self._pending, self._above_count = [], 0
        if (
            self.enabled
            and self.state is SegmenterState.MOTION
            and self._last_found_s is not None
            and now - self._last_found_s > self.settings.lost_timeout_s
        ):
            result = self._discard(DiscardReason.TRACKING_LOST, now)
        return SegmenterUpdate(0.0, False, self.state, result)

    def _update_found(self, point: _Point) -> SegmenterUpdate:
        s = self.settings
        now = point[0]
        result = None

        if (
            self._last_found_s is not None
            and now - self._last_found_s > s.lost_timeout_s
        ):
            # A long gap: the old history says nothing about this position.
            if self.enabled and self.state is SegmenterState.MOTION:
                result = self._discard(DiscardReason.TRACKING_LOST, now)
            self._recent.clear()
            self._window.clear()
            self._previous_smoothed = None
            self._pending, self._above_count = [], 0
        self._last_found_s = now

        self._recent.append(point)
        self._window.append(point)
        smoothed = self._smoothed(now)
        speed = self._speed(smoothed)
        self._previous_smoothed = smoothed

        if not self.enabled:
            moving = speed >= s.start_speed
            return SegmenterUpdate(speed, moving, SegmenterState.IDLE, None)

        finished = self._advance(point, speed)
        result = finished or result
        if self.state is SegmenterState.MOTION:
            moving = speed >= s.end_speed
        else:
            moving = speed >= s.start_speed
        return SegmenterUpdate(speed, moving, self.state, result)

    def _smoothed(self, now: float) -> _Point:
        n = len(self._window)
        return (
            now,
            sum(p[1] for p in self._window) / n,
            sum(p[2] for p in self._window) / n,
        )

    def _speed(self, smoothed: _Point) -> float:
        previous = self._previous_smoothed
        if previous is None:
            return 0.0
        dt = smoothed[0] - previous[0]
        if dt <= 0:
            return 0.0
        return self._distance(previous, smoothed) / dt

    def _distance(self, a: _Point, b: _Point) -> float:
        return math.hypot((b[1] - a[1]) * self.aspect_ratio, b[2] - a[2])

    # --- State machine -------------------------------------------------

    def _advance(self, point: _Point, speed: float) -> Gesture | Discard | None:
        s = self.settings
        now = point[0]

        if self.state is SegmenterState.WAITING:
            if speed < s.end_speed:
                self.state = SegmenterState.IDLE
            return None

        if self.state is SegmenterState.IDLE:
            if speed < s.start_speed:
                self._pending, self._above_count = [], 0
                return None
            if self._above_count == 0:
                # The detection just before the motion began.
                before = self._recent[-2] if len(self._recent) > 1 else point
                self._pending = [before]
            self._pending.append(point)
            self._above_count += 1
            if self._above_count >= s.start_frames:
                self.state = SegmenterState.MOTION
                self._points = self._pending
                self._pending, self._above_count = [], 0
                self._below_since = None
            return None

        # MOTION
        self._points.append(point)
        if now - self._points[0][0] > s.max_duration_s:
            return self._discard(DiscardReason.TOO_LONG, now)
        if speed >= s.end_speed:
            self._below_since = None
            return None
        if self._below_since is None:
            self._below_since = now
        if now - self._below_since >= s.end_hold_s:
            return self._finish(now)
        return None

    def _finish(self, now: float) -> Gesture | Discard:
        s = self.settings
        end = self._below_since
        points = [p for p in self._points if p[0] <= end]
        start = points[0][0]
        duration = end - start
        extent = self._extent(points)
        self._clear_motion()
        self.state = SegmenterState.IDLE
        if duration > s.max_duration_s:
            self.state = SegmenterState.WAITING
            return Discard(DiscardReason.TOO_LONG, now)
        if duration < s.min_duration_s:
            return Discard(DiscardReason.TOO_SHORT, now)
        if extent < s.min_extent:
            return Discard(DiscardReason.TOO_SMALL, now)
        width, height = self.frame_size or (None, None)
        return Gesture(
            positions=[Position(p[0] - start, p[1], p[2]) for p in points],
            start_timestamp_s=start,
            end_timestamp_s=points[-1][0],
            frame_width=width,
            frame_height=height,
        )

    def _extent(self, points: list[_Point]) -> float:
        xs = [p[1] * self.aspect_ratio for p in points]
        ys = [p[2] for p in points]
        return math.hypot(max(xs) - min(xs), max(ys) - min(ys))

    def _discard(self, reason: DiscardReason, now: float) -> Discard:
        self._clear_motion()
        self.state = SegmenterState.WAITING
        return Discard(reason, now)
