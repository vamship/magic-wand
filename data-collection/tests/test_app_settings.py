from pathlib import Path

import pytest

from wand_collect.settings import (
    DataCollectionSettings,
    load_app_settings,
)
from wand_core.settings import SettingsError, validate

CONFIG = Path(__file__).parents[2] / "config"


def test_repository_config_matches_defaults():
    settings = load_app_settings(CONFIG)
    assert settings == DataCollectionSettings()
    assert settings.camera.width == 640
    assert settings.clip_padding.pre_s == 2.0
    assert settings.server.host == "127.0.0.1"


def test_local_override_for_the_data_location_and_the_dataset(tmp_path):
    (tmp_path / "data-collection.yaml").write_text(
        "dataLocation: data\ndataset: default\n"
    )
    (tmp_path / "data-collection.local.yaml").write_text(
        "dataLocation: /mnt/datasets\ndataset: ada\ncamera:\n  index: 1\n"
    )
    settings = load_app_settings(tmp_path)
    assert settings.data_location == "/mnt/datasets"
    assert settings.dataset == "ada"
    assert settings.camera.index == 1
    assert settings.camera.width == 640


def test_the_defaults_are_the_data_folder_and_a_default_dataset():
    settings = DataCollectionSettings()
    assert (settings.data_location, settings.dataset) == ("data", "default")


def test_the_old_data_folder_key_is_rejected_naming_the_new_keys(tmp_path):
    (tmp_path / "data-collection.yaml").write_text("dataFolder: data\n")
    with pytest.raises(SettingsError) as error:
        load_app_settings(tmp_path)
    assert "dataLocation" in str(error.value) and "dataset" in str(error.value)


@pytest.mark.parametrize("name", ["", "Ada", "has space", "a/b", "-x"])
def test_an_invalid_dataset_name_is_rejected(name):
    with pytest.raises(SettingsError, match="dataset"):
        validate(DataCollectionSettings, {"dataset": name})


def test_invalid_values_name_key():
    with pytest.raises(SettingsError, match="server.port"):
        validate(DataCollectionSettings, {"server": {"port": 0}})
    with pytest.raises(SettingsError, match="countdownS"):
        validate(DataCollectionSettings, {"countdownS": -1})


def test_the_preview_is_mirrored_by_default_and_the_option_is_read(tmp_path):
    assert DataCollectionSettings().mirror_preview is True
    (tmp_path / "data-collection.yaml").write_text("mirrorPreview: false\n")
    assert load_app_settings(tmp_path).mirror_preview is False


def test_reject_takes_one_key_or_a_list_of_keys(tmp_path):
    defaults = DataCollectionSettings().shortcuts
    assert defaults.reject == [" ", "r"]
    assert defaults.delete == "Backspace"
    (tmp_path / "data-collection.yaml").write_text(
        'shortcuts:\n  reject: "/"\n'
    )
    assert load_app_settings(tmp_path).shortcuts.reject == "/"
    (tmp_path / "data-collection.yaml").write_text(
        'shortcuts:\n  reject: ["/", x]\n'
    )
    assert load_app_settings(tmp_path).shortcuts.reject == ["/", "x"]
