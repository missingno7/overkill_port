"""Backend protocols (ports) for the OVERKILL native game core.

These ``Protocol`` definitions are the seam between a future backend-agnostic
native game core and the concrete platform adapters that realise it (SDL window,
keyboard, nuked-OPL3 / PC-speaker audio, wall-clock timing, overlay asset
loader, or — crucially — the existing VM/oracle adapters used to keep behaviour
exact).

A protocol here MUST stay platform-neutral.  None of these methods may expose:

* CPU registers or flags,
* segmented / video memory or its Tandy/EGA/CGA layout,
* DOS interrupts / BIOS,
* SDL / pygame types.

They speak only in :mod:`overkill.game_core.types` vocabulary.  Because they are
``runtime_checkable`` Protocols, an adapter satisfies them structurally — no
inheritance required — so the VM-backed adapters and the pure null adapters are
interchangeable from the core's point of view.
"""
from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from .types import Asset, AssetId, Framebuffer, GameButton, InputEvent


@runtime_checkable
class VideoBackend(Protocol):
    """Sink for finished logical frames."""

    def present(self, frame: Framebuffer) -> None:
        """Display ``frame``.  Called once per presented game frame."""
        ...


@runtime_checkable
class InputBackend(Protocol):
    """Source of logical game input."""

    def poll(self) -> Sequence[InputEvent]:
        """Return the input edges that occurred since the last poll, in order."""
        ...

    def is_pressed(self, button: GameButton) -> bool:
        """Return whether ``button`` is currently held down."""
        ...


@runtime_checkable
class AudioBackend(Protocol):
    """Sink for the game's two independent audio paths.

    OVERKILL drives sound effects through the PC speaker (a single square-wave
    tone) and music through an optional AdLib/Roland card (OPL register writes).
    The backend decides how — or whether — to realise either; it may synthesise,
    forward to hardware, or stay silent.
    """

    def set_tone(self, frequency_hz: float) -> None:
        """Start/retune the PC-speaker sound-effect tone."""
        ...

    def stop_tone(self) -> None:
        """Silence the PC-speaker sound-effect tone."""
        ...

    def write_music_register(self, register: int, value: int) -> None:
        """Apply one music-chip (OPL) register write from the music driver."""
        ...


@runtime_checkable
class TimingBackend(Protocol):
    """Frame pacing and a monotonic clock.

    One ``wait_next_frame`` corresponds to one logical game tick — the role the
    PIT-paced ``1010:0679`` timer wait plays inside the VM.
    """

    @property
    def frame_hz(self) -> float:
        """Nominal logical frames per second."""
        ...

    def monotonic_seconds(self) -> float:
        """A monotonic time source in seconds (need not be wall-clock)."""
        ...

    def wait_next_frame(self) -> None:
        """Block until the next logical frame boundary is due."""
        ...


@runtime_checkable
class AssetProvider(Protocol):
    """Source of decoded game assets, addressed by neutral id."""

    def has(self, asset_id: AssetId) -> bool:
        """Return whether ``asset_id`` can be provided."""
        ...

    def load(self, asset_id: AssetId) -> Asset:
        """Return the decoded :class:`~overkill.game_core.types.Asset`.

        Implementations raise ``KeyError`` for an unknown id.
        """
        ...
