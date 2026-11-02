from pathlib import Path

import pytest

from wand_core.settings import (
    MotionSettings,
    SettingsError,
    VisionSettings,
    WorkingSettings,
    load_motion,
    load_profile,
    load_settings,
    load_vision,
    read_yaml,
    resolve_settings,
    save_profile,
    save_settings,
    validate,
)

CONFIG = Path(__file__).parents[2] / "config"


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_repository_config_loads_and_matches_defaults():
    assert load_vision(CONFIG) == VisionSettings()
    assert load_motion(CONFIG) == MotionSettings()


def test_camel_case_file_gives_snake_case_attributes(tmp_path):
    path = write(tmp_path / "motion.yaml", "startSpeed: 0.5\nendSpeed: 0.2\n")
    motion = load_settings(MotionSettings, path)
    assert motion.start_speed == 0.5
    assert motion.end_speed == 0.2
    assert motion.min_duration_s == 0.3  # default


def test_negative_speed_names_key():
    with pytest.raises(SettingsError, match="startSpeed"):
        validate(MotionSettings, {"startSpeed": -1})


def test_end_speed_above_start_speed_names_keys():
    with pytest.raises(SettingsError, match="endSpeed.*startSpeed"):
        validate(MotionSettings, {"startSpeed": 0.2, "endSpeed": 0.3})


def test_wrong_type_and_unknown_key_name_key():
    with pytest.raises(SettingsError, match="hueCenter"):
        validate(VisionSettings, {"hueCenter": "orange"})
    with pytest.raises(SettingsError, match="hueCentre"):
        validate(VisionSettings, {"hueCentre": 5})


def test_hue_out_of_range_names_key():
    with pytest.raises(SettingsError, match="hueCenter"):
        validate(VisionSettings, {"hueCenter": 200})


def test_assignment_is_validated():
    vision = VisionSettings()
    with pytest.raises(ValueError):
        vision.sat_min = 300


def test_local_override_replaces_only_given_keys(tmp_path):
    path = write(tmp_path / "vision.yaml", "hueCenter: 20\nsatMin: 100\n")
    write(tmp_path / "vision.local.yaml", "hueCenter: 90\n")
    vision = load_settings(VisionSettings, path)
    assert vision.hue_center == 90
    assert vision.sat_min == 100


def test_save_then_read_round_trips_with_camel_keys(tmp_path):
    original = VisionSettings(hue_center=100, min_roundness=0.8)
    path = tmp_path / "vision.yaml"
    save_settings(original, path)
    assert "hueCenter: 100" in path.read_text()
    assert "hue_center" not in path.read_text()
    assert load_settings(VisionSettings, path) == original


def test_read_yaml_errors(tmp_path):
    with pytest.raises(SettingsError, match="cannot read"):
        read_yaml(tmp_path / "missing.yaml")
    with pytest.raises(SettingsError, match="not valid YAML"):
        read_yaml(write(tmp_path / "bad.yaml", "a: [1, 2"))
    with pytest.raises(SettingsError, match="mapping"):
        read_yaml(write(tmp_path / "list.yaml", "- 1\n- 2\n"))
    assert read_yaml(write(tmp_path / "empty.yaml", "")) == {}


def test_resolve_defaults_then_profile(tmp_path):
    write(tmp_path / "vision.yaml", "hueCenter: 30\n")
    write(tmp_path / "motion.yaml", "startSpeed: 0.4\n")
    defaults = resolve_settings(tmp_path)
    assert defaults.vision.hue_center == 30
    assert defaults.motion.start_speed == 0.4

    profile = WorkingSettings(
        vision=VisionSettings(hue_center=60), motion=MotionSettings()
    )
    save_profile(tmp_path, "desk", profile)
    assert load_profile(tmp_path, "desk") == profile
    resolved = resolve_settings(tmp_path, profile="desk")
    assert resolved == profile  # replaces, does not merge with defaults


def test_profile_errors(tmp_path):
    with pytest.raises(SettingsError, match="not found"):
        load_profile(tmp_path, "nope")
    with pytest.raises(SettingsError, match="invalid profile name"):
        save_profile(tmp_path, "../evil", WorkingSettings())
