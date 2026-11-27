import numpy as np
import pytest

from wand_core.normalize import (
    DEFAULT_POINTS,
    NORMALIZATION_VERSION,
    normalize,
    normalize_batch,
    output_size,
    settings,
)

SQUARE = (100, 100)

EXAMPLE_TIMES = [0.0, 0.10, 0.20, 0.45, 0.50, 0.80, 1.00]
EXAMPLE_X = [0.30, 0.34, 0.40, 0.52, 0.54, 0.60, 0.62]
EXAMPLE_Y = [0.50, 0.44, 0.38, 0.30, 0.30, 0.38, 0.46]


def circle(count, duration=1.0, offset=(0.5, 0.5)):
    times = np.linspace(0, duration, count)
    angle = np.linspace(0, 2 * np.pi, count)
    return (
        times,
        offset[0] + 0.1 * np.cos(angle),
        offset[1] + 0.1 * np.sin(angle),
    )


def test_worked_example_from_the_architecture():
    result = normalize(EXAMPLE_TIMES, EXAMPLE_X, EXAMPLE_Y, SQUARE, points=5)
    expected = [
        (0.124, -0.136, 0.184),
        (0.116, -0.064, 0.132),
        (0.050, 0.067, 0.083),
        (0.030, 0.093, 0.098),
    ]
    assert result.shape == (13,)
    np.testing.assert_allclose(result[:-1].reshape(4, 3), expected, atol=1e-3)
    assert result[-1] == pytest.approx(1.0)


def test_default_settings_give_190_numbers():
    result = normalize(*circle(30), SQUARE)
    assert result.shape == (190,)
    assert output_size() == 190
    assert normalize([0, 1], [0.1, 0.2], [0.1, 0.2], SQUARE).shape == (190,)


def test_settings_record_points_and_version():
    assert settings() == {"points": DEFAULT_POINTS, "version": 1}
    assert NORMALIZATION_VERSION == 1
    assert settings(8)["points"] == 8


def test_duration_scales_but_steps_do_not():
    fast = normalize(*circle(30, 1.0), SQUARE)
    slow = normalize(*circle(30, 2.0), SQUARE)
    np.testing.assert_allclose(fast[:-1], slow[:-1], atol=1e-12)
    assert fast[-1] == pytest.approx(1.0)
    assert slow[-1] == pytest.approx(2.0)


def test_position_in_the_frame_is_discarded():
    first = normalize(*circle(30, offset=(0.3, 0.4)), SQUARE)
    second = normalize(*circle(30, offset=(0.7, 0.6)), SQUARE)
    np.testing.assert_allclose(first, second, atol=1e-12)


def test_frame_rate_and_dropped_frames_keep_the_shape():
    dense = normalize(*circle(400), SQUARE)
    sparse = normalize(*circle(60), SQUARE)
    times, xs, ys = circle(400)
    keep = np.ones(400, dtype=bool)
    keep[100:140] = False
    dropped = normalize(times[keep], xs[keep], ys[keep], SQUARE)
    assert sparse.shape == dropped.shape == dense.shape
    np.testing.assert_allclose(sparse, dense, atol=5e-3)
    np.testing.assert_allclose(dropped, dense, atol=5e-3)


def test_frame_size_and_aspect_ratio():
    args = circle(30)
    small = normalize(*args, (320, 240))
    large = normalize(*args, (640, 480))
    np.testing.assert_allclose(small, large, atol=1e-12)
    wide = normalize(*args, (640, 240))  # twice the aspect ratio
    np.testing.assert_allclose(wide[0:-1:3], small[0:-1:3] * 2)
    np.testing.assert_allclose(wide[1:-1:3], small[1:-1:3])


@pytest.mark.parametrize(
    "positions",
    [
        ([0.0], [0.1], [0.1]),
        ([], [], []),
        ([0.0, 1.0], [0.1], [0.1, 0.2]),
        ([0.0, 0.0], [0.1, 0.2], [0.1, 0.2]),
        ([1.0, 0.0], [0.1, 0.2], [0.1, 0.2]),
    ],
)
def test_invalid_gestures_are_rejected(positions):
    with pytest.raises(ValueError):
        normalize(*positions, SQUARE)


def test_bad_frame_size_is_rejected():
    with pytest.raises(ValueError, match="frame size"):
        normalize([0, 1], [0, 1], [0, 1], (0, 100))


def test_equal_timestamps_are_averaged():
    merged = normalize([0, 0.5, 0.5, 1], [0, 0.2, 0.4, 0.6], [0] * 4, SQUARE, 3)
    clean = normalize([0, 0.5, 1], [0, 0.3, 0.6], [0] * 3, SQUARE, 3)
    np.testing.assert_allclose(merged, clean)


def test_batch_matches_one_by_one():
    gestures = [
        (t, x, y, SQUARE)
        for t, x, y in (circle(20), circle(35, 2.0), circle(50, 0.5))
    ]
    batch = normalize_batch(gestures)
    assert batch.shape == (3, 190)
    for row, gesture in zip(batch, gestures):
        np.testing.assert_array_equal(row, normalize(*gesture))
    assert normalize_batch([]).shape == (0, 190)
