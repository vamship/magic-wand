import math
import time

import cv2
import numpy as np
import pytest

from wand_core.render import END_COLOR, START_COLOR, encode_png, render_path


def circle(n=60, cx=0.5, cy=0.5, r=0.3):
    return [
        (
            cx + r * math.cos(2 * math.pi * i / n),
            cy + r * math.sin(2 * math.pi * i / n),
        )
        for i in range(n)
    ]


def near(image, color, point, tolerance=60):
    x, y = point
    patch = image[max(y - 1, 0) : y + 2, max(x - 1, 0) : x + 2].reshape(-1, 3)
    return np.any(np.abs(patch.astype(int) - color).max(axis=1) <= tolerance)


def pixel(size, position):
    return (
        round(position[0] * (size[0] - 1)),
        round(position[1] * (size[1] - 1)),
    )


@pytest.mark.parametrize("size", [(96, 72), (640, 480), (1280, 720)])
def test_the_image_has_the_requested_size_and_marks_both_ends(size):
    path = [(0.1, 0.8), (0.4, 0.3), (0.9, 0.5)]
    image = render_path(path, size)
    assert image.shape == (size[1], size[0], 3)
    assert near(image, START_COLOR, pixel(size, path[0]))
    assert near(image, END_COLOR, pixel(size, path[-1]))


def test_the_background_is_black_in_path_mode():
    image = render_path([(0.2, 0.2), (0.8, 0.8)], (640, 480))
    assert (image[0, 639] == 0).all() and (image[479, 0] == 0).all()


def test_the_gradient_runs_from_start_to_end():
    size = (640, 480)
    path = [(0.1, 0.5), (0.9, 0.5)]
    image = render_path(path, size)
    y = pixel(size, (0, 0.5))[1]
    early = image[y, int(0.25 * 639)].astype(int)
    late = image[y, int(0.75 * 639)].astype(int)
    assert abs(early - START_COLOR).sum() < abs(early - END_COLOR).sum()
    assert abs(late - END_COLOR).sum() < abs(late - START_COLOR).sum()


def test_overlay_draws_on_a_resized_copy_and_leaves_the_input_alone():
    frame = np.full((120, 160, 3), 90, np.uint8)
    original = frame.copy()
    image = render_path([(0.2, 0.2), (0.8, 0.8)], (320, 240), frame)
    assert image.shape == (240, 320, 3)
    assert (frame == original).all()
    assert tuple(image[5, 315]) == (90, 90, 90)  # background is the frame
    assert image is not frame


def test_overlay_accepts_grayscale_frames():
    frame = np.full((120, 160), 90, np.uint8)
    image = render_path([(0.2, 0.2), (0.8, 0.8)], (160, 120), frame)
    assert image.shape == (120, 160, 3)


def test_empty_and_single_position_gestures_draw():
    assert not render_path([], (96, 72)).any()
    single = render_path([(0.5, 0.5)], (96, 72))
    assert single.any()
    assert near(single, START_COLOR, pixel((96, 72), (0.5, 0.5)))


def test_positions_are_not_mirrored():
    size = (200, 100)
    image = render_path([(0.1, 0.5), (0.3, 0.5)], size)
    assert image[:, :100].any() and not image[:, 100:].any()


def test_positions_outside_the_frame_are_kept_on_the_canvas():
    image = render_path([(-0.5, 1.5), (1.5, -0.5)], (96, 72))
    assert image.shape == (72, 96, 3) and image.any()


def test_a_bad_size_is_refused():
    with pytest.raises(ValueError):
        render_path([(0.5, 0.5)], (0, 10))


def test_a_typical_gesture_renders_quickly():
    path = circle(90)
    render_path(path, (640, 480))
    start = time.perf_counter()
    for _ in range(20):
        render_path(path, (640, 480))
    assert (time.perf_counter() - start) / 20 < 0.02


def test_png_bytes_decode_to_the_same_image():
    image = render_path(circle(), (96, 72))
    png = encode_png(image)
    assert png.startswith(b"\x89PNG")
    decoded = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    assert (decoded == image).all()
