"""Types shared across the library and the applications.

Field names are snake case here and camel case in JSON and YAML
(``docs/standards.md``).
"""

from dataclasses import dataclass


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
