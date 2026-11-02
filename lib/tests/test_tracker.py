import math

import cv2
import numpy as np
import pytest

from wand_core.settings import VisionSettings
from wand_core.testing.synthetic import (
    SceneStyle,
    circle_path,
    figure_eight_path,
    generate,
    hsv_color,
    line_path,
    render_frame,
    write_video,
)
from wand_core.vision import Tracker

PATHS = {
    "circle": circle_path(60),
    "line": line_path(60),
    "eight": figure_eight_path(60),
}


def track(path, style, settings=None):
    tracker = Tracker(settings)
    errors, found = [], 0
    count = 0
    for frame in generate(path, style):
        count += 1
        tip = tracker.process(frame.image, frame.timestamp_s)
        assert tip.timestamp_s == frame.timestamp_s
        if tip.found:
            found += 1
            dx = (tip.horizontal - frame.truth[0]) * style.width
            dy = (tip.vertical - frame.truth[1]) * style.height
            errors.append(math.hypot(dx, dy) / style.height)
    return float(np.mean(errors)) if errors else 1.0, found / count


@pytest.mark.parametrize("path_name", PATHS)
@pytest.mark.parametrize(
    "style",
    [
        SceneStyle(),
        SceneStyle(background="light", noise_std=6, seed=1),
        SceneStyle(background="gradient", noise_std=8, seed=2),
        SceneStyle(background="clutter", noise_std=5, seed=3),
        SceneStyle(brightness=0.8, noise_std=5, seed=4),
        SceneStyle(brightness=1.1, background="gradient", seed=5),
    ],
    ids=["dark", "light-noise", "gradient-noise", "clutter", "dim", "bright"],
)
def test_tracks_known_paths(path_name, style):
    error, found = track(PATHS[path_name], style)
    assert error < 0.015
    assert found >= 0.95


def test_radius_in_frame_heights():
    style = SceneStyle(disk_radius=0.05)
    frame = render_frame(style, (0.5, 0.5))
    tip = Tracker().process(frame, 1.0)
    assert tip.radius == pytest.approx(0.05, abs=0.01)


@pytest.mark.parametrize("hue", [0, 3, 176, 179])
def test_red_across_the_wrap_around(hue):
    settings = VisionSettings(hue_center=0, hue_half_width=10)
    style = SceneStyle(disk_hsv=(hue, 220, 230))
    error, found = track(circle_path(30), style, settings)
    assert found == 1.0
    assert error < 0.015


def test_hue_interval_past_the_top_end():
    settings = VisionSettings(hue_center=178, hue_half_width=8)
    style = SceneStyle(disk_hsv=(3, 220, 230))
    assert track(circle_path(10), style, settings)[1] == 1.0


def test_other_colors_are_ignored():
    style = SceneStyle(disk_hsv=(100, 220, 230))  # blue
    assert track(circle_path(10), style)[1] == 0.0


def test_no_ball_gives_not_found():
    frame = render_frame(SceneStyle(), None)
    tip = Tracker().process(frame, 2.5)
    assert not tip.found
    assert tip.timestamp_s == 2.5
    assert tip.horizontal is None
    assert tip.vertical is None
    assert tip.radius is None


def blank():
    return np.full((480, 640, 3), 40, dtype=np.uint8)


def paint(frame, shape, center, size):
    color = hsv_color(15, 220, 230)
    x, y = center
    if shape == "disk":
        cv2.circle(frame, (x, y), size, color, -1)
    else:
        cv2.rectangle(
            frame,
            (x - size * 4, y - size // 2),
            (x + size * 4, y + size // 2),
            color,
            -1,
        )


def test_speck_below_min_area_is_ignored():
    frame = blank()
    paint(frame, "disk", (300, 200), 2)  # area ~ 13 px << min_area
    assert not Tracker().process(frame, 0).found


def test_region_above_max_area_is_ignored():
    frame = blank()
    paint(frame, "disk", (320, 240), 150)  # about 23% of the frame
    assert not Tracker().process(frame, 0).found


def test_non_round_region_is_ignored():
    frame = blank()
    paint(frame, "bar", (320, 240), 10)  # 80 x 10 bar, roundness ~ 0.3
    assert not Tracker().process(frame, 0).found
    # Allowed when the roundness limit is lowered.
    relaxed = Tracker(VisionSettings(min_roundness=0.1))
    assert relaxed.process(frame, 0).found


def test_nearest_to_previous_tip_wins():
    near_left = blank()
    paint(near_left, "disk", (100, 240), 20)
    both = blank()
    paint(both, "disk", (100, 240), 20)
    paint(both, "disk", (500, 240), 30)  # larger

    fresh = Tracker().process(both, 0)
    assert fresh.horizontal == pytest.approx(500 / 640, abs=0.01)

    tracker = Tracker()
    tracker.process(near_left, 0)
    chosen = tracker.process(both, 1)
    assert chosen.horizontal == pytest.approx(100 / 640, abs=0.01)

    tracker.reset()
    assert tracker.process(both, 2).horizontal == pytest.approx(
        500 / 640, abs=0.01
    )


def test_mask_is_binary_and_matches_detection():
    frame = render_frame(SceneStyle(), (0.5, 0.5))
    mask = Tracker().mask(frame)
    assert mask.shape == frame.shape[:2]
    assert mask.dtype == np.uint8
    assert set(np.unique(mask)) <= {0, 255}
    assert mask[240, 320] == 255
    assert mask[10, 10] == 0


@pytest.mark.parametrize("size", [(320, 240), (640, 480), (1280, 720)])
def test_same_settings_work_at_different_resolutions(size):
    style = SceneStyle(width=size[0], height=size[1])
    error, found = track(circle_path(20), style)
    assert found == 1.0
    assert error < 0.015


def test_write_video_round_trip(tmp_path):
    file = tmp_path / "clip.avi"
    path = circle_path(15)
    write_video(path, file, SceneStyle())
    capture = cv2.VideoCapture(str(file))
    tracker = Tracker()
    count = 0
    while True:
        ok, image = capture.read()
        if not ok:
            break
        assert tracker.process(image, count / 30).found
        count += 1
    capture.release()
    assert count == 15
