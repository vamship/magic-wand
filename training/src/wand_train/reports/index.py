"""The index of reports (design section 10.3).

Rebuilt from the folders each time: an exploration run that was deleted
disappears from it, and a report or model stays valid without its run.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from wand_train.explore import runs
from wand_train.reports import exploration, markdown, training

INDEX_FILE = "index.md"


def write(reports: Path) -> Path:
    reports = Path(reports)
    families = (
        sorted(
            folder.name
            for folder in reports.iterdir()
            if folder.is_dir() and _has_entries(folder)
        )
        if reports.is_dir()
        else []
    )
    blocks = ["# Reports"]
    if not families:
        blocks.append("No explorations or models yet.")
    for family in families:
        blocks.append(f"## {family}")
        blocks.append("### Explorations")
        blocks.append(_explorations(reports, family))
        blocks.append("### Models")
        blocks.append(_models(reports, family))
    path = reports / INDEX_FILE
    reports.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown.document(*blocks), encoding="utf-8")
    return path


def _has_entries(family: Path) -> bool:
    return bool(_runs(family) or _trainings(family))


def _runs(family: Path) -> list[Path]:
    folder = family / runs.EXPLORATION_FOLDER
    if not folder.is_dir():
        return []
    return sorted(
        item for item in folder.iterdir() if (item / runs.RUN_FILE).is_file()
    )


def _trainings(family: Path) -> list[Path]:
    folder = family / "training"
    if not folder.is_dir():
        return []
    return sorted(
        item
        for item in folder.iterdir()
        if (item / training.SOURCE_FILE).is_file()
    )


def _link(text: str, reports: Path, target: Path) -> str:
    if not target.is_file():
        return text
    return f"[{text}]({target.relative_to(reports).as_posix()})"


def _day(text: str | None) -> str:
    if not text:
        return ""
    try:
        return f"{datetime.fromisoformat(text):%Y-%m-%d %H:%M}"
    except ValueError:
        return text


def _explorations(reports: Path, family: str) -> str:
    rows = []
    for folder in _runs(reports / family):
        started = ""
        best = "unreadable"
        try:
            started = _day(
                json.loads((folder / runs.RUN_FILE).read_text("utf-8")).get(
                    "startedAt"
                )
            )
            stored = runs.ExplorerFactory.from_run(folder)
            metric = exploration.compared_metric(stored)
            if stored.finished_candidates:
                best = f"{metric} {markdown.number(stored.best().mean[metric])}"
            else:
                best = "no finished candidate"
        except (OSError, ValueError, KeyError):
            pass
        rows.append(
            [
                _link(folder.name, reports, folder / exploration.REPORT_FILE),
                started,
                best,
            ]
        )
    if not rows:
        return "None."
    return markdown.table(["Run", "Date", "Best candidate"], rows)


def _models(reports: Path, family: str) -> str:
    rows = []
    for folder in _trainings(reports / family):
        accuracy = rejection = None
        try:
            stored = training.read_metrics(folder / training.METRICS_FILE)
            accuracy = stored.measures.get("accuracy")
            rejection = stored.measures.get("rejection_auc")
        except (OSError, ValueError, KeyError):
            pass
        rows.append(
            [
                _link(folder.name, reports, folder / training.REPORT_FILE),
                _model_day(folder.name),
                markdown.number(accuracy),
                markdown.number(rejection),
            ]
        )
    if not rows:
        return "None."
    return markdown.table(["Model", "Date", "Accuracy", "Rejection AUC"], rows)


def _model_day(model_id: str) -> str:
    """The date in ``<family>-<yyyymmdd>-<HHMMSS>``."""
    parts = model_id.rsplit("-", 2)
    try:
        moment = datetime.strptime(parts[-2] + parts[-1], "%Y%m%d%H%M%S")
        return f"{moment:%Y-%m-%d %H:%M}"
    except (ValueError, IndexError):
        return ""
