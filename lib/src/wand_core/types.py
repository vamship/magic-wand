"""Types shared across the library and the applications.

Field names are snake case here and camel case in JSON and YAML
(``docs/standards.md``).
"""

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class TipDetection:
    """Where the wand tip was in one frame.

    ``timestamp_s`` is absolute, taken from the frame. ``horizontal`` and
    ``vertical`` are fractions of the frame width and height (vertical down),
    and ``radius`` is in frame-heights. The last three are ``None`` when the
    tip was not found.
    """

    timestamp_s: float
    found: bool
    horizontal: float | None = None
    vertical: float | None = None
    radius: float | None = None


@dataclass(frozen=True)
class Position:
    """One point of a gesture's path.

    ``time_s`` is seconds from the gesture's first position. ``horizontal``
    and ``vertical`` are fractions of the frame (vertical down).
    """

    time_s: float
    horizontal: float
    vertical: float


@dataclass(frozen=True)
class Gesture:
    """A finished, valid gesture.

    ``start_timestamp_s`` and ``end_timestamp_s`` are the absolute timestamps
    of its first and last positions. The frame size is the size of the frames
    it was tracked in, when known.
    """

    positions: list[Position]
    start_timestamp_s: float
    end_timestamp_s: float
    frame_width: int | None = None
    frame_height: int | None = None


class DiscardReason(str, Enum):
    """Why a movement was not reported as a gesture."""

    TOO_LONG = "too_long"
    TOO_SHORT = "too_short"
    TOO_SMALL = "too_small"
    TRACKING_LOST = "tracking_lost"


@dataclass(frozen=True)
class Discard:
    """A movement that was rejected, with the reason and when."""

    reason: DiscardReason
    timestamp_s: float


class SegmenterState(str, Enum):
    IDLE = "idle"
    MOTION = "motion"
    WAITING = "waiting"  # after a discard, until the tip is idle again


@dataclass(frozen=True)
class SegmenterUpdate:
    """What the segmenter reports after each detection.

    ``speed`` is in frame-heights per second. ``result`` is ``None``, a
    finished ``Gesture`` or a ``Discard``.
    """

    speed: float
    moving: bool
    state: SegmenterState
    result: Gesture | Discard | None = None
