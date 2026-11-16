"""Config loading + validation."""

from pathlib import Path

import pytest
import yaml

from carla_rig.config import ConfigError, dump_config, from_dict, load_config

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "config" / "default.yaml"


def default_dict():
    return yaml.safe_load(DEFAULT.read_text())


def test_default_config_loads():
    cfg = load_config(DEFAULT)
    assert cfg.world.fixed_delta_seconds == pytest.approx(0.05)
    assert cfg.input.source == "keyboard_mouse"
    assert cfg.camera.chase.x < 0  # chase cam sits behind the car


def test_bad_substep_combo_raises():
    d = default_dict()
    d["world"].update(fixed_delta_seconds=0.2, max_substep_delta_time=0.01, max_substeps=10)
    with pytest.raises(ConfigError, match="max_substep_delta_time"):
        from_dict(d)


def test_substep_combo_at_exact_limit_is_ok():
    d = default_dict()
    d["world"].update(fixed_delta_seconds=0.1, max_substep_delta_time=0.01, max_substeps=10)
    from_dict(d)


def test_max_substeps_over_carla_limit_raises():
    d = default_dict()
    d["world"]["max_substeps"] = 17
    with pytest.raises(ConfigError, match="max_substeps"):
        from_dict(d)


def test_unknown_key_raises():
    d = default_dict()
    d["world"]["fixed_delta_second"] = 0.05  # typo
    with pytest.raises(ConfigError, match="unknown key"):
        from_dict(d)


def test_wrong_type_raises():
    d = default_dict()
    d["server"]["port"] = "2000"
    with pytest.raises(ConfigError, match="server.port"):
        from_dict(d)


def test_bool_is_not_accepted_as_int():
    d = default_dict()
    d["server"]["port"] = True
    with pytest.raises(ConfigError):
        from_dict(d)


def test_bad_input_source_raises():
    d = default_dict()
    d["input"]["source"] = "joystick"
    with pytest.raises(ConfigError, match="input.source"):
        from_dict(d)


def test_blinker_thresholds_order_enforced():
    d = default_dict()
    d["control"].update(blinker_cancel_arm_threshold=0.1, blinker_cancel_center_threshold=0.2)
    with pytest.raises(ConfigError, match="threshold"):
        from_dict(d)


def test_no_rendering_mode_rejected():
    d = default_dict()
    d["world"]["no_rendering_mode"] = True
    with pytest.raises(ConfigError, match="no_rendering_mode"):
        from_dict(d)


def test_zero_delta_rejected():
    d = default_dict()
    d["world"]["fixed_delta_seconds"] = 0
    with pytest.raises(ConfigError, match="fixed_delta_seconds"):
        from_dict(d)


def test_missing_file_raises(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.yaml")


def test_partial_config_uses_defaults():
    cfg = from_dict({"world": {"map": "Town03"}})
    assert cfg.world.map == "Town03"
    assert cfg.server.port == 2000


def test_dump_roundtrip(tmp_path):
    cfg = load_config(DEFAULT)
    out = tmp_path / "resolved.yaml"
    dump_config(cfg, out)
    assert load_config(out) == cfg
