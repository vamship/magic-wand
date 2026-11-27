"""Reports of explorations and trained models (design section 10).

Reports are built from the stored files only, so they can be written again
later without training anything.
"""

from __future__ import annotations

from pathlib import Path

from wand_train.reports import exploration, index, training


def write_exploration_report(folder: Path, reports: Path) -> Path:
    """The report of a stored run, then the index."""
    path = exploration.write(folder)
    index.write(reports)
    return path


def write_training_report(folder: Path, reports: Path) -> Path:
    """The report of a training folder, then the index."""
    path = training.write(folder)
    index.write(reports)
    return path


def write_index(reports: Path) -> Path:
    return index.write(reports)
