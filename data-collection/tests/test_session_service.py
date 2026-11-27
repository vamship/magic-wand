import queue

import pytest
from fastapi.testclient import TestClient

from wand_collect.cameras import CameraCatalog
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
from wand_core.dataset import DatasetStore, Handedness
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
    # The rate is not measured yet, so the one the camera reported is kept.
    assert not rig.state.snapshot.camera.fps_measured
    assert record.camera.actual.fps == rig.state.snapshot.camera.actual.fps
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


def test_hold_stops_capture_unloads_the_session_and_keeps_it_open(rig):
    session_id = rig.start().json()["id"]
    assert rig.client.post("/api/sessions/current/hold").status_code == 204
    assert rig.log == ["stop"]
    assert session_on_disk(rig, session_id).ended_at is None
    assert rig.state.snapshot.session is None
    listed = rig.client.get("/api/sessions").json()
    assert [(e["id"], e["open"]) for e in listed] == [(session_id, True)]
    unlocked = rig.client.put(
        "/api/settings", json={"vision": {"hueCenter": 5}}
    )
    assert unlocked.status_code == 204


def test_a_new_session_can_start_while_another_is_on_hold(rig):
    first = rig.start(name="First").json()["id"]
    assert rig.start().status_code == 409  # still loaded: refused
    rig.client.post("/api/sessions/current/hold")
    second = rig.start(name="Second")
    assert second.status_code == 200
    assert second.json()["id"] != first
    assert rig.state.snapshot.session.id == second.json()["id"]
    assert session_on_disk(rig, first).ended_at is None
    rig.client.post("/api/sessions/current/hold")
    assert [e["open"] for e in rig.client.get("/api/sessions").json()] == [
        True,
        True,
    ]


def test_a_session_on_hold_can_be_resumed_and_checked(rig):
    session_id = rig.start().json()["id"]
    rig.client.post("/api/sessions/current/hold")
    response = rig.client.post(f"/api/sessions/{session_id}/load?mode=resume")
    assert response.status_code == 200
    assert response.json()["cameraCheck"] is True
    assert rig.state.snapshot.session.id == session_id


def test_hold_without_a_session_is_refused(rig):
    response = rig.client.post("/api/sessions/current/hold")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "no_session"


def test_hold_of_a_session_open_for_review_just_closes_it(rig):
    session_id = start_and_close(rig)
    rig.client.post(f"/api/sessions/{session_id}/load?mode=review")
    assert rig.client.post("/api/sessions/current/hold").status_code == 204
    assert rig.state.snapshot.session is None
    assert session_on_disk(rig, session_id).ended_at is None
    assert rig.log == []  # nothing was capturing


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


def test_resume_does_not_need_the_recorded_camera_but_asks_for_a_check(rig):
    session_id = start_and_close(rig)
    rig.engine.close_camera().result(2)
    rig.cameras = [CameraInfo(0, "Other Cam", "Other Cam")]
    response = rig.client.post(f"/api/sessions/{session_id}/load?mode=resume")
    assert response.status_code == 200
    assert response.json()["cameraCheck"] is True
    session = rig.state.snapshot.session
    assert session.role is SessionRole.CAPTURE
    assert session.camera_check
    assert session.recorded_camera == "Test Cam"
    assert rig.opened[-1][0] == 0  # the camera that is there


def test_resume_without_any_camera_is_refused(rig):
    session_id = start_and_close(rig)
    rig.engine.close_camera().result(2)
    rig.cameras = []
    before = rig.state.snapshot
    response = rig.client.post(f"/api/sessions/{session_id}/load?mode=resume")
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "camera_unavailable"
    assert "Test Cam" in error["message"]
    assert rig.state.snapshot.session == before.session


def test_the_camera_can_change_only_while_it_is_being_checked(rig):
    session_id = start_and_close(rig)
    rig.engine.close_camera().result(2)
    rig.client.post(f"/api/sessions/{session_id}/load?mode=resume")
    # While the camera is checked: the camera may change, settings may not.
    assert rig.client.put("/api/camera", json={"index": 0}).status_code == 204
    locked = rig.client.put("/api/settings", json={"vision": {"hueCenter": 3}})
    assert locked.status_code == 409
    assert (
        rig.client.post("/api/sessions/current/camera/confirm").status_code
        == 204
    )
    # After it: nothing changes.
    after = rig.client.put("/api/camera", json={"index": 0})
    assert after.status_code == 409
    assert after.json()["error"]["code"] == "session_active"


