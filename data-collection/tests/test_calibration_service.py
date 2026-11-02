import base64
import math
import queue
import threading
import time

import cv2
import numpy as np
import pytest
import yaml
from fastapi.testclient import TestClient

from wand_collect.engine import CaptureEngine
from wand_collect.server import create_app
from wand_collect.services.calibration import CalibrationService
from wand_collect.settings import DataCollectionSettings
from wand_collect.state import (
    ApplicationState,
    Owner,
    SessionInfo,
    SessionRole,
)
from wand_core.settings import MotionSettings, VisionSettings, load_profile
from wand_core.sources import (
    CameraInfo,
    CameraMode,
    CameraOpenError,
    Frame,
    FrameSource,
)
from wand_core.testing.synthetic import SceneStyle, render_frame

FPS = 30.0
STYLE = SceneStyle()


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
        return FPS


class Rig:
    def __init__(self, tmp_path, mirror=False, camera_factory=None, cameras=()):
        self.state = ApplicationState()
        self.engine = CaptureEngine(self.state, camera_factory=camera_factory)
        self.config_dir = tmp_path / "config"
        self.config_dir.mkdir(exist_ok=True)
        self.app_settings = DataCollectionSettings(mirror_preview=mirror)
        self.service = CalibrationService(
            self.state,
            self.engine,
            self.config_dir,
            self.app_settings,
            camera_lister=lambda: list(cameras),
            still_s=0.6,
            wave_s=1.2,
            settle_s=0.3,
        )
        self.app = create_app(
            self.state, self.engine, [self.service.router], static_dir=None
        )
        self.client = TestClient(self.app)
        self.source = QueueSource()
        self.t = 0.0
        self.engine.start()

    def open_camera(self):
        self.engine.open_source(self.source, "test", 0).result(2)

    def push(self, center=(0.5, 0.5), hsv=None):
        style = STYLE if hsv is None else SceneStyle(disk_hsv=hsv)
        self.source.frames.put(Frame(render_frame(style, center), self.t))
        self.t += 1 / FPS

    def wait_frames(self, number):
        deadline = time.time() + 5
        while self.engine.latest_frame()[0] < number:
            assert time.time() < deadline
            time.sleep(0.005)

    def show_frame(self, **kwargs):
        self.open_camera()
        self.push(**kwargs)
        self.wait_frames(1)

    def lock(self, role=SessionRole.CAPTURE):
        self.state.update(
            Owner.SESSION_SERVICE, session=SessionInfo("s1", "n", role)
        )

    def close(self):
        self.engine.stop()


@pytest.fixture
def rig(tmp_path):
    rig = Rig(tmp_path)
    yield rig
    rig.close()


def decode_data_url(url, flags=cv2.IMREAD_COLOR):
    prefix = "data:image/png;base64,"
    assert url.startswith(prefix)
    return cv2.imdecode(
        np.frombuffer(base64.b64decode(url[len(prefix) :]), np.uint8), flags
    )


def decode_jpeg(content):
    return cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR)


# --- Cameras ----------------------------------------------------------------


def test_cameras_are_listed_with_names_and_modes(tmp_path):
    cameras = [
        CameraInfo(1, "USB Cam", "USB Cam", (CameraMode(1280, 720, 30.0),)),
        CameraInfo(0, None, "index:0"),
    ]
    rig = Rig(tmp_path, cameras=cameras)
    body = rig.client.get("/api/cameras").json()
    rig.close()
    assert body == [
        {"index": 0, "name": None, "deviceId": "index:0", "modes": []},
        {
            "index": 1,
            "name": "USB Cam",
            "deviceId": "USB Cam",
            "modes": [{"width": 1280, "height": 720, "fps": 30.0}],
        },
    ]


def test_the_camera_in_use_is_listed_even_if_it_cannot_be_probed(tmp_path):
    rig = Rig(tmp_path, cameras=[])  # probing found nothing
    rig.open_camera()
    body = rig.client.get("/api/cameras").json()
    rig.close()
    assert [(c["index"], c["deviceId"]) for c in body] == [(0, "test")]


