import math

import numpy as np
import pytest

from wand_core.motion import Segmenter
from wand_core.settings import MotionSettings
from wand_core.testing.synthetic import circle_path, line_path
from wand_core.types import (
    Discard,
    DiscardReason,
    Gesture,
    SegmenterState,
    TipDetection,
)

FPS = 30.0
ASPECT = 4 / 3


class Stream:
    """Builds a stream of tip detections, one segment after another."""

    def __init__(self, fps=FPS, start=(0.5, 0.5)):
        self.fps = fps
        self.t = 0.0
        self.last = start
        self.detections = []

    def _add(self, x, y, found=True):
        if found:
            self.detections.append(TipDetection(self.t, True, x, y, 0.04))
            self.last = (x, y)
        else:
            self.detections.append(TipDetection(self.t, False))
        self.t += 1 / self.fps

    def still(self, seconds, jitter=0.0):
        rng = np.random.default_rng(0)
        for _ in range(round(seconds * self.fps)):
            x, y = self.last
            self._add(
                x + rng.uniform(-jitter, jitter),
                y + rng.uniform(-jitter, jitter),
            )
            self.last = (x, y)
        return self

    def path(self, points):
        for x, y in points:
            self._add(float(x), float(y))
        return self

    def circle(self, seconds, turns=1.0, radius=0.25):
        """A circle that starts (and ends, for whole turns) at the tip."""
        n = round(seconds * self.fps)
        x, y = self.last
        center = (x - radius / ASPECT, y)
        return self.path(circle_path(n, center, radius, turns))

    def line(self, seconds, length):
        n = round(seconds * self.fps)
        x, y = self.last
        return self.path(line_path(n, (x, y), (x + length / ASPECT, y)))

    def lost(self, seconds):
        for _ in range(round(seconds * self.fps)):
            self._add(0, 0, found=False)
        return self


def run(stream, settings=None, **options):
    segmenter = Segmenter(settings, aspect_ratio=ASPECT, **options)
    updates = [segmenter.update(d) for d in stream.detections]
    return segmenter, updates


def results(updates):
    return [u.result for u in updates if u.result is not None]


def test_stationary_tip_stays_idle():
    _, updates = run(Stream().still(3))
    assert not results(updates)
    assert all(u.state is SegmenterState.IDLE for u in updates)
    assert all(not u.moving for u in updates)


def test_tremor_below_start_speed_gives_nothing():
    _, updates = run(Stream().still(5, jitter=0.0015))
    assert not results(updates)
    assert max(u.speed for u in updates) < 0.25


def test_circle_gives_one_gesture_with_expected_positions():
    stream = Stream().still(0.5).circle(1.5).still(1.0)
    _, updates = run(stream)
    found = results(updates)
    assert len(found) == 1
    gesture = found[0]
    assert isinstance(gesture, Gesture)
    # The circle has 45 points; one extra point before motion; tail trimmed.
    assert 44 <= len(gesture.positions) <= 49
    assert gesture.positions[0].time_s == 0
    assert gesture.start_timestamp_s == pytest.approx(0.5 - 1 / FPS, abs=0.1)
    assert gesture.end_timestamp_s == pytest.approx(0.5 + 1.5, abs=0.15)
    # Every position lies on the circle (center 0.25 / aspect left of start).
    center = (0.5 - 0.25 / ASPECT, 0.5)
    for p in gesture.positions:
        r = math.hypot(
            (p.horizontal - center[0]) * ASPECT, p.vertical - center[1]
        )
        assert r == pytest.approx(0.25, abs=0.005)


def test_gesture_reports_frame_size_when_given():
    stream = Stream().still(0.3).circle(1.5).still(1.0)
    _, updates = run(stream, frame_size=(640, 480))
    gesture = results(updates)[0]
    assert (gesture.frame_width, gesture.frame_height) == (640, 480)


def test_too_long_is_discarded_at_once():
    stream = Stream().still(0.3).circle(8.0, turns=3).still(1.0)
    _, updates = run(stream)
    found = results(updates)
    assert [r.reason for r in found] == [DiscardReason.TOO_LONG]
    discard = found[0]
    assert isinstance(discard, Discard)
    assert discard.timestamp_s == pytest.approx(0.3 + 4.0, abs=0.2)
    # It is reported while still moving, not at the end.
    index = next(i for i, u in enumerate(updates) if u.result)
    assert updates[index].state is SegmenterState.WAITING
    assert updates[index].moving


def test_too_short_is_discarded():
    stream = Stream().still(0.3).line(0.1, length=0.3).still(1.0)
    _, updates = run(stream)
    assert [r.reason for r in results(updates)] == [DiscardReason.TOO_SHORT]


