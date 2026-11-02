import math

import cv2
import numpy as np
import pytest

from wand_core.calibration import (
    ColorCalibration,
    ColorCalibrator,
    UnusableColorError,
)
from wand_core.settings import VisionSettings
from wand_core.testing.synthetic import (
    ORANGE,
    SceneStyle,
    hsv_color,
    render_frame,
)
from wand_core.vision import Tracker

CENTER = (0.5, 0.5)


def scene(
    hsv=ORANGE,
    center=CENTER,
    extras=(),
    width=640,
    height=480,
    **style_args,
):
    """A frame with the ball, plus extra (hsv, center, radius) disks."""
    style = SceneStyle(width=width, height=height, disk_hsv=hsv, **style_args)
    frame = render_frame(style, center)
    for color, (x, y), radius in extras:
        cv2.circle(
            frame,
            (round(x * width), round(y * height)),
            round(radius * height),
            hsv_color(*color),
            -1,
            cv2.LINE_AA,
        )
    return frame


def hue_straddles_wrap(settings):
    return (
        settings.hue_center - settings.hue_half_width < 0
        or settings.hue_center + settings.hue_half_width > 179
    )


# --- Finding the ball -------------------------------------------------------


@pytest.mark.parametrize(
    "style",
    [
        {},
        {"background": "light", "noise_std": 6, "seed": 1},
        {"background": "gradient", "noise_std": 8, "seed": 2},
        {"background": "clutter", "noise_std": 5, "seed": 3},
        {"brightness": 0.8, "noise_std": 5, "seed": 4},
    ],
    ids=["dark", "light", "gradient", "clutter", "dim"],
)
def test_the_settings_make_the_tracker_find_the_disk_and_little_else(style):
    frame = scene(**style)
    result = ColorCalibrator().add_clicks(frame, [CENTER])
    assert isinstance(result, ColorCalibration)
    assert result.detection.found
    assert result.detection.horizontal == pytest.approx(0.5, abs=0.01)
    assert result.detection.vertical == pytest.approx(0.5, abs=0.01)
    assert result.other_regions == 0
    # The mask marks the disk and almost nothing outside it.
    assert result.mask[240, 320] == 255
    outside = np.ones(result.mask.shape, bool)
    cv2.circle(outside.view(np.uint8), (320, 240), 40, 0, -1)
    assert (result.mask[outside] > 0).mean() < 0.005


def test_the_result_is_what_the_live_view_will_show():
    frame = scene(noise_std=6, seed=1)
    result = ColorCalibrator().add_clicks(frame, [CENTER], timestamp_s=3.5)
    tracker = Tracker(result.settings)
    assert tracker.process(frame, 3.5) == result.detection
    assert np.array_equal(tracker.last_mask, result.mask)


def test_other_settings_are_kept_from_the_base():
    base = VisionSettings(blur_size=3, cleanup_size=5, min_area=0.001)
    result = ColorCalibrator(base).add_clicks(scene(), [CENTER])
    assert result.settings.blur_size == 3
    assert result.settings.cleanup_size == 5
    assert result.settings.min_area == 0.001
    assert result.settings.min_roundness == base.min_roundness


# --- Red, which wraps around the hue circle ---------------------------------


@pytest.mark.parametrize("hue", [0, 3, 176, 179])
def test_a_red_disk_gives_an_interval_across_the_wrap(hue):
    frame = scene(hsv=(hue, 220, 230), noise_std=6, seed=7)
    result = ColorCalibrator().add_clicks(frame, [CENTER])
    assert hue_straddles_wrap(result.settings), result.settings
    assert result.detection.found
    assert result.detection.horizontal == pytest.approx(0.5, abs=0.01)


def test_the_circular_average_of_hues_either_side_of_zero_is_near_zero():
    # Hues 178 and 2 average to 0, not to 90.
    frame = scene(hsv=(178, 220, 230))
    cv2.circle(frame, (320, 240), 19, hsv_color(2, 220, 230), -1)
    result = ColorCalibrator().add_clicks(frame, [CENTER])
    center = result.settings.hue_center
    assert min(center, 180 - center) <= 3
    assert result.detection.found


# --- More clicks, tolerance -------------------------------------------------


def test_more_clicks_widen_the_ranges_to_cover_the_new_samples():
    other = ((24, 150, 170), (0.8, 0.3), 0.04)
    frame = scene(extras=[other])
    calibrator = ColorCalibrator()
    first = calibrator.add_clicks(frame, [CENTER])
    assert first.mask[int(0.3 * 480), int(0.8 * 640)] == 0  # not marked yet
    second = calibrator.add_clicks(frame, [(0.8, 0.3)])
    assert second.sample_count > first.sample_count
    a, b = first.settings, second.settings
    assert b.hue_half_width >= a.hue_half_width
    assert b.sat_min <= a.sat_min and b.sat_max >= a.sat_max
    assert b.val_min <= a.val_min and b.val_max >= a.val_max
    assert (b.sat_max - b.sat_min) > (a.sat_max - a.sat_min)
    assert second.mask[int(0.3 * 480), int(0.8 * 640)] == 255  # now covered
    assert second.mask[240, 320] == 255
    assert second.other_regions == 0  # both are clicked


def test_several_points_in_one_call_are_the_same_as_one_by_one():
    other = ((24, 150, 170), (0.8, 0.3), 0.04)
    frame = scene(extras=[other])
    together = ColorCalibrator().add_clicks(frame, [CENTER, (0.8, 0.3)])
    calibrator = ColorCalibrator()
    calibrator.add_clicks(frame, [CENTER])
    one_by_one = calibrator.add_clicks(frame, [(0.8, 0.3)])
    assert together.settings == one_by_one.settings


