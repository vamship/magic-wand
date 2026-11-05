"""The clip encoder: a worker process that turns JPEG frames into an MP4.

It is started by ``clip_writer.ClipWriter`` and talks over its standard
input and output. It imports PyAV but never OpenCV (which bundles a clashing
copy of ``libavdevice`` on macOS), so it decodes the JPEG frames with PyAV
too. See ``data-collection/docs/design.md`` section 4.8.

Protocol. For each clip the parent sends one JSON line
``{"path": ..., "fps": ..., "sizes": [...], "times": [...]}`` followed by the
frames' bytes, back to back, as long as ``sizes`` says; ``times`` are the
frames' capture times in seconds from the first. The worker answers with one
JSON line ``{"ok": true, "path": ...}`` or ``{"ok": false, "error": ...}``. It
exits when its input ends.
"""

from __future__ import annotations

import json
import os
import sys
from fractions import Fraction
from pathlib import Path
from typing import BinaryIO

import av

COLOR_RANGE_MPEG = 1  # limited range, as video uses
COLOR_RANGE_JPEG = 2  # full range, as JPEG uses
TIME_BASE = Fraction(1, 90000)  # fine enough for any camera's timing
PRESET = "veryfast"
CRF = "23"


def decode_jpeg(decoder: av.codec.CodecContext, jpeg: bytes) -> av.VideoFrame:
    frames = decoder.decode(av.Packet(jpeg))
    if not frames:
        frames = decoder.decode(None)  # a decoder that held the frame back
    if not frames:
        raise ValueError("a frame is not a valid JPEG image")
    return frames[0]


def encode(
    frames: list[bytes],
    fps: float,
    target: Path,
    times: list[float] | None = None,
) -> None:
    rate = Fraction(fps).limit_denominator(1000)
    decoder = av.CodecContext.create("mjpeg", "r")
    first = decode_jpeg(decoder, frames[0])
    # yuv420p needs even sizes; the odd last row or column is dropped.
    width, height = first.width // 2 * 2, first.height // 2 * 2
    if not width or not height:
        raise ValueError("the frames are too small to encode")
    with av.open(
        str(target), "w", format="mp4", options={"movflags": "faststart"}
    ) as out:
        stream = out.add_stream("libx264", rate=rate)
        stream.width, stream.height = width, height
        stream.pix_fmt = "yuv420p"
        stream.options = {"preset": PRESET, "crf": CRF}
        # Frames go at their capture times, not at a steady rate: a camera's
        # rate drifts, and a steady rate would stretch or squeeze the clip
        # against the recorded positions.
        stream.codec_context.time_base = TIME_BASE
        ticks = _ticks(times, len(frames), rate)
        for index, jpeg in enumerate(frames):
            # One frame is decoded at a time, so memory stays small.
            image = first if index == 0 else decode_jpeg(decoder, jpeg)
            if (image.width, image.height) != (first.width, first.height):
                raise ValueError("the frames differ in size")
            # JPEG frames use the full range of values and video the limited
            # one, so the range is converted too, or the picture brightens.
            video = image.reformat(
                format="yuv420p",
                src_color_range=COLOR_RANGE_JPEG,
                dst_color_range=COLOR_RANGE_MPEG,
            )
            if (width, height) != (video.width, video.height):
                video = video.reformat(width=width, height=height)
            video.pts = ticks[index]
            video.time_base = TIME_BASE
            for packet in stream.encode(video):
                out.mux(packet)
        for packet in stream.encode():
            out.mux(packet)


def _ticks(times: list[float] | None, count: int, rate: Fraction) -> list[int]:
    """Each frame's time in ticks, strictly increasing."""
    if times is None:  # a steady rate
        times = [i / float(rate) for i in range(count)]
    if len(times) != count:
        raise ValueError("there is not one capture time per frame")
    ticks: list[int] = []
    for seconds in times:
        tick = round(seconds * TIME_BASE.denominator)
        if ticks and tick <= ticks[-1]:
            tick = ticks[-1] + 1  # the encoder needs increasing times
        ticks.append(tick)
    return ticks


def write_clip(
    frames: list[bytes],
    fps: float,
    path: Path,
    times: list[float] | None = None,
) -> None:
    """Encode to a temporary file beside ``path``, then rename it."""
    temp = path.with_name(f".{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        encode(frames, fps, temp, times)
        os.replace(temp, path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


def read_exactly(stream: BinaryIO, size: int) -> bytes:
    data = stream.read(size)
    if len(data) != size:
        raise EOFError("the input ended in the middle of a clip")
    return data


def main() -> int:
    source, sink = sys.stdin.buffer, sys.stdout.buffer
    sys.stdout = sys.stderr  # nothing but the protocol goes to the pipe
    while header := source.readline():
        request = json.loads(header)
        # Always take the frames, so the next request starts in sync.
        frames = [read_exactly(source, size) for size in request["sizes"]]
        try:
            write_clip(
                frames,
                request["fps"],
                Path(request["path"]),
                request.get("times"),
            )
            reply = {"ok": True, "path": request["path"]}
        except Exception as error:  # noqa: BLE001 - reported to the parent
            reply = {"ok": False, "error": str(error) or repr(error)}
        sink.write(json.dumps(reply).encode() + b"\n")
        sink.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
