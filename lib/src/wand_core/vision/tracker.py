"""Tracker: finds the center of the colored ball in a single frame.

Steps (``lib/docs/design.md`` section 6): smooth the frame, mark the pixels
inside the color range, remove specks and fill small holes, find connected
regions, discard those outside the size range or not round enough, choose the
best remaining region (preferring one near the previous tip) and report the
center of its enclosing circle.

The tracker takes frames only; it never touches a camera or a file.
"""

import math

import cv2
import numpy as np

from wand_core.settings import VisionSettings
from wand_core.types import TipDetection

_HUE_MAX = 179


class Tracker:
    """Finds the tip in each frame it is given.

    The only memory is the previous tip position, used to choose between
    candidate regions. ``settings`` may be replaced at any time, for example
    while the user adjusts the calibration.
    """

    def __init__(self, settings: VisionSettings | None = None) -> None:
        self.settings = settings or VisionSettings()
        self._previous: tuple[float, float] | None = None  # pixels
        self.last_mask: np.ndarray | None = None  # mask of the last frame

    def reset(self) -> None:
        """Forget the previous tip."""
        self._previous = None

    def mask(self, frame: np.ndarray) -> np.ndarray:
        """Return the binary mask (0 or 255) of pixels that match the color.

        This is the mask used for detection, after cleanup.
        """
        s = self.settings
        hsv = cv2.cvtColor(smooth(frame, s.blur_size), cv2.COLOR_BGR2HSV)
        marked = np.zeros(frame.shape[:2], dtype=np.uint8)
        for low, high in _hue_bands(s.hue_center, s.hue_half_width):
            marked |= cv2.inRange(
                hsv,
                (low, s.sat_min, s.val_min),
                (high, s.sat_max, s.val_max),
            )
        if s.cleanup_size > 0:
            kernel = cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE, (s.cleanup_size, s.cleanup_size)
            )
            marked = cv2.morphologyEx(marked, cv2.MORPH_OPEN, kernel)
            marked = cv2.morphologyEx(marked, cv2.MORPH_CLOSE, kernel)
        return marked

    def process(self, frame: np.ndarray, timestamp_s: float) -> TipDetection:
        """Find the tip in ``frame``, taken at ``timestamp_s``."""
        height, width = frame.shape[:2]
        self.last_mask = self.mask(frame)
        regions = self._candidates(self.last_mask, width, height)
        if not regions:
            return TipDetection(timestamp_s=timestamp_s, found=False)
        (x, y), radius = self._choose(regions)
        self._previous = (x, y)
        return TipDetection(
            timestamp_s=timestamp_s,
            found=True,
            horizontal=x / width,
            vertical=y / height,
            radius=radius / height,
        )

    def _candidates(self, mask: np.ndarray, width: int, height: int) -> list:
        """Regions that pass the size and roundness tests.

        Each is ``(area, (x, y), radius)`` with pixel units.
        """
        s = self.settings
        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        frame_area = float(width * height)
        regions = []
        for contour in contours:
            area = cv2.contourArea(contour)
            fraction = area / frame_area
            if area <= 0 or not s.min_area <= fraction <= s.max_area:
                continue
            perimeter = cv2.arcLength(contour, True)
            if perimeter <= 0:
                continue
            roundness = 4 * math.pi * area / (perimeter * perimeter)
            if roundness < s.min_roundness:
                continue
            center, radius = cv2.minEnclosingCircle(contour)
            regions.append((area, center, radius))
        return regions

    def _choose(self, regions: list) -> tuple[tuple[float, float], float]:
        """Nearest to the previous tip, else the largest."""
        if self._previous is None:
            _, center, radius = max(regions, key=lambda r: r[0])
        else:
            px, py = self._previous
            _, center, radius = min(
                regions,
                key=lambda r: (r[1][0] - px) ** 2 + (r[1][1] - py) ** 2,
            )
        return center, radius


def smooth(frame: np.ndarray, blur_size: int) -> np.ndarray:
    """Reduce sensor noise; ``blur_size`` 0 leaves the frame as it is."""
    if blur_size <= 0:
        return frame
    size = blur_size if blur_size % 2 else blur_size + 1
    return cv2.GaussianBlur(frame, (size, size), 0)


def _hue_bands(center: int, half_width: int) -> list[tuple[int, int]]:
    """Split a hue interval on the circle into bands within 0 to 179."""
    if half_width * 2 + 1 >= _HUE_MAX + 1:
        return [(0, _HUE_MAX)]
    low, high = center - half_width, center + half_width
    circle = _HUE_MAX + 1
    if low < 0:
        return [(0, high), (low + circle, _HUE_MAX)]
    if high > _HUE_MAX:
        return [(low, _HUE_MAX), (0, high - circle)]
    return [(low, high)]
