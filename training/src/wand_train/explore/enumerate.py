"""The hyperparameter candidates of a definition (design section 7)."""

from __future__ import annotations

import itertools
import math
from typing import Any

import numpy as np

from wand_train.definitions import Definition, Range
from wand_train.trainers.base import HyperparameterError, Trainer


def range_values(entry: Range) -> list[float | int]:
    """The values of a range, from ``min`` to ``max`` inclusive.

    ``count`` 1 gives ``[min]``. Linear values are evenly spaced, log values
    evenly spaced in logarithm. With ``integer`` the values are rounded to
    whole numbers and duplicates removed, keeping the first.
    """
    if entry.count == 1:
        values = [float(entry.min)]
    elif entry.type == "linear":
        values = [
            float(v) for v in np.linspace(entry.min, entry.max, entry.count)
        ]
    else:
        values = [
            float(v) for v in np.geomspace(entry.min, entry.max, entry.count)
        ]
        values[0], values[-1] = float(entry.min), float(entry.max)
    if entry.integer:
        rounded = [int(math.floor(value + 0.5)) for value in values]
        return list(dict.fromkeys(rounded))
    return values


def hyperparameter_values(definition: Definition) -> dict[str, list[Any]]:
    """The list of values of each hyperparameter, in file order."""
    return {
        name: range_values(entry) if isinstance(entry, Range) else list(entry)
        for name, entry in definition.hyperparameters.items()
    }


def candidate_count(definition: Definition) -> int:
    """The number of candidates: the product of the value counts."""
    return math.prod(
        len(values) for values in hyperparameter_values(definition).values()
    )


def enumerate_candidates(definition: Definition) -> list[dict[str, Any]]:
    """All combinations, the last hyperparameter changing fastest.

    The order is fixed, so repeating it gives the same list.
    """
    values = hyperparameter_values(definition)
    names = list(values)
    return [
        dict(zip(names, combination))
        for combination in itertools.product(*values.values())
    ]


def check_against_trainer(definition: Definition, trainer: Trainer) -> None:
    """Reject a hyperparameter the trainer does not accept, or a value of
    one that it would refuse."""
    for name, values in hyperparameter_values(definition).items():
        for value in values:
            try:
                trainer.validate({name: value})
            except HyperparameterError as error:
                raise HyperparameterError(
                    f"{definition.name}: {error}"
                ) from None
