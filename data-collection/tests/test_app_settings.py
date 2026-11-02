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


def test_local_override_for_data_folder(tmp_path):
    (tmp_path / "data-collection.yaml").write_text("dataFolder: data\n")
    (tmp_path / "data-collection.local.yaml").write_text(
        "dataFolder: /mnt/datasets\ncamera:\n  index: 1\n"
    )
    settings = load_app_settings(tmp_path)
    assert settings.data_folder == "/mnt/datasets"
    assert settings.camera.index == 1
    assert settings.camera.width == 640


def test_invalid_values_name_key():
    with pytest.raises(SettingsError, match="server.port"):
        validate(DataCollectionSettings, {"server": {"port": 0}})
    with pytest.raises(SettingsError, match="countdownS"):
        validate(DataCollectionSettings, {"countdownS": -1})
