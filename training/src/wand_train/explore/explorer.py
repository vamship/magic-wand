"""The explorer (design section 8).

An explorer is composed of a trainer, a definition (the hyperparameter space
and the validation scheme) and a comparator. It never sees the test set: it is
given only the training set, which it divides into folds.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from functools import cmp_to_key

from wand_train.data.gestureset import GestureSet
from wand_train.definitions import Definition
from wand_train.explore.comparator import Comparator, build_comparator
from wand_train.explore.enumerate import enumerate_candidates
from wand_train.explore.results import CandidateResult, aggregate
from wand_train.trainers.base import HyperparameterError, Trainer
from wand_train.trainers.registry import get_trainer

Progress = Callable[[int, int], None]
OnCandidate = Callable[[int, list[dict[str, float]], CandidateResult], None]


@dataclass(frozen=True)
class Fold:
    """A training part and a validation part, which never overlap."""

    training: GestureSet
    validation: GestureSet


class Explorer(ABC):
    """Common logic; a subclass decides how the folds are made."""

    def __init__(
        self,
        trainer: Trainer,
        definition: Definition,
        comparator: Comparator,
    ):
        self.trainer = trainer
        self.definition = definition
        self.comparator = comparator

    @abstractmethod
    def make_folds(self, training_set: GestureSet, seed: int) -> list[Fold]:
        """Divide the training set into folds."""

    def explore(
        self,
        training_set: GestureSet,
        seed: int,
        progress: Progress | None = None,
        on_candidate: OnCandidate | None = None,
    ) -> list[CandidateResult]:
        """Run every candidate on every fold and return them ranked."""
        candidates = enumerate_candidates(self.definition)
        for number, candidate in enumerate(candidates, start=1):
            try:
                self.trainer.validate(candidate)
            except HyperparameterError as error:
                raise HyperparameterError(
                    f"candidate {number} of {self.definition.name}: {error}"
                ) from None
        folds = self.make_folds(training_set, seed)
        total = len(candidates) * len(folds)
        done = 0
        results = []
        for number, candidate in enumerate(candidates, start=1):
            fold_metrics = []
            values = candidate
            for fold in folds:
                outcome = self.trainer.train(
                    fold.training, fold.validation, candidate, seed
                )
                values = outcome.hyperparameters
                fold_metrics.append(outcome.metrics)
                done += 1
                if progress:
                    progress(done, total)
            result = aggregate(number, values, fold_metrics)
            if on_candidate:
                on_candidate(number, fold_metrics, result)
            results.append(result)
        return sorted(results, key=cmp_to_key(self.comparator.compare))


class KFoldExplorer(Explorer):
    """Stratified k-fold: each part is the validation fold once."""

    def make_folds(self, training_set: GestureSet, seed: int) -> list[Fold]:
        count = self.definition.validation.folds
        if len(training_set) < count:
            raise ValueError(
                f"{len(training_set)} training gestures are too few "
                f"for {count} folds"
            )
        parts = training_set.shuffle(seed).split([1 / count] * count, seed)
        return [
            Fold(
                GestureSet.concat(parts[:index] + parts[index + 1 :]),
                parts[index],
            )
            for index in range(count)
        ]


class SingleSplitExplorer(Explorer):
    """One stratified split into a training and a validation part."""

    def make_folds(self, training_set: GestureSet, seed: int) -> list[Fold]:
        fraction = self.definition.validation.fraction
        training, validation = training_set.split(
            [1 - fraction, fraction], seed
        )
        return [Fold(training, validation)]


_SCHEMES: dict[str, type[Explorer]] = {
    "kFold": KFoldExplorer,
    "singleSplit": SingleSplitExplorer,
}


def register_scheme(name: str, explorer_class: type[Explorer]) -> None:
    """Register an explorer for a validation scheme."""
    _SCHEMES[name] = explorer_class


def unregister_scheme(name: str) -> None:
    _SCHEMES.pop(name, None)


def build_explorer(definition: Definition) -> Explorer:
    """The explorer for a definition: its trainer, comparator and scheme."""
    scheme = definition.validation.scheme
    try:
        explorer_class = _SCHEMES[scheme]
    except KeyError:
        raise ValueError(f"unknown validation scheme {scheme!r}") from None
    return explorer_class(
        get_trainer(definition.family),
        definition,
        build_comparator(
            definition.comparator.name, definition.comparator.settings
        ),
    )
