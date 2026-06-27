"""Persisted settings for the native backend.

The native backend owns its own config file so the user does not need a wall of
``play.py`` flags: ``play.py --backend native`` launches it, and everything else
(interpolation, vsync, …) is toggled in the in-game settings overlay, which saves
back here. The file is plain JSON keyed by :class:`BackendConfig` field name;
unknown keys are ignored and missing keys fall back to the conservative defaults,
so the file stays forward/backward compatible as settings are added.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, fields
from pathlib import Path
from typing import Optional

from overkill.native_video.frame import BackendConfig

CONFIG_FILENAME = "native_video.json"
_ENV_OVERRIDE = "OVERKILL_CONFIG_DIR"


def default_config_path() -> Path:
    """The standard per-user config-file location (overridable via
    ``OVERKILL_CONFIG_DIR``)."""
    override = os.environ.get(_ENV_OVERRIDE)
    if override:
        return Path(override) / CONFIG_FILENAME
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA") or str(Path.home())
        return Path(root) / "overkill" / CONFIG_FILENAME
    return Path.home() / ".config" / "overkill" / CONFIG_FILENAME


def config_from_dict(data: dict) -> BackendConfig:
    """Build a :class:`BackendConfig` from a dict, ignoring unknown keys and
    defaulting missing ones."""
    known = {f.name for f in fields(BackendConfig)}
    kwargs = {k: v for k, v in data.items() if k in known}
    return BackendConfig(**kwargs)


def load_config(path: Optional[Path] = None) -> BackendConfig:
    """Load settings from ``path`` (default location if omitted).

    A missing file returns the conservative defaults (normal first run). A present
    but unreadable/corrupt file is reported loudly and falls back to defaults —
    visible, never silent.
    """
    path = path or default_config_path()
    if not path.is_file():
        return BackendConfig()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("config root is not an object")
        return config_from_dict(data)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"native_video: ignoring unreadable config {path} ({exc}); using defaults", flush=True)
        return BackendConfig()


def save_config(config: BackendConfig, path: Optional[Path] = None) -> Path:
    """Persist ``config`` as JSON (creating the directory). Returns the path."""
    path = path or default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(config), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