def test_other_marked_regions_are_reported():
    twin = (ORANGE, (0.2, 0.7), 0.04)
    result = ColorCalibrator().add_clicks(scene(extras=[twin]), [CENTER])
    assert result.other_regions == 1
    assert result.mask[int(0.7 * 480), int(0.2 * 640)] == 255
    assert result.mask[240, 320] == 255
    # Clicking both leaves nothing else.
    both = ColorCalibrator().add_clicks(
        scene(extras=[twin]), [CENTER, (0.2, 0.7)]
    )
    assert both.other_regions == 0


def test_tiny_marked_specks_are_not_counted():
    speck = (ORANGE, (0.2, 0.7), 0.004)  # about 2 pixels across
    result = ColorCalibrator().add_clicks(scene(extras=[speck]), [CENTER])
    assert result.other_regions == 0


def shaded_scene():
    """A ball whose hue, saturation and brightness vary across it."""
    hsv = np.full((480, 640, 3), (0, 0, 60), dtype=np.float32)
    ys, xs = np.mgrid[:480, :640]
    inside = (xs - 320) ** 2 + (ys - 240) ** 2 <= 19**2
    hsv[..., 0][inside] = 12 + (xs[inside] - 320) * 0.8
    hsv[..., 1][inside] = 200 + (xs[inside] - 320) * 6
    hsv[..., 2][inside] = 200 + (xs[inside] - 320) * 6
    hsv = np.clip(hsv, 0, 255).astype(np.uint8)
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


def test_a_larger_tolerance_gives_larger_margins():
    frame = shaded_scene()
    calibrator = ColorCalibrator()
    calibrator.add_clicks(frame, [CENTER])
    widths = []
    for tolerance in (0.5, 2.5, 6.0):
        result = calibrator.calibrate(frame, tolerance=tolerance)
        s = result.settings
        widths.append(
            (s.hue_half_width, s.sat_max - s.sat_min, s.val_max - s.val_min)
        )
    for narrow, wide in zip(widths, widths[1:]):
        assert all(w >= n for n, w in zip(narrow, wide)), widths
    assert widths[-1][0] > widths[0][0]  # hue strictly wider
    assert widths[-1][1] > widths[0][1]  # saturation too
    assert calibrator.tolerance == 6.0
    assert calibrator.sample_count == result.sample_count  # no new clicks


def test_a_very_uniform_patch_still_gets_the_minimum_margin():
    result = ColorCalibrator().add_clicks(scene(), [CENTER])
    s = result.settings
    assert s.hue_half_width >= 8
    # The patch is saturation 220 and brightness 230: 40 either side, with
    # the top clipped at 255.
    assert s.sat_min <= 181 and s.sat_max == 255
    assert s.val_min <= 191 and s.val_max == 255


def test_ranges_stay_within_the_valid_limits():
    result = ColorCalibrator().add_clicks(
        scene(hsv=(15, 250, 250), noise_std=10, seed=1), [CENTER]
    )
    s = result.settings
    assert 0 <= s.sat_min <= s.sat_max <= 255
    assert 0 <= s.val_min <= s.val_max <= 255
    assert 0 <= s.hue_center <= 179 and 0 <= s.hue_half_width <= 90


# --- Clicks with no usable color --------------------------------------------


def test_a_click_on_black_gives_a_clear_error():
    with pytest.raises(UnusableColorError, match="too dark"):
        ColorCalibrator().add_clicks(scene(), [(0.1, 0.1)])


@pytest.mark.parametrize("background", ["light"])
def test_a_click_on_gray_or_white_gives_a_clear_error(background):
    frame = scene(background=background)
    with pytest.raises(UnusableColorError, match="gray or white"):
        ColorCalibrator().add_clicks(frame, [(0.1, 0.1)])


def test_a_bad_click_adds_nothing_even_among_good_ones():
    calibrator = ColorCalibrator()
    with pytest.raises(UnusableColorError):
        calibrator.add_clicks(scene(), [CENTER, (0.1, 0.1)])
    assert calibrator.sample_count == 0
    calibrator.add_clicks(scene(), [CENTER])
    count = calibrator.sample_count
    with pytest.raises(UnusableColorError):
        calibrator.add_clicks(scene(), [(0.9, 0.9)])
    assert calibrator.sample_count == count


def test_input_errors():
    calibrator = ColorCalibrator()
    with pytest.raises(ValueError, match="at least one"):
        calibrator.add_clicks(scene(), [])
    with pytest.raises(ValueError, match="outside the frame"):
        calibrator.add_clicks(scene(), [(1.2, 0.5)])
    with pytest.raises(ValueError, match="click on the wand tip"):
        calibrator.calibrate(scene())


def test_reset_forgets_the_clicks():
    calibrator = ColorCalibrator()
    calibrator.add_clicks(scene(), [CENTER])
    calibrator.reset()
    assert calibrator.sample_count == 0
    with pytest.raises(ValueError):
        calibrator.calibrate(scene())


# --- Resolution -------------------------------------------------------------


@pytest.mark.parametrize("size", [(320, 240), (640, 480), (1280, 720)])
def test_it_works_at_different_resolutions(size):
    frame = scene(width=size[0], height=size[1], noise_std=5, seed=2)
    result = ColorCalibrator().add_clicks(frame, [CENTER])
    assert result.detection.found
    assert result.other_regions == 0
    assert result.detection.horizontal == pytest.approx(0.5, abs=0.01)
    assert math.isclose(result.settings.hue_center, 15, abs_tol=2)
