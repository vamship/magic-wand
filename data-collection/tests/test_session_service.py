import queue

import pytest
from fastapi.testclient import TestClient

from wand_collect.engine import CaptureEngine
from wand_collect.server import create_app
from wand_collect.services.calibration import CalibrationService
from wand_collect.services.session import SessionService
from wand_collect.settings import DataCollectionSettings
from wand_collect.state import (
    ApplicationState,
    Owner,
    SessionRole,
    SettingsState,
)
from wand_core.dataset import DatasetStore
from wand_core.settings import MotionSettings, VisionSettings
from wand_core.sources import CameraInfo, CameraMode, FrameSource

FPS = 30.0
CAMERA = CameraInfo(0, "Test Cam", "Test Cam", (CameraMode(640, 480, 30.0),))


class FakeSource(FrameSource):
    def __init__(self, width=640, height=480):
        self.frames = queue.Queue()
        self._size = (width, height)

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
        return self._size

    @property
    def nominal_fps(self):
        return FPS


class FakeController:
    def __init__(self, log):
        self.log = log

    def stop(self):
        self.log.append("stop")


class Rig:
    def __init__(self, tmp_path, cameras=(CAMERA,), size=(640, 480)):
        self.state = ApplicationState()
        self.size = size
        self.opened = []

        def factory(index, width, height, fps):
            self.opened.append((index, width, height, fps))
            return FakeSource(*self.size)

        self.engine = CaptureEngine(self.state, camera_factory=factory)
        self.store = DatasetStore.open(tmp_path / "data", create=True)
        self.app_settings = DataCollectionSettings()
        self.cameras = list(cameras)
        calibration = CalibrationService(
            self.state,
            self.engine,
            tmp_path / "config",
            self.app_settings,
            camera_lister=lambda: list(self.cameras),
        )
        self.service = SessionService(
            self.state,
            self.engine,
            self.store,
            calibration,
            self.app_settings,
            camera_lister=lambda: list(self.cameras),
        )
        self.log = []
        self.service.set_controller(FakeController(self.log))
        app = create_app(
            self.state,
            self.engine,
            [calibration.router, self.service.router],
            static_dir=None,
        )
        self.client = TestClient(app)
        self.engine.start()

    def open_camera(self):
        self.engine.open_source(FakeSource(*self.size), "Test Cam", 0).result(2)

    def start(self, **body):
        body = {"author": "Ada", "handedness": "right", **body}
        return self.client.post("/api/sessions", json=body)

    def close(self):
        self.engine.stop()


@pytest.fixture
def rig(tmp_path):
    rig = Rig(tmp_path)
    rig.open_camera()
    yield rig
    rig.close()


def session_on_disk(rig, session_id):
    return rig.store.get_session(session_id)


# --- Start ------------------------------------------------------------------


def test_start_records_everything_and_locks_settings(rig):
    vision = VisionSettings(hue_center=11)
    rig.state.update(
        Owner.CALIBRATION_SERVICE,
        settings=SettingsState(vision=vision, motion=MotionSettings()),
    )
    response = rig.start(name="Morning", notes="n1")
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "capture"
    record = session_on_disk(rig, body["id"])
    assert record.author == "Ada"
    assert record.handedness.value == "right"
    assert record.name == "Morning"
    assert record.notes == "n1"
    assert record.started_at is not None and record.ended_at is None
    assert record.camera.device == "Test Cam"
    assert record.camera.actual.width == 640
    assert record.vision_settings.hue_center == 11
    assert record.clip_padding.pre_s == rig.app_settings.clip_padding.pre_s
    assert record.highest_sample_number == 0
    session = rig.state.snapshot.session
    assert session.id == body["id"]
    assert session.role is SessionRole.CAPTURE
    # settings are locked
    locked = rig.client.put("/api/settings", json={"vision": {"hueCenter": 5}})
    assert locked.status_code == 409
    assert locked.json()["error"]["code"] == "session_active"


def test_second_start_is_refused(rig):
    assert rig.start().status_code == 200
    again = rig.start()
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "session_active"
    assert len(rig.store.list_sessions()) == 1


def test_start_needs_a_camera(tmp_path):
    rig = Rig(tmp_path)
    try:
        response = rig.start()
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "camera_unavailable"
        assert rig.state.snapshot.session is None
        assert rig.store.list_sessions() == []
    finally:
        rig.close()


def test_start_needs_an_author_and_valid_handedness(rig):
    assert rig.start(author="  ").status_code == 400
    assert rig.start(handedness="both").status_code == 400
    assert rig.state.snapshot.session is None
    assert rig.store.list_sessions() == []


# --- List -------------------------------------------------------------------


def test_list_shows_open_and_ended_sessions(rig):
    first = rig.start(name="One").json()["id"]
    rig.client.post("/api/sessions/current/end")
    second = rig.start().json()["id"]
    listed = {s["id"]: s for s in rig.client.get("/api/sessions").json()}
    assert listed[first]["open"] is False
    assert listed[first]["endedAt"] is not None
    assert listed[first]["name"] == "One"
    assert listed[second]["open"] is True
    assert listed[second]["author"] == "Ada"
    assert listed[second]["sampleCount"] == 0
    assert "startedAt" in listed[second]


# --- End --------------------------------------------------------------------


def test_end_stops_capture_ends_the_session_and_unlocks(rig):
    session_id = rig.start().json()["id"]
    assert rig.client.post("/api/sessions/current/end").status_code == 204
    assert rig.log == ["stop"]
    assert session_on_disk(rig, session_id).ended_at is not None
    assert rig.state.snapshot.session is None
    unlocked = rig.client.put(
        "/api/settings", json={"vision": {"hueCenter": 5}}
    )
    assert unlocked.status_code == 204


