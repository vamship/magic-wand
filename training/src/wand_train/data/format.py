"""The training data format (``training/docs/design.md`` section 5.2).

A folder with ``gestures.parquet`` (one row per accepted sample) and
``gestures.json`` (its description).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from wand_core.casing import camel_keys, snake_keys

FORMAT_VERSION = 1
TABLE_FILE = "gestures.parquet"
INFO_FILE = "gestures.json"

COLUMNS = (
    "sampleId",
    "sessionId",
    "author",
    "handedness",
    "label",
    "durationS",
    "frameWidth",
    "frameHeight",
    "rawTimeS",
    "rawX",
    "rawY",
    "steps",
)


class TrainingDataError(Exception):
    """Training data that is missing, unreadable or of an unknown format."""


@dataclass(frozen=True)
class TrainingDataInfo:
    """The content of ``gestures.json``."""

    built_at: str
    datasets: list[str]
    source_commit: str
    session_ids: list[str]
    sample_count: int
    fingerprint: str
    normalization: dict[str, int]
    format_version: int = FORMAT_VERSION

    def to_json(self) -> dict[str, Any]:
        data = camel_keys(self.__dict__)
        data["normalization"] = dict(self.normalization)
        return data


def fingerprint(samples: list[tuple[str, str, str]]) -> str:
    """SHA-256 of the sorted ``(sample id, label, status)`` lines."""
    text = "".join(
        f"{sample_id}\t{label}\t{status}\n"
        for sample_id, label, status in sorted(samples)
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_info(folder: Path, info: TrainingDataInfo) -> None:
    (folder / INFO_FILE).write_text(
        json.dumps(info.to_json(), indent=2) + "\n", encoding="utf-8"
    )


def read_info(folder: Path) -> TrainingDataInfo:
    """Read ``gestures.json``; an unknown format version is refused."""
    path = Path(folder) / INFO_FILE
    if not path.is_file():
        raise TrainingDataError(f"{path} does not exist")
    try:
        data = snake_keys(json.loads(path.read_text(encoding="utf-8")))
    except ValueError as error:
        raise TrainingDataError(f"cannot read {path}: {error}") from error
    version = data.get("format_version")
    if version != FORMAT_VERSION:
        raise TrainingDataError(
            f"{path} has format version {version!r}; "
            f"this code reads version {FORMAT_VERSION}"
        )
    try:
        return TrainingDataInfo(
            built_at=data["built_at"],
            datasets=list(data["datasets"]),
            source_commit=data["source_commit"],
            session_ids=list(data["session_ids"]),
            sample_count=data["sample_count"],
            fingerprint=data["fingerprint"],
            normalization=dict(data["normalization"]),
        )
    except KeyError as error:
        raise TrainingDataError(f"{path} lacks the field {error}") from error


def read_table(folder: Path) -> pd.DataFrame:
    """Read ``gestures.parquet`` after checking ``gestures.json``."""
    read_info(folder)
    path = Path(folder) / TABLE_FILE
    if not path.is_file():
        raise TrainingDataError(f"{path} does not exist")
    return pd.read_parquet(path)


def write_table(folder: Path, table: pd.DataFrame) -> None:
    table.to_parquet(Path(folder) / TABLE_FILE, index=False)
