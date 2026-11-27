"""Errors raised when loading or using a classifier."""


class ClassifierError(Exception):
    """Base class of every classifier error."""


class MissingClassifierFileError(ClassifierError):
    """The folder has no ``classifier.json``."""


class InvalidClassifierFileError(ClassifierError):
    """``classifier.json`` is not valid JSON or lacks a required field."""


class UnsupportedFormatVersionError(ClassifierError):
    """``classifier.json`` has a format version this library cannot read."""


class NormalizationMismatchError(ClassifierError):
    """The classifier was trained with other normalization settings."""


class UnknownFamilyError(ClassifierError):
    """No loader is registered for the classifier's family."""


class MissingDependencyError(ClassifierError):
    """A family's loader needs an optional dependency that is not installed."""
