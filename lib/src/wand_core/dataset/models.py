"""Record models of the dataset (``docs/data-handling.md`` section 5).

Python attributes are snake case; on disk the keys are camel case. Convert
with ``to_disk`` and ``from_disk``, which are the only places that happen.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Any, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    ValidationError,
    field_validator,
    model_validator,
)

from wand_core.casing import camel_keys, snake_keys
from wand_core.settings import MotionSettings, VisionSettings

FORMAT_VERSION = 1
LABEL_PATTERN = re.compile(r"^[a-z0-9_]+$")


class DatasetError(Exception):
    """Something is wrong with a dataset, its files or a record."""


class UnsupportedFormatError(DatasetError):
    """A dataset or session has a format version this code does not know."""


class Record(BaseModel):
    """Base of all records: strict about unknown keys."""

    model_config = ConfigDict(extra="forbid")


class Handedness(str, Enum):
    RIGHT = "right"
    LEFT = "left"


class SampleStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamps must include a UTC offset")
    return value


class Mode(Record):
    width: int
    height: int
    fps: float


class CameraRecord(Record):
    device: str | None = None
    index: int | None = None
    requested: Mode | None = None
    actual: Mode | None = None


class ClipPadding(Record):
    pre_s: float = 2.0
    post_s: float = 2.0


class SessionRecord(Record):
    """``session.json``."""

    format_version: int = FORMAT_VERSION
    session_id: str
    name: str | None = None
    author: str
    handedness: Handedness
    started_at: datetime
    ended_at: datetime | None = None
    notes: str | None = None
    camera: CameraRecord = CameraRecord()
    vision_settings: VisionSettings = VisionSettings()
    motion_settings: MotionSettings = MotionSettings()
    clip_padding: ClipPadding = ClipPadding()
    highest_sample_number: int = 0
    profile: str | None = None

    @field_validator("started_at", "ended_at")
    @classmethod
    def _has_offset(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _aware(value)


class DatasetInfo(Record):
    """``dataset.json``."""

    format_version: int = FORMAT_VERSION
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def _has_offset(cls, value: datetime) -> datetime:
        return _aware(value)


class PositionColumns(Record):
    """Tip positions stored column by column."""

    time_s: list[float]
    horizontal: list[float]
    vertical: list[float]

    @model_validator(mode="after")
    def _same_length(self) -> PositionColumns:
        if not len(self.time_s) == len(self.horizontal) == len(self.vertical):
            raise ValueError("timeS, horizontal and vertical differ in length")
        return self


class VideoRecord(Record):
    file: str  # relative to the session folder
    gesture_start_s: float


class SampleRecord(Record):
    """One line of ``samples.jsonl``."""

    sample_id: str
    session_id: str
    captured_at: datetime
    updated_at: datetime
    label: str
    status: SampleStatus = SampleStatus.ACCEPTED
    handedness: Handedness
    frame_size: tuple[int, int]
    positions: PositionColumns
    video: VideoRecord | None = None

    @field_validator("captured_at", "updated_at")
    @classmethod
    def _has_offset(cls, value: datetime) -> datetime:
        return _aware(value)

    @field_validator("label")
    @classmethod
    def _label_is_a_slug(cls, value: str) -> str:
        if not LABEL_PATTERN.match(value):
            raise ValueError(
                "a label must be a lowercase slug (letters, digits, underscore)"
            )
        return value


R = TypeVar("R", bound=Record)


def to_disk(record: Record) -> dict[str, Any]:
    """The record as plain data with camel case keys, ready for JSON."""
    return camel_keys(record.model_dump(mode="json"))


def from_disk(
    record_class: type[R], data: dict[str, Any], source: str = ""
) -> R:
    """Build a record from data read from disk (camel case keys)."""
    version = data.get("formatVersion", FORMAT_VERSION)
    if version != FORMAT_VERSION:
        raise UnsupportedFormatError(
            f"{source or record_class.__name__}: format version {version} is "
            f"not supported (this code reads version {FORMAT_VERSION})"
        )
    try:
        return record_class.model_validate(snake_keys(data))
    except ValidationError as error:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: "
            f"{e['msg'].removeprefix('Value error, ')}"
            for e in error.errors()
        )
        prefix = f"{source}: " if source else ""
        raise DatasetError(prefix + problems) from error
