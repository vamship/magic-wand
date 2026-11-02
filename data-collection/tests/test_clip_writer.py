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
