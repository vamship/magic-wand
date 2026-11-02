import asyncio
import json
import threading

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import BaseModel

from wand_collect.engine import CaptureEngine, MotionReading
from wand_collect.server import (
    ConflictError,
    EventClient,
    InvalidRequestError,
    NotFoundError,
    create_app,
)
from wand_collect.state import (
    ApplicationState,
    Label,
    Owner,
)
from wand_core.types import SegmenterState


class FakeRequest:
    """Stands in for the request of an event stream."""

    def __init__(self):
        self.disconnected = False

    async def is_disconnected(self):
        return self.disconnected


def make_app(**options):
    state = ApplicationState()
    return state, create_app(state, **options)


def event_endpoint(app):
    return app.state.events_endpoint


def parse(chunk):
    """('state', {...}) from one event, or ('heartbeat', None)."""
    if chunk.startswith(":"):
        return ("heartbeat", None)
    lines = chunk.strip().split("\n")
    assert lines[0].startswith("event: ") and lines[1].startswith("data: ")
    return lines[0][7:], json.loads(lines[1][6:])


def reading(speed=1.0):
    return MotionReading(
        2.5,
        speed,
        True,
        SegmenterState.MOTION,
        start_speed=0.25,
        end_speed=0.15,
    )


# --- State endpoint and static files ----------------------------------------


def test_state_endpoint_returns_the_current_snapshot():
    state, app = make_app(static_dir=None)
    state.update(Owner.LABEL_SERVICE, labels=[Label("a", "A")])
    with TestClient(app) as client:
        response = client.get("/api/state")
    assert response.status_code == 200
    body = response.json()
    assert body["labels"] == [{"id": "a", "name": "A"}]
    assert body["capture"]["state"] == "STOPPED"
    assert body["settings"]["vision"]["hueCenter"] == 15
    assert body == state.snapshot.to_json_dict()


def test_state_endpoint_reflects_later_changes():
    state, app = make_app(static_dir=None)
    with TestClient(app) as client:
        assert client.get("/api/state").json()["samplesRevision"] == 0
        state.update(Owner.SAMPLE_LIBRARY, samples_revision=4)
        assert client.get("/api/state").json()["samplesRevision"] == 4


def test_web_ui_files_are_served_at_the_root(tmp_path):
    (tmp_path / "index.html").write_text("<h1>hello</h1>")
    (tmp_path / "app.js").write_text("console.log(1)")
    _, app = make_app(static_dir=tmp_path)
    with TestClient(app) as client:
        assert "<h1>hello</h1>" in client.get("/").text
        assert client.get("/app.js").text == "console.log(1)"
        # The api still works beside the static files.
        assert client.get("/api/state").status_code == 200


def test_the_packaged_placeholder_page_is_served():
    _, app = make_app()
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "Magic Wand" in response.text


# --- Services register their own routes ------------------------------------


class Body(BaseModel):
    count: int


def sample_router():
    router = APIRouter()

    @router.get("/things/{thing_id}")
    def get_thing(thing_id: str):
        if thing_id != "known":
            raise NotFoundError(f"no thing {thing_id}")
        return {"id": thing_id}

    @router.post("/things")
    def add_thing(body: Body):
        if body.count < 0:
            raise InvalidRequestError("count must not be negative")
        if body.count == 0:
            raise ConflictError("session_active", "a session is already active")
        return {"count": body.count}

    return router


def test_routers_are_mounted_under_api_without_editing_the_core():
    _, app = make_app(routers=[sample_router()], static_dir=None)
    with TestClient(app) as client:
        assert client.get("/api/things/known").json() == {"id": "known"}
        assert client.post("/api/things", json={"count": 3}).json() == {
            "count": 3
        }


