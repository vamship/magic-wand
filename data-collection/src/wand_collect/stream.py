"""Live video: ``GET /api/stream`` sends the camera as MJPEG.

The response never ends: it is a ``multipart/x-mixed-replace`` stream whose
parts are JPEG images, which a browser shows in an image element
(``data-collection/docs/design.md`` section 4.2).

A frame is encoded only when a browser asks for it, and one encoded frame is
shared by every browser watching the same view. A slow browser always gets the
newest frame, because each loop asks for one newer than the last it was sent.
"""

from __future__ import annotations

import asyncio
import time

import cv2
import numpy as np
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from wand_collect.engine import VIEWS, CaptureEngine
from wand_collect.server import InvalidRequestError
from wand_collect.state import ApplicationState

BOUNDARY = "frame"
MEDIA_TYPE = f"multipart/x-mixed-replace; boundary={BOUNDARY}"
JPEG_QUALITY = 80
WAIT_S = 0.5  # how long to wait for a frame before checking the connection
PLACEHOLDER_EVERY_S = 1.0


def encode_jpeg(image: np.ndarray, quality: int = JPEG_QUALITY) -> bytes:
    ok, data = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("cannot encode a frame as JPEG")
    return data.tobytes()


def make_part(jpeg: bytes) -> bytes:
    """One part of the multipart stream: headers, then the whole JPEG."""
    header = (
        f"--{BOUNDARY}\r\n"
        "Content-Type: image/jpeg\r\n"
        f"Content-Length: {len(jpeg)}\r\n\r\n"
    )
    return header.encode("ascii") + jpeg + b"\r\n"


def make_placeholder(
    text: str = "No camera", size: tuple[int, int] = (640, 480)
) -> np.ndarray:
    """The picture shown when there is no camera."""
    width, height = size
    image = np.full((height, width, 3), 40, dtype=np.uint8)
    scale = 1.0
    (text_w, text_h), _ = cv2.getTextSize(
        text, cv2.FONT_HERSHEY_SIMPLEX, scale, 2
    )
    cv2.putText(
        image,
        text,
        ((width - text_w) // 2, (height + text_h) // 2),
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        (200, 200, 200),
        2,
        cv2.LINE_AA,
    )
    return image


class StreamService:
    """Serves the live video of the Capture Engine."""

    def __init__(
        self,
        engine: CaptureEngine,
        state: ApplicationState,
        quality: int = JPEG_QUALITY,
        wait_s: float = WAIT_S,
        placeholder_every_s: float = PLACEHOLDER_EVERY_S,
    ) -> None:
        self._engine = engine
        self._state = state
        self._quality = quality
        self._wait_s = wait_s
        self._placeholder_every_s = placeholder_every_s
        self._encoded: dict[str, tuple[int, bytes]] = {}
        self._placeholder = make_part(encode_jpeg(make_placeholder(), quality))
        self.encode_count = 0  # frames encoded so far (for tests)
        self.connections = 0  # browsers watching now

        self.router = APIRouter()
        self.router.add_api_route("/stream", self.stream, methods=["GET"])

    async def stream(
        self, request: Request, view: str = "camera"
    ) -> StreamingResponse:
        if view not in VIEWS:
            raise InvalidRequestError(
                f"view must be one of {', '.join(VIEWS)}, not {view!r}"
            )
        return StreamingResponse(
            self._parts(request, view), media_type=MEDIA_TYPE
        )

    def _jpeg_for(self, view: str, number: int, image: np.ndarray) -> bytes:
        """The encoded frame, encoded once and shared by every browser."""
        cached = self._encoded.get(view)
        if cached is not None and cached[0] == number:
            return cached[1]
        part = make_part(encode_jpeg(image, self._quality))
        self.encode_count += 1
        self._encoded[view] = (number, part)
        return part

    async def _parts(self, request: Request, view: str):
        self.connections += 1
        last = 0
        placeholder_sent = float("-inf")
        try:
            while not await request.is_disconnected():
                newest = await asyncio.to_thread(
                    self._engine.wait_for_frame, view, last, self._wait_s
                )
                if newest is not None:
                    last, image = newest
                    yield self._jpeg_for(view, last, image)
                elif self._state.snapshot.camera.device is None:
                    now = time.monotonic()
                    if now - placeholder_sent >= self._placeholder_every_s:
                        placeholder_sent = now
                        yield self._placeholder
        finally:
            self.connections -= 1
