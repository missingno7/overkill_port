"""Backend-agnostic OVERKILL native game core.

This package defines the platform-neutral seam between a future source-like game
core and the concrete backends that realise it.  It contains:

* :mod:`overkill.game_core.types` -- neutral value types (Framebuffer, GameButton,
  InputEvent, Asset, ...),
* :mod:`overkill.game_core.backends` -- the five backend protocols (ports):
  :class:`~overkill.game_core.backends.VideoBackend`,
  :class:`~overkill.game_core.backends.InputBackend`,
  :class:`~overkill.game_core.backends.AudioBackend`,
  :class:`~overkill.game_core.backends.TimingBackend`,
  :class:`~overkill.game_core.backends.AssetProvider`,
* :mod:`overkill.game_core.null_backends` -- pure headless reference adapters.

Nothing in this package may import the VM, DOS, SDL/pygame, or reference
video-memory layout: exactness is preserved by the existing VM/oracle system,
which lives behind *adapters* that implement these protocols, not inside them.
"""
from __future__ import annotations

from .backends import (
    AssetProvider,
    AudioBackend,
    InputBackend,
    TimingBackend,
    VideoBackend,
)
from .types import (
    RGB,
    Asset,
    AssetId,
    AssetKind,
    Framebuffer,
    GameButton,
    InputEvent,
)

__all__ = [
    "VideoBackend",
    "InputBackend",
    "AudioBackend",
    "TimingBackend",
    "AssetProvider",
    "RGB",
    "Framebuffer",
    "GameButton",
    "InputEvent",
    "Asset",
    "AssetId",
    "AssetKind",
]
