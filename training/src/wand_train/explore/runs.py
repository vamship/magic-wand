"""Stored explorations (design sections 8 and 11).

A run lives in ``<reports>/<family>/exploration/<run id>/`` with
``definition.json``, ``run.json`` and ``results.csv``. Rows are appended and
flushed as each candidate finishes, so an interrupted run keeps what it
measured. A stored run is reloaded without training, and the ranking is
computed from the results each time.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from functools import cmp_to_key
from importlib import metadata
from pathlib import Path
from typing import Any

from wand_core.casing import camel_keys, snake_keys
from wand_train import definitions
from wand_train.definitions import Definition
from wand_train.explore.enumerate import enumerate_candidates
from wand_train.explore.explorer import Explorer, build_explorer
from wand_train.explore.results import CandidateResult, aggregate

DEFINITION_FILE = "definition.json"
RUN_FILE = "run.json"
RESULTS_FILE = "results.csv"
EXPLORATION_FOLDER = "exploration"
FIXED_COLUMNS = ("candidate", "fold")
RUN_FORMAT_VERSION = 1


class RunExistsError(FileExistsError):
    """A run folder with this id already exists; runs are never overwritten."""


class RunNotFoundError(FileNotFoundError):
    """No stored run with this id or folder."""


def now() -> datetime:
    return datetime.now().astimezone()


def make_run_id(definition_name: str, moment: datetime | None = None) -> str:
    """``<yyyymmdd-HHMMSS>-<definition name>`` in local time."""
    moment = moment or now()
    return f"{moment:%Y%m%d-%H%M%S}-{definition_name}"


def run_folder(reports: Path, family: str, run_id: str) -> Path:
    return Path(reports) / family / EXPLORATION_FOLDER / run_id


def tool_version() -> str:
    try:
        return metadata.version("wand-train")
    except metadata.PackageNotFoundError:
        return ""


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


# --- Writing -----------------------------------------------------------


class RunWriter:
    """Writes a run as it progresses. Create it with ``RunWriter.start``."""

    def __init__(
        self,
        folder: Path,
        run_info: dict[str, Any],
        hyperparameter_names: list[str],
    ):
        self.folder = folder
        self._info = run_info
        self._names = hyperparameter_names
        self._file = open(
            folder / RESULTS_FILE, "w", newline="", encoding="utf-8"
        )
        self._writer = csv.writer(self._file)
        self._header_written = False

    @classmethod
    def start(
        cls,
        reports: Path,
        explorer: Explorer,
        definition_data: Mapping[str, Any],
        seed: int,
        test_fraction: float,
        fingerprint: str,
        run_id: str | None = None,
    ) -> RunWriter:
        """Create the run folder with ``definition.json`` and ``run.json``.

        An existing folder is an error and is left untouched.
        """
        definition = explorer.definition
        run_id = run_id or make_run_id(definition.name)
        folder = run_folder(reports, definition.family, run_id)
        if folder.exists():
            raise RunExistsError(f"the run folder {folder} already exists")
        folder.mkdir(parents=True)
        _write_json(folder / DEFINITION_FILE, definition_data)
        info = {
            "format_version": RUN_FORMAT_VERSION,
            "run_id": run_id,
            "definition_name": definition.name,
            "seed": seed,
            "test_fraction": test_fraction,
            "training_data_fingerprint": fingerprint,
            "started_at": now().isoformat(timespec="seconds"),
            "finished_at": None,
            "candidate_count": len(enumerate_candidates(definition)),
            "tool_version": tool_version(),
        }
        _write_json(folder / RUN_FILE, camel_keys(info))
        names = [spec.name for spec in explorer.trainer.hyperparameter_specs]
        return cls(folder, info, names)

    def on_candidate(
        self,
        number: int,
        fold_metrics: list[dict[str, float]],
        result: CandidateResult,
    ) -> None:
        """Append the rows of a finished candidate and flush them."""
        metric_names = list(fold_metrics[0])
        if not self._header_written:
            self._writer.writerow([*FIXED_COLUMNS, *self._names, *metric_names])
            self._header_written = True
        for fold, metrics in enumerate(fold_metrics, start=1):
            self._writer.writerow(
                [
                    number,
                    fold,
                    *(result.hyperparameters.get(name) for name in self._names),
                    *(metrics[name] for name in metric_names),
                ]
            )
        self._file.flush()

    def finish(self) -> None:
        """Record the end time; call it only when every candidate is done."""
        self._file.close()
        self._info["finished_at"] = now().isoformat(timespec="seconds")
        _write_json(self.folder / RUN_FILE, camel_keys(self._info))

    def close(self) -> None:
        """Close the results file (an interrupted run stays unfinished)."""
        if not self._file.closed:
            self._file.close()


# --- Reading -----------------------------------------------------------


@dataclass(frozen=True)
class RunInfo:
    run_id: str
    definition_name: str
    seed: int
    test_fraction: float
    training_data_fingerprint: str
    started_at: str
    finished_at: str | None
    candidate_count: int
    tool_version: str


class StoredExploration:
    """A stored run, reloaded without training."""

    def __init__(
        self,
        folder: Path,
        info: RunInfo,
        explorer: Explorer,
        results: list[CandidateResult],
        folds_per_candidate: int,
    ):
        self.folder = folder
        self.info = info
        self.explorer = explorer
        self.definition: Definition = explorer.definition
        self._results = results
        self.folds_per_candidate = folds_per_candidate

    @property
    def complete(self) -> bool:
        """Whether every candidate has all of its folds."""
        return len(self._results) == self.info.candidate_count

    @property
    def finished_candidates(self) -> int:
        return len(self._results)

    def ranking(self) -> list[CandidateResult]:
        """The finished candidates, ranked with the comparator each time."""
        return sorted(
            self._results, key=cmp_to_key(self.explorer.comparator.compare)
        )

    def best(self) -> CandidateResult:
        ranked = self.ranking()
        if not ranked:
            raise ValueError("the run has no finished candidates")
        return ranked[0]

    def top(self, count: int) -> list[CandidateResult]:
        return self.ranking()[:count]

    def metrics(self, candidate: int) -> CandidateResult:
        """The per-fold and aggregated metrics of one candidate."""
        for result in self._results:
            if result.number == candidate:
                return result
        raise KeyError(f"candidate {candidate} has no complete results")

    def effect(
        self, hyperparameter: str, metric: str
    ) -> list[tuple[Any, float]]:
        """The mean of ``metric`` at each value of ``hyperparameter``.

        For each value, the mean over the candidates that use it of their
        mean over the folds, in order of first appearance.
        """
        grouped: dict[Any, list[float]] = defaultdict(list)
        for result in self._results:
            if hyperparameter not in result.hyperparameters:
                raise KeyError(f"unknown hyperparameter {hyperparameter!r}")
            if metric not in result.mean:
                raise KeyError(f"unknown metric {metric!r}")
            grouped[result.hyperparameters[hyperparameter]].append(
                result.mean[metric]
            )
        return [
            (value, sum(values) / len(values))
            for value, values in grouped.items()
        ]


class ExplorerFactory:
    """Builds explorers from a definition or from a stored run."""

    @staticmethod
    def from_definition(definition: Definition) -> Explorer:
        return build_explorer(definition)

    @staticmethod
    def from_run(folder: str | Path) -> StoredExploration:
        """Rebuild the explorer and load the results; nothing is trained."""
        folder = Path(folder)
        if not (folder / RUN_FILE).is_file():
            raise RunNotFoundError(f"{folder} is not a stored run")
        definition = definitions.parse(
            json.loads((folder / DEFINITION_FILE).read_text(encoding="utf-8"))
        )
        info = RunInfo(
            **snake_keys(
                {
                    key: value
                    for key, value in json.loads(
                        (folder / RUN_FILE).read_text(encoding="utf-8")
                    ).items()
                    if key != "formatVersion"
                }
            )
        )
        explorer = build_explorer(definition)
        folds = (
            1
            if definition.validation.scheme == "singleSplit"
            else (definition.validation.folds)
        )
        results = _read_results(folder / RESULTS_FILE, explorer, folds)
        return StoredExploration(folder, info, explorer, results, folds)


def _read_results(
    path: Path, explorer: Explorer, folds: int
) -> list[CandidateResult]:
    if not path.is_file():
        return []
    candidates = enumerate_candidates(explorer.definition)
    names = [spec.name for spec in explorer.trainer.hyperparameter_specs]
    rows: dict[int, dict[int, dict[str, float]]] = defaultdict(dict)
    with open(path, newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            metrics = {
                key: float(value)
                for key, value in row.items()
                if key not in (*FIXED_COLUMNS, *names)
            }
            rows[int(row["candidate"])][int(row["fold"])] = metrics
    results = []
    for number in sorted(rows):
        by_fold = rows[number]
        if len(by_fold) != folds:
            continue  # an interrupted candidate is left out
        values = explorer.trainer.validate(candidates[number - 1])
        results.append(
            aggregate(
                number, values, [by_fold[fold] for fold in sorted(by_fold)]
            )
        )
    return results


def find_run(reference: str, reports: Path) -> Path:
    """A run folder from a path, or from a run id under ``reports``."""
    if Path(reference).is_dir():
        return Path(reference)
    matches = sorted(Path(reports).glob(f"*/{EXPLORATION_FOLDER}/{reference}"))
    if not matches:
        raise RunNotFoundError(
            f"no run {reference!r} under {reports} (and it is not a folder)"
        )
    return matches[0]