def test_too_small_is_discarded():
    t = np.arange(0, 1.0, 1 / FPS)
    wiggle = [
        (0.5 + 0.03 * math.sin(2 * math.pi * 5 * x) / ASPECT, 0.5) for x in t
    ]
    stream = Stream().still(0.3).path(wiggle).still(1.0)
    _, updates = run(stream)
    found = results(updates)
    assert [r.reason for r in found] == [DiscardReason.TOO_SMALL]


def test_tracking_lost_is_discarded():
    stream = Stream().still(0.3).circle(1.0).lost(1.0).still(0.5)
    _, updates = run(stream)
    found = results(updates)
    assert [r.reason for r in found] == [DiscardReason.TRACKING_LOST]
    # Reported about lost_timeout_s after the last detection.
    assert found[0].timestamp_s == pytest.approx(0.3 + 1.0 + 0.25, abs=0.12)


def test_short_loss_does_not_end_a_gesture():
    stream = Stream().still(0.3).line(0.6, 0.5)
    stream.lost(0.1)
    stream.line(0.6, 0.5).still(1.0)
    _, updates = run(stream)
    found = results(updates)
    assert len(found) == 1
    assert isinstance(found[0], Gesture)


def test_short_pause_does_not_split_a_gesture():
    stream = Stream().still(0.3).line(0.5, 0.4).still(0.2).line(0.5, 0.4)
    stream.still(1.0)
    _, updates = run(stream)
    found = results(updates)
    assert len(found) == 1
    assert isinstance(found[0], Gesture)
    assert found[0].positions[-1].time_s > 1.0


def test_long_pause_splits_into_two_gestures():
    stream = Stream().still(0.3).line(0.6, 0.4).still(0.6).line(0.6, 0.4)
    stream.still(1.0)
    _, updates = run(stream)
    assert len(results(updates)) == 2


def test_new_gesture_only_after_idle_following_a_discard():
    stream = Stream().still(0.3).circle(8.0, turns=3)  # discarded at 4 s
    stream.circle(1.5)  # still moving: no gesture may start
    stream.still(0.6).circle(1.5).still(1.0)
    _, updates = run(stream)
    found = results(updates)
    assert isinstance(found[0], Discard)
    assert isinstance(found[-1], Gesture)
    assert len(found) == 2
    first_waiting = next(
        i for i, u in enumerate(updates) if u.state is SegmenterState.WAITING
    )
    idle_again = next(
        i
        for i, u in enumerate(updates)
        if i > first_waiting and u.state is SegmenterState.IDLE
    )
    gesture_index = next(
        i for i, u in enumerate(updates) if isinstance(u.result, Gesture)
    )
    assert idle_again < gesture_index


def test_switched_off_gives_speed_but_no_result():
    segmenter = Segmenter(aspect_ratio=ASPECT)
    segmenter.set_enabled(False)
    stream = Stream().still(0.3).circle(1.5).still(1.0)
    updates = [segmenter.update(d) for d in stream.detections]
    assert not results(updates)
    assert max(u.speed for u in updates) > 0.5
    assert any(u.moving for u in updates)
    assert all(u.state is SegmenterState.IDLE for u in updates)


def test_switching_on_again_works():
    segmenter = Segmenter(aspect_ratio=ASPECT)
    segmenter.set_enabled(False)
    segmenter.set_enabled(True)
    stream = Stream().still(0.3).circle(1.5).still(1.0)
    updates = [segmenter.update(d) for d in stream.detections]
    assert len(results(updates)) == 1


@pytest.mark.parametrize("fps", [15.0, 30.0, 60.0])
def test_frame_rate_does_not_change_the_result(fps):
    stream = Stream(fps=fps).still(0.5).circle(1.5).still(1.0)
    _, updates = run(stream)
    found = results(updates)
    assert len(found) == 1
    assert isinstance(found[0], Gesture)
    assert max(u.speed for u in updates) == pytest.approx(1.05, abs=0.2)


def test_aspect_ratio_gives_equal_units_on_both_axes():
    horizontal = Stream().still(0.2).line(1.0, 0.8).still(1.0)
    vertical = Stream(start=(0.5, 0.1)).still(0.2)
    n = round(1.0 * FPS)
    vertical.path(line_path(n, (0.5, 0.1), (0.5, 0.9)))
    vertical.still(1.0)
    _, up_h = run(horizontal)
    _, up_v = run(vertical)
    assert max(u.speed for u in up_h) == pytest.approx(
        max(u.speed for u in up_v), rel=0.05
    )


def test_apply_settings_resets_state():
    stream = Stream().still(0.3).circle(1.0)
    segmenter, updates = run(stream)
    assert updates[-1].state is SegmenterState.MOTION
    segmenter.apply_settings(MotionSettings(start_speed=2.0, end_speed=1.0))
    assert segmenter.state is SegmenterState.IDLE
    update = segmenter.update(stream.detections[-1])
    assert update.state is SegmenterState.IDLE
