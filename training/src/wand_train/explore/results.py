"""Results of exploring one hyperparameter candidate."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class CandidateResult:
    """A hyperparameter candidate with its metrics on each fold.

    ``number`` counts from 1 in enumeration order. ``mean`` and ``std`` hold,
    for each metric, the mean and the (population) standard deviation over the
    folds.
    """

    number: int
    hyperparameters: dict[str, Any]
    fold_metrics: list[dict[str, float]]
    mean: dict[str, float]
    std: dict[str, float]


def aggregate(
    number: int,
    hyperparameters: dict[str, Any],
    fold_metrics: Sequence[dict[str, float]],
) -> CandidateResult:
    """Build a candidate result from its per-fold metrics."""
    names = list(fold_metrics[0])
    columns = {
        name: np.array([fold[name] for fold in fold_metrics]) for name in names
    }
    return CandidateResult(
        number=number,
        hyperparameters=dict(hyperparameters),
        fold_metrics=[dict(fold) for fold in fold_metrics],
        mean={name: float(values.mean()) for name, values in columns.items()},
        std={name: float(values.std()) for name, values in columns.items()},
    )
