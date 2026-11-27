"""Gesture sets: views of rows of the training data (design section 5.3).

The table is loaded once. A set holds only an array of row positions into it,
so selecting, shuffling and splitting copy no data.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from wand_core import normalize
from wand_train.data.format import TrainingDataInfo, read_info, read_table

FRACTION_TOLERANCE = 1e-9
DEFAULT_TEST_FRACTION = 0.2


@dataclass(frozen=True)
class RawPositions:
    """The recorded positions of one gesture, as stored in the dataset."""

    sample_id: str
    time_s: np.ndarray
    horizontal: np.ndarray
    vertical: np.ndarray
    frame_size: tuple[int, int]


class _Loaded:
    """The loaded table and its arrays. Shared by every set made from it."""

    def __init__(self, table: pd.DataFrame, info: TrainingDataInfo):
        self.table = table
        self.info = info
        steps = (
            np.vstack(table["steps"].to_numpy())
            if len(table)
            else (np.zeros((0, normalize.output_size() - 1)))
        )
        self.gestures = np.hstack(
            [steps, table["durationS"].to_numpy(dtype=float)[:, None]]
        )
        self.columns = {
            name: table[name].to_numpy()
            for name in ("sampleId", "sessionId", "author", "label")
            + ("handedness",)
        }


class GestureSet:
    """A view of rows of the training data."""

    def __init__(self, loaded: _Loaded, rows: np.ndarray):
        self._loaded = loaded
        self._rows = rows

    # --- Basics ---------------------------------------------------------

    def __len__(self) -> int:
        return len(self._rows)

    @property
    def info(self) -> TrainingDataInfo:
        """The description of the training data this set comes from."""
        return self._loaded.info

    @property
    def rows(self) -> np.ndarray:
        """Row positions in the loaded table."""
        return self._rows

    def column(self, name: str) -> np.ndarray:
        """The values of ``sampleId``, ``sessionId``, ``author``,
        ``handedness`` or ``label`` for the rows of this set."""
        if name not in self._loaded.columns:
            raise KeyError(f"unknown column {name!r}")
        return self._loaded.columns[name][self._rows]

    @property
    def sample_ids(self) -> np.ndarray:
        return self.column("sampleId")

    @property
    def labels(self) -> np.ndarray:
        return self.column("label")

    # --- Views ----------------------------------------------------------

    def select(self, **criteria: Any) -> GestureSet:
        """Keep the rows whose column equals a value or is in a list.

        ``select(author="ann")``, ``select(label=["reparo", "revelio"])``.
        Several criteria must all hold.
        """
        keep = np.ones(len(self._rows), dtype=bool)
        for name, wanted in criteria.items():
            values = self.column(name)
            if isinstance(wanted, (list, tuple, set, frozenset, np.ndarray)):
                keep &= np.isin(values, list(wanted))
            else:
                keep &= values == wanted
        return GestureSet(self._loaded, self._rows[keep])

    def shuffle(self, seed: int) -> GestureSet:
        """The same rows in a random order that depends only on the seed."""
        order = np.random.default_rng(seed).permutation(len(self._rows))
        return GestureSet(self._loaded, self._rows[order])

    def split(
        self,
        fractions: Sequence[float],
        seed: int,
        stratify: bool = True,
    ) -> list[GestureSet]:
        """Split into one set for each fraction.

        The fractions must be positive and sum to 1. With ``stratify`` each
        label's rows are shuffled and cut separately, so every set keeps the
        label shares within one row. The same rows, fractions and seed give
        the same sets, and every row is in exactly one set.
        """
        fractions = list(fractions)
        if not fractions or any(value <= 0 for value in fractions):
            raise ValueError("every fraction must be above zero")
        if abs(sum(fractions) - 1.0) > FRACTION_TOLERANCE:
            raise ValueError("the fractions must sum to 1")
        generator = np.random.default_rng(seed)
        parts: list[list[np.ndarray]] = [[] for _ in fractions]
        if stratify:
            labels = self.labels
            groups = [
                self._rows[labels == label] for label in sorted(set(labels))
            ]
        else:
            groups = [self._rows]
        for group in groups:
            shuffled = group[generator.permutation(len(group))]
            for part, piece in zip(parts, _cut(shuffled, fractions)):
                part.append(piece)
        result = []
        for part in parts:
            rows = np.concatenate(part) if part else self._rows[:0]
            result.append(
                GestureSet(self._loaded, rows[generator.permutation(len(rows))])
            )
        return result

    def train_test_split(
        self,
        fraction: float = DEFAULT_TEST_FRACTION,
        seed: int = 42,
    ) -> tuple[GestureSet, GestureSet]:
        """The training set and the test set: a stratified split of all rows.

        ``fraction`` is the share of the test set (default 0.2).
        """
        if not 0 < fraction < 1:
            raise ValueError("the test fraction must be between 0 and 1")
        training, test = self.split([1 - fraction, fraction], seed)
        return training, test

    @staticmethod
    def concat(sets: Sequence[GestureSet]) -> GestureSet:
        """The set holding the rows of the given sets, in order."""
        if not sets:
            raise ValueError("concat needs at least one set")
        loaded = sets[0]._loaded
        if any(other._loaded is not loaded for other in sets):
            raise ValueError("the sets come from different training data")
        return GestureSet(
            loaded, np.concatenate([other._rows for other in sets])
        )

    # --- Reading --------------------------------------------------------

    @property
    def gestures(self) -> np.ndarray:
        """The normalized gestures: one row of 190 numbers per sample."""
        return self._loaded.gestures[self._rows]

    def batches(self, size: int) -> Iterator[tuple[np.ndarray, np.ndarray]]:
        """Batches of (normalized gestures, labels); the last may be smaller."""
        if size < 1:
            raise ValueError("the batch size must be at least 1")
        for start in range(0, len(self._rows), size):
            rows = self._rows[start : start + size]
            yield (
                self._loaded.gestures[rows],
                self._loaded.columns["label"][rows],
            )

    def raw(self, position: int) -> RawPositions:
        """The raw positions of the ``position``-th row of this set."""
        row = self._rows[position]
        record = self._loaded.table.iloc[row]
        return RawPositions(
            sample_id=record["sampleId"],
            time_s=np.asarray(record["rawTimeS"], dtype=float),
            horizontal=np.asarray(record["rawX"], dtype=float),
            vertical=np.asarray(record["rawY"], dtype=float),
            frame_size=(int(record["frameWidth"]), int(record["frameHeight"])),
        )

    # --- Counting -------------------------------------------------------

    def counts(self) -> dict[str, dict[str, int]]:
        """The number of rows per label and per author."""
        return {name: _count(self.column(name)) for name in ("label", "author")}


def _cut(rows: np.ndarray, fractions: Sequence[float]) -> list[np.ndarray]:
    """Cut ``rows`` at the rounded cumulative fractions."""
    bounds = [0]
    total = 0.0
    for fraction in fractions[:-1]:
        total += fraction
        bounds.append(int(round(total * len(rows))))
    bounds.append(len(rows))
    return [rows[low:high] for low, high in zip(bounds, bounds[1:])]


def _count(values: np.ndarray) -> dict[str, int]:
    names, counts = np.unique(values, return_counts=True)
    return {str(name): int(count) for name, count in zip(names, counts)}


def load(folder: str | Path) -> GestureSet:
    """Load ``training-data/`` as a set that covers every row.

    An unknown format version is refused.
    """
    folder = Path(folder)
    info = read_info(folder)
    table = read_table(folder)
    return GestureSet(_Loaded(table, info), np.arange(len(table)))
