"""Comparators: which of two candidate results is better (design section 8).

The interface compares two results and says which ranks first, or that they
tie. A registry maps the name used in a definition to a comparator built from
its settings, so a new comparator is added by registering it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from typing import Any

from wand_train.explore.results import CandidateResult


class ComparatorError(ValueError):
    """An unknown comparator or invalid settings for it."""


class Comparator(ABC):
    @abstractmethod
    def compare(self, first: CandidateResult, second: CandidateResult) -> int:
        """Negative if ``first`` ranks first, positive if ``second`` does,
        zero if they tie."""


class ByMetric(Comparator):
    """Compares the mean of one metric; ``direction`` says which is better."""

    DIRECTIONS = ("max", "min")

    def __init__(self, metric: str, direction: str):
        if direction not in self.DIRECTIONS:
            raise ComparatorError(
                f"byMetric: direction must be one of {list(self.DIRECTIONS)}, "
                f"got {direction!r}"
            )
        self.metric = metric
        self.direction = direction

    @classmethod
    def from_settings(cls, settings: Mapping[str, Any]) -> ByMetric:
        unknown = set(settings) - {"metric", "direction"}
        if unknown:
            raise ComparatorError(
                f"byMetric: unknown setting {sorted(unknown)[0]!r}"
            )
        for key in ("metric", "direction"):
            if key not in settings:
                raise ComparatorError(
                    f"byMetric: the setting {key!r} is missing"
                )
        metric = settings["metric"]
        if not isinstance(metric, str) or not metric:
            raise ComparatorError("byMetric: metric must be a metric name")
        return cls(metric, settings["direction"])

    def compare(self, first: CandidateResult, second: CandidateResult) -> int:
        try:
            a, b = first.mean[self.metric], second.mean[self.metric]
        except KeyError:
            raise ComparatorError(
                f"byMetric: no metric named {self.metric!r}"
            ) from None
        if a == b:
            return 0
        better_first = a > b if self.direction == "max" else a < b
        return -1 if better_first else 1


Factory = Callable[[Mapping[str, Any]], Comparator]

_COMPARATORS: dict[str, Factory] = {"byMetric": ByMetric.from_settings}


def register_comparator(name: str, factory: Factory) -> None:
    """Register (or replace) a comparator built from its settings."""
    _COMPARATORS[name] = factory


def unregister_comparator(name: str) -> None:
    _COMPARATORS.pop(name, None)


def build_comparator(name: str, settings: Mapping[str, Any]) -> Comparator:
    """The comparator called ``name``, built from ``settings``."""
    try:
        factory = _COMPARATORS[name]
    except KeyError:
        known = ", ".join(sorted(_COMPARATORS))
        raise ComparatorError(
            f"unknown comparator {name!r} (known: {known})"
        ) from None
    return factory(settings)
