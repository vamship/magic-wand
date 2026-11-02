"""Clip Writer: encodes buffered frames into an H.264 video clip.

Work happens on one background thread, one clip after another, so the caller
never waits. A clip is written to a temporary file in the target folder and
renamed, so it is complete or absent. Encoding uses PyAV with ``libx264``,
as decided in DC-S1 (``data-collection/docs/design.md`` section 4.8). A
failure is reported in the result, never raised on the caller's thread.
"""

from __future__ import annotations

import logging
import os
import queue
import threading
from collections.abc import Sequence
from concurrent.futures import Future
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Protocol

import av
import cv2
import numpy as np

logger = logging.getLogger(__name__)

PRESET = "veryfast"
CRF = "23"


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
        """Finish the queued clips, then stop the thread."""
        self._jobs.put(None)
        self._thread.join()

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
        temp = job.path.with_name(f".{job.path.name}.tmp")
        try:
            job.path.parent.mkdir(parents=True, exist_ok=True)
            _encode(job.frames, job.fps, temp)
            os.replace(temp, job.path)
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
        return ClipResult(True, path=job.path)


def _decode(jpeg: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("a frame is not a valid JPEG image")
    return image


def _encode(frames: Sequence[TimedJpeg], fps: float, target: Path) -> None:
    rate = Fraction(fps).limit_denominator(1000)
    first = _decode(frames[0].jpeg)
    # yuv420p needs even sizes; the odd last row or column is dropped.
    height, width = first.shape[0] // 2 * 2, first.shape[1] // 2 * 2
    if not width or not height:
        raise ValueError("the frames are too small to encode")
    with av.open(
        str(target), "w", format="mp4", options={"movflags": "faststart"}
    ) as out:
        stream = out.add_stream("libx264", rate=rate)
        stream.width, stream.height = width, height
        stream.pix_fmt = "yuv420p"
        stream.options = {"preset": PRESET, "crf": CRF}
        for index, frame in enumerate(frames):
            # One frame is decoded at a time, so memory stays small.
            image = first if index == 0 else _decode(frame.jpeg)
            if image.shape[:2] != first.shape[:2]:
                raise ValueError("the frames differ in size")
            video = av.VideoFrame.from_ndarray(
                np.ascontiguousarray(image[:height, :width]), format="bgr24"
            )
            for packet in stream.encode(video):
                out.mux(packet)
        for packet in stream.encode():
            out.mux(packet)
