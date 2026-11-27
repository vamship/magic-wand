import shutil
from pathlib import Path

import pytest

from wand_collect import cli
from wand_collect.app import build_application, is_loopback
from wand_collect.labels import LabelsError, load_labels
from wand_collect.state import CaptureStatus
from wand_core.dataset import DatasetStore, InvalidDatasetNameError
from wand_core.sources import CameraOpenError, Frame, FrameSource
from wand_core.testing.synthetic import SceneStyle, render_frame

REPO_CONFIG = Path(__file__).parents[2] / "config"


@pytest.fixture
def config(tmp_path):
    folder = tmp_path / "repo" / "config"
    shutil.copytree(REPO_CONFIG, folder)
    return folder


class OneFrameSource(FrameSource):
    def __init__(self):
        self.closed = False

    def open(self):
        pass

    def read(self):
        return Frame(render_frame(SceneStyle(), (0.5, 0.5)), 0.0)

    def close(self):
        self.closed = True

    @property
    def frame_size(self):
        return (640, 480)

    @property
    def nominal_fps(self):
        return 30.0


def failing_camera(index, width, height, fps):
    raise CameraOpenError(f"cannot open camera {index}")


def stub_camera(index, width, height, fps):
    return OneFrameSource()


# --- Labels -----------------------------------------------------------------


def test_the_repository_labels_load():
    labels = load_labels(REPO_CONFIG / "labels.yaml")
    assert [label.id for label in labels] == [
        "alohomora",
        "reparo",
        "silencio",
        "revelio",
        "aparecum",
        "herbivicus",
        "expelliarmus",
    ]
    assert [label.name for label in labels] == [
        "Alohomora",
        "Reparo",
        "Silencio",
        "Revelio",
        "Aparecum",
        "Herbivicus",
        "Expelliarmus",
    ]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("labels:\n  - {id: Bad Id, name: X}\n", "slug"),
        ("labels:\n  - {id: a, name: A}\n  - {id: a, name: B}\n", "duplicate"),
        ("labels:\n  - {id: a}\n", "id and a name"),
        ("other: 1\n", "labels"),
        ("labels: [", "not valid YAML"),
    ],
)
def test_bad_labels_files_are_reported(tmp_path, text, message):
    path = tmp_path / "labels.yaml"
    path.write_text(text)
    with pytest.raises(LabelsError, match=message):
        load_labels(path)


def test_missing_labels_file_is_reported(tmp_path):
    with pytest.raises(LabelsError, match="cannot read"):
        load_labels(tmp_path / "none.yaml")


# --- Startup ----------------------------------------------------------------


def test_startup_loads_configuration_opens_the_data_folder_and_labels(config):
    application = build_application(config, open_camera=False)
    try:
        # The dataset is created in data/ next to config/ (the repository root).
        assert (config.parent / "data" / "default" / "dataset.json").is_file()
        assert application.dataset == "default"
        assert application.data_location == config.parent / "data"
        assert isinstance(application.store, DatasetStore)
        snapshot = application.state.snapshot
        assert [label.id for label in snapshot.labels][0] == "alohomora"
        assert snapshot.settings.vision.hue_center == 15
        assert snapshot.capture.state is CaptureStatus.STOPPED
        assert application.settings.server.port == 8000
        assert application.engine.buffer.max_seconds == pytest.approx(8.0)
    finally:
        application.shutdown()


def test_the_location_and_the_dataset_can_be_overridden(config, tmp_path):
    target = tmp_path / "elsewhere"
    application = build_application(config, target, "mine", open_camera=False)
    application.shutdown()
    assert (target / "mine" / "dataset.json").is_file()
    assert not (config.parent / "data").exists()


def test_an_invalid_dataset_name_stops_the_startup(config):
    with pytest.raises(InvalidDatasetNameError):
        build_application(config, dataset="Not Valid", open_camera=False)
    assert not (config.parent / "data").exists()


def test_a_data_location_that_is_itself_a_dataset_is_warned_about(config):
    DatasetStore.open(config.parent / "data", create=True)
    application = build_application(config, open_camera=False)
    application.shutdown()
    assert "old layout" in application.layout_warning
    assert (config.parent / "data" / "default" / "dataset.json").is_file()


def test_a_local_override_changes_the_configuration(config):
    (config / "data-collection.local.yaml").write_text(
        "dataLocation: mine\ndataset: ada\nserver:\n  port: 9100\n"
    )
    application = build_application(config, open_camera=False)
    application.shutdown()
    assert (config.parent / "mine" / "ada" / "dataset.json").is_file()
    assert application.settings.server.port == 9100


