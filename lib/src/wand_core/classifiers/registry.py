"""Registry of classifier families.

A family's loader is a function ``loader(folder, description)`` that returns
a ``Classifier``. Heavy imports belong inside the loader. A loader whose
optional dependency is missing may raise ``ImportError``; ``load`` turns it
into a ``MissingDependencyError`` naming the dependency.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from wand_core.classifiers.base import Classifier
from wand_core.classifiers.errors import (
    MissingDependencyError,
    UnknownFamilyError,
)
from wand_core.classifiers.files import ClassifierDescription, read_description

Loader = Callable[[Path, ClassifierDescription], Classifier]

_LOADERS: dict[str, Loader] = {}


def register_family(family: str, loader: Loader) -> None:
    """Register (or replace) the loader of a family."""
    _LOADERS[family] = loader


def unregister_family(family: str) -> None:
    """Remove a family's loader, if any."""
    _LOADERS.pop(family, None)


def registered_families() -> list[str]:
    return sorted(_LOADERS)


def load(folder: str | Path) -> Classifier:
    """Load the classifier in ``folder``."""
    folder = Path(folder)
    description = read_description(folder)
    loader = _LOADERS.get(description.family)
    if loader is None:
        known = ", ".join(registered_families()) or "none"
        raise UnknownFamilyError(
            f"unknown classifier family {description.family!r} "
            f"(registered: {known})"
        )
    try:
        return loader(folder, description)
    except ImportError as error:
        name = error.name or str(error)
        raise MissingDependencyError(
            f"loading a {description.family!r} classifier needs the "
            f"optional dependency {name!r}; install it"
        ) from error
