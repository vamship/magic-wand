import math

import numpy as np
import pytest

from wand_core.calibration import (
    MotionCalibrationError,
    calibrate_from_speeds,
    calibrate_motion,
    speeds_of,
)
from wand_core.motion import Segmenter
from wand_core.settings import MotionSettings
from wand_core.types import TipDetection

FPS = 30.0
ASPECT = 4 / 3


def still_stream(seconds=4.0, jitter=0.002, seed=0, fps=FPS):
    """A tip held still: it only trembles."""
    rng = np.random.default_rng(seed)
    detections = []
    for i in range(round(seconds * fps)):
        x = 0.5 + rng.uniform(-jitter, jitter) / ASPECT
        y = 0.5 + rng.uniform(-jitter, jitter)
        detections.append(TipDetection(i / fps, True, x, y, 0.04))
    return detections


def waving_stream(
    seconds=4.0, amplitude=0.2, hertz=2.0, jitter=0.002, seed=1, fps=FPS
):
    """The tip waved from side to side. Peak speed is 2 pi f A."""
    rng = np.random.default_rng(seed)
    detections = []
    for i in range(round(seconds * fps)):
        t = i / fps
        x = 0.5 + amplitude * math.sin(2 * math.pi * hertz * t) / ASPECT
        x += rng.uniform(-jitter, jitter) / ASPECT
        y = 0.5 + rng.uniform(-jitter, jitter)
        detections.append(TipDetection(t, True, x, y, 0.04))
    return detections


# --- Speeds -----------------------------------------------------------------


def test_speeds_match_what_the_segmenter_reports():
    stream = waving_stream()
    segmenter = Segmenter(aspect_ratio=ASPECT)
    expected = [segmenter.update(d).speed for d in stream][1:]
    assert speeds_of(stream) == pytest.approx(expected)


def test_speeds_follow_the_motion_settings_smoothing():
    stream = still_stream(jitter=0.01)
    smooth = speeds_of(stream, MotionSettings(smoothing_frames=8))
    rough = speeds_of(stream, MotionSettings(smoothing_frames=1))
    assert np.mean(smooth) < np.mean(rough)


def test_frames_without_a_tip_are_left_out():
    stream = still_stream(seconds=1.0)
    stream[10] = TipDetection(stream[10].timestamp_s, False)
    assert len(speeds_of(stream)) == len(stream) - 2  # first and the lost one


# --- The proposal -----------------------------------------------------------


def test_thresholds_are_ordered_below_the_typical_gesture_speed():
    result = calibrate_motion(still_stream(), waving_stream())
    s = result.settings
    assert 0 < result.idle_ceiling < s.end_speed
    assert s.end_speed < s.start_speed < result.typical_gesture_speed
    assert result.peak_count >= 6  # 2 Hz for 4 s is about 16 strokes
    # Peak speed of the wave is 2 pi f A = 2.5 frame-heights per second.
    assert result.typical_gesture_speed == pytest.approx(2.5, rel=0.25)


def test_end_speed_is_three_times_the_idle_ceiling_but_at_least_a_floor():
    result = calibrate_motion(still_stream(jitter=0.01), waving_stream())
    assert result.settings.end_speed == pytest.approx(
        3 * result.idle_ceiling, abs=0.001
    )
    calm = calibrate_motion(still_stream(jitter=0.0001), waving_stream())
    assert calm.settings.end_speed == 0.05


def test_start_speed_is_the_geometric_mean_of_end_speed_and_typical_speed():
    result = calibrate_motion(still_stream(), waving_stream())
    expected = math.sqrt(
        result.settings.end_speed * result.typical_gesture_speed
    )
    assert result.settings.start_speed == pytest.approx(expected, abs=0.001)


def test_noisier_still_data_gives_a_higher_end_speed():
    ends = [
        calibrate_motion(
            still_stream(jitter=j), waving_stream()
        ).settings.end_speed
        for j in (0.001, 0.004, 0.012)
    ]
    assert ends[0] < ends[1] < ends[2]


def test_faster_waving_gives_a_higher_start_speed():
    slow = calibrate_motion(still_stream(), waving_stream(hertz=1.0))
    fast = calibrate_motion(still_stream(), waving_stream(hertz=3.0))
    assert fast.settings.start_speed > slow.settings.start_speed
    assert fast.typical_gesture_speed > slow.typical_gesture_speed


def test_other_settings_are_kept_from_the_base():
    base = MotionSettings(min_duration_s=0.5, smoothing_frames=4)
    result = calibrate_motion(still_stream(), waving_stream(), base)
    assert result.settings.min_duration_s == 0.5
    assert result.settings.smoothing_frames == 4
    assert result.settings.max_duration_s == base.max_duration_s


def test_the_proposal_is_valid_motion_settings():
    result = calibrate_motion(still_stream(jitter=0.02), waving_stream())
    assert isinstance(result.settings, MotionSettings)
    assert result.settings.start_speed > result.settings.end_speed


@pytest.mark.parametrize("fps", [15.0, 30.0, 60.0])
def test_the_frame_rate_does_not_change_the_proposal_much(fps):
    result = calibrate_motion(still_stream(fps=fps), waving_stream(fps=fps))
    assert result.typical_gesture_speed == pytest.approx(2.5, rel=0.3)
    assert result.settings.end_speed < result.settings.start_speed


def test_the_same_proposal_comes_from_speeds_already_measured():
    still, waving = still_stream(), waving_stream()
    from_detections = calibrate_motion(still, waving)
    from_speeds = calibrate_from_speeds(speeds_of(still), speeds_of(waving))
    assert from_speeds == from_detections


# --- Not enough to go on ----------------------------------------------------


def test_too_little_data_while_still_is_an_error():
    with pytest.raises(MotionCalibrationError, match="holding still"):
        calibrate_motion(still_stream(seconds=0.3), waving_stream())


def test_too_little_data_while_waving_is_an_error():
    with pytest.raises(MotionCalibrationError, match="while waving"):
        calibrate_motion(still_stream(), waving_stream(seconds=0.3))


def test_waving_no_faster_than_the_noise_is_an_error():
    timid = waving_stream(amplitude=0.0, jitter=0.002)
    with pytest.raises(MotionCalibrationError, match="not clearly faster"):
        calibrate_motion(still_stream(jitter=0.002), timid)


def test_waving_slower_than_the_noise_floor_is_an_error():
    shaky = still_stream(jitter=0.03)
    gentle = waving_stream(amplitude=0.02, hertz=0.5, jitter=0.0)
    with pytest.raises(MotionCalibrationError):
        calibrate_motion(shaky, gentle)


def test_a_single_flick_is_not_enough_to_calibrate():
    stream = still_stream(seconds=2.0)
    flick = waving_stream(seconds=0.5, hertz=1.0)  # less than one stroke
    with pytest.raises(MotionCalibrationError, match="strokes"):
        calibrate_motion(still_stream(), stream[:5] + flick + stream[:20])


def test_errors_are_value_errors():
    assert issubclass(MotionCalibrationError, ValueError)
