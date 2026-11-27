"""Experiment definitions (``training/docs/design.md`` section 7).

A definition is a JSON file with camel case keys in
``experiments/<family>/<name>.json``. It is checked here; the
hyperparameter candidates are listed by ``explore.enumerate``.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from wand_core.casing import to_snake

FORMAT_VERSION = 1
SCHEMES = ("kFold", "singleSplit")
RANGE_TYPES = ("linear", "log")
DEFAULT_FOLDS = 5
DEFAULT_FRACTION = 0.2

TOP_KEYS = {
    "formatVersion",
    "name",
    "family",
    "validation",
    "comparator",
    "hyperparameters",
}
REQUIRED_TOP_KEYS = TOP_KEYS
RANGE_KEYS = {"min", "max", "count", "type", "integer"}
REQUIRED_RANGE_KEYS = {"min", "max", "count", "type"}


class DefinitionError(ValueError):
    """An invalid definition; the message names the key."""


@dataclass(frozen=True)
class Range:
    """A hyperparameter given as a range of ``count`` values."""

    min: float
    max: float
    count: int
    type: str  # "linear" or "log"
    integer: bool = False


@dataclass(frozen=True)
class Validation:
    scheme: str  # "kFold" or "singleSplit"
    folds: int = DEFAULT_FOLDS
    fraction: float = DEFAULT_FRACTION


@dataclass(frozen=True)
class Comparator:
    name: str
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Definition:
    """A checked experiment definition.

    ``hyperparameters`` maps each hyperparameter's name (snake case) to a
    ``Range`` or a list of values, in the order of the file.
    """

    name: str
    family: str
    validation: Validation
    comparator: Comparator
    hyperparameters: dict[str, Range | list[Any]]
    format_version: int = FORMAT_VERSION


def load(path: str | Path) -> Definition:
    """Read and check a definition file."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise DefinitionError(f"cannot read {path}: {error}") from error
    except ValueError as error:
        raise DefinitionError(f"{path} is not valid JSON: {error}") from error
    try:
        return parse(data, expected_name=path.stem)
    except DefinitionError as error:
        raise DefinitionError(f"{path}: {error}") from None


def parse(data: Any, expected_name: str | None = None) -> Definition:
    """Check a definition read from JSON (camel case keys)."""
    top = _object(data, "definition")
    _keys(top, TOP_KEYS, REQUIRED_TOP_KEYS, "definition")
    if top["formatVersion"] != FORMAT_VERSION:
        raise DefinitionError(
            f"formatVersion is {top['formatVersion']!r}; "
            f"this code reads version {FORMAT_VERSION}"
        )
    name = _text(top["name"], "name")
    if expected_name is not None and name != expected_name:
        raise DefinitionError(
            f"name {name!r} differs from the file name {expected_name!r}"
        )
    return Definition(
        name=name,
        family=_text(top["family"], "family"),
        validation=_validation(top["validation"]),
        comparator=_comparator(top["comparator"]),
        hyperparameters=_hyperparameters(top["hyperparameters"]),
    )


def _validation(data: Any) -> Validation:
    block = _object(data, "validation")
    _keys(block, {"scheme", "folds", "fraction"}, {"scheme"}, "validation")
    scheme = block["scheme"]
    if scheme not in SCHEMES:
        raise DefinitionError(
            f"validation.scheme must be one of {list(SCHEMES)}, got {scheme!r}"
        )
    folds = block.get("folds", DEFAULT_FOLDS)
    if not _is_int(folds) or folds < 2:
        raise DefinitionError(
            f"validation.folds must be an integer of at least 2, got {folds!r}"
        )
    fraction = block.get("fraction", DEFAULT_FRACTION)
    if not _is_number(fraction) or not 0 < fraction < 1:
        raise DefinitionError(
            f"validation.fraction must be above 0 and below 1, got {fraction!r}"
        )
    return Validation(scheme, folds, float(fraction))


def _comparator(data: Any) -> Comparator:
    block = _object(data, "comparator")
    _keys(block, {"name", "settings"}, {"name"}, "comparator")
    settings = _object(block.get("settings", {}), "comparator.settings")
    return Comparator(
        _text(block["name"], "comparator.name"),
        {to_snake(key): value for key, value in settings.items()},
    )


def _hyperparameters(data: Any) -> dict[str, Range | list[Any]]:
    block = _object(data, "hyperparameters")
    result: dict[str, Range | list[Any]] = {}
    for key, entry in block.items():
        where = f"hyperparameters.{key}"
        if isinstance(entry, list):
            if not entry:
                raise DefinitionError(f"{where} is an empty list")
            if any(isinstance(item, (list, dict)) for item in entry):
                raise DefinitionError(f"{where} must list single values")
            value: Range | list[Any] = list(entry)
        elif isinstance(entry, dict):
            value = _range(entry, where)
        else:
            raise DefinitionError(
                f"{where} must be a range or a list of values"
            )
        result[to_snake(key)] = value
    return result


def _range(entry: dict, where: str) -> Range:
    _keys(entry, RANGE_KEYS, REQUIRED_RANGE_KEYS, where)
    low, high = entry["min"], entry["max"]
    for part, value in (("min", low), ("max", high)):
        if not _is_number(value):
            raise DefinitionError(f"{where}.{part} must be a number")
    count = entry["count"]
    if not _is_int(count) or count < 1:
        raise DefinitionError(
            f"{where}.count must be an integer of at least 1, got {count!r}"
        )
    kind = entry["type"]
    if kind not in RANGE_TYPES:
        raise DefinitionError(
            f"{where}.type must be one of {list(RANGE_TYPES)}, got {kind!r}"
        )
    integer = entry.get("integer", False)
    if not isinstance(integer, bool):
        raise DefinitionError(f"{where}.integer must be true or false")
    if low > high:
        raise DefinitionError(f"{where}.min is above {where}.max")
    if kind == "log" and low <= 0:
        raise DefinitionError(
            f"{where}.min must be above 0 for a log range, got {low!r}"
        )
    return Range(low, high, count, kind, integer)


def _object(value: Any, where: str) -> dict:
    if not isinstance(value, dict):
        raise DefinitionError(f"{where} must be an object")
    return value


def _keys(block: dict, allowed: set, required: set, where: str) -> None:
    for key in block:
        if key not in allowed:
            raise DefinitionError(
                f"unknown key {key!r} in {where} "
                f"(allowed: {', '.join(sorted(allowed))})"
            )
    for key in sorted(required - set(block)):
        raise DefinitionError(f"{where} lacks the key {key!r}")


def _text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DefinitionError(f"{where} must be a non-empty string")
    return value


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )
