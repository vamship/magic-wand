import asyncio
import queue
import time

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from wand_collect.engine import CaptureEngine
from wand_collect.server import create_app
from wand_collect.state import ApplicationState
from wand_collect.stream import BOUNDARY, MEDIA_TYPE, StreamService
from wand_core.sources import Frame, FrameSource, VideoFileSource
from wand_core.testing.synthetic import (
    SceneStyle,
    circle_path,
    render_frame,
    write_video,
)

STYLE = SceneStyle()


class FakeRequest:
    def __init__(self):
        self.disconnected = False

    async def is_disconnected(self):
        return self.disconnected


class QueueSource(FrameSource):
    def __init__(self):
        self.frames = queue.Queue()

    def open(self):
        pass

    def read(self):
        try:
            return self.frames.get(timeout=0.02)
        except queue.Empty:
            return None

    def close(self):
        pass

    @property
    def frame_size(self):
        return (640, 480)

    @property
    def nominal_fps(self):
        return 30.0

    def push(self, center, timestamp_s):
        self.frames.put(Frame(render_frame(STYLE, center), timestamp_s))


class PacedSource(VideoFileSource):
    """A recorded video played at about 50 frames per second."""

    def read(self):
        time.sleep(0.02)
        return super().read()


class Rig:
    def __init__(self, with_camera=True, **service_args):
        self.state = ApplicationState()
        self.engine = CaptureEngine(self.state)
        self.service = StreamService(self.engine, self.state, **service_args)
        self.engine.start()
        self.source = QueueSource()
        self.t = 0.0
        if with_camera:
            self.engine.open_source(self.source, "test", 0).result(2)

    def push(self, center=(0.5, 0.5), count=1):
        for _ in range(count):
            self.source.push(center, self.t)
            self.t += 1 / 30

    def wait_frames(self, number, timeout=5):
        deadline = time.time() + timeout
        while self.engine.latest_frame()[0] < number:
            assert time.time() < deadline, "engine did not process the frames"
            time.sleep(0.005)

    async def open(self, view="camera"):
        request = FakeRequest()
        response = await self.service.stream(request, view)
        return request, response

    def close(self):
        self.engine.stop()


@pytest.fixture
def rig():
    rig = Rig()
    yield rig
    rig.close()


def run(coroutine):
    return asyncio.run(coroutine)


def parse_part(part: bytes):
    """(headers, jpeg) of one part, checking it is complete."""
    head, _, rest = part.partition(b"\r\n\r\n")
    lines = head.decode("ascii").split("\r\n")
    assert lines[0] == f"--{BOUNDARY}"
    headers = dict(line.split(": ", 1) for line in lines[1:])
    length = int(headers["Content-Length"])
    assert len(rest) == length + 2
    assert rest.endswith(b"\r\n")
    return headers, rest[:length]


def decode(part: bytes) -> np.ndarray:
    headers, jpeg = parse_part(part)
    assert headers["Content-Type"] == "image/jpeg"
    image = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    assert image is not None
    return image


# --- The response -----------------------------------------------------------


def test_the_response_is_multipart_mixed_replace_with_a_boundary(rig):
    async def scenario():
        _, response = await rig.open()
        assert response.media_type == MEDIA_TYPE
        assert MEDIA_TYPE == "multipart/x-mixed-replace; boundary=frame"
        await response.body_iterator.aclose()

    run(scenario())


def test_each_part_is_a_complete_jpeg_with_type_and_length(rig):
    rig.push((0.5, 0.5))
    rig.wait_frames(1)

    async def scenario():
        _, response = await rig.open()
        part = await asyncio.wait_for(anext(response.body_iterator), 2)
        headers, jpeg = parse_part(part)
        assert headers["Content-Type"] == "image/jpeg"
        assert int(headers["Content-Length"]) == len(jpeg)
        assert jpeg[:2] == b"\xff\xd8" and jpeg[-2:] == b"\xff\xd9"
        assert decode(part).shape == (480, 640, 3)
        await response.body_iterator.aclose()

    run(scenario())


def test_several_parts_from_a_recorded_video_decode_as_images(tmp_path):
    file = tmp_path / "clip.avi"
    write_video(circle_path(60), file, STYLE, fps=30.0)
    state = ApplicationState()
    engine = CaptureEngine(state)
    service = StreamService(engine, state)
    engine.start()

    async def scenario():
        engine.open_source(PacedSource(file), "clip.avi").result(2)
        request = FakeRequest()
        response = await service.stream(request, "camera")
        images = []
        for _ in range(5):
            part = await asyncio.wait_for(anext(response.body_iterator), 3)
            images.append(decode(part))
        await response.body_iterator.aclose()
        return images

    images = run(scenario())
    engine.stop()
    assert len(images) == 5
    assert all(image.shape == (480, 640, 3) for image in images)
    # The video moves, so the frames are not all the same picture.
    assert any(not np.array_equal(images[0], other) for other in images[1:])


