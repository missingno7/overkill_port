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
    ``object_type`` is kept for classification/animation lookups; ``screen_di``
    is the projected destination the present pass wrote (object record +0C, the
    layer scan's ``OBJ_DEST_SLOT_0C``) — a VRAM offset encoding the on-screen
    position. Off-screen objects (``screen_di == 0xFFFF``) are culled and never
    appear in the draw list.
    """

    sprite: int
    x: int
    y: int
    layer: int
    object_type: int
    screen_di: int


@dataclass(frozen=True, slots=True)
class CameraState:
    """The view origin the sprites are projected against (world space)."""

    x: int
    y: int


@dataclass(frozen=True, slots=True)
class PlayfieldLayer:
    """The scrolling action area: the camera + the sprite draw list.

    This is the layer the enhanced renderer **interpolates** — sprites move and
    the camera scrolls between source frames (`enhanced_renderer_plan.md` R4).
    Drawn by the 5AC8 object scan.
    """

    camera: CameraState
    sprites: tuple[SpriteDraw, ...]


@dataclass(frozen=True, slots=True)
class BackgroundLayer:
    """The scrolling level background — bottom of the stack.

    OVERKILL **pre-renders** the level into the ``[9592]`` work plane (tiles are
    materialised into it as the level scrolls); the per-frame present just copies
    that plane to the framebuffer scrolled by ``scroll_row`` (DS:2350). So the
    background *content* is the ``[9592]`` plane (already rasterised) — NOT a
    per-frame tile grid — and the renderer reuses it, interpolating only the
    scroll. ``scroll_row`` is the scroll offset into the plane (it tracks level
    progress, slow-changing); ``column_index`` (DS:2356) is the current map
    column. Note: the background often holds still while the *objects* move (the
    interpolation then rides on the playfield, not the scroll).
    """

    scroll_row: int
    column_index: int


@dataclass(frozen=True, slots=True)
class HudLayer:
    """The status panel — a separate, fixed render region (NOT interpolated).

    Drawn by the 1010:61DC status display as six status-counter cells
    (DS:2368..2372). It does not scroll and must not be lerped; the renderer
    composites it over the playfield as a discrete overlay. ``score_bcd`` is the
    packed-decimal score (DS:2314 low word, DS:2316 high word; e.g. 0x0990,0x0003
    = 30990).
    """

    counters: tuple[int, ...]
    score_bcd: tuple[int, int]


@dataclass(frozen=True, slots=True)
class FrameSnapshot:
    """One source-frame's render intent, split into clean layers.

    The visual stack, bottom to top: ``background`` (scrolling tilemap) →
    ``playfield`` (action sprites + camera) → ``hud`` (fixed status overlay).
    Background and playfield are interpolated (they scroll/move); the HUD is
    composited as-is. Grows toward the full contract (palette, tile grid,
    screen-shake) as each piece is recovered.
    """

    background: BackgroundLayer
    playfield: PlayfieldLayer
    hud: HudLayer
