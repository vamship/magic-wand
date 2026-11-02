"""Application Server: the one door into the application.

It serves the Web UI files, the state endpoint and the event stream, and
mounts the routes that each service registers. It contains no capture or
storage logic (``data-collection/docs/design.md`` section 4.2).

Errors follow ``tasks.md`` section 2.5: ``{"error": {"code", "message"}}``
with 400 for bad input, 404 for unknown ids and 409 for rule violations.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from collections.abc import Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from wand_collect.engine import CaptureEngine, MotionReading
from wand_collect.settings import DataCollectionSettings
from wand_collect.state import ApplicationState
from wand_core.casing import camel_keys, to_camel

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
HEARTBEAT_S = 15.0
MOTION_QUEUE_LIMIT = 30


# --- Errors -----------------------------------------------------------------


class ApiError(Exception):
    """An error with a status and a code, returned to the browser."""

    status = 400
    code = "invalid_request"

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code


class InvalidRequestError(ApiError):
    status = 400
    code = "invalid_request"


class NotFoundError(ApiError):
    status = 404
    code = "not_found"


class ConflictError(ApiError):
    """A rule violation. The code says which (for example session_active)."""

    status = 409

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message, code)


def error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def _error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(error_body(code, message), status_code=status)


# --- Events -----------------------------------------------------------------


class EventClient:
    """The bounded queue of events waiting for one browser.

    Every ``state`` event is a whole snapshot, so a newer one replaces any
    still waiting: nothing is lost in effect. Old ``motion`` events are
    dropped when the browser falls behind.
    """

    def __init__(self, motion_limit: int = MOTION_QUEUE_LIMIT) -> None:
        self._events: deque[tuple[str, str]] = deque()
        self._motion_limit = motion_limit
        self._wakeup = asyncio.Event()

    def __len__(self) -> int:
        return len(self._events)

    def push_state(self, data: str) -> None:
        self._events = deque(e for e in self._events if e[0] != "state")
        self._events.append(("state", data))
        self._wakeup.set()

    def push_motion(self, data: str) -> None:
        self._events.append(("motion", data))
        motion = [e for e in self._events if e[0] == "motion"]
        for _ in range(len(motion) - self._motion_limit):
            self._events.remove(motion.pop(0))
        self._wakeup.set()

    async def next(self, timeout: float) -> tuple[str, str] | None:
        """The next event, or ``None`` if none arrives within ``timeout``."""
        while not self._events:
            self._wakeup.clear()
            try:
                await asyncio.wait_for(self._wakeup.wait(), timeout)
            except asyncio.TimeoutError:
                return None
        return self._events.popleft()


class EventHub:
    """Sends state snapshots and motion readings to every browser."""

    def __init__(self, state: ApplicationState) -> None:
        self._state = state
        self._clients: set[EventClient] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def client_count(self) -> int:
        return len(self._clients)

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        """Set the event loop the browsers' queues live on."""
        self._loop = loop

    def connect(self) -> EventClient:
        """A new browser: its queue starts with the current snapshot."""
        client = EventClient()
        client.push_state(self._state.snapshot.to_json())
        self._clients.add(client)
        return client

    def disconnect(self, client: EventClient) -> None:
        self._clients.discard(client)

    # These two are called from other threads (the state's listener and
    # the engine's); they hand the work to the event loop.

    def on_state(self, snapshot) -> None:
        self._dispatch("state", snapshot.to_json())

    def on_motion(self, reading: MotionReading) -> None:
        data = {to_camel(k): v for k, v in asdict(reading).items()}
        data["state"] = reading.state.value
        self._dispatch("motion", json.dumps(data))

    def _dispatch(self, kind: str, data: str) -> None:
        loop = self._loop
        if loop is None or loop.is_closed() or not self._clients:
            return
        loop.call_soon_threadsafe(self._deliver, kind, data)

    def _deliver(self, kind: str, data: str) -> None:
        for client in list(self._clients):
            if kind == "state":
                client.push_state(data)
            else:
                client.push_motion(data)


def format_event(name: str, data: str) -> str:
    return f"event: {name}\ndata: {data}\n\n"


# --- The application --------------------------------------------------------


def create_app(
    state: ApplicationState,
    engine: CaptureEngine | None = None,
    routers: Sequence[APIRouter] = (),
    static_dir: Path | None = STATIC_DIR,
    heartbeat_s: float = HEARTBEAT_S,
    on_shutdown: Callable[[], None] | None = None,
    app_settings: DataCollectionSettings | None = None,
) -> FastAPI:
    """Build the web application.

    ``routers`` are the routes each service registers (mounted under
    ``/api``), so a service adds endpoints without editing this module. The
    state and the services are arguments so tests can pass fakes.
    """
    hub = EventHub(state)
    state.subscribe(hub.on_state)
    if engine is not None:
        engine.add_motion_listener(hub.on_motion)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        hub.bind(asyncio.get_running_loop())
        try:
            yield
        finally:
            if on_shutdown is not None:
                on_shutdown()

    app = FastAPI(title="Magic Wand data collection", lifespan=lifespan)
    app.state.hub = hub
    app.state.application_state = state

    _install_error_handlers(app)

    api = APIRouter(prefix="/api")

    @api.get("/state")
    def get_state() -> dict:
        return state.snapshot.to_json_dict()

    @api.get("/config")
    def get_config() -> dict:
        """The application settings the page needs (shortcuts, countdown)."""
        settings = app_settings or DataCollectionSettings()
        return camel_keys(settings.model_dump())

    @api.get("/events")
    async def get_events(request: Request) -> StreamingResponse:
        return StreamingResponse(
            _event_stream(hub, request, heartbeat_s),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    app.state.events_endpoint = get_events  # a seam for tests

    for router in routers:
        api.include_router(router)
    app.include_router(api)

    if static_dir is not None and Path(static_dir).is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="ui")
    return app


async def _event_stream(hub: EventHub, request: Request, heartbeat_s: float):
    client = hub.connect()
    try:
        while True:
            if await request.is_disconnected():
                break
            event = await client.next(heartbeat_s)
            if event is None:
                yield ": heartbeat\n\n"
            else:
                yield format_event(*event)
    finally:
        hub.disconnect(client)


def _install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(request: Request, error: ApiError) -> JSONResponse:
        return _error_response(error.status, error.code, error.message)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
            for e in error.errors()
        )
        return _error_response(400, "invalid_request", problems)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(
        request: Request, error: StarletteHTTPException
    ) -> JSONResponse:
        code = "not_found" if error.status_code == 404 else "invalid_request"
        return _error_response(error.status_code, code, str(error.detail))
