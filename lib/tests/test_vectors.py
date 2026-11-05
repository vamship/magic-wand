import numpy as np
import pytest

from wand_core.motion.vectors import build_vectors


def test_n_positions_give_n_minus_one_vectors():
    vectors = build_vectors(
        [0, 0.1, 0.2, 0.3], [0.1, 0.2, 0.3, 0.4], [0.5] * 4, (640, 480)
    )
    assert vectors.shape == (3, 4)


def test_units_are_frame_heights_and_seconds():
    # Across the full width of a 4:3 frame in half a second.
    vectors = build_vectors([0.0, 0.5], [0.0, 1.0], [0.5, 0.5], (640, 480))
    dx, dy, dt, speed = vectors[0]
    assert dx == pytest.approx(4 / 3)
    assert dy == 0 and dt == 0.5
    assert speed == pytest.approx(4 / 3 / 0.5)


def test_vertical_steps_and_diagonals():
    vectors = build_vectors([0, 1], [0.5, 0.5 + 0.3], [0.2, 0.6], (400, 400))
    assert vectors[0][:2] == pytest.approx([0.3, 0.4])
    assert vectors[0][3] == pytest.approx(0.5)  # a 3-4-5 step in one second


def test_frame_size_does_not_matter_at_the_same_aspect_ratio():
    args = ([0, 0.1, 0.25], [0.1, 0.4, 0.5], [0.2, 0.3, 0.9])
    small = build_vectors(*args, (320, 240))
    large = build_vectors(*args, (1280, 960))
    assert np.allclose(small, large)


def test_the_aspect_ratio_scales_the_horizontal_step():
    args = ([0, 1], [0.0, 0.5], [0.0, 0.0])
    wide = build_vectors(*args, (1280, 720))
    square = build_vectors(*args, (500, 500))
    assert wide[0][0] == pytest.approx(0.5 * 16 / 9)
    assert square[0][0] == pytest.approx(0.5)


@pytest.mark.parametrize("count", [0, 1])
def test_fewer_than_two_positions_give_nothing(count):
    vectors = build_vectors([0.0][:count], [0.5][:count], [0.5][:count], (4, 3))
    assert vectors.shape == (0, 4)


def test_a_zero_time_step_does_not_divide_by_zero():
    vectors = build_vectors([0.0, 0.0, 0.1], [0, 0.1, 0.2], [0, 0, 0], (4, 3))
    assert vectors[0][2] == 0 and vectors[0][3] == 0
    assert np.isfinite(vectors).all()
    assert vectors[1][3] > 0


def test_bad_input_is_refused():
    with pytest.raises(ValueError):
        build_vectors([0, 1], [0], [0, 1], (4, 3))
    with pytest.raises(ValueError):
        build_vectors([0, 1], [0, 1], [0, 1], (0, 3))