def test_the_preview_camera_is_opened_and_written_to_the_state(config):
    application = build_application(config, camera_factory=stub_camera)
    try:
        assert application.camera_error is None
        camera = application.state.snapshot.camera
        assert camera.index == 0
        assert camera.actual.width == 640
    finally:
        application.shutdown()


def test_the_application_starts_when_no_camera_is_available(config):
    application = build_application(config, camera_factory=failing_camera)
    try:
        assert "cannot open camera 0" in application.camera_error
        assert application.state.snapshot.camera.device is None
        assert application.engine._thread.is_alive()  # still running
    finally:
        application.shutdown()


def test_an_existing_data_folder_is_reopened_not_replaced(config):
    first = build_application(config, open_camera=False)
    first.shutdown()
    marker = config.parent / "data" / "default" / "sessions" / "keep.txt"
    marker.write_text("x")
    second = build_application(config, open_camera=False)
    second.shutdown()
    assert marker.exists()


def test_loopback_detection():
    for host in ("127.0.0.1", "localhost", "::1", "127.0.0.5"):
        assert is_loopback(host)
    for host in ("0.0.0.0", "192.168.1.5", "example.com", "::"):
        assert not is_loopback(host)


# --- The serve command ------------------------------------------------------


@pytest.fixture
def served(monkeypatch):
    calls = []
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kw: calls.append(kw))
    monkeypatch.setattr(
        "wand_collect.app.CaptureEngine.open_camera",
        lambda self, *a, **k: _failed_future(),
    )
    return calls


def _failed_future():
    from concurrent.futures import Future

    future = Future()
    future.set_exception(CameraOpenError("no camera in tests"))
    return future


def test_serve_starts_the_server_on_the_configured_host_and_port(
    config, served, capsys
):
    assert cli.main(["serve", "--config", str(config)]) == 0
    assert len(served) == 1
    assert (served[0]["host"], served[0]["port"]) == ("127.0.0.1", 8000)
    assert served[0]["timeout_graceful_shutdown"] == 2
    out = capsys.readouterr()
    assert "http://127.0.0.1:8000/" in out.out
    assert "WARNING" not in out.err
    assert "No camera available" in out.err  # starts anyway


def test_serve_warns_about_a_non_loopback_host(config, served, capsys):
    (config / "data-collection.local.yaml").write_text(
        "server:\n  host: 0.0.0.0\n  port: 8123\n"
    )
    cli.main(["serve", "--config", str(config)])
    assert len(served) == 1
    assert (served[0]["host"], served[0]["port"]) == ("0.0.0.0", 8123)
    assert "WARNING" in capsys.readouterr().err


def test_serve_accepts_a_location_and_a_dataset_override(
    config, served, tmp_path
):
    target = tmp_path / "custom"
    args = ["serve", "--config", str(config)]
    args += ["--data-location", str(target), "--dataset", "mine"]
    assert cli.main(args) == 0
    assert (target / "mine" / "dataset.json").is_file()


def test_serve_refuses_an_invalid_dataset_name(config, served, capsys):
    args = ["serve", "--config", str(config), "--dataset", "Not Valid"]
    assert cli.main(args) == 1
    assert "not a valid dataset name" in capsys.readouterr().err
    assert served == []


def test_serve_names_the_new_keys_for_the_old_setting(config, served, capsys):
    (config / "data-collection.local.yaml").write_text("dataFolder: mine\n")
    assert cli.main(["serve", "--config", str(config)]) == 1
    err = capsys.readouterr().err
    assert "dataLocation" in err and "dataset" in err
    assert served == []


def test_the_old_data_folder_option_is_gone(config, served, capsys):
    with pytest.raises(SystemExit) as info:
        cli.main(["serve", "--config", str(config), "--data-folder", "x"])
    assert info.value.code == 2


def test_serve_warns_when_the_location_is_a_dataset(config, served, capsys):
    DatasetStore.open(config.parent / "data", create=True)
    assert cli.main(["serve", "--config", str(config)]) == 0
    assert "old layout" in capsys.readouterr().err


def test_no_command_prints_help(capsys):
    assert cli.main([]) == 0
    assert "serve" in capsys.readouterr().out


def test_startup_passes_the_mirror_setting_to_the_engine(config):
    on = build_application(config, open_camera=False)
    on.shutdown()
    assert on.engine._mirror is True
    (config / "data-collection.local.yaml").write_text("mirrorPreview: false\n")
    off = build_application(config, open_camera=False)
    off.shutdown()
    assert off.engine._mirror is False