def test_errors_use_the_documented_shape_and_statuses():
    _, app = make_app(routers=[sample_router()], static_dir=None)
    with TestClient(app) as client:
        missing = client.get("/api/things/unknown")
        assert missing.status_code == 404
        assert missing.json() == {
            "error": {"code": "not_found", "message": "no thing unknown"}
        }
        negative = client.post("/api/things", json={"count": -1})
        assert negative.status_code == 400
        assert negative.json()["error"]["code"] == "invalid_request"
        conflict = client.post("/api/things", json={"count": 0})
        assert conflict.status_code == 409
        assert conflict.json()["error"] == {
            "code": "session_active",
            "message": "a session is already active",
        }


def test_malformed_input_and_unknown_routes_give_json_errors():
    _, app = make_app(routers=[sample_router()], static_dir=None)
    with TestClient(app) as client:
        bad = client.post("/api/things", json={"count": "many"})
        assert bad.status_code == 400
        assert bad.json()["error"]["code"] == "invalid_request"
        assert "count" in bad.json()["error"]["message"]
        unknown = client.get("/api/no/such/route")
        assert unknown.status_code == 404
        assert unknown.json()["error"]["code"] == "not_found"


# --- Event stream -----------------------------------------------------------


def run(coroutine):
    return asyncio.run(coroutine)


def test_a_new_connection_gets_the_current_snapshot_first():
    async def scenario():
        state, app = make_app(static_dir=None)
        app.state.hub.bind(asyncio.get_running_loop())
        state.update(Owner.SAMPLE_LIBRARY, samples_revision=3)
        response = await event_endpoint(app)(FakeRequest())
        assert response.media_type == "text/event-stream"
        name, data = parse(await anext(response.body_iterator))
        assert name == "state"
        assert data["samplesRevision"] == 3
        await response.body_iterator.aclose()

    run(scenario())


def test_every_later_change_and_motion_reading_is_sent():
    async def scenario():
        state, app = make_app(static_dir=None)
        app.state.hub.bind(asyncio.get_running_loop())
        response = await event_endpoint(app)(FakeRequest())
        stream = response.body_iterator
        await anext(stream)  # the first snapshot

        state.update(Owner.SAMPLE_LIBRARY, samples_revision=1)
        name, data = parse(await anext(stream))
        assert (name, data["samplesRevision"]) == ("state", 1)

        app.state.hub.on_motion(reading(0.75))
        name, data = parse(await anext(stream))
        assert name == "motion"
        assert data == {
            "timestampS": 2.5,
            "speed": 0.75,
            "moving": True,
            "state": "motion",
            "startSpeed": 0.25,
            "endSpeed": 0.15,
        }
        await stream.aclose()

    run(scenario())


def test_updates_from_other_threads_reach_the_browser():
    async def scenario():
        state, app = make_app(static_dir=None)
        app.state.hub.bind(asyncio.get_running_loop())
        response = await event_endpoint(app)(FakeRequest())
        stream = response.body_iterator
        await anext(stream)
        worker = threading.Thread(
            target=lambda: state.update(
                Owner.SAMPLE_LIBRARY, samples_revision=9
            )
        )
        worker.start()
        name, data = parse(await asyncio.wait_for(anext(stream), 2))
        worker.join()
        assert (name, data["samplesRevision"]) == ("state", 9)
        await stream.aclose()

    run(scenario())


def test_a_heartbeat_comment_is_sent_when_nothing_happens():
    async def scenario():
        _, app = make_app(static_dir=None, heartbeat_s=0.05)
        app.state.hub.bind(asyncio.get_running_loop())
        response = await event_endpoint(app)(FakeRequest())
        stream = response.body_iterator
        await anext(stream)
        chunk = await asyncio.wait_for(anext(stream), 2)
        assert chunk == ": heartbeat\n\n"
        await stream.aclose()

    run(scenario())