def test_confirming_records_the_camera_in_use_and_unlocks_capture(rig):
    session_id = start_and_close(rig)
    rig.engine.close_camera().result(2)
    rig.client.post(f"/api/sessions/{session_id}/load?mode=resume")
    # The user switched to another camera while checking.
    rig.engine.open_source(FakeSource(*rig.size), "Other Cam", 1).result(2)
    assert (
        rig.client.post("/api/sessions/current/camera/confirm").status_code
        == 204
    )
    record = session_on_disk(rig, session_id)
    assert record.camera.device == "Other Cam"
    assert record.camera.index == 1
    assert (
        record.vision_settings
        == session_on_disk(rig, session_id).vision_settings
    )
    session = rig.state.snapshot.session
    assert not session.camera_check and session.recorded_camera is None


def test_confirming_without_a_check_is_refused(rig):
    rig.start()
    response = rig.client.post("/api/sessions/current/camera/confirm")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "no_camera_check"


def test_editing_the_name_keeps_the_camera_check(rig):
    session_id = start_and_close(rig)
    rig.engine.close_camera().result(2)
    rig.client.post(f"/api/sessions/{session_id}/load?mode=resume")
    rig.client.patch(f"/api/sessions/{session_id}", json={"name": "New"})
    assert rig.state.snapshot.session.camera_check


def _count_scans(rig):
    scans = []

    def lister():
        scans.append(1)
        return list(rig.cameras)

    rig.service._cameras = CameraCatalog(lister)
    return scans


def test_resume_uses_the_camera_list_already_read(rig):
    scans = _count_scans(rig)
    session_id = start_and_close(rig)
    rig.engine.close_camera().result(2)
    assert (
        rig.client.post(
            f"/api/sessions/{session_id}/load?mode=resume"
        ).status_code
        == 200
    )
    assert len(scans) == 1
    rig.client.post("/api/sessions/current/hold")
    rig.engine.close_camera().result(2)
    assert (
        rig.client.post(
            f"/api/sessions/{session_id}/load?mode=resume"
        ).status_code
        == 200
    )
    assert len(scans) == 1  # the second resume read nothing again


def test_resume_looks_again_when_the_recorded_camera_is_not_in_the_list(rig):
    scans = _count_scans(rig)
    session_id = start_and_close(rig)  # recorded with "Test Cam"
    rig.engine.close_camera().result(2)
    rig.cameras = [CameraInfo(0, "Other Cam", "Other Cam")]
    rig.service._cameras.get()  # a list without the recorded camera is kept
    assert len(scans) == 1
    rig.cameras = [
        CameraInfo(0, "Other Cam", "Other Cam"),
        CameraInfo(2, "Test Cam", "Test Cam"),  # plugged in since
    ]
    response = rig.client.post(f"/api/sessions/{session_id}/load?mode=resume")
    assert response.status_code == 200
    assert len(scans) == 2
    assert rig.opened[-1][0] == 2  # and the recorded camera was found


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


# --- Delete ------------------------------------------------------------------


def test_a_session_that_is_not_loaded_can_be_deleted(rig):
    first = rig.start(name="old").json()["id"]
    rig.client.post("/api/sessions/current/end")
    second = rig.start().json()["id"]
    response = rig.client.delete(f"/api/sessions/{first}")
    assert response.status_code == 204
    listed = [s["id"] for s in rig.client.get("/api/sessions").json()]
    assert listed == [second]
    assert not rig.store.session_dir(first).exists()


def test_a_loaded_session_cannot_be_deleted(rig):
    session_id = rig.start().json()["id"]
    refused = rig.client.delete(f"/api/sessions/{session_id}")
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "session_loaded"
    rig.client.post("/api/sessions/current/end")
    rig.client.post(f"/api/sessions/{session_id}/load?mode=review")
    assert rig.client.delete(f"/api/sessions/{session_id}").status_code == 409
    assert rig.store.session_dir(session_id).exists()
    rig.client.post("/api/sessions/current/end")  # close the review
    assert rig.client.delete(f"/api/sessions/{session_id}").status_code == 204


def test_deleting_an_unknown_session_is_not_found(rig):
    missing = "00000000-0000-4000-8000-000000000000"
    assert rig.client.delete(f"/api/sessions/{missing}").status_code == 404
    assert rig.client.delete("/api/sessions/nonsense").status_code == 404


