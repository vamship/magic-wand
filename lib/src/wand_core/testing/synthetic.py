"""Synthetic test videos: a colored disk moving over a background.

Used to test the tracker, the segmenter, the calibrators and the application
without a camera. Every function is deterministic for a given ``seed``.
Positions are fractions of the frame (vertical down), as everywhere else.
"""

import math
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

# An orange that suits the default vision settings (OpenCV hue 15).
ORANGE = (15, 220, 230)  # (hue 0-179, saturation, value)

Path2D = np.ndarray  # shape (n, 2): horizontal, vertical


def hsv_color(hue: int, saturation: int, value: int) -> tuple[int, int, int]:
    """Convert OpenCV HSV to the BGR color to draw with."""
    pixel = np.uint8([[[hue, saturation, value]]])
    b, g, r = cv2.cvtColor(pixel, cv2.COLOR_HSV2BGR)[0, 0]
    return int(b), int(g), int(r)


# --- Paths ------------------------------------------------------------------


def line_path(n: int, start=(0.2, 0.5), end=(0.8, 0.5)) -> Path2D:
    t = np.linspace(0.0, 1.0, n)[:, None]
    return np.asarray(start) * (1 - t) + np.asarray(end) * t


def circle_path(
    n: int, center=(0.5, 0.5), radius: float = 0.25, turns: float = 1.0
) -> Path2D:
    angle = np.linspace(0.0, 2 * math.pi * turns, n)
    return np.stack(
        [
            center[0] + radius * 0.75 * np.cos(angle),  # 4:3 frame
            center[1] + radius * np.sin(angle),
        ],
        axis=1,
    )


def figure_eight_path(
    n: int, center=(0.5, 0.5), radius: float = 0.25
) -> Path2D:
    angle = np.linspace(0.0, 2 * math.pi, n)
    return np.stack(
        [
            center[0] + radius * 0.75 * np.sin(angle),
            center[1] + radius * 0.5 * np.sin(2 * angle),
        ],
        axis=1,
    )


# --- Frames -----------------------------------------------------------------


@dataclass(frozen=True)
class SceneStyle:
    """How a frame looks apart from the disk's position."""

    width: int = 640
    height: int = 480
    disk_hsv: tuple[int, int, int] = ORANGE
    disk_radius: float = 0.04  # in frame-heights
    background: str = "dark"  # dark, light, gradient or clutter
    brightness: float = 1.0  # multiplies the whole frame
    noise_std: float = 0.0  # gray levels
    seed: int = 0


def render_frame(
    style: SceneStyle,
    center: tuple[float, float] | None,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Render one BGR frame with the disk at ``center`` (or none)."""
    rng = rng or np.random.default_rng(style.seed)
    frame = _background(style)
    if center is not None:
        cv2.circle(
            frame,
            (round(center[0] * style.width), round(center[1] * style.height)),
            round(style.disk_radius * style.height),
            hsv_color(*style.disk_hsv),
            -1,
            cv2.LINE_AA,
        )
    frame = frame.astype(np.float32) * style.brightness
    if style.noise_std > 0:
        frame += rng.normal(0.0, style.noise_std, frame.shape)
    return np.clip(frame, 0, 255).astype(np.uint8)


def _background(style: SceneStyle) -> np.ndarray:
    h, w = style.height, style.width
    if style.background == "light":
        return np.full((h, w, 3), 200, dtype=np.uint8)
    if style.background == "gradient":
        ramp = np.linspace(30, 190, w, dtype=np.uint8)
        return np.repeat(ramp[None, :, None], h, axis=0).repeat(3, axis=2)
    if style.background == "clutter":
        # Blue, green and gray blocks, none near the disk's color.
        rng = np.random.default_rng(style.seed + 1)
        frame = np.full((h, w, 3), 60, dtype=np.uint8)
        for _ in range(12):
            x, y = int(rng.integers(0, w - 60)), int(rng.integers(0, h - 60))
            color = [(200, 80, 40), (60, 170, 60), (140, 140, 140)][
                int(rng.integers(0, 3))
            ]
            cv2.rectangle(frame, (x, y), (x + 60, y + 50), color, -1)
        return frame
    return np.full((h, w, 3), 40, dtype=np.uint8)


# --- Videos -----------------------------------------------------------------


@dataclass(frozen=True)
class SyntheticFrame:
    timestamp_s: float
    image: np.ndarray
    truth: tuple[float, float]  # the disk's center, as fractions


def generate(
    path: Path2D, style: SceneStyle | None = None, fps: float = 30.0
) -> Iterator[SyntheticFrame]:
    """Yield a frame for each point of ``path``, with the true center."""
    style = style or SceneStyle()
    rng = np.random.default_rng(style.seed)
    for i, point in enumerate(path):
        center = (float(point[0]), float(point[1]))
        yield SyntheticFrame(i / fps, render_frame(style, center, rng), center)


def write_video(
    path: Path2D,
    file: Path,
    style: SceneStyle | None = None,
    fps: float = 30.0,
) -> None:
    """Write the frames of ``generate`` to a video file (MJPG in an AVI)."""
    style = style or SceneStyle()
    writer = cv2.VideoWriter(
        str(file),
        cv2.VideoWriter_fourcc(*"MJPG"),
        fps,
        (style.width, style.height),
    )
    if not writer.isOpened():
        raise RuntimeError(f"cannot write {file}")
    for frame in generate(path, style, fps):
        writer.write(frame.image)
    writer.release()