def test_a_slow_browser_gets_the_newest_snapshot_not_every_one():
    async def scenario():
        state, app = make_app(static_dir=None, heartbeat_s=0.05)
        hub = app.state.hub
        hub.bind(asyncio.get_running_loop())
        response = await event_endpoint(app)(FakeRequest())
        stream = response.body_iterator
        await anext(stream)
        for revision in range(1, 6):  # the browser reads none of these
            state.update(Owner.SAMPLE_LIBRARY, samples_revision=revision)
        await asyncio.sleep(0.01)  # let the hub deliver them
        (client,) = hub._clients
        assert len(client) == 1  # one waiting snapshot, replaced each time
        name, data = parse(await anext(stream))
        assert (name, data["samplesRevision"]) == ("state", 5)
        await stream.aclose()

    run(scenario())


def test_old_motion_readings_are_dropped_when_the_browser_falls_behind():
    client = EventClient(motion_limit=3)

    async def scenario():
        for i in range(10):
            client.push_motion(json.dumps({"i": i}))
        client.push_state("{}")
        events = []
        while len(client):
            events.append(await client.next(0.01))
        motions = [json.loads(d)["i"] for n, d in events if n == "motion"]
        assert motions == [7, 8, 9]  # the newest three
        assert [n for n, _ in events].count("state") == 1

    run(scenario())


def test_state_events_are_not_dropped_by_a_flood_of_motion():
    client = EventClient(motion_limit=2)
    client.push_state('{"a": 1}')
    for i in range(50):
        client.push_motion(str(i))
    kinds = [name for name, _ in client._events]
    assert kinds.count("state") == 1
    assert kinds.count("motion") == 2


def test_a_disconnected_browsers_queue_is_removed():
    async def scenario():
        state, app = make_app(static_dir=None)
        hub = app.state.hub
        hub.bind(asyncio.get_running_loop())
        request = FakeRequest()
        response = await event_endpoint(app)(request)
        stream = response.body_iterator
        await anext(stream)
        assert hub.client_count == 1
        request.disconnected = True
        state.update(Owner.SAMPLE_LIBRARY, samples_revision=1)
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(anext(stream), 2)
        assert hub.client_count == 0

    run(scenario())


def test_closing_a_stream_removes_the_client():
    async def scenario():
        _, app = make_app(static_dir=None)
        app.state.hub.bind(asyncio.get_running_loop())
        response = await event_endpoint(app)(FakeRequest())
        await anext(response.body_iterator)
        assert app.state.hub.client_count == 1
        await response.body_iterator.aclose()
        assert app.state.hub.client_count == 0

    run(scenario())


def test_two_browsers_see_the_same_snapshots():
    async def scenario():
        state, app = make_app(static_dir=None)
        app.state.hub.bind(asyncio.get_running_loop())
        streams = []
        for _ in range(2):
            response = await event_endpoint(app)(FakeRequest())
            streams.append(response.body_iterator)
            await anext(response.body_iterator)
        state.update(Owner.SAMPLE_LIBRARY, samples_revision=2)
        seen = [parse(await asyncio.wait_for(anext(s), 2)) for s in streams]
        assert seen[0] == seen[1]
        for stream in streams:
            await stream.aclose()

    run(scenario())


def test_engine_motion_readings_are_forwarded_to_browsers():
    async def scenario():
        state = ApplicationState()
        engine = CaptureEngine(state)
        app = create_app(state, engine, static_dir=None)
        app.state.hub.bind(asyncio.get_running_loop())
        response = await event_endpoint(app)(FakeRequest())
        stream = response.body_iterator
        await anext(stream)
        for listener in engine._motion_listeners:
            listener(reading(0.5))
        name, data = parse(await asyncio.wait_for(anext(stream), 2))
        assert (name, data["speed"]) == ("motion", 0.5)
        await stream.aclose()

    run(scenario())


def test_shutdown_callback_runs_when_the_app_stops():
    stopped = []
    _, app = make_app(static_dir=None, on_shutdown=lambda: stopped.append(1))
    with TestClient(app):
        assert stopped == []
    assert stopped == [1]
