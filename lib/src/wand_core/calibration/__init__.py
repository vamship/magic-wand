"""Calibration: deriving settings from what the user shows the camera."""

from wand_core.calibration.color import (
    ColorCalibration,
    ColorCalibrator,
    UnusableColorError,
)
from wand_core.calibration.motion import (
    MotionCalibration,
    MotionCalibrationError,
    calibrate_from_speeds,
    calibrate_motion,
    speeds_of,
)

__all__ = [
    "ColorCalibration",
    "ColorCalibrator",
    "MotionCalibration",
    "MotionCalibrationError",
    "UnusableColorError",
    "calibrate_from_speeds",
    "calibrate_motion",
    "speeds_of",
]
