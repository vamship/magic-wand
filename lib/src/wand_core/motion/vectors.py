"""Vector builder: positions to motion vectors.

For each pair of consecutive positions: the displacement, the time between
them and the speed. Distances are in frame-heights, so the horizontal
difference is scaled by the frame's aspect ratio and the result does not
depend on the frame size. Vectors are never stored; training and inference
both call this function (``lib/docs/design.md`` section 10).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

COLUMNS = ("dx", "dy", "dt", "speed")


def build_vectors(
    time_s: Sequence[float],
    horizontal: Sequence[float],
    vertical: Sequence[float],
    frame_size: tuple[int, int],
) -> np.ndarray:
    """One row per step, columns ``dx``, ``dy``, ``dt`` and ``speed``.

    ``horizontal`` and ``vertical`` are fractions of the frame, ``frame_size``
    is (width, height). ``dx`` and ``dy`` are in frame-heights, ``dt`` in
    seconds and ``speed`` in frame-heights per second (0 when ``dt`` is not
    positive). Fewer than two positions give an empty (0, 4) array.
    """
    if not len(time_s) == len(horizontal) == len(vertical):
        raise ValueError("time, horizontal and vertical differ in length")
    width, height = frame_size
    if width <= 0 or height <= 0:
        raise ValueError("the frame size must be positive")
    if len(time_s) < 2:
        return np.zeros((0, len(COLUMNS)))
    aspect = width / height
    dx = np.diff(np.asarray(horizontal, dtype=float)) * aspect
    dy = np.diff(np.asarray(vertical, dtype=float))
    dt = np.diff(np.asarray(time_s, dtype=float))
    distance = np.hypot(dx, dy)
    speed = np.divide(
        distance, dt, out=np.zeros_like(distance), where=dt > 0
    )
    return np.column_stack([dx, dy, dt, speed])
