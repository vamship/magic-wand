"""Motion calibrator: motion settings from two short measurements.

The user holds the wand still, then waves it. The still period shows the
speed noise from hand tremor and detector jitter (the idle ceiling, a high
percentile of the measured speeds). The waving period shows the speeds of
real gestures. ``end_speed`` is then a multiple of the idle ceiling and
``start_speed`` lies between it and the typical gesture speed
(``lib/docs/design.md`` section 9). The values are a proposal for the user
to check and adjust.

Speeds are measured by the segmenter itself, so they use the same smoothing
as live detection.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from wand_core.motion import Segmenter
from wand_core.settings import MotionSettings
from wand_core.types import TipDetection

IDLE_PERCENTILE = 95
END_SPEED_FACTOR = 3.0  # end_speed = factor x idle ceiling
MIN_END_SPEED = 0.05  # frame-heights per second
MIN_SAMPLES = 15  # speeds needed from each measurement (about half a second)
MIN_PEAKS = 3  # distinct strokes needed while waving
PEAK_NEIGHBORS = 2  # a peak beats this many samples on each side


class MotionCalibrationError(ValueError):
    """The measurements cannot give thresholds (too little data, no waving)."""


@dataclass(frozen=True)
class MotionCalibration:
    """The proposed settings and the numbers they come from."""

    settings: MotionSettings
    idle_ceiling: float
    typical_gesture_speed: float
    peak_count: int


def speeds_of(
    detections: Sequence[TipDetection],
    settings: MotionSettings | None = None,
    aspect_ratio: float = 4 / 3,
) -> list[float]:
    """The tip speeds the segmenter reports for a stream of detections.

    Frames where the tip was not found are left out, and so is the first
    detection, which has no speed yet.
    """
    segmenter = Segmenter(settings, aspect_ratio=aspect_ratio)
    segmenter.set_enabled(False)  # speeds only; no gestures
    speeds = []
    for index, detection in enumerate(detections):
        update = segmenter.update(detection)
        if detection.found and index > 0:
            speeds.append(update.speed)
    return speeds


def calibrate_motion(
    still: Sequence[TipDetection],
    waving: Sequence[TipDetection],
    base: MotionSettings | None = None,
    aspect_ratio: float = 4 / 3,
) -> MotionCalibration:
    """Propose motion settings from a still stream and a waving stream."""
    base = base or MotionSettings()
    return calibrate_from_speeds(
        speeds_of(still, base, aspect_ratio),
        speeds_of(waving, base, aspect_ratio),
        base,
    )


def calibrate_from_speeds(
    still_speeds: Sequence[float],
    waving_speeds: Sequence[float],
    base: MotionSettings | None = None,
) -> MotionCalibration:
    """Propose motion settings from speeds already measured."""
    base = base or MotionSettings()
    if len(still_speeds) < MIN_SAMPLES:
        raise MotionCalibrationError(
            f"too little data while holding still: {len(still_speeds)} "
            f"readings, need at least {MIN_SAMPLES}"
        )
    if len(waving_speeds) < MIN_SAMPLES:
        raise MotionCalibrationError(
            f"too little data while waving: {len(waving_speeds)} readings, "
            f"need at least {MIN_SAMPLES}"
        )

    idle_ceiling = float(np.percentile(still_speeds, IDLE_PERCENTILE))
    end_speed = round(max(END_SPEED_FACTOR * idle_ceiling, MIN_END_SPEED), 3)

    peaks = _peak_speeds(waving_speeds, floor=end_speed)
    if len(peaks) < MIN_PEAKS:
        raise MotionCalibrationError(
            f"waving is not clearly faster than the noise: found "
            f"{len(peaks)} strokes above {end_speed:.2f} frame-heights per "
            f"second, need at least {MIN_PEAKS}. Wave the wand faster, or "
            "hold it steadier while still."
        )
    typical = float(np.median(peaks))
    start_speed = math.sqrt(end_speed * typical)  # between the two
    settings = MotionSettings.model_validate(
        {
            **base.model_dump(),
            "start_speed": round(start_speed, 3),
            "end_speed": end_speed,
        }
    )
    return MotionCalibration(
        settings=settings,
        idle_ceiling=idle_ceiling,
        typical_gesture_speed=typical,
        peak_count=len(peaks),
    )


def _peak_speeds(speeds: Sequence[float], floor: float) -> list[float]:
    """The speed at the top of each stroke: local maxima above ``floor``."""
    values = np.asarray(speeds, dtype=float)
    peaks = []
    n = PEAK_NEIGHBORS
    for i in range(n, len(values) - n):
        window = values[i - n : i + n + 1]
        if values[i] > floor and values[i] == window.max():
            # A plateau counts once: only its first sample.
            if i == n or values[i - 1] < values[i]:
                peaks.append(float(values[i]))
    return peaks
