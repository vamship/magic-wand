"""Gesture normalization: positions to a fixed-size list of numbers.

Implements ``docs/architecture.md`` section 4.3 and ``lib/docs/design.md``
section 10. Training and inference both call this module, so a gesture gives
the same numbers in both. Nothing here is stored in a dataset.

The output of one gesture is the ``(dx, dy, magnitude)`` of each of the
``points - 1`` steps in order, followed by the duration in seconds: with the
default 64 points, 190 numbers.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

import numpy as np

NORMALIZATION_VERSION = 1
"""Increases whenever a change alters the normalizer's output."""

DEFAULT_POINTS = 64
"""The fixed number of points; every saved classifier records it."""

NUMBERS_PER_STEP = 3

Gesture = tuple[
    Sequence[float], Sequence[float], Sequence[float], tuple[int, int]
]
"""``(time_s, horizontal, vertical, frame_size)`` of one gesture."""


def settings(points: int = DEFAULT_POINTS) -> dict[str, int]:
    """The normalization settings to record with a result or a classifier."""
    return {"points": points, "version": NORMALIZATION_VERSION}


def output_size(points: int = DEFAULT_POINTS) -> int:
    """How many numbers a normalized gesture has."""
    return (points - 1) * NUMBERS_PER_STEP + 1


def normalize(
    time_s: Sequence[float],
    horizontal: Sequence[float],
    vertical: Sequence[float],
    frame_size: tuple[int, int],
    points: int = DEFAULT_POINTS,
) -> np.ndarray:
    """Normalize one gesture into a one-dimensional array of floats.

    ``time_s`` is in seconds from the first position, ``horizontal`` and
    ``vertical`` are fractions of the frame and ``frame_size`` is (width,
    height) in pixels. Raises ``ValueError`` for mismatched lengths, a
    non-positive frame size, fewer than two positions, times that go
    backwards, or a duration of zero or less.
    """
    if points < 2:
        raise ValueError("points must be at least 2")
    width, height = frame_size
    if width <= 0 or height <= 0:
        raise ValueError("the frame size must be positive")
    if not len(time_s) == len(horizontal) == len(vertical):
        raise ValueError("time, horizontal and vertical differ in length")
    if len(time_s) < 2:
        raise ValueError("a gesture needs at least 2 positions")

    times = np.asarray(time_s, dtype=float)
    xs = np.asarray(horizontal, dtype=float) * (width / height)
    ys = np.asarray(vertical, dtype=float)
    if np.any(np.diff(times) < 0):
        raise ValueError("the times must not go backwards")
    times, xs, ys = _merge_equal_times(times, xs, ys)
    if len(times) < 2:
        raise ValueError("the gesture's duration must be above zero")
    duration = float(times[-1] - times[0])

    moments = times[0] + np.arange(points) * (duration / (points - 1))
    moments[-1] = times[-1]
    path = np.column_stack(
        [np.interp(moments, times, xs), np.interp(moments, times, ys)]
    )
    path -= path[0]
    steps = np.diff(path, axis=0)
    magnitude = np.hypot(steps[:, 0], steps[:, 1])
    return np.concatenate(
        [np.column_stack([steps, magnitude]).ravel(), [duration]]
    )


def normalize_batch(
    gestures: Iterable[Gesture], points: int = DEFAULT_POINTS
) -> np.ndarray:
    """Normalize many gestures: a 2-D array with one row per gesture."""
    rows = [normalize(*gesture, points=points) for gesture in gestures]
    if not rows:
        return np.zeros((0, output_size(points)))
    return np.vstack(rows)


def _merge_equal_times(
    times: np.ndarray, xs: np.ndarray, ys: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Replace positions that share a timestamp with their average."""
    unique, first, counts = np.unique(
        times, return_index=True, return_counts=True
    )
    if len(unique) == len(times):
        return times, xs, ys
    groups = np.repeat(np.arange(len(unique)), counts)
    return (
        unique,
        np.bincount(groups, weights=xs[np.argsort(times, kind="stable")])
        / counts,
        np.bincount(groups, weights=ys[np.argsort(times, kind="stable")])
        / counts,
    )
