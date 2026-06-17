"""Pure, headless reference adapters for the game-core backend protocols.

These exist for three reasons:

* they prove each :mod:`overkill.game_core.backends` protocol is actually
  satisfiable without any platform/VM dependency,
* they give the native core something deterministic to run against in tests and
  headless verification,
* they document the minimal contract each backend must meet.

Everything here is stdlib-only and platform-neutral — the same purity rule the
protocols carry.  They record the last interaction so tests can assert on it.
"""
from __future__ import annotations

from collections import deque
from typing import Deque, Dict, List, Sequence

from .types import Asset, AssetId, Framebuffer, GameButton, InputEvent


class NullVideoBackend:
    """Discards frames but counts them and keeps the most recent one."""

    def __init__(self) -> None:
        self.frames_presented = 0
        self.last_frame: Framebuffer | None = None

    def present(self, frame: Framebuffer) -> None:
        self.frames_presented += 1
        self.last_frame = frame


class ScriptedInputBackend:
    """Replays a fixed list of input edges; tracks held buttons.

    With an empty script this is a perfectly good "no input" backend; with a
    script it is a deterministic stand-in for a keyboard or demo player.
    """

    def __init__(self, script: Sequence[InputEvent] | None = None) -> None:
        self._queue: Deque[InputEvent] = deque(script or ())
        self._held: set[GameButton] = set()

    def poll(self) -> Sequence[InputEvent]:
        drained: List[InputEvent] = list(self._queue)
        self._queue.clear()
        for event in drained:
            if event.pressed:
                self._held.add(event.button)
            else:
                self._held.discard(event.button)
        return drained

    def is_pressed(self, button: GameButton) -> bool:
        return button in self._held

    def feed(self, event: InputEvent) -> None:
        self._queue.append(event)


class NullAudioBackend:
    """Drops all audio but records the latest tone/register for assertions."""

    def __init__(self) -> None:
        self.tone_hz: float | None = None
        self.music_writes: List[tuple[int, int]] = []

    def set_tone(self, frequency_hz: float) -> None:
        self.tone_hz = frequency_hz

    def stop_tone(self) -> None:
        self.tone_hz = None

    def write_music_register(self, register: int, value: int) -> None:
        self.music_writes.append((register & 0xFF, value & 0xFF))


class ManualTimingBackend:
    """A deterministic clock advanced by ``wait_next_frame`` (never sleeps).

    Ideal for tests and headless verification: time only moves when the core
    asks for the next frame, so runs are reproducible and instant.
    """

    def __init__(self, frame_hz: float = 1193182.0 / 0x4000) -> None:
        self._frame_hz = frame_hz
        self._period = 1.0 / frame_hz if frame_hz > 0 else 0.0
        self._now = 0.0
        self.frames_waited = 0

    @property
    def frame_hz(self) -> float:
        return self._frame_hz

    def monotonic_seconds(self) -> float:
        return self._now

    def wait_next_frame(self) -> None:
        self._now += self._period
        self.frames_waited += 1


class InMemoryAssetProvider:
    """A dict-backed asset source — the decode/container layer already done."""

    def __init__(self, assets: Dict[AssetId, Asset] | None = None) -> None:
        self._assets: Dict[AssetId, Asset] = dict(assets or {})

    def has(self, asset_id: AssetId) -> bool:
        return asset_id in self._assets

    def load(self, asset_id: AssetId) -> Asset:
        return self._assets[asset_id]

    def add(self, asset: Asset) -> None:
        self._assets[asset.asset_id] = asset
