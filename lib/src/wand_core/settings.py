"""Validated settings models and the code that reads and writes them.

Settings files are YAML with camel case keys. Reading a file gives a
validated model with snake case attributes (``docs/standards.md``). Reading
the file and validating its content are separate steps so each can be tested
alone.

The vision and motion settings used for recording are built up as described
in ``docs/architecture.md`` section 4.3: the defaults from ``vision.yaml`` and
``motion.yaml`` (with an optional ``*.local.yaml`` override), then a profile
when one is given.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from wand_core.casing import camel_keys, snake_keys, to_camel

PROFILES_FOLDER = "profiles"


# --- Value checks -----------------------------------------------------------
# Messages name the key as it appears in the file (camel case).


def in_range(key: str, value: float, low: float, high: float) -> None:
    if not low <= value <= high:
        raise ValueError(f"{key} must be between {low} and {high}, got {value}")


def at_least(key: str, value: float, low: float) -> None:
    if value < low:
        raise ValueError(f"{key} must be at least {low}, got {value}")


def positive(key: str, value: float) -> None:
    if value <= 0:
        raise ValueError(f"{key} must be greater than 0, got {value}")


def order(low_key: str, low: float, high_key: str, high: float) -> None:
    if low > high:
        raise ValueError(
            f"{low_key} ({low}) must not exceed {high_key} ({high})"
        )


class SettingsError(ValueError):
    """Settings are missing, unreadable or invalid. Names the bad key."""


class SettingsModel(BaseModel):
    """Base of all settings models: strict, and checked on every change."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class VisionSettings(SettingsModel):
    """Settings of the tracker (``lib/docs/design.md`` section 6).

    ``hue_center`` and ``hue_half_width`` are in OpenCV hue units (0 to 179)
    and describe an interval on a circle. Areas are fractions of the frame.
    The defaults suit an orange ball and are provisional.
    """

    hue_center: int = 15
    hue_half_width: int = 10
    sat_min: int = 120
    sat_max: int = 255
    val_min: int = 120
    val_max: int = 255
    blur_size: int = 5
    cleanup_size: int = 3
    min_area: float = 0.0003
    max_area: float = 0.05
    min_roundness: float = 0.6

    @model_validator(mode="after")
    def _check(self) -> VisionSettings:
        in_range("hueCenter", self.hue_center, 0, 179)
        in_range("hueHalfWidth", self.hue_half_width, 0, 90)
        in_range("satMin", self.sat_min, 0, 255)
        in_range("satMax", self.sat_max, 0, 255)
        in_range("valMin", self.val_min, 0, 255)
        in_range("valMax", self.val_max, 0, 255)
        at_least("blurSize", self.blur_size, 0)
        at_least("cleanupSize", self.cleanup_size, 0)
        in_range("minArea", self.min_area, 0, 1)
        in_range("maxArea", self.max_area, 0, 1)
        in_range("minRoundness", self.min_roundness, 0, 1)
        order("satMin", self.sat_min, "satMax", self.sat_max)
        order("valMin", self.val_min, "valMax", self.val_max)
        order("minArea", self.min_area, "maxArea", self.max_area)
        return self


class MotionSettings(SettingsModel):
    """Settings of the segmenter (``lib/docs/design.md`` section 8.2).

    Speeds are in frame-heights per second, durations in seconds and
    distances in frame-heights. The defaults are provisional.
    """

    start_speed: float = 0.25
    end_speed: float = 0.15
    start_frames: int = 2
    end_hold_s: float = 0.3
    min_duration_s: float = 0.3
    max_duration_s: float = 4.0
    min_extent: float = 0.10
    lost_timeout_s: float = 0.25
    smoothing_frames: int = 3

    @model_validator(mode="after")
    def _check(self) -> MotionSettings:
        positive("startSpeed", self.start_speed)
        positive("endSpeed", self.end_speed)
        at_least("startFrames", self.start_frames, 1)
        positive("endHoldS", self.end_hold_s)
        positive("minDurationS", self.min_duration_s)
        positive("maxDurationS", self.max_duration_s)
        positive("minExtent", self.min_extent)
        positive("lostTimeoutS", self.lost_timeout_s)
        at_least("smoothingFrames", self.smoothing_frames, 1)
        order("endSpeed", self.end_speed, "startSpeed", self.start_speed)
        order(
            "minDurationS",
            self.min_duration_s,
            "maxDurationS",
            self.max_duration_s,
        )
        return self


