"""Small helpers to write Markdown with plain string formatting."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def number(value: Any, digits: int = 4) -> str:
    """A number for a table; a missing value is ``n/a``."""
    if value is None:
        return "n/a"
    if isinstance(value, float):
        if value != value:  # NaN
            return "n/a"
        return f"{value:.{digits}f}"
    return str(value)


def cell(value: Any) -> str:
    """Text safe inside a table cell."""
    return str(value).replace("|", "\\|").replace("\n", " ")


def table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    """A Markdown table; numbers are not formatted here."""
    lines = [
        "| " + " | ".join(cell(header) for header in headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(cell(value) for value in row) + " |")
    return "\n".join(lines)


def bullets(items: Sequence[tuple[str, Any]]) -> str:
    return "\n".join(f"- **{name}**: {value}" for name, value in items)


def document(*blocks: str) -> str:
    """Blocks separated by a blank line, ending with a newline."""
    return "\n\n".join(block.strip("\n") for block in blocks if block) + "\n"
