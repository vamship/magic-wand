"""Clip Writer: encodes buffered frames into an H.264 video clip.

Clips are queued and handed, one after another, to a worker process
(``clip_worker``) that does the encoding, so the caller never waits and
PyAV is never loaded into this process: PyAV and OpenCV bundle clashing
copies of ``libavdevice`` on macOS (``docs/notes.md``). The worker writes to a
temporary file and renames it, so a clip is complete or absent. A failure,
including a worker that stops unexpectedly, is reported in the result and
never raised on the caller's thread (``data-collection/docs/design.md``
section 4.8).
"""

from __future__ import annotations

import json
import logging
import queue
import subprocess
import sys
import threading
from collections.abc import Sequence
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)

WORKER_EXIT_TIMEOUT_S = 10.0


class TimedJpeg(Protocol):
    """A buffered frame: ``timestamp_s`` and ``jpeg`` bytes."""

    timestamp_s: float
    jpeg: bytes


@dataclass(frozen=True)
class ClipResult:
    """The outcome of one clip: the path on success, else the reason."""

    ok: bool
    path: Path | None = None
    error: str | None = None


@dataclass(frozen=True)
class _Job:
    frames: tuple[TimedJpeg, ...]
    fps: float
    path: Path
    future: Future


class ClipWriter:
    def __init__(self) -> None:
        self._jobs: queue.Queue[_Job | None] = queue.Queue()
        self._worker: subprocess.Popen | None = None
        self._thread = threading.Thread(
            target=self._run, name="clip-writer", daemon=True
        )
        self._thread.start()

    def submit(
        self, frames: Sequence[TimedJpeg], fps: float, path: Path
    ) -> Future:
        """Queue a clip. The future always completes with a ``ClipResult``."""
        future: Future = Future()
        self._jobs.put(_Job(tuple(frames), fps, Path(path), future))
        return future

    def close(self) -> None:
        """Finish the queued clips, then stop the thread and the worker."""
        self._jobs.put(None)
        self._thread.join()
        self._stop_worker()

    # --- The queue thread ------------------------------------------------

    def _run(self) -> None:
        while (job := self._jobs.get()) is not None:
            try:
                result = self._write(job)
            except Exception as error:  # noqa: BLE001 - reported, not raised
                logger.warning("clip %s failed: %s", job.path, error)
                result = ClipResult(False, error=str(error) or repr(error))
            job.future.set_result(result)

    def _write(self, job: _Job) -> ClipResult:
        if not job.frames:
            return ClipResult(False, error="there are no frames")
        if not job.fps > 0:
            return ClipResult(False, error=f"bad frame rate {job.fps}")
        first = job.frames[0].timestamp_s
        header = json.dumps(
            {
                "path": str(job.path),
                "fps": job.fps,
                "sizes": [len(f.jpeg) for f in job.frames],
                "times": [f.timestamp_s - first for f in job.frames],
            }
        )
        try:
            worker = self._ensure_worker()
            worker.stdin.write(header.encode() + b"\n")
            for frame in job.frames:
                worker.stdin.write(frame.jpeg)
            worker.stdin.flush()
            reply = worker.stdout.readline()
        except OSError as error:  # for example a broken pipe
            self._stop_worker(kill=True)
            return ClipResult(False, error=f"the clip encoder failed: {error}")
        if not reply:  # the worker died; the next clip starts a new one
            self._stop_worker(kill=True)
            return ClipResult(
                False, error="the clip encoder stopped unexpectedly"
            )
        answer = json.loads(reply)
        if answer["ok"]:
            return ClipResult(True, path=job.path)
        return ClipResult(False, error=answer["error"])

    # --- The worker process ----------------------------------------------

    def _ensure_worker(self) -> subprocess.Popen:
        if self._worker is None or self._worker.poll() is not None:
            self._worker = subprocess.Popen(
                [sys.executable, "-m", "wand_collect.clip_worker"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
            )
        return self._worker

    def _stop_worker(self, kill: bool = False) -> None:
        worker, self._worker = self._worker, None
        if worker is None:
            return
        if kill:
            worker.kill()
        try:
            if worker.stdin:
                worker.stdin.close()
        except OSError:
            pass
        try:
            worker.wait(WORKER_EXIT_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            worker.kill()
            worker.wait()
        if worker.stdout:
            worker.stdout.close()
