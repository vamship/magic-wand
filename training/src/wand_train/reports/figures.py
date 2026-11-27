"""Figures of the reports, drawn headless with matplotlib (``Agg``)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

DPI = 110
# Okabe-Ito colors: distinct for readers with color vision deficiency.
COLORS = {
    "recognition_rate": "#009E73",
    "misrecognition_rate": "#D55E00",
    "missed_rate": "#E69F00",
    "backward_false_trigger_rate": "#0072B2",
}
LABELS = {
    "recognition_rate": "recognized",
    "misrecognition_rate": "misrecognized",
    "missed_rate": "missed",
    "backward_false_trigger_rate": "backward false trigger",
}
STYLES = {
    "recognition_rate": "-",
    "misrecognition_rate": "--",
    "missed_rate": ":",
    "backward_false_trigger_rate": "-.",
}


def _save(figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.tight_layout()
    figure.savefig(path, dpi=DPI)
    plt.close(figure)


def effect_chart(
    path: Path,
    hyperparameter: str,
    metric: str,
    values: Sequence[Any],
    means: Sequence[float],
    spreads: Sequence[float],
) -> None:
    """A metric against the values of one hyperparameter, with error bars."""
    figure, axes = plt.subplots(figsize=(6, 3.6))
    positions = list(range(len(values)))
    axes.errorbar(
        positions,
        means,
        yerr=spreads,
        fmt="o-",
        color="#0072B2",
        ecolor="#56B4E9",
        capsize=4,
        linewidth=2,
        markersize=6,
    )
    axes.set_xticks(positions)
    axes.set_xticklabels(
        [
            f"{value:g}" if isinstance(value, float) else str(value)
            for value in values
        ]
    )
    axes.set_xlabel(hyperparameter)
    axes.set_ylabel(f"{metric} (mean, bars: spread over folds)")
    axes.grid(alpha=0.3)
    _save(figure, path)


def rates_chart(path: Path, curve: pd.DataFrame) -> None:
    """The rates against the confidence threshold."""
    figure, axes = plt.subplots(figsize=(6, 3.8))
    for name in COLORS:
        axes.plot(
            curve["threshold"],
            curve[name],
            STYLES[name],
            color=COLORS[name],
            label=LABELS[name],
            linewidth=2,
        )
    axes.set_xlabel("confidence threshold")
    axes.set_ylabel("share of cases")
    axes.set_xlim(0, 1)
    axes.set_ylim(-0.02, 1.02)
    axes.grid(alpha=0.3)
    axes.legend(loc="center left", fontsize=8)
    _save(figure, path)


def roc_chart(path: Path, curve: pd.DataFrame, auc: float | None) -> None:
    """Recognizing a spell against triggering on a backward one.

    Each point is a threshold: the share of spells with a confidence at or
    above it against the share of backward gestures with one.
    """
    figure, axes = plt.subplots(figsize=(4.4, 4.4))
    false_rate = [0.0, *curve["backward_false_trigger_rate"], 1.0]
    true_rate = [0.0, *(1 - curve["missed_rate"]), 1.0]
    pairs = sorted(set(zip(false_rate, true_rate)))
    axes.plot(
        [pair[0] for pair in pairs],
        [pair[1] for pair in pairs],
        color="#0072B2",
        linewidth=2,
    )
    axes.plot([0, 1], [0, 1], color="#999999", linestyle="--", linewidth=1)
    axes.set_xlabel("backward gestures above the threshold")
    axes.set_ylabel("spells above the threshold")
    title = "Rejection ROC"
    if auc is not None:
        title += f" (AUC {auc:.3f})"
    axes.set_title(title, fontsize=10)
    axes.set_xlim(0, 1)
    axes.set_ylim(0, 1.02)
    axes.grid(alpha=0.3)
    _save(figure, path)
