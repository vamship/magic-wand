"""DC-S1 spike: can we encode browser-playable H.264 fast enough?

Encodes 150 synthetic frames (640x480, 30 fps, 5 seconds of moving shapes
over noise) with PyAV, then with the fallbacks, and reports timing, codec
and whether the result can be read back. Run with:

    uv run python data-collection/spikes/h264_spike.py [output-folder]

It also writes ``play.html`` in the output folder; open it in browsers to
check playback.
"""

import platform
import sys
import time
from pathlib import Path

import av
import cv2
import numpy as np

WIDTH, HEIGHT, FPS, FRAMES = 640, 480, 30, 150


def make_frames() -> list[np.ndarray]:
    """BGR frames: noise background, with a ball and a box moving."""
    rng = np.random.default_rng(0)
    frames = []
    for i in range(FRAMES):
        frame = rng.integers(0, 256, (HEIGHT, WIDTH, 3), dtype=np.uint8)
        t = i / FRAMES
        x = int(50 + 540 * t)
        y = int(240 + 150 * np.sin(t * 6.28))
        cv2.circle(frame, (x, y), 25, (0, 140, 255), -1)
        cv2.rectangle(frame, (600 - x, 40), (640 - x, 100), (255, 255, 0), -1)
        frames.append(frame)
    return frames


def encode_pyav(frames, path: Path) -> None:
    with av.open(str(path), "w", options={"movflags": "faststart"}) as out:
        stream = out.add_stream("libx264", rate=FPS)
        stream.width, stream.height = WIDTH, HEIGHT
        stream.pix_fmt = "yuv420p"
        stream.options = {"preset": "veryfast", "crf": "23"}
        for frame in frames:
            for packet in stream.encode(
                av.VideoFrame.from_ndarray(frame, format="bgr24")
            ):
                out.mux(packet)
        for packet in stream.encode():
            out.mux(packet)


def encode_cv2(frames, path: Path, fourcc: str) -> None:
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*fourcc), FPS, (WIDTH, HEIGHT)
    )
    if not writer.isOpened():
        raise RuntimeError(f"cv2 writer with {fourcc} did not open")
    for frame in frames:
        writer.write(frame)
    writer.release()
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError(f"cv2 writer with {fourcc} wrote nothing")


def inspect(path: Path) -> str:
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        count = sum(1 for _ in container.decode(stream))
        codec = stream.codec_context.name
        pix = stream.codec_context.pix_fmt
    return f"codec={codec} pix_fmt={pix} frames={count}"


def faststart(path: Path) -> bool:
    """True when the moov box comes before the mdat box."""
    data = path.read_bytes()
    moov, mdat = data.find(b"moov"), data.find(b"mdat")
    return 0 <= moov < mdat


def attempt(name: str, path: Path, encode) -> None:
    start = time.perf_counter()
    try:
        encode()
    except Exception as error:  # noqa: BLE001 - a spike reports everything
        print(f"[FAIL] {name}: {error}")
        return
    seconds = time.perf_counter() - start
    size = path.stat().st_size / 1024
    try:
        info = inspect(path)
    except Exception as error:  # noqa: BLE001
        info = f"unreadable ({error})"
    extra = f" faststart={faststart(path)}" if path.suffix == ".mp4" else ""
    print(f"[ OK ] {name}: {seconds:.2f}s {size:.0f} KiB {info}{extra}")


def main() -> None:
    folder = Path(sys.argv[1] if len(sys.argv) > 1 else "spike-output")
    folder.mkdir(parents=True, exist_ok=True)
    print(
        f"{platform.system()} {platform.machine()}, python "
        f"{platform.python_version()}, PyAV {av.__version__}, "
        f"OpenCV {cv2.__version__}"
    )
    print(f"clip: {FRAMES} frames, {WIDTH}x{HEIGHT} @ {FPS} fps")
    frames = make_frames()

    pyav = folder / "pyav.mp4"
    attempt("PyAV libx264", pyav, lambda: encode_pyav(frames, pyav))
    avc1 = folder / "cv2-avc1.mp4"
    attempt("OpenCV avc1", avc1, lambda: encode_cv2(frames, avc1, "avc1"))
    mjpg = folder / "cv2-mjpg.avi"
    attempt("OpenCV MJPG", mjpg, lambda: encode_cv2(frames, mjpg, "MJPG"))

    (folder / "play.html").write_text(
        "<!doctype html><meta charset=utf-8><title>H.264 check</title>"
        "<p>pyav.mp4</p><video src=pyav.mp4 controls muted loop></video>"
        "<p>cv2-avc1.mp4</p><video src=cv2-avc1.mp4 controls muted loop>"
        "</video>"
    )
    print(f"wrote {folder}/play.html")


if __name__ == "__main__":
    main()
