"""The training report (design section 10.3).

Built only from the stored files of the training folder: ``source.json``,
``metrics.csv`` and ``predictions.parquet``.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from wand_core.casing import snake_keys
from wand_train import evaluate as evaluation
from wand_train.reports import figures, markdown

REPORT_FILE = "report.md"
FIGURES_FOLDER = "figures"
SOURCE_FILE = "source.json"
METRICS_FILE = "metrics.csv"
PREDICTIONS_FILE = "predictions.parquet"

MEASURE_NAMES = {
    "accuracy": "Accuracy",
    "macro_f1": "Macro F1",
    "log_loss": "Log loss",
    "label_auc_mean": "Mean label AUC",
    "rejection_auc": "Rejection AUC",
}
RATES = {
    "recognition_rate": "Recognized (right spell)",
    "misrecognition_rate": "Misrecognized (wrong spell)",
    "missed_rate": "Missed (below the threshold)",
    "backward_false_trigger_rate": "Backward false trigger",
}


@dataclass
class StoredMetrics:
    """What ``metrics.csv`` holds."""

    measures: dict[str, float | None]
    label_auc: dict[str, float | None]
    precision: dict[str, float | None]
    recall: dict[str, float | None]
    confusion: pd.DataFrame
    max_false_trigger: float | None
    lowest_threshold: float | None
    curve: pd.DataFrame

    @property
    def labels(self) -> list[str]:
        return list(self.label_auc)


def _value(text: str) -> float | None:
    return float(text) if text != "" else None


def read_metrics(path: Path) -> StoredMetrics:
    measures: dict[str, float | None] = {}
    label_auc: dict[str, float | None] = {}
    precision: dict[str, float | None] = {}
    recall: dict[str, float | None] = {}
    confusion: dict[tuple[str, str], float] = {}
    info: dict[str, float | None] = {}
    curve: dict[float, dict[str, float | None]] = {}
    with open(path, newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            section, name, value = row["section"], row["name"], row["value"]
            if section == "measure":
                measures[name] = _value(value)
            elif section == "label_auc":
                label_auc[name] = _value(value)
            elif section == "precision":
                precision[name] = _value(value)
            elif section == "recall":
                recall[name] = _value(value)
            elif section == "confusion":
                correct, guess = name.split(">", 1)
                confusion[(correct, guess)] = float(value)
            elif section == "threshold_info":
                info[name] = _value(value)
            elif section == "curve":
                curve.setdefault(float(row["threshold"]), {})[name] = _value(
                    value
                )
    labels = list(label_auc)
    matrix = pd.DataFrame(
        [[int(confusion.get((a, b), 0)) for b in labels] for a in labels],
        index=labels,
        columns=labels,
    )
    curve_table = pd.DataFrame(
        [
            {"threshold": threshold, **curve[threshold]}
            for threshold in sorted(curve)
        ],
        columns=list(evaluation.CURVE_COLUMNS),
    ).astype(float)
    return StoredMetrics(
        measures=measures,
        label_auc=label_auc,
        precision=precision,
        recall=recall,
        confusion=matrix,
        max_false_trigger=info.get("max_false_trigger"),
        lowest_threshold=info.get("lowest_threshold"),
        curve=curve_table,
    )


def read_source(path: Path) -> dict:
    return snake_keys(json.loads(path.read_text(encoding="utf-8")))


def write(folder: Path) -> Path:
    """Write ``report.md`` and the figures into a training folder."""
    folder = Path(folder)
    source = read_source(folder / SOURCE_FILE)
    stored = read_metrics(folder / METRICS_FILE)
    predictions = pd.read_parquet(folder / PREDICTIONS_FILE)

    rates_path = f"{FIGURES_FOLDER}/rates-against-threshold.png"
    roc_path = f"{FIGURES_FOLDER}/rejection-roc.png"
    figures.rates_chart(folder / rates_path, stored.curve)
    figures.roc_chart(
        folder / roc_path, stored.curve, stored.measures.get("rejection_auc")
    )

    blocks = [
        f"# Training report {folder.name}",
        _overview(folder, source, predictions),
        "## Hyperparameters",
        _hyperparameters(source),
        "## Measures that need no threshold",
        _measures(stored),
        "## Label AUC",
        _label_auc(stored),
        "## Precision and recall",
        _per_label(stored),
        "## Confusion matrix",
        "Rows are the correct spell, columns the predicted spell, over the "
        "spell test cases.\n\n" + _confusion(stored),
        "## Timing",
        _timing(stored),
        "## Rates against the threshold",
        f"![Rates against the confidence threshold]({rates_path})",
        _rates_table(stored),
        "## Rejection ROC",
        f"![Rejection ROC curve]({roc_path})",
        "## Threshold",
        _threshold(stored),
    ]
    path = folder / REPORT_FILE
    path.write_text(markdown.document(*blocks), encoding="utf-8")
    return path


def _overview(folder: Path, source: dict, predictions: pd.DataFrame) -> str:
    spells = int((predictions["kind"] == evaluation.SPELL).sum())
    backward = int((predictions["kind"] == evaluation.BACKWARD).sum())
    run_id = source.get("exploration_run_id")
    if run_id is None:
        origin = "hyperparameter values given directly"
    else:
        origin = f"exploration `{run_id}`, candidate {source.get('candidate')}"
        link = Path("..") / ".." / "exploration" / run_id / "report.md"
        if (folder / link).resolve().is_file():
            origin += f" ([report]({link.as_posix()}))"
    items = [
        ("Model", f"`{folder.name}`"),
        ("Family", source["family"]),
        ("Source", origin),
        ("Seed", source["seed"]),
        ("Test fraction", source["test_fraction"]),
        (
            "Training data fingerprint",
            f"`{source['training_data_fingerprint']}`",
        ),
    ]
    if source.get("training_gestures") is not None:
        items.append(("Training gestures", source["training_gestures"]))
    if source.get("test_gestures") is not None:
        items.append(("Test gestures", source["test_gestures"]))
    items.append(("Test spell cases", spells))
    items.append(("Test backward cases", backward))
    return markdown.bullets(items)


def _hyperparameters(source: dict) -> str:
    values = source.get("hyperparameters") or {}
    if not values:
        return "The family has no hyperparameters."
    return markdown.table(
        ["Hyperparameter", "Value"], [[k, v] for k, v in values.items()]
    )


def _measures(stored: StoredMetrics) -> str:
    rows = [
        [title, markdown.number(stored.measures.get(name))]
        for name, title in MEASURE_NAMES.items()
    ]
    return markdown.table(["Measure", "Value"], rows)


def _label_auc(stored: StoredMetrics) -> str:
    rows = [
        [label, markdown.number(value)]
        for label, value in stored.label_auc.items()
    ]
    text = markdown.table(["Label", "AUC"], rows)
    skipped = [
        label for label, value in stored.label_auc.items() if value is None
    ]
    if skipped:
        text += (
            "\n\nNot computed for "
            + ", ".join(skipped)
            + ": the test set lacks positive or negative cases."
        )
    return text


def _per_label(stored: StoredMetrics) -> str:
    rows = [
        [
            label,
            markdown.number(stored.precision.get(label)),
            markdown.number(stored.recall.get(label)),
        ]
        for label in stored.labels
    ]
    return markdown.table(["Label", "Precision", "Recall"], rows)


def _confusion(stored: StoredMetrics) -> str:
    rows = [
        [label, *[int(value) for value in stored.confusion.loc[label]]]
        for label in stored.labels
    ]
    return markdown.table(["correct \\ predicted", *stored.labels], rows)


def _timing(stored: StoredMetrics) -> str:
    return markdown.table(
        ["Time to classify one gesture", "Milliseconds"],
        [
            ["Mean", markdown.number(stored.measures.get("time_mean_ms"))],
            [
                "95th percentile",
                markdown.number(stored.measures.get("time_p95_ms")),
            ],
        ],
    )


def _rates_table(stored: StoredMetrics) -> str:
    curve = stored.curve
    if curve.empty:
        return ""
    picks = curve[
        (curve["threshold"] * 10).round(6) % 1 == 0
    ]  # 0.0, 0.1, ... 1.0
    rows = [
        [
            f"{point['threshold']:.1f}",
            *[markdown.number(point[name], 3) for name in RATES],
        ]
        for _, point in picks.iterrows()
    ]
    return markdown.table(["Threshold", *RATES.values()], rows)


def _threshold(stored: StoredMetrics) -> str:
    limit = stored.max_false_trigger
    if stored.lowest_threshold is None:
        text = (
            "No threshold keeps the backward false trigger rate at or below "
            f"{markdown.number(limit, 3)}."
        )
    else:
        text = (
            "The lowest threshold at which the backward false trigger rate is "
            f"at or below {markdown.number(limit, 3)} is "
            f"{stored.lowest_threshold:.2f}."
        )
    return (
        text
        + " Training chooses no threshold: the model is saved without one, "
        "and the threshold is set after reading this report."
    )
