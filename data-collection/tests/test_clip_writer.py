import threading
from dataclasses import dataclass

import av
import cv2
import numpy as np
import pytest

from wand_collect.clip_writer import ClipWriter


@dataclass
class Frame:
    timestamp_s: float
    jpeg: bytes


def make_frames(count, fps=30.0, size=(64, 48)):
    frames = []
    for i in range(count):
        image = np.full((size[1], size[0], 3), 40, np.uint8)
        cv2.circle(image, (5 + i, 20), 6, (0, 140, 255), -1)
        ok, jpeg = cv2.imencode(".jpg", image)
        frames.append(Frame(i / fps, jpeg.tobytes()))
    return frames


def inspect(path):
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        count = sum(1 for _ in container.decode(stream))
        return (
            stream.codec_context.name,
            stream.codec_context.pix_fmt,
            count,
            float(stream.duration * stream.time_base),
        )


@pytest.fixture
def writer():
    writer = ClipWriter()
    yield writer
    writer.close()


def test_a_clip_is_written_with_the_measured_rate(writer, tmp_path):
    target = tmp_path / "videos" / "a.mp4"
    result = writer.submit(make_frames(45, 25.0), 25.0, target).result(10)
    assert result.ok and result.path == target and result.error is None
    codec, pix_fmt, count, duration = inspect(target)
    assert (codec, pix_fmt, count) == ("h264", "yuv420p", 45)
    assert abs(duration - 45 / 25.0) <= 1 / 25.0


def test_no_temporary_file_remains_after_success(writer, tmp_path):
    target = tmp_path / "a.mp4"
    writer.submit(make_frames(5), 30.0, target).result(10)
    assert [p.name for p in tmp_path.iterdir()] == ["a.mp4"]


def test_the_file_has_faststart_for_browsers(writer, tmp_path):
    target = tmp_path / "a.mp4"
    writer.submit(make_frames(10), 30.0, target).result(10)
    data = target.read_bytes()
    assert 0 <= data.find(b"moov") < data.find(b"mdat")


def test_odd_sized_frames_are_encoded(writer, tmp_path):
    target = tmp_path / "a.mp4"
    frames = make_frames(5, size=(65, 49))
    assert writer.submit(frames, 30.0, target).result(10).ok


@pytest.mark.parametrize(
    "frames, fps",
    [
        ([], 30.0),
        ("bad", 30.0),
        ("good", 0.0),
        ("mixed", 30.0),
    ],
)
def test_failures_are_reported_and_leave_no_file(writer, tmp_path, frames, fps):
    if frames == "bad":
        frames = [Frame(0.0, b"not a jpeg")]
    elif frames == "good":
        frames = make_frames(3)
    elif frames == "mixed":
        frames = make_frames(2) + make_frames(2, size=(32, 24))
    target = tmp_path / "a.mp4"
    result = writer.submit(frames, fps, target).result(10)
    assert not result.ok and result.path is None and result.error
    assert list(tmp_path.iterdir()) == []


def test_a_disk_error_is_reported(writer, tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a folder")
    result = writer.submit(make_frames(3), 30.0, blocker / "a.mp4").result(10)
    assert not result.ok and result.error


def test_the_caller_is_not_blocked(tmp_path):
    writer = ClipWriter()
    gate = threading.Event()
    original = writer._write

    def slow(job):
        gate.wait(5)
        return original(job)

    writer._write = slow
    future = writer.submit(make_frames(3), 30.0, tmp_path / "a.mp4")
    assert not future.done()  # submit returned while the job waits
    gate.set()
    assert future.result(10).ok
    writer.close()


def test_clips_are_written_one_after_another(writer, tmp_path):
    order = []
    original = writer._write

    def recording(job):
        order.append(job.path.name)
        return original(job)

    writer._write = recording
    futures = [
        writer.submit(make_frames(10 + i), 30.0, tmp_path / f"{i}.mp4")
        for i in range(4)
    ]
    assert all(f.result(20).ok for f in futures)
    assert order == ["0.mp4", "1.mp4", "2.mp4", "3.mp4"]
    assert [inspect(tmp_path / f"{i}.mp4")[2] for i in range(4)] == [
        10,
        11,
        12,
        13,
    ]


def test_a_worker_that_dies_fails_one_clip_and_the_next_one_works(
    writer, tmp_path
):
    import subprocess
    import sys

    assert writer.submit(make_frames(3), 30.0, tmp_path / "a.mp4").result(10).ok
    writer._stop_worker()
    writer._worker = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stdin.buffer.read(1)"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    failed = writer.submit(make_frames(3), 30.0, tmp_path / "b.mp4").result(10)
    assert not failed.ok and "encoder" in failed.error
    assert not (tmp_path / "b.mp4").exists()
    assert writer.submit(make_frames(3), 30.0, tmp_path / "c.mp4").result(10).ok


def test_the_encoder_keeps_the_picture_content(writer, tmp_path):
    target = tmp_path / "a.mp4"
    frames = make_frames(5)
    writer.submit(frames, 30.0, target).result(10)
    with av.open(str(target)) as container:
        image = next(container.decode(video=0)).to_ndarray(format="bgr24")
    assert abs(int(image[2, 2].mean()) - 40) < 12  # the grey background
    assert image[20, 6, 2] > 150  # the orange disc (red channel)


def run_python(code):
    import subprocess
    import sys

    return subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True
    )


def test_pyav_is_not_loaded_in_the_server_process():
    result = run_python(
        "import sys, wand_collect.cli, wand_collect.clip_writer\n"
        "import wand_collect.services.library\n"
        "assert 'av' not in sys.modules, 'PyAV was imported'\n"
    )
    assert result.returncode == 0, result.stderr
    assert "implemented in both" not in result.stderr


def test_the_worker_does_not_load_opencv():
    result = run_python(
        "import sys, wand_collect.clip_worker\n"
        "assert 'cv2' not in sys.modules, 'OpenCV was imported'\n"
    )
    assert result.returncode == 0, result.stderr


def read_times(path):
    """Each frame's time in the clip, in seconds."""
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        return [
            float(frame.pts * stream.time_base)
            for frame in container.decode(stream)
        ]


def test_frames_are_placed_at_their_capture_times(writer, tmp_path):
    # A camera that runs faster than the rate it was measured at, with jitter.
    frames = make_frames(60, fps=30.0)
    for i, frame in enumerate(frames):
        frame.timestamp_s = 100.0 + i / 30.0 + (0.004 if i % 7 == 0 else 0.0)
    target = tmp_path / "a.mp4"
    result = writer.submit(frames, 24.8, target).result(10)  # a wrong rate
    assert result.ok
    times = read_times(target)
    assert len(times) == 60
    wanted = [f.timestamp_s - frames[0].timestamp_s for f in frames]
    assert max(abs(a - b) for a, b in zip(times, wanted)) < 0.002
    assert times[-1] == pytest.approx(59 / 30.0, abs=0.01)  # not 59 / 24.8


def test_equal_capture_times_still_encode(writer, tmp_path):
    frames = make_frames(4)
    for frame in frames:
        frame.timestamp_s = 5.0
    target = tmp_path / "a.mp4"
    assert writer.submit(frames, 30.0, target).result(10).ok
    times = read_times(target)
    assert times == sorted(times) and len(set(times)) == 4
