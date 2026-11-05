"""Path renderer: draws a gesture's path as an image.

The path is a polyline whose color runs from the start color to the end
color, with a small circle at the start and a small square at the end, so
the direction is clear even in a thumbnail. Positions are fractions of the
frame, drawn exactly as given; the caller mirrors them for display
(``lib/docs/design.md`` section 11).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import cv2
import numpy as np

# BGR colors: the path runs from green to red.
START_COLOR = (80, 200, 40)
END_COLOR = (40, 40, 240)
OUTLINE_COLOR = (0, 0, 0)
MARKER_RIM_COLOR = (255, 255, 255)
MAX_PIECES = 24  # per segment


def render_path(
    positions: Sequence[tuple[float, float]],
    size: tuple[int, int],
    frame: np.ndarray | None = None,
) -> np.ndarray:
    """Draw the path as a BGR image of ``size`` (width, height).

    ``positions`` are ``(horizontal, vertical)`` fractions of the frame. With
    no ``frame`` the path is drawn on black; with one, on a resized copy of
    it (the input is never changed).
    """
    width, height = size
    if width < 1 or height < 1:
        raise ValueError("the image size must be positive")
    if frame is None:
        canvas = np.zeros((height, width, 3), np.uint8)
    else:
        canvas = _as_bgr(cv2.resize(frame, (width, height)))
    if len(positions) == 0:
        return canvas

    points = [
        (
            int(round(min(max(h, 0.0), 1.0) * (width - 1))),
            int(round(min(max(v, 0.0), 1.0) * (height - 1))),
        )
        for h, v in positions
    ]
    line = max(2, height // 60)
    marker = max(3, height // 60)

    # A dark outline under the colored line keeps it visible on any frame.
    for a, b in zip(points, points[1:]):
        cv2.line(canvas, a, b, OUTLINE_COLOR, line + 2, cv2.LINE_AA)
    _draw_gradient(canvas, points, line)

    _draw_start(canvas, points[0], marker)
    if len(points) > 1:
        _draw_end(canvas, points[-1], marker)
    return canvas


def _draw_gradient(
    canvas: np.ndarray, points: list[tuple[int, int]], thickness: int
) -> None:
    """Color each piece by how far along the path it lies (by length).

    Long segments are cut into pieces, so even a single stroke shows the
    gradient.
    """
    lengths = [math.dist(a, b) for a, b in zip(points, points[1:])]
    total = sum(lengths) or 1.0
    done = 0.0
    for (a, b), length in zip(zip(points, points[1:]), lengths):
        pieces = min(MAX_PIECES, max(1, int(length // (thickness * 4))))
        for k in range(pieces):
            t0, t1 = k / pieces, (k + 1) / pieces
            p0 = (a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0)
            p1 = (a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1)
            fraction = (done + length * (t0 + t1) / 2) / total
            cv2.line(
                canvas,
                (round(p0[0]), round(p0[1])),
                (round(p1[0]), round(p1[1])),
                _blend(fraction),
                thickness,
                cv2.LINE_AA,
            )
        done += length


def encode_png(image: np.ndarray) -> bytes:
    """The image as PNG bytes."""
    ok, png = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("the image could not be encoded")
    return png.tobytes()


def _as_bgr(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    return image


def _blend(fraction: float) -> tuple[int, int, int]:
    return tuple(
        int(round(s + (e - s) * fraction))
        for s, e in zip(START_COLOR, END_COLOR)
    )


def _draw_start(canvas: np.ndarray, center: tuple[int, int], r: int) -> None:
    cv2.circle(canvas, center, r + 1, MARKER_RIM_COLOR, -1, cv2.LINE_AA)
    cv2.circle(canvas, center, r - 1, START_COLOR, -1, cv2.LINE_AA)


def _draw_end(canvas: np.ndarray, center: tuple[int, int], r: int) -> None:
    x, y = center
    cv2.rectangle(
        canvas,
        (x - r - 1, y - r - 1),
        (x + r + 1, y + r + 1),
        MARKER_RIM_COLOR,
        -1,
    )
    cv2.rectangle(
        canvas, (x - r + 1, y - r + 1), (x + r - 1, y + r - 1), END_COLOR, -1
    )
