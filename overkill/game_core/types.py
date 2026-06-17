"""Backend-agnostic value types for the OVERKILL native game core.

These types are the *vocabulary* the native game core and its platform backends
speak.  They are intentionally free of every emulation/platform detail:

* no CPU registers or flags,
* no segmented (DOS) memory or video-memory layout (B800/A000/Tandy banks),
* no DOS interrupts / BIOS,
* no SDL/pygame,
* no Tandy/EGA/CGA packing.

A logical frame is just a 2-D grid of palette indices plus an RGB palette; input
is logical buttons; assets are decoded blobs addressed by a neutral id.  The
*adapters* that bridge these to the VM (video-memory decoders, scancode sources,
OPL/PC-speaker sinks, overlay asset loaders) live elsewhere and depend on this
module, never the other way around.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Tuple

# An (R, G, B) colour, each channel 0..255.
RGB = Tuple[int, int, int]


@dataclass(frozen=True)
class Framebuffer:
    """A logical indexed-colour image ready to be shown by a VideoBackend.

    ``pixels`` holds ``width * height`` palette indices (one byte each, row-major,
    top-left origin); ``palette`` maps each index to an RGB colour.  This is the
    intended *logical* image (OVERKILL's reference is 320x200, 16 colours) — not a
    Tandy/EGA/CGA memory aperture.  Turning packed video memory into a Framebuffer
    is an adapter's job; turning a Framebuffer into on-screen pixels is the
    VideoBackend's job.
    """

    width: int
    height: int
    pixels: bytes
    palette: Tuple[RGB, ...]

    def __post_init__(self) -> None:
        if len(self.pixels) != self.width * self.height:
            raise ValueError(
                f"Framebuffer pixels length {len(self.pixels)} != "
                f"{self.width}*{self.height}={self.width * self.height}"
            )

    def index_at(self, x: int, y: int) -> int:
        return self.pixels[y * self.width + x]

    def rgb_at(self, x: int, y: int) -> RGB:
        return self.palette[self.index_at(x, y)]


class GameButton(Enum):
    """Logical, device-neutral game inputs.

    The core reasons about these abstract buttons; an InputBackend maps physical
    devices (keyboard scancodes, a gamepad, a demo script) onto them.  Names are
    deliberately conservative — the precise gameplay role of each action button
    is not asserted here, only that the game distinguishes a primary and a
    secondary action plus directions and a few UI controls.  The proven
    physical-key mapping currently lives in the VM scancode path, not here.
    """

    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"
    BUTTON_PRIMARY = "button_primary"
    BUTTON_SECONDARY = "button_secondary"
    PAUSE = "pause"
    CONFIRM = "confirm"
    CANCEL = "cancel"


@dataclass(frozen=True)
class InputEvent:
    """A single edge: ``button`` was pressed (True) or released (False)."""

    button: GameButton
    pressed: bool


class AssetKind(Enum):
    """Coarse, conservative classification of a decoded asset.

    Defaults to ``RAW`` because the exact semantic type of most OVERKILL assets
    is not proven; richer kinds are only used where evidence supports them.
    """

    RAW = "raw"
    IMAGE = "image"
    PALETTE = "palette"
    AUDIO = "audio"


# A neutral asset identifier.  OVERKILL addresses decoded assets by a numeric id
# in its asset table; an int keeps that faithful while staying platform-neutral.
AssetId = int


@dataclass(frozen=True)
class Asset:
    """A decoded game resource, free of container/codec/DOS-file details."""

    asset_id: AssetId
    data: bytes
    kind: AssetKind = AssetKind.RAW
    # Optional logical dimensions for image-like assets; None when not applicable
    # or not yet proven.
    width: int | None = None
    height: int | None = None
    metadata: dict[str, object] = field(default_factory=dict)