class WorkingSettings(SettingsModel):
    """The vision and motion settings in force while recording."""

    vision: VisionSettings = VisionSettings()
    motion: MotionSettings = MotionSettings()


M = TypeVar("M", bound=SettingsModel)


# --- Reading, validating and writing ----------------------------------------


def read_yaml(path: Path) -> dict[str, Any]:
    """Read a YAML file holding a mapping. An empty file gives ``{}``."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as error:
        raise SettingsError(f"cannot read {path}: {error}") from error
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise SettingsError(f"{path} is not valid YAML: {error}") from error
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise SettingsError(f"{path} must hold a mapping of keys to values")
    return data


def validate(model_class: type[M], data: dict[str, Any], source: str = "") -> M:
    """Build a validated model from a dictionary with camel case keys."""
    prefix = f"{source}: " if source else ""
    try:
        return model_class.model_validate(snake_keys(data))
    except ValidationError as error:
        problems = []
        for item in error.errors():
            key = ".".join(to_camel(str(part)) for part in item["loc"])
            message = item["msg"].removeprefix("Value error, ")
            problems.append(f"{key}: {message}" if key else message)
        raise SettingsError(prefix + "; ".join(problems)) from error


def merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Return ``base`` with ``override`` applied; nested mappings are merged."""
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = value
    return result


def local_override_path(path: Path) -> Path:
    """``vision.yaml`` -> ``vision.local.yaml`` in the same folder."""
    return path.with_name(f"{path.stem}.local{path.suffix}")


def load_settings(model_class: type[M], path: Path) -> M:
    """Load a settings file, applying its ``.local`` override if present.

    Keys the override omits keep the value they have in the main file.
    """
    path = Path(path)
    data = read_yaml(path)
    local = local_override_path(path)
    if local.exists():
        data = merge(data, read_yaml(local))
    return validate(model_class, data, source=str(path))


def save_settings(model: SettingsModel, path: Path) -> None:
    """Write a model to a YAML file with camel case keys."""
    data = camel_keys(model.model_dump())
    text = yaml.safe_dump(data, sort_keys=False)
    Path(path).write_text(text, encoding="utf-8")


def load_vision(config_dir: Path) -> VisionSettings:
    return load_settings(VisionSettings, Path(config_dir) / "vision.yaml")


def load_motion(config_dir: Path) -> MotionSettings:
    return load_settings(MotionSettings, Path(config_dir) / "motion.yaml")


# --- Profiles and working settings ------------------------------------------


def profile_path(config_dir: Path, name: str) -> Path:
    if not name or name != Path(name).name or name.startswith("."):
        raise SettingsError(f"invalid profile name: {name!r}")
    return Path(config_dir) / PROFILES_FOLDER / f"{name}.yaml"


def save_profile(
    config_dir: Path, name: str, settings: WorkingSettings
) -> Path:
    """Save a full set of vision and motion settings as a named profile."""
    path = profile_path(config_dir, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    save_settings(settings, path)
    return path


def load_profile(config_dir: Path, name: str) -> WorkingSettings:
    path = profile_path(config_dir, name)
    if not path.exists():
        raise SettingsError(f"profile {name!r} not found at {path}")
    return validate(WorkingSettings, read_yaml(path), source=str(path))


def resolve_settings(
    config_dir: Path, profile: str | None = None
) -> WorkingSettings:
    """Build the working settings in the order of the architecture.

    Start from the defaults (with local overrides); when a profile is given,
    its values replace them. Adjustments are made later on the result.
    """
    if profile is not None:
        return load_profile(config_dir, profile)
    return WorkingSettings(
        vision=load_vision(config_dir), motion=load_motion(config_dir)
    )
