"""The exploration report (design section 10.3).

Built only from the stored run: ``definition.json``, ``run.json`` and
``results.csv``.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from wand_train.explore import runs
from wand_train.explore.runs import StoredExploration
from wand_train.reports import figures, markdown

REPORT_FILE = "report.md"
FIGURES_FOLDER = "figures"


def compared_metric(stored: StoredExploration) -> str:
    return getattr(stored.explorer.comparator, "metric", "accuracy")


def write(folder: Path) -> Path:
    """Write ``report.md`` and the figures into a stored run's folder."""
    folder = Path(folder)
    stored = runs.ExplorerFactory.from_run(folder)
    metric = compared_metric(stored)
    ranked = stored.ranking()
    names = [spec.name for spec in stored.explorer.trainer.hyperparameter_specs]
    other = sorted(
        {name for result in ranked for name in result.mean} - {metric}
    )

    blocks = [
        f"# Exploration {stored.info.run_id}",
        _settings(stored, metric),
        "## Hyperparameter candidates in rank order",
        _candidates(ranked, names, metric, other),
    ]
    charts = _charts(folder, stored, ranked, names, metric)
    if charts:
        blocks.append("## Effect of each hyperparameter")
        blocks.extend(charts)
    path = folder / REPORT_FILE
    path.write_text(markdown.document(*blocks), encoding="utf-8")
    return path


def _settings(stored: StoredExploration, metric: str) -> str:
    info = stored.info
    validation = stored.definition.validation
    if validation.scheme == "kFold":
        scheme = f"k-fold, {validation.folds} folds"
    else:
        scheme = f"single split, validation fraction {validation.fraction}"
    items = [
        ("Definition", info.definition_name),
        ("Family", stored.definition.family),
        ("Validation", scheme),
        ("Comparator", f"by {metric}"),
        ("Seed", info.seed),
        ("Test fraction", info.test_fraction),
        ("Training data fingerprint", f"`{info.training_data_fingerprint}`"),
        ("Started", info.started_at),
        ("Finished", info.finished_at or "not finished"),
        (
            "Candidates",
            f"{stored.finished_candidates} of {info.candidate_count} finished",
        ),
    ]
    text = markdown.bullets(items)
    if not stored.complete:
        text += (
            "\n\nThe run is incomplete; only finished candidates are ranked."
        )
    return text


def _candidates(ranked, names, metric, other) -> str:
    if not ranked:
        return "No candidate has finished."
    headers = [
        "Rank",
        "Candidate",
        *names,
        f"{metric} mean",
        f"{metric} std",
        *[f"{name} mean" for name in other],
    ]
    rows = []
    for rank, result in enumerate(ranked, start=1):
        rows.append(
            [
                rank,
                result.number,
                *[result.hyperparameters.get(name) for name in names],
                markdown.number(result.mean.get(metric)),
                markdown.number(result.std.get(metric)),
                *[markdown.number(result.mean.get(name)) for name in other],
            ]
        )
    return markdown.table(headers, rows)


def _charts(folder, stored, ranked, names, metric) -> list[str]:
    blocks = []
    for name in names:
        groups: dict[Any, list] = defaultdict(list)
        for result in ranked:
            groups[result.hyperparameters[name]].append(result)
        if len(groups) < 2:
            continue
        values = sorted(groups)
        means = [
            float(np.mean([r.mean[metric] for r in groups[value]]))
            for value in values
        ]
        spreads = [
            float(np.mean([r.std[metric] for r in groups[value]]))
            for value in values
        ]
        relative = f"{FIGURES_FOLDER}/effect-{name}.png"
        figures.effect_chart(
            folder / relative, name, metric, values, means, spreads
        )
        blocks.append(f"### {name}\n\n![{metric} against {name}]({relative})")
    return blocks
