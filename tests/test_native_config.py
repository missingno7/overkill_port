"""The native backend's persisted settings round-trip and stay compatible."""
from __future__ import annotations

import json

from overkill.native_video.config import (
    config_from_dict,
    default_config_path,
    load_config,
    save_config,
)
from overkill.native_video.frame import BackendConfig


def test_round_trip(tmp_path):
    path = tmp_path / "native_video.json"
    cfg = BackendConfig(camera_interpolation=True, object_interpolation=True, target_present_hz=240)
    save_config(cfg, path)
    assert load_config(path) == cfg


def test_missing_file_returns_defaults(tmp_path):
    assert load_config(tmp_path / "absent.json") == BackendConfig()


def test_unknown_keys_ignored_and_missing_defaulted():
    # forward/backward compatible: a future/extra key is dropped, missing -> default
    cfg = config_from_dict({"camera_interpolation": True, "a_future_setting": 99})
    assert cfg.camera_interpolation is True
    assert cfg.object_interpolation is False  # defaulted


def test_corrupt_file_falls_back_loudly(tmp_path, capsys):
    path = tmp_path / "native_video.json"
    path.write_text("{not valid json", encoding="utf-8")
    cfg = load_config(path)
    assert cfg == BackendConfig()
    assert "ignoring unreadable config" in capsys.readouterr().out


def test_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("OVERKILL_CONFIG_DIR", str(tmp_path))
    assert default_config_path() == tmp_path / "native_video.json"


def test_saved_file_is_plain_json(tmp_path):
    path = tmp_path / "native_video.json"
    save_config(BackendConfig(debug_compare=True), path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["debug_compare"] is True
    assert "camera_interpolation" in data