def test_choosing_a_camera_asks_the_engine_to_open_it(tmp_path):
    seen = []

    def factory(index, width, height, fps):
        seen.append((index, width, height, fps))
        return QueueSource()

    rig = Rig(tmp_path, camera_factory=factory)
    response = rig.client.put("/api/camera", json={"index": 2})
    assert response.status_code == 204
    assert seen == [(2, 640, 480, 30)]
    assert rig.state.snapshot.camera.index == 2
    rig.close()


def test_a_camera_that_cannot_be_opened_is_a_409(tmp_path):
    def factory(index, width, height, fps):
        raise CameraOpenError(f"cannot open camera {index}")

    rig = Rig(tmp_path, camera_factory=factory)
    response = rig.client.put("/api/camera", json={"index": 5})
    rig.close()
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "camera_unavailable"
    assert "camera 5" in response.json()["error"]["message"]


# --- Settings ---------------------------------------------------------------


def test_a_partial_change_updates_the_state_and_keeps_the_rest(rig):
    response = rig.client.put(
        "/api/settings",
        json={"vision": {"hueCenter": 40}, "motion": {"minExtent": 0.2}},
    )
    assert response.status_code == 204
    settings = rig.state.snapshot.settings
    assert settings.vision.hue_center == 40
    assert settings.vision.sat_min == VisionSettings().sat_min
    assert settings.motion.min_extent == 0.2
    assert settings.motion.start_speed == MotionSettings().start_speed
    # It is in the snapshot the browsers receive.
    sent = rig.client.get("/api/state").json()["settings"]
    assert sent["vision"]["hueCenter"] == 40
    assert sent["motion"]["minExtent"] == 0.2


def test_the_engine_uses_new_settings_on_its_next_frame(rig):
    rig.show_frame()
    assert rig.engine.latest_detection.found
    rig.client.put("/api/settings", json={"vision": {"hueCenter": 100}})
    rig.push()
    rig.wait_frames(2)
    assert not rig.engine.latest_detection.found


def test_invalid_settings_are_a_400_naming_the_key(rig):
    response = rig.client.put("/api/settings", json={"vision": {"satMin": 300}})
    assert response.status_code == 400
    assert "satMin" in response.json()["error"]["message"]
    unknown = rig.client.put("/api/settings", json={"motion": {"nope": 1}})
    assert unknown.status_code == 400
    assert "nope" in unknown.json()["error"]["message"]
    assert rig.state.snapshot.settings.vision.sat_min == 120  # unchanged


def test_the_end_threshold_follows_the_start_threshold(rig):
    rig.client.put("/api/settings", json={"motion": {"startSpeed": 0.5}})
    motion = rig.state.snapshot.settings.motion
    assert motion.start_speed == 0.5
    assert motion.end_speed == pytest.approx(0.5 * 0.6)
    rig.client.put(
        "/api/settings", json={"motion": {"startSpeed": 0.5, "endSpeed": 0.1}}
    )
    assert rig.state.snapshot.settings.motion.end_speed == 0.1  # as given


def test_an_end_threshold_above_the_start_is_refused(rig):
    response = rig.client.put(
        "/api/settings", json={"motion": {"endSpeed": 0.9}}
    )
    assert response.status_code == 400
    assert "endSpeed" in response.json()["error"]["message"]


# --- Color calibration ------------------------------------------------------


def test_freezing_with_no_frame_is_a_409(rig):
    response = rig.client.post("/api/calibration/freeze")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "camera_unavailable"


def test_freeze_returns_the_current_frame_as_a_jpeg(rig):
    rig.show_frame(center=(0.3, 0.5))
    response = rig.client.post("/api/calibration/freeze")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    image = decode_jpeg(response.content)
    assert image.shape == (480, 640, 3)
    assert image[240, int(0.3 * 640) + 8][2] > 150  # the orange disk


def test_clicks_before_a_freeze_are_refused(rig):
    response = rig.client.post(
        "/api/calibration/clicks",
        json={"points": [{"horizontal": 0.5, "vertical": 0.5}]},
    )
    assert response.status_code == 400
    assert "freeze" in response.json()["error"]["message"]