def test_the_mask_view_shows_the_detection_mask(rig):
    rig.push((0.5, 0.5))
    rig.wait_frames(1)

    async def scenario():
        _, camera = await rig.open("camera")
        _, mask = await rig.open("mask")
        camera_image = decode(await anext(camera.body_iterator))
        mask_image = decode(await anext(mask.body_iterator))
        await camera.body_iterator.aclose()
        await mask.body_iterator.aclose()
        return camera_image, mask_image

    camera_image, mask_image = run(scenario())
    assert mask_image[240, 320].min() > 200  # inside the disk: white
    assert mask_image[10, 10].max() < 50  # background: black
    assert not np.array_equal(camera_image, mask_image)


def test_an_unknown_view_returns_400():
    state = ApplicationState()
    engine = CaptureEngine(state)
    service = StreamService(engine, state)
    app = create_app(state, engine, routers=[service.router], static_dir=None)
    with TestClient(app) as client:
        response = client.get("/api/stream?view=bogus")
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    assert "camera" in error["message"] and "mask" in error["message"]


# --- Encoding on demand, shared, newest first -------------------------------


def test_frames_are_not_encoded_while_nobody_watches(rig):
    rig.push(count=10)
    rig.wait_frames(10)
    assert rig.service.encode_count == 0
    assert rig.service.connections == 0


def test_one_encoded_frame_is_shared_by_browsers_on_the_same_view(rig):
    async def scenario():
        _, first = await rig.open()
        _, second = await rig.open()
        _, mask = await rig.open("mask")
        rig.push()
        a = await asyncio.wait_for(anext(first.body_iterator), 2)
        b = await asyncio.wait_for(anext(second.body_iterator), 2)
        m = await asyncio.wait_for(anext(mask.body_iterator), 2)
        for response in (first, second, mask):
            await response.body_iterator.aclose()
        return a, b, m

    a, b, m = run(scenario())
    assert a == b
    assert m != a
    assert rig.service.encode_count == 2  # one camera frame, one mask frame


def test_a_slow_browser_skips_to_the_newest_frame(rig):
    async def scenario():
        _, response = await rig.open()
        stream = response.body_iterator
        rig.push((0.2, 0.5))
        await asyncio.wait_for(anext(stream), 2)
        encoded_before = rig.service.encode_count
        # The browser reads nothing while ten more frames arrive.
        rig.push((0.5, 0.5), count=9)
        rig.push((0.8, 0.5))
        rig.wait_frames(11)
        part = await asyncio.wait_for(anext(stream), 2)
        await stream.aclose()
        return part, encoded_before

    part, encoded_before = run(scenario())
    image = decode(part)
    # The newest frame has the disk on the right, not the stale ones.
    assert image[240, int(0.8 * 640) + 8][2] > 150
    assert rig.service.encode_count == encoded_before + 1


def test_a_stream_waits_for_a_newer_frame_and_never_repeats_one(rig):
    async def scenario():
        _, response = await rig.open()
        stream = response.body_iterator
        rig.push()
        await asyncio.wait_for(anext(stream), 2)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(anext(stream), 0.3)  # nothing new
        await stream.aclose()

    run(scenario())


# --- Connections ------------------------------------------------------------


def test_closing_the_connection_stops_the_generator(rig):
    async def scenario():
        _, response = await rig.open()
        stream = response.body_iterator
        rig.push()
        await asyncio.wait_for(anext(stream), 2)
        assert rig.service.connections == 1
        await stream.aclose()
        assert rig.service.connections == 0

    run(scenario())


def test_a_disconnected_client_ends_the_stream(rig):
    async def scenario():
        request, response = await rig.open()
        stream = response.body_iterator
        rig.push()
        await asyncio.wait_for(anext(stream), 2)
        request.disconnected = True
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(anext(stream), 2)
        assert rig.service.connections == 0

    run(scenario())


# --- No camera --------------------------------------------------------------


def test_with_no_camera_a_placeholder_is_sent_instead_of_failing():
    rig = Rig(with_camera=False, wait_s=0.05, placeholder_every_s=0.1)

    async def scenario():
        _, response = await rig.open()
        stream = response.body_iterator
        first = await asyncio.wait_for(anext(stream), 2)
        second = await asyncio.wait_for(anext(stream), 2)
        await stream.aclose()
        return first, second

    first, second = run(scenario())
    assert first == second  # the same picture, repeated as a keep-alive
    image = decode(first)
    assert image.shape == (480, 640, 3)
    assert image.mean() < 100  # a dark card with text
    assert rig.service.encode_count == 0  # the placeholder is made once
    rig.close()


def test_the_stream_switches_to_real_frames_when_a_camera_opens():
    rig = Rig(with_camera=False, wait_s=0.05, placeholder_every_s=0.1)

    async def scenario():
        _, response = await rig.open()
        stream = response.body_iterator
        placeholder = await asyncio.wait_for(anext(stream), 2)
        rig.engine.open_source(rig.source, "late", 0).result(2)
        rig.push()
        while True:
            part = await asyncio.wait_for(anext(stream), 2)
            if part != placeholder:
                break
        await stream.aclose()
        return part

    part = run(scenario())
    assert decode(part)[240, 328][2] > 100  # the orange disk
    rig.close()


def test_a_stalled_camera_does_not_send_the_placeholder():
    rig = Rig(wait_s=0.05, placeholder_every_s=0.05)  # camera open, no frames

    async def scenario():
        _, response = await rig.open()
        stream = response.body_iterator
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(anext(stream), 0.4)
        await stream.aclose()

    run(scenario())
    rig.close()
