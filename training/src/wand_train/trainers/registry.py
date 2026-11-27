"""Registry of trainers by family name."""

from __future__ import annotations

from wand_train.trainers.base import Trainer


class UnknownFamilyError(ValueError):
    """No trainer is registered for the family."""


_TRAINERS: dict[str, type[Trainer]] = {}


def register_trainer(trainer_class: type[Trainer]) -> None:
    """Register (or replace) the trainer of ``trainer_class.family``."""
    _TRAINERS[trainer_class.family] = trainer_class


def unregister_trainer(family: str) -> None:
    _TRAINERS.pop(family, None)


def trainer_families() -> list[str]:
    return sorted(_TRAINERS)


def get_trainer(family: str) -> Trainer:
    """A new trainer of the family."""
    try:
        return _TRAINERS[family]()
    except KeyError:
        known = ", ".join(trainer_families()) or "none"
        raise UnknownFamilyError(
            f"unknown family {family!r} (registered: {known})"
        ) from None
