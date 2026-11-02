"""Color calibrator: vision settings from clicks on the wand tip.

The user clicks on the ball in a frame. For each click the calibrator takes
the pixels in a small disc, finds the typical color (a circular average for
hue, which wraps around) and its spread, and sets each range to the typical
value plus a margin proportional to the spread. A minimum margin lets very
uniform patches tolerate lighting changes. More clicks add samples and widen
the ranges (``lib/docs/design.md`` section 7).

The result is checked by running the tracker, so it is what the live view
will show.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

from wand_core.settings import VisionSettings
from wand_core.types import TipDetection
from wand_core.vision.tracker import Tracker, smooth

DEFAULT_TOLERANCE = 2.5  # margin = tolerance x spread
MIN_HUE_MARGIN = 8  # OpenCV hue units (0 to 179)
MIN_SV_MARGIN = 40  # saturation and brightness (0 to 255)
DISC_RADIUS = 0.01  # of the frame height, at least MIN_DISC_RADIUS pixels
MIN_DISC_RADIUS = 3
MIN_USABLE_SATURATION = 40  # below this the color is gray or white
MIN_USABLE_VALUE = 50  # below this the color is black
HUE_UNITS = 180  # hue is an angle of 2 degrees per unit


class UnusableColorError(ValueError):
    """The clicked spot has no color to calibrate on (black, gray, white)."""


@dataclass(frozen=True)
class ColorCalibration:
    """The result of a calibration run.

    ``other_regions`` is how many regions the mask marks besides the clicked
    ones, so the user can tighten the tolerance or click a more distinctive
    spot.
    """

    settings: VisionSettings
    mask: np.ndarray
    detection: TipDetection
    other_regions: int
    sample_count: int


class ColorCalibrator:
    """Collects color samples from clicks and derives vision settings."""

    def __init__(
        self,
        base: VisionSettings | None = None,
        tolerance: float = DEFAULT_TOLERANCE,
    ) -> None:
        self.base = base or VisionSettings()
        self.tolerance = tolerance
        self.reset()

    def reset(self) -> None:
        """Forget every click."""
        self._samples = np.empty((0, 3), dtype=np.float64)  # h, s, v
        self._clicks: list[tuple[float, float]] = []  # fractions

    @property
    def sample_count(self) -> int:
        return len(self._samples)

    def add_clicks(
        self,
        frame: np.ndarray,
        points: list[tuple[float, float]],
        timestamp_s: float = 0.0,
    ) -> ColorCalibration:
        """Add the colors around clicked points (fractions of the frame).

        If any point has no usable color, nothing is added and
        ``UnusableColorError`` is raised.
        """
        if not points:
            raise ValueError("at least one point is needed")
        smoothed = smooth(frame, self.base.blur_size)
        hsv = cv2.cvtColor(smoothed, cv2.COLOR_BGR2HSV)
        gathered = [_disc_pixels(hsv, point) for point in points]
        for point, pixels in zip(points, gathered):
            _require_usable(point, pixels)
        self._samples = np.vstack([self._samples, *gathered])
        self._clicks.extend(points)
        return self.calibrate(frame, timestamp_s=timestamp_s)

    def calibrate(
        self,
        frame: np.ndarray,
        tolerance: float | None = None,
        timestamp_s: float = 0.0,
    ) -> ColorCalibration:
        """Derive settings from the samples so far and check them on ``frame``.

        Pass ``tolerance`` to change it for this and later runs without
        clicking again.
        """
        if tolerance is not None:
            self.tolerance = tolerance
        if not len(self._samples):
            raise ValueError("click on the wand tip first")
        settings = self._settings_from_samples()
        tracker = Tracker(settings)
        detection = tracker.process(frame, timestamp_s)
        mask = tracker.last_mask
        return ColorCalibration(
            settings=settings,
            mask=mask,
            detection=detection,
            other_regions=self._count_other_regions(mask, settings),
            sample_count=self.sample_count,
        )

    # --- Working out the ranges ------------------------------------------

    def _settings_from_samples(self) -> VisionSettings:
        hue, sat, val = self._samples.T
        center, hue_spread = _circular_stats(hue)
        hue_margin = max(self.tolerance * hue_spread, MIN_HUE_MARGIN)
        sat_low, sat_high = _linear_range(sat, self.tolerance)
        val_low, val_high = _linear_range(val, self.tolerance)
        return self.base.model_copy(
            update={
                "hue_center": int(round(center)) % HUE_UNITS,
                "hue_half_width": min(90, int(math.ceil(hue_margin))),
                "sat_min": sat_low,
                "sat_max": sat_high,
                "val_min": val_low,
                "val_max": val_high,
            }
        )

    def _count_other_regions(
        self, mask: np.ndarray, settings: VisionSettings
    ) -> int:
        """Marked regions big enough to matter that no click is inside."""
        height, width = mask.shape
        count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
        clicked = set()
        for horizontal, vertical in self._clicks:
            x = min(width - 1, int(horizontal * width))
            y = min(height - 1, int(vertical * height))
            if labels[y, x]:
                clicked.add(int(labels[y, x]))
        minimum = settings.min_area * width * height
        return sum(
            1
            for label in range(1, count)
            if label not in clicked
            and stats[label, cv2.CC_STAT_AREA] >= minimum
        )


# --- Helpers ----------------------------------------------------------------


def _disc_pixels(hsv: np.ndarray, point: tuple[float, float]) -> np.ndarray:
    """The (h, s, v) of the pixels in a small disc around a point."""
    horizontal, vertical = point
    if not (0.0 <= horizontal <= 1.0 and 0.0 <= vertical <= 1.0):
        raise ValueError(f"point {point} is outside the frame")
    height, width = hsv.shape[:2]
    radius = max(MIN_DISC_RADIUS, round(DISC_RADIUS * height))
    cx = min(width - 1, int(horizontal * width))
    cy = min(height - 1, int(vertical * height))
    ys, xs = np.ogrid[:height, :width]
    inside = (xs - cx) ** 2 + (ys - cy) ** 2 <= radius**2
    return hsv[inside].astype(np.float64)


def _require_usable(point: tuple[float, float], pixels: np.ndarray) -> None:
    saturation = float(np.median(pixels[:, 1]))
    value = float(np.median(pixels[:, 2]))
    if value < MIN_USABLE_VALUE:
        raise UnusableColorError(
            f"the spot at {point} is too dark to have a color; "
            "click on the ball"
        )
    if saturation < MIN_USABLE_SATURATION:
        raise UnusableColorError(
            f"the spot at {point} is gray or white, with no color to "
            "calibrate on; click on the ball"
        )


def _circular_stats(hue: np.ndarray) -> tuple[float, float]:
    """Mean hue and its spread, treating hue as an angle that wraps."""
    angles = hue * (2 * math.pi / HUE_UNITS)
    mean_angle = math.atan2(np.sin(angles).mean(), np.cos(angles).mean())
    center = (mean_angle * HUE_UNITS / (2 * math.pi)) % HUE_UNITS
    # Each sample's signed distance from the mean, in -90..90.
    offset = (hue - center + HUE_UNITS / 2) % HUE_UNITS - HUE_UNITS / 2
    return center, float(offset.std())


def _linear_range(values: np.ndarray, tolerance: float) -> tuple[int, int]:
    margin = max(tolerance * float(values.std()), MIN_SV_MARGIN)
    mean = float(values.mean())
    return (
        max(0, int(math.floor(mean - margin))),
        min(255, int(math.ceil(mean + margin))),
    )
