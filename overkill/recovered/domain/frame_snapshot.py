"""Reconstructed semantic frame-render state — the render *intent*, VM-free.

This is the semantic layer the enhanced renderer and frame interpolation consume:
*what* to draw (sprites + their world positions, the camera, later the palette /
tilemap / shake) — independent of the original VRAM. It is the declared merge
target the render/object islands collapse into. See
`docs/overkill/enhanced_renderer_plan.md`.

Pure dataclasses, no VM. The byte-level extraction from live memory lives in the
bridge (`recovered/adapters/frame_snapshot_adapter.py`); the renderer/interpolator
consume only these records.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SpriteDraw:
    """One on-screen sprite's draw intent (world space).

    Reconstructed from an object slot: ``sprite`` is the object record's
    sprite/state id (offset +08) which maps to a bitmap + animation frame;
    ``x``/``y`` are the signed world coordinates; ``layer`` orders the draw;
    ``object_type`` is kept for classification/animation lookups.
    """

    sprite: int
    x: int
    y: int
    layer: int
    object_type: int


@dataclass(frozen=True, slots=True)
class CameraState:
    """The view origin the sprites are projected against (world space)."""

    x: int
    y: int


@dataclass(frozen=True, slots=True)
class FrameSnapshot:
    """One source-frame's render intent: camera + the sprite draw list.

    Grows toward the full render contract (palette, tilemap/scroll, screen-shake)
    as each piece is recovered and grounded. Two consecutive snapshots are what
    the enhanced renderer interpolates between (`enhanced_renderer_plan.md` R4).
    """

    camera: CameraState
    sprites: tuple[SpriteDraw, ...]