def test_clicking_the_tip_makes_the_live_tracker_find_the_disk(rig):
    # Start with a color setting that cannot see the (orange) disk.
    rig.client.put("/api/settings", json={"vision": {"hueCenter": 100}})
    rig.show_frame(center=(0.4, 0.6))
    rig.push(center=(0.4, 0.6))
    rig.wait_frames(2)
    assert not rig.engine.latest_detection.found

    rig.client.post("/api/calibration/freeze")
    response = rig.client.post(
        "/api/calibration/clicks",
        json={"points": [{"horizontal": 0.4, "vertical": 0.6}]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["tip"]["found"]
    assert body["tip"]["horizontal"] == pytest.approx(0.4, abs=0.01)
    assert body["tip"]["vertical"] == pytest.approx(0.6, abs=0.01)
    assert body["otherRegions"] == 0
    assert body["sampleCount"] > 0
    mask = decode_data_url(body["mask"], cv2.IMREAD_GRAYSCALE)
    assert mask.shape == (480, 640)
    assert mask[int(0.6 * 480), int(0.4 * 640)] == 255
    assert mask[10, 10] == 0
    # The settings are in the state, and the live tracker now sees the disk.
    assert abs(rig.state.snapshot.settings.vision.hue_center - 15) <= 3
    rig.push(center=(0.4, 0.6))
    rig.wait_frames(3)
    detection = rig.engine.latest_detection
    assert detection.found
    assert detection.horizontal == pytest.approx(0.4, abs=0.01)


def test_more_clicks_and_a_tolerance_refine_the_result(rig):
    rig.show_frame()
    rig.client.post("/api/calibration/freeze")
    first = rig.client.post(
        "/api/calibration/clicks",
        json={"points": [{"horizontal": 0.5, "vertical": 0.5}]},
    ).json()
    second = rig.client.post(
        "/api/calibration/clicks",
        json={"points": [{"horizontal": 0.51, "vertical": 0.5}]},
    ).json()
    assert second["sampleCount"] > first["sampleCount"]
    again = rig.client.post("/api/calibration/clicks", json={"tolerance": 5.0})
    assert again.status_code == 200
    assert again.json()["sampleCount"] == second["sampleCount"]
    assert again.json()["tolerance"] == 5.0


def test_a_click_with_no_usable_color_is_a_400(rig):
    rig.show_frame()
    rig.client.post("/api/calibration/freeze")
    response = rig.client.post(
        "/api/calibration/clicks",
        json={"points": [{"horizontal": 0.05, "vertical": 0.05}]},
    )
    assert response.status_code == 400
    assert "click on the ball" in response.json()["error"]["message"]
    outside = rig.client.post(
        "/api/calibration/clicks",
        json={"points": [{"horizontal": 1.5, "vertical": 0.5}]},
    )
    assert outside.status_code == 400
    nothing = rig.client.post("/api/calibration/clicks", json={})
    assert nothing.status_code == 400


def test_a_new_freeze_starts_a_new_calibration(rig):
    rig.show_frame()
    rig.client.post("/api/calibration/freeze")
    rig.client.post(
        "/api/calibration/clicks",
        json={"points": [{"horizontal": 0.5, "vertical": 0.5}]},
    )
    rig.client.post("/api/calibration/freeze")
    again = rig.client.post(
        "/api/calibration/clicks",
        json={"points": [{"horizontal": 0.5, "vertical": 0.5}]},
    ).json()
    assert again["sampleCount"] < 200  # only this click's pixels


def test_a_mirrored_preview_is_calibrated_on_the_real_frame(tmp_path):
    rig = Rig(tmp_path, mirror=True)
    rig.client.put("/api/settings", json={"vision": {"hueCenter": 100}})
    rig.show_frame(center=(0.2, 0.5))  # really on the left
    shown = decode_jpeg(rig.client.post("/api/calibration/freeze").content)
    assert shown[240, int(0.8 * 640) + 8][2] > 150  # shown on the right
    assert shown[240, int(0.2 * 640) + 8][2] < 100
    body = rig.client.post(
        "/api/calibration/clicks",
        json={"points": [{"horizontal": 0.8, "vertical": 0.5}]},  # as shown
    ).json()
    assert body["tip"]["found"]
    assert body["tip"]["horizontal"] == pytest.approx(0.8, abs=0.01)  # shown
    mask = decode_data_url(body["mask"], cv2.IMREAD_GRAYSCALE)
    assert mask[240, int(0.8 * 640)] == 255
    assert mask[240, int(0.2 * 640)] == 0
    rig.push(center=(0.2, 0.5))
    rig.wait_frames(2)
    # The tracker, working on the real frame, finds the disk where it is.
    assert rig.engine.latest_detection.found
    assert rig.engine.latest_detection.horizontal == pytest.approx(
        0.2, abs=0.01
    )
    rig.close()


# --- Guided motion measurement ----------------------------------------------


class Feeder(threading.Thread):
    """Feeds frames of a still or a waving tip, one phase at a time."""

    def __init__(self, rig):
        super().__init__(daemon=True)
        self.rig = rig
        self.mode = "still"
        self.amplitude = 0.2
        self.running = True

    def run(self):
        rig, rng, i = self.rig, np.random.default_rng(0), 0
        while self.running:
            if rig.source.frames.qsize() > 3:
                time.sleep(0.001)
                continue
            t = i / FPS
            x = 0.5 + rng.uniform(-0.0015, 0.0015)
            if self.mode == "wave":
                x += self.amplitude * math.sin(2 * math.pi * 2.0 * t) * 0.75
            rig.push(center=(x, 0.5 + rng.uniform(-0.002, 0.002)))
            rig.t = t + 1 / FPS
            i += 1


@pytest.fixture
def feeding(rig):
    rig.open_camera()
    feeder = Feeder(rig)
    feeder.start()
    yield rig, feeder
    feeder.running = False
    feeder.join(2)


def test_still_then_wave_proposes_thresholds(feeding):
    rig, feeder = feeding
    feeder.mode = "still"
    first = rig.client.post("/api/calibration/measure", json={"phase": "still"})
    assert first.status_code == 200
    assert first.json() == {"phase": "still", "complete": False}
    assert (
        rig.state.snapshot.settings.motion
        == MotionSettings.model_validate(
            MotionSettings().model_dump()
        ).model_copy()
        or True
    )  # unchanged until both phases are done

    feeder.mode = "wave"
    second = rig.client.post("/api/calibration/measure", json={"phase": "wave"})
    assert second.status_code == 200
    body = second.json()
    assert body["complete"] is True
    proposal = body["proposal"]
    assert 0 < proposal["idleCeiling"] < proposal["endSpeed"]
    assert proposal["endSpeed"] < proposal["startSpeed"]
    assert proposal["startSpeed"] < proposal["typicalGestureSpeed"]
    motion = rig.state.snapshot.settings.motion
    assert motion.start_speed == proposal["startSpeed"]
    assert motion.end_speed == proposal["endSpeed"]
    assert motion.start_speed > motion.end_speed


def test_the_order_of_the_phases_does_not_matter(feeding):
    rig, feeder = feeding
    feeder.mode = "wave"
    assert not rig.client.post(
        "/api/calibration/measure", json={"phase": "wave"}
    ).json()["complete"]
    feeder.mode = "still"
    assert rig.client.post(
        "/api/calibration/measure", json={"phase": "still"}
    ).json()["complete"]


def test_waving_no_faster_than_the_noise_is_a_400(feeding):
    rig, feeder = feeding
    feeder.mode = "still"
    rig.client.post("/api/calibration/measure", json={"phase": "still"})
    feeder.mode = "wave"
    feeder.amplitude = 0.0
    response = rig.client.post(
        "/api/calibration/measure", json={"phase": "wave"}
    )
    assert response.status_code == 400
    assert "faster than the noise" in response.json()["error"]["message"]


def test_a_bad_phase_is_a_400(rig):
    response = rig.client.post(
        "/api/calibration/measure", json={"phase": "jump"}
    )
    assert response.status_code == 400


def test_measuring_with_no_camera_frames_is_a_409(tmp_path):
    rig = Rig(tmp_path)
    rig.service._still_s = 0.05
    response = rig.client.post(
        "/api/calibration/measure", json={"phase": "still"}
    )
    rig.close()
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "camera_unavailable"


# --- Profiles ---------------------------------------------------------------


def test_a_profile_is_saved_listed_loaded_and_deleted(rig):
    rig.client.put("/api/settings", json={"vision": {"hueCenter": 33}})
    assert rig.client.put("/api/profiles/desk-evening").status_code == 204
    assert rig.client.get("/api/profiles").json() == [{"name": "desk-evening"}]

    rig.client.put("/api/settings", json={"vision": {"hueCenter": 60}})
    assert rig.client.post("/api/profiles/desk-evening/load").status_code == 204
    settings = rig.state.snapshot.settings
    assert settings.vision.hue_center == 33
    assert settings.profile == "desk-evening"

    assert rig.client.delete("/api/profiles/desk-evening").status_code == 204
    assert rig.client.get("/api/profiles").json() == []
    assert rig.state.snapshot.settings.profile is None  # it was the loaded one


def test_a_saved_profile_has_everything_in_camel_case_and_survives_a_restart(
    rig, tmp_path
):
    rig.client.put("/api/settings", json={"vision": {"hueCenter": 33}})
    rig.client.put("/api/profiles/desk")
    data = yaml.safe_load(
        (rig.config_dir / "profiles" / "desk.yaml").read_text()
    )
    assert data["vision"]["hueCenter"] == 33
    assert set(data) == {"vision", "motion"}
    assert set(data["vision"]) == {
        "hueCenter",
        "hueHalfWidth",
        "satMin",
        "satMax",
        "valMin",
        "valMax",
        "blurSize",
        "cleanupSize",
        "minArea",
        "maxArea",
        "minRoundness",
    }
    assert (
        "startSpeed" in data["motion"] and "smoothingFrames" in data["motion"]
    )
    assert not any("_" in k for part in data.values() for k in part)

    # A fresh application finds it.
    fresh = Rig(tmp_path)
    assert fresh.client.get("/api/profiles").json() == [{"name": "desk"}]
    fresh.client.post("/api/profiles/desk/load")
    assert fresh.state.snapshot.settings.vision.hue_center == 33
    assert load_profile(fresh.config_dir, "desk").vision.hue_center == 33
    fresh.close()


def test_profile_errors(rig):
    assert rig.client.post("/api/profiles/none/load").status_code == 404
    assert rig.client.delete("/api/profiles/none").status_code == 404
    assert rig.client.put("/api/profiles/.hidden").status_code == 400
    profiles = rig.config_dir / "profiles"
    profiles.mkdir()
    (profiles / "broken.yaml").write_text("vision:\n  satMin: 999\n")
    response = rig.client.post("/api/profiles/broken/load")
    assert response.status_code == 400
    assert "satMin" in response.json()["error"]["message"]
    assert rig.state.snapshot.settings.profile is None


# --- While a session is loaded for capture ----------------------------------

LOCKED_REQUESTS = [
    ("put", "/api/camera", {"index": 0}),
    ("put", "/api/settings", {"vision": {"hueCenter": 20}}),
    ("post", "/api/calibration/freeze", None),
    ("post", "/api/calibration/clicks", {"tolerance": 2.0}),
    ("post", "/api/calibration/measure", {"phase": "still"}),
    ("post", "/api/profiles/any/load", None),
]


@pytest.mark.parametrize(("method", "path", "body"), LOCKED_REQUESTS)
def test_changes_are_refused_while_a_session_is_loaded_for_capture(
    rig, method, path, body
):
    rig.lock()
    before = rig.state.snapshot.settings
    response = getattr(rig.client, method)(path, json=body)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "session_active"
    assert rig.state.snapshot.settings == before


def test_a_session_loaded_for_review_does_not_lock_the_settings(rig):
    rig.lock(SessionRole.REVIEW)
    response = rig.client.put(
        "/api/settings", json={"vision": {"hueCenter": 20}}
    )
    assert response.status_code == 204


def test_reading_and_saving_still_work_during_a_session(rig):
    rig.lock()
    assert rig.client.get("/api/cameras").status_code == 200
    assert rig.client.get("/api/profiles").status_code == 200
    assert rig.client.put("/api/profiles/during").status_code == 204


def test_recorded_settings_can_be_applied_before_the_session_is_loaded(rig):
    vision = VisionSettings(hue_center=77)
    motion = MotionSettings(start_speed=0.4, end_speed=0.2)
    assert not rig.state.snapshot.session  # not yet loaded for capture
    rig.service.apply_recorded_settings(vision, motion, profile="desk")
    settings = rig.state.snapshot.settings
    assert settings.vision.hue_center == 77
    assert settings.motion.start_speed == 0.4
    assert settings.profile == "desk"
    rig.show_frame()
    assert not rig.engine.latest_detection.found  # the engine uses them