# --- Name and notes ----------------------------------------------------------


def test_the_name_and_notes_change_while_the_session_is_loaded(rig):
    session_id = rig.start(name="first").json()["id"]
    response = rig.client.patch(
        f"/api/sessions/{session_id}",
        json={"name": " evening ", "notes": "dim light"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "evening"
    record = rig.store.get_session(session_id)
    assert (record.name, record.notes) == ("evening", "dim light")
    assert rig.state.snapshot.session.name == "evening"
    listed = rig.client.get("/api/sessions").json()[0]
    assert (listed["name"], listed["notes"]) == ("evening", "dim light")


def test_the_name_and_notes_change_after_the_session_has_ended(rig):
    session_id = rig.start(name="old", notes="x").json()["id"]
    rig.client.post("/api/sessions/current/end")
    done = rig.client.patch(f"/api/sessions/{session_id}", json={"notes": ""})
    assert done.status_code == 200
    record = rig.store.get_session(session_id)
    assert (record.name, record.notes) == ("old", None)  # name left alone
    assert record.ended_at is not None


def test_a_session_change_needs_a_field_and_a_known_session(rig):
    session_id = rig.start().json()["id"]
    assert (
        rig.client.patch(f"/api/sessions/{session_id}", json={}).status_code
        == 400
    )
    missing = "00000000-0000-4000-8000-000000000000"
    response = rig.client.patch(f"/api/sessions/{missing}", json={"name": "a"})
    assert response.status_code == 404


# --- End any open session ----------------------------------------------------


def make_open_session(rig, name="Held"):
    """An open session on disk that is not loaded (as after a hold)."""
    session = rig.store.create_session("Ada", Handedness.RIGHT, name=name)
    return session.session_id


def test_an_open_session_that_is_not_loaded_can_be_ended(tmp_path):
    rig = Rig(tmp_path)  # no camera is needed
    try:
        session_id = make_open_session(rig)
        before = rig.state.snapshot
        assert (
            rig.client.post(f"/api/sessions/{session_id}/end").status_code
            == 204
        )
        assert session_on_disk(rig, session_id).ended_at is not None
        assert rig.state.snapshot is before  # the state did not change
        assert rig.log == []  # nothing was stopped
        listed = rig.client.get("/api/sessions").json()
        assert [(e["id"], e["open"]) for e in listed] == [(session_id, False)]
    finally:
        rig.close()


def test_ending_the_session_loaded_for_capture_stops_capture(rig):
    session_id = rig.start().json()["id"]
    response = rig.client.post(f"/api/sessions/{session_id}/end")
    assert response.status_code == 204
    assert rig.log == ["stop"]
    assert session_on_disk(rig, session_id).ended_at is not None
    assert rig.state.snapshot.session is None
    unlocked = rig.client.put(
        "/api/settings", json={"vision": {"hueCenter": 5}}
    )
    assert unlocked.status_code == 204


def test_ending_the_session_loaded_for_review_unloads_it(rig):
    session_id = make_open_session(rig)
    rig.client.post(f"/api/sessions/{session_id}/load?mode=review")
    assert rig.state.snapshot.session.role is SessionRole.REVIEW
    assert rig.client.post(f"/api/sessions/{session_id}/end").status_code == 204
    assert rig.state.snapshot.session is None
    assert session_on_disk(rig, session_id).ended_at is not None
    assert rig.log == []  # nothing was capturing


def test_ending_another_session_leaves_the_loaded_one_alone(rig):
    other = make_open_session(rig, "Other")
    loaded = rig.start().json()["id"]
    assert rig.client.post(f"/api/sessions/{other}/end").status_code == 204
    assert session_on_disk(rig, other).ended_at is not None
    assert session_on_disk(rig, loaded).ended_at is None
    assert rig.state.snapshot.session.id == loaded
    assert rig.state.snapshot.session.role is SessionRole.CAPTURE
    assert rig.log == []


def test_an_ended_session_cannot_be_ended_again(rig):
    session_id = make_open_session(rig)
    assert rig.client.post(f"/api/sessions/{session_id}/end").status_code == 204
    ended_at = session_on_disk(rig, session_id).ended_at
    again = rig.client.post(f"/api/sessions/{session_id}/end")
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "session_ended"
    assert session_on_disk(rig, session_id).ended_at == ended_at


def test_an_unknown_session_cannot_be_ended(rig):
    response = rig.client.post("/api/sessions/nope/end")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_an_ended_session_cannot_be_resumed_but_can_be_reviewed(rig):
    session_id = make_open_session(rig)
    rig.client.post(f"/api/sessions/{session_id}/end")
    resume = rig.client.post(f"/api/sessions/{session_id}/load?mode=resume")
    assert resume.status_code == 409
    assert resume.json()["error"]["code"] == "session_ended"
    review = rig.client.post(f"/api/sessions/{session_id}/load?mode=review")
    assert review.status_code == 200


def test_the_current_session_endpoint_closes_a_review_without_ending(rig):
    session_id = make_open_session(rig)
    rig.client.post(f"/api/sessions/{session_id}/load?mode=review")
    assert rig.client.post("/api/sessions/current/end").status_code == 204
    assert rig.state.snapshot.session is None
    assert session_on_disk(rig, session_id).ended_at is None


def test_the_current_session_endpoint_still_needs_a_loaded_session(rig):
    response = rig.client.post("/api/sessions/current/end")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "no_session"


# --- Datasets -----------------------------------------------------------------


def location_of(rig):
    return rig.store.path.parent


def make_dataset(rig, name, author="Bob", sessions=1, end=True):
    store = DatasetStore.open(location_of(rig) / name, create=True)
    ids = []
    for _ in range(sessions):
        record = store.create_session(author, Handedness.RIGHT, name=name)
        ids.append(record.session_id)
        if end:
            store.end_session(record.session_id)
    return ids


def listed(rig):
    return {d["name"]: d for d in rig.client.get("/api/datasets").json()}


def tree(folder):
    return {
        str(p.relative_to(folder)): p.read_bytes() if p.is_file() else None
        for p in sorted(folder.rglob("*"))
    }


def test_the_state_names_the_dataset_in_use(rig):
    assert rig.state.snapshot.dataset == rig.store.path.name
    assert rig.state.snapshot.to_json_dict()["dataset"] == rig.store.path.name


def test_datasets_are_listed_with_counts_and_the_one_in_use(rig):
    make_dataset(rig, "bob", sessions=2)
    found = listed(rig)
    assert set(found) == {"data", "bob"}
    assert found["data"]["inUse"] is True and found["bob"]["inUse"] is False
    assert (found["bob"]["sessions"], found["bob"]["samples"]) == (2, 0)


def test_a_dataset_can_be_created(rig):
    response = rig.client.post("/api/datasets", json={"name": "fresh"})
    assert response.status_code == 200 and response.json() == {"name": "fresh"}
    assert listed(rig)["fresh"]["sessions"] == 0
    assert (location_of(rig) / "fresh" / "dataset.json").is_file()


@pytest.mark.parametrize("name", ["", "Has Caps", "a/b", "-x"])
def test_an_invalid_dataset_name_is_refused(rig, name):
    response = rig.client.post("/api/datasets", json={"name": name})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_an_existing_dataset_name_is_refused(rig):
    make_dataset(rig, "bob")
    response = rig.client.post("/api/datasets", json={"name": "bob"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "dataset_exists"


def test_choosing_a_dataset_changes_what_the_session_list_shows(rig):
    mine = make_dataset(rig, "data", author="Ada")
    theirs = make_dataset(rig, "bob", author="Bob", sessions=2)
    assert {s["id"] for s in rig.client.get("/api/sessions").json()} == set(
        mine
    )

    response = rig.client.put("/api/dataset", json={"name": "bob"})

    assert response.status_code == 204
    assert rig.state.snapshot.dataset == "bob"
    assert {s["id"] for s in rig.client.get("/api/sessions").json()} == set(
        theirs
    )
    assert listed(rig)["bob"]["inUse"] is True
    assert listed(rig)["data"]["inUse"] is False


def test_choosing_an_unknown_or_invalid_dataset_is_refused(rig):
    missing = rig.client.put("/api/dataset", json={"name": "nobody"})
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"
    bad = rig.client.put("/api/dataset", json={"name": "No Good"})
    assert bad.status_code == 400
    assert rig.state.snapshot.dataset == "data"


def test_new_sessions_go_into_the_chosen_dataset(rig):
    make_dataset(rig, "bob")
    rig.client.put("/api/dataset", json={"name": "bob"})
    session_id = rig.start().json()["id"]
    assert (location_of(rig) / "bob" / "sessions" / session_id).is_dir()
    assert not (location_of(rig) / "data" / "sessions" / session_id).exists()


@pytest.mark.parametrize("role", ["capture", "review"])
def test_datasets_cannot_change_while_a_session_is_loaded(rig, role):
    make_dataset(rig, "bob")
    if role == "capture":
        rig.start()
    else:
        held = make_dataset(rig, "data", author="Ada", end=False)[0]
        rig.client.post(f"/api/sessions/{held}/load?mode=review")
    calls = [
        rig.client.post("/api/datasets", json={"name": "fresh"}),
        rig.client.put("/api/dataset", json={"name": "bob"}),
        rig.client.post(
            "/api/datasets/merge", json={"sources": ["bob"], "target": "new"}
        ),
    ]
    for response in calls:
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "session_active"
    assert rig.state.snapshot.dataset == "data"
    assert "fresh" not in listed(rig) and "new" not in listed(rig)


def test_datasets_can_change_after_the_session_is_ended_or_held(rig):
    make_dataset(rig, "bob")
    rig.start()
    rig.client.post("/api/sessions/current/hold")
    assert (
        rig.client.put("/api/dataset", json={"name": "bob"}).status_code == 204
    )
    rig.client.put("/api/dataset", json={"name": "data"})
    held = rig.client.get("/api/sessions").json()[0]["id"]
    rig.client.post(f"/api/sessions/{held}/end")
    assert (
        rig.client.post("/api/datasets", json={"name": "ok"}).status_code == 200
    )


def test_merging_into_a_new_dataset_copies_sessions_and_keeps_sources(rig):
    a = make_dataset(rig, "ada", author="Ada")
    b = make_dataset(rig, "bob", author="Bob", sessions=2)
    before = (tree(location_of(rig) / "ada"), tree(location_of(rig) / "bob"))

    response = rig.client.post(
        "/api/datasets/merge", json={"sources": ["ada", "bob"], "target": "all"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["target"] == "all" and body["counts"] == {"copied": 3}
    assert {s["sessionId"] for s in body["sessions"]} == set(a + b)
    assert {s["source"] for s in body["sessions"]} == {"ada", "bob"}
    assert listed(rig)["all"]["sessions"] == 3
    after = (tree(location_of(rig) / "ada"), tree(location_of(rig) / "bob"))
    assert after == before


def test_a_conflict_is_skipped_or_replaced_as_asked(rig):
    make_dataset(rig, "ada", author="Ada")
    merge = {"sources": ["ada"], "target": "all"}
    rig.client.post("/api/datasets/merge", json=merge)
    ada = DatasetStore.open(location_of(rig) / "ada")
    session_id = ada.list_sessions()[0].session_id
    ada.update_session(session_id, name="edited")

    skipped = rig.client.post("/api/datasets/merge", json=merge).json()
    assert skipped["counts"] == {"conflict": 1}
    mine = DatasetStore.open(location_of(rig) / "all")
    assert mine.get_session(session_id).name != "edited"

    replaced = rig.client.post(
        "/api/datasets/merge", json={**merge, "onConflict": "replace"}
    ).json()
    assert replaced["counts"] == {"replaced": 1}
    assert (
        DatasetStore.open(location_of(rig) / "all").get_session(session_id).name
        == "edited"
    )


def test_merging_into_the_dataset_in_use_updates_the_lists(rig):
    make_dataset(rig, "bob", sessions=2)
    assert rig.client.get("/api/sessions").json() == []
    response = rig.client.post(
        "/api/datasets/merge", json={"sources": ["bob"], "target": "data"}
    )
    assert response.status_code == 200
    assert len(rig.client.get("/api/sessions").json()) == 2


def test_bad_merges_are_refused(rig):
    make_dataset(rig, "bob")
    post = lambda body: rig.client.post("/api/datasets/merge", json=body)  # noqa: E731
    assert post({"sources": ["bob"], "target": "bob"}).status_code == 400
    assert post({"sources": [], "target": "x"}).status_code == 400
    assert post({"sources": ["bob"], "target": "Bad Name"}).status_code == 400
    assert post({"sources": ["nobody"], "target": "x"}).status_code == 404
    assert "x" not in listed(rig)


def test_the_store_reindexing_follows_a_dataset_change(rig):
    changes = []
    rig.store.subscribe(changes.append)
    make_dataset(rig, "bob")
    rig.client.put("/api/dataset", json={"name": "bob"})
    assert [c.kind.value for c in changes] == ["dataset_changed"]
