"""Classifier loading and prediction."""

from wand_core.classifiers.base import Classifier, Prediction
from wand_core.classifiers.errors import (
    ClassifierError,
    InvalidClassifierFileError,
    MissingClassifierFileError,
    MissingDependencyError,
    NormalizationMismatchError,
    UnknownFamilyError,
    UnsupportedFormatVersionError,
)
from wand_core.classifiers.registry import (
    load,
    register_family,
    registered_families,
    unregister_family,
)

__all__ = [
    "Classifier",
    "ClassifierError",
    "InvalidClassifierFileError",
    "MissingClassifierFileError",
    "MissingDependencyError",
    "NormalizationMismatchError",
    "Prediction",
    "UnknownFamilyError",
    "UnsupportedFormatVersionError",
    "load",
    "register_family",
    "registered_families",
    "unregister_family",
]
