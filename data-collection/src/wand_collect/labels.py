"""Reading the spell labels (``config/labels.yaml``)."""

from __future__ import annotations

from pathlib import Path

import yaml

from wand_collect.state import Label
from wand_core.dataset.models import LABEL_PATTERN


class LabelsError(ValueError):
    """The labels file is missing, unreadable or invalid."""


def load_labels(path: Path) -> list[Label]:
    """Read the labels. Ids must be unique lowercase slugs."""
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except OSError as error:
        raise LabelsError(f"cannot read {path}: {error}") from error
    except yaml.YAMLError as error:
        raise LabelsError(f"{path} is not valid YAML: {error}") from error
    entries = (data or {}).get("labels") if isinstance(data, dict) else None
    if entries is None:
        raise LabelsError(f"{path} must have a 'labels' list")
    labels: list[Label] = []
    for entry in entries:
        if (
            not isinstance(entry, dict)
            or "id" not in entry
            or "name" not in entry
        ):
            raise LabelsError(f"{path}: each label needs an id and a name")
        label_id, name = str(entry["id"]), str(entry["name"])
        if not LABEL_PATTERN.match(label_id):
            raise LabelsError(
                f"{path}: label id {label_id!r} must be a lowercase slug"
            )
        if any(label.id == label_id for label in labels):
            raise LabelsError(f"{path}: duplicate label id {label_id!r}")
        labels.append(Label(label_id, name))
    return labels
