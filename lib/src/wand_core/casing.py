"""Conversion of dictionary keys between camel case and snake case.

Files on disk (YAML and JSON) use camel case keys; Python code uses snake
case. All conversion happens through this module. Only keys are converted;
values are never touched.
"""

import re
from collections.abc import Callable
from typing import Any

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def to_snake(name: str) -> str:
    """Convert camel case to snake case (``hueCenter`` -> ``hue_center``)."""
    return _CAMEL_BOUNDARY.sub("_", name).lower()


def to_camel(name: str) -> str:
    """Convert snake case to camel case (``hue_center`` -> ``hueCenter``)."""
    head, *rest = name.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in rest)


def snake_keys(data: Any) -> Any:
    """Return a copy of ``data`` with every dictionary key in snake case."""
    return _convert(data, to_snake)


def camel_keys(data: Any) -> Any:
    """Return a copy of ``data`` with every dictionary key in camel case."""
    return _convert(data, to_camel)


def _convert(data: Any, convert_key: Callable[[str], str]) -> Any:
    if isinstance(data, dict):
        return {
            (convert_key(k) if isinstance(k, str) else k): _convert(
                v, convert_key
            )
            for k, v in data.items()
        }
    if isinstance(data, (list, tuple)):
        return [_convert(item, convert_key) for item in data]
    return data
