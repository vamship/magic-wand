"""Reading ``classifier.json``."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from wand_core import normalize
from wand_core.casing import snake_keys
from wand_core.classifiers.errors import (
    InvalidClassifierFileError,
    MissingClassifierFileError,
    NormalizationMismatchError,
    UnsupportedFormatVersionError,
)

CLASSIFIER_FILE = "classifier.json"
FORMAT_VERSION = 1


@dataclass(frozen=True)
class ClassifierDescription:
    """The fields of ``classifier.json`` that the library uses."""

    family: str
    labels: tuple[str, ...]
    points: int
    normalization_version: int
    extra: dict[str, Any] = field(default_factory=dict)


def read_description(folder: str | Path) -> ClassifierDescription:
    """Read and check ``classifier.json`` in ``folder``.

    Fields the library does not know are kept in ``extra`` and otherwise
    ignored.
    """
    path = Path(folder) / CLASSIFIER_FILE
    if not path.is_file():
        raise MissingClassifierFileError(f"{path} does not exist")
    try:
        data = snake_keys(json.loads(path.read_text()))
    except (OSError, ValueError) as error:
        raise InvalidClassifierFileError(f"cannot read {path}: {error}")
    if not isinstance(data, dict):
        raise InvalidClassifierFileError(f"{path} is not a JSON object")

    version = data.get("format_version")
    if version != FORMAT_VERSION:
        raise UnsupportedFormatVersionError(
            f"{path} has format version {version!r}; "
            f"this library reads version {FORMAT_VERSION}"
        )
    try:
        family = data["family"]
        labels = tuple(data["labels"])
        points = data["normalization"]["points"]
        normalization_version = data["normalization"]["version"]
    except (KeyError, TypeError) as error:
        raise InvalidClassifierFileError(
            f"{path} lacks a required field: {error}"
        )
    if not isinstance(family, str) or not labels:
        raise InvalidClassifierFileError(
            f"{path} needs a family name and at least one label"
        )
    if (
        points != normalize.DEFAULT_POINTS
        or normalization_version != normalize.NORMALIZATION_VERSION
    ):
        raise NormalizationMismatchError(
            f"{path} was trained with normalization points {points} and "
            f"version {normalization_version}; this library uses points "
            f"{normalize.DEFAULT_POINTS} and version "
            f"{normalize.NORMALIZATION_VERSION}"
        )
    extra = {
        key: value
        for key, value in data.items()
        if key not in ("format_version", "family", "labels", "normalization")
    }
    return ClassifierDescription(
        family, labels, points, normalization_version, extra
    )