def test_end_without_a_session_is_refused(rig):
    response = rig.client.post("/api/sessions/current/end")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "no_session"


def test_closing_the_application_leaves_the_session_open(rig):
    session_id = rig.start().json()["id"]
    rig.close()
    assert session_on_disk(rig, session_id).ended_at is None
    listed = rig.client.get("/api/sessions").json()
    assert listed[0]["open"] is True


# --- Review -----------------------------------------------------------------


def test_review_of_an_ended_session_changes_nothing_on_disk(rig):
    session_id = rig.start().json()["id"]
    rig.client.post("/api/sessions/current/end")
    before = session_on_disk(rig, session_id)
    rig.log.clear()
    response = rig.client.post(f"/api/sessions/{session_id}/load?mode=review")
    assert response.status_code == 200
    assert response.json()["role"] == "review"
    assert rig.state.snapshot.session.role is SessionRole.REVIEW
    assert rig.client.post("/api/sessions/current/end").status_code == 204
    assert rig.state.snapshot.session is None
    assert rig.log == []  # capture was never running
    assert session_on_disk(rig, session_id) == before


def test_review_does_not_lock_settings(rig):
    session_id = rig.start().json()["id"]
    rig.client.post("/api/sessions/current/end")
    rig.client.post(f"/api/sessions/{session_id}/load?mode=review")
    response = rig.client.put(
        "/api/settings", json={"vision": {"hueCenter": 5}}
    )
    assert response.status_code == 204


def test_unknown_session_is_not_found(rig):
    response = rig.client.post("/api/sessions/nope/load?mode=review")
    assert response.status_code == 404


def test_load_while_capturing_is_refused(rig):
    first = rig.start().json()["id"]
    for mode in ("review", "resume"):
        response = rig.client.post(f"/api/sessions/{first}/load?mode={mode}")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "session_active"
    assert rig.state.snapshot.session.role is SessionRole.CAPTURE


# --- Resume -----------------------------------------------------------------


def start_and_close(rig, **body):
    """An open session on disk with nothing loaded, as after a restart."""
    session_id = rig.start(**body).json()["id"]
    rig.state.update(Owner.SESSION_SERVICE, session=None)
    return session_id


def test_an_ended_session_cannot_be_resumed(rig):
    session_id = rig.start().json()["id"]
    rig.client.post("/api/sessions/current/end")
    response = rig.client.post(f"/api/sessions/{session_id}/load?mode=resume")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "session_ended"
    assert rig.state.snapshot.session is None


def test_resume_applies_the_recorded_settings_and_locks(rig):
    rig.state.update(
        Owner.CALIBRATION_SERVICE,
        settings=SettingsState(
            vision=VisionSettings(hue_center=11),
            motion=MotionSettings(),
            profile="mine",
        ),
    )
    session_id = start_and_close(rig)
    rig.state.update(
        Owner.CALIBRATION_SERVICE,
        settings=SettingsState(vision=VisionSettings(hue_center=40)),
    )
    response = rig.client.post(f"/api/sessions/{session_id}/load?mode=resume")
    assert response.status_code == 200
    assert response.json()["warnings"] == []
    snapshot = rig.state.snapshot
    assert snapshot.settings.vision.hue_center == 11
    assert snapshot.settings.profile == "mine"
    assert snapshot.session.role is SessionRole.CAPTURE
    assert snapshot.session.id == session_id
    assert rig.opened[-1] == (0, 640, 480, FPS)


def test_resume_is_refused_when_the_camera_is_missing(rig):
    session_id = start_and_close(rig)
    rig.engine.close_camera().result(2)
    rig.cameras = [CameraInfo(0, "Other Cam", "Other Cam")]
    before = rig.state.snapshot
    response = rig.client.post(f"/api/sessions/{session_id}/load?mode=resume")
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "camera_unavailable"
    assert "Test Cam" in error["message"]
    assert rig.state.snapshot.session == before.session
    assert rig.state.snapshot.settings == before.settings


def test_resume_opens_the_recorded_camera(rig):
    session_id = start_and_close(rig)
    rig.engine.close_camera().result(2)
    rig.cameras = [
        CameraInfo(0, "Other Cam", "Other Cam"),
        CameraInfo(2, "Test Cam", "Test Cam"),
    ]
    response = rig.client.post(f"/api/sessions/{session_id}/load?mode=resume")
    assert response.status_code == 200
    assert rig.opened[-1][0] == 2


def test_resume_with_a_different_mode_warns_but_resumes(rig):
    session_id = start_and_close(rig)
    rig.size = (1280, 720)
    response = rig.client.post(f"/api/sessions/{session_id}/load?mode=resume")
    assert response.status_code == 200
    warnings = response.json()["warnings"]
    assert len(warnings) == 1
    assert "640x480" in warnings[0] and "1280x720" in warnings[0]
    assert rig.state.snapshot.session.role is SessionRole.CAPTURE


# --- Sample numbers ---------------------------------------------------------


def test_sample_numbers_continue_after_a_resume(rig):
    session_id = rig.start().json()["id"]
    assert rig.service.next_sample_number() == 1
    rig.store.update_session(session_id, highest_sample_number=7)
    rig.state.update(Owner.SESSION_SERVICE, session=None)
    rig.client.post(f"/api/sessions/{session_id}/load?mode=resume")
    assert rig.service.next_sample_number() == 8


def test_next_sample_number_needs_a_capture_session(rig):
    with pytest.raises(Exception) as caught:
        rig.service.next_sample_number()
    assert getattr(caught.value, "code", None) == "no_session"
