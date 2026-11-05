"""File routines of the dataset: formats and crash-safe writes.

Every write follows one of the routines in ``docs/data-handling.md``
section 6, so a reader never sees a damaged file:

- **replace**: write a temporary file in the same folder, flush it to disk,
  rename it over the target, then flush the folder;
- **append**: write a complete line and its newline in one write and flush.

All files are UTF-8. JSON keys are camel case on disk.
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from wand_core.dataset.models import (
    FORMAT_VERSION,
    DatasetError,
    DatasetInfo,
    Record,
    SampleRecord,
    SessionRecord,
    from_disk,
    to_disk,
)

DATASET_FILE = "dataset.json"
SESSIONS_FOLDER = "sessions"
SESSION_FILE = "session.json"
SAMPLES_FILE = "samples.jsonl"
VIDEOS_FOLDER = "videos"
TEMP_SUFFIX = ".tmp"


class NotADatasetError(DatasetError):
    """The folder exists but is not a dataset (or does not exist)."""


# --- Low-level writes -------------------------------------------------------


def _fsync_folder(folder: Path) -> None:
    try:
        fd = os.open(folder, os.O_RDONLY)
    except OSError:  # for example on Windows, where folders cannot be opened
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def temp_path_for(target: Path) -> Path:
    return target.with_name(f".{target.name}.{uuid.uuid4().hex}{TEMP_SUFFIX}")


def replace_file(target: Path, content: bytes) -> None:
    """The replace routine: the file is the old content or the new one."""
    target = Path(target)
    temp = temp_path_for(target)
    try:
        with open(temp, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    _fsync_folder(target.parent)


def append_line(target: Path, line: str) -> None:
    """The append routine: one complete line, newline included, one write."""
    data = (line.rstrip("\n") + "\n").encode("utf-8")
    fd = os.open(target, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        written = os.write(fd, data)
        while written < len(data):  # only if the system wrote part of it
            written += os.write(fd, data[written:])
        os.fsync(fd)
    finally:
        os.close(fd)


def dump_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def dump_line(data: dict[str, Any]) -> str:
    """One compact JSON object on a single line (no newline)."""
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


# --- Records ----------------------------------------------------------------


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, ValueError) as error:
        raise DatasetError(f"cannot read {path}: {error}") from error
    if not isinstance(data, dict):
        raise DatasetError(f"{path} must hold a JSON object")
    return data


def write_record(path: Path, record: Record) -> None:
    """Write a record as a JSON file with the replace routine."""
    replace_file(path, dump_json(to_disk(record)).encode("utf-8"))


def read_session(path: Path) -> SessionRecord:
    return from_disk(SessionRecord, read_json(path), source=str(path))


def read_dataset_info(path: Path) -> DatasetInfo:
    return from_disk(DatasetInfo, read_json(path), source=str(path))


def split_complete_lines(raw: bytes) -> tuple[list[bytes], bool]:
    """Split file content into complete lines.

    Returns the lines that end in a newline, and whether anything follows
    the last newline (an incomplete last line).
    """
    lines = raw.split(b"\n")
    incomplete = lines.pop()  # what follows the last newline (maybe empty)
    return [line for line in lines], bool(incomplete)


def read_samples(path: Path) -> list[SampleRecord]:
    """Read ``samples.jsonl``, ignoring a damaged last line.

    A last line that lacks its newline, or is not valid JSON, is ignored (a
    crash during an append can leave one). A bad line anywhere else is
    reported, because that is damage, not an interrupted write.
    """
    try:
        raw = Path(path).read_bytes()
    except FileNotFoundError:
        return []
    lines, _ = split_complete_lines(raw)
    records = []
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        last = number == len(lines)
        try:
            data = json.loads(line.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as error:
            if last:
                break
            raise DatasetError(
                f"{path} line {number} is not valid JSON"
            ) from error
        records.append(
            from_disk(SampleRecord, data, source=f"{path} line {number}")
        )
    return records


def sample_to_line(record: SampleRecord) -> str:
    return dump_line(to_disk(record))


def append_sample(path: Path, record: SampleRecord) -> None:
    append_line(path, sample_to_line(record))


def write_samples(path: Path, records: list[SampleRecord]) -> None:
    """Rewrite the whole samples file with the replace routine."""
    text = "".join(sample_to_line(r) + "\n" for r in records)
    replace_file(path, text.encode("utf-8"))


# --- Opening a data folder --------------------------------------------------


@dataclass
class OpenReport:
    """What opening a data folder cleaned up."""

    created: bool = False
    removed_temp_files: list[Path] = field(default_factory=list)
    truncated_files: list[Path] = field(default_factory=list)


@dataclass
class DataFolder:
    path: Path
    info: DatasetInfo
    report: OpenReport

    @property
    def sessions_dir(self) -> Path:
        return self.path / SESSIONS_FOLDER


def truncate_damaged_tail(path: Path) -> bool:
    """Remove an incomplete or invalid last line. True if the file changed."""
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return False
    keep = raw.rfind(b"\n") + 1  # everything up to the last newline
    lines = raw[:keep].split(b"\n")[:-1]
    if lines and lines[-1].strip():
        try:
            json.loads(lines[-1].decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            keep -= len(lines[-1]) + 1  # drop the invalid last line too
    if keep == len(raw):
        return False
    with open(path, "r+b") as handle:
        handle.truncate(keep)
        handle.flush()
        os.fsync(handle.fileno())
    return True


def open_data_folder(path: Path, create: bool = False) -> DataFolder:
    """Open a data folder, cleaning up what a crash may have left.

    Leftover temporary files are removed and an incomplete last line of each
    samples file is truncated. A missing folder is created only when
    ``create`` is true. A folder with an unknown format version is refused.
    """
    path = Path(path)
    report = OpenReport()
    info_path = path / DATASET_FILE
    if not info_path.exists():
        if not create:
            raise NotADatasetError(f"{path} is not a dataset folder")
        if path.exists() and any(path.iterdir()):
            raise NotADatasetError(
                f"{path} is not empty and has no {DATASET_FILE}"
            )
        path.mkdir(parents=True, exist_ok=True)
        (path / SESSIONS_FOLDER).mkdir(exist_ok=True)
        info = DatasetInfo(created_at=datetime.now().astimezone())
        write_record(info_path, info)
        report.created = True
        return DataFolder(path, info, report)

    info = read_dataset_info(info_path)  # refuses unknown versions
    (path / SESSIONS_FOLDER).mkdir(exist_ok=True)
    for temp in sorted(path.rglob(f"*{TEMP_SUFFIX}")):
        if temp.is_dir():  # an interrupted merge leaves a folder
            shutil.rmtree(temp, ignore_errors=True)
            report.removed_temp_files.append(temp)
        elif temp.is_file():
            temp.unlink()
            report.removed_temp_files.append(temp)
    for samples in sorted((path / SESSIONS_FOLDER).glob(f"*/{SAMPLES_FILE}")):
        if truncate_damaged_tail(samples):
            report.truncated_files.append(samples)
    return DataFolder(path, info, report)


__all__ = [
    "DATASET_FILE",
    "FORMAT_VERSION",
    "SAMPLES_FILE",
    "SESSIONS_FOLDER",
    "SESSION_FILE",
    "VIDEOS_FOLDER",
    "DataFolder",
    "NotADatasetError",
    "OpenReport",
    "append_line",
    "append_sample",
    "open_data_folder",
    "read_dataset_info",
    "read_samples",
    "read_session",
    "replace_file",
    "truncate_damaged_tail",
    "write_record",
    "write_samples",
]
