"""The seam between the recovered model and the native presentation backend.

A :class:`RenderSnapshot` is one *game-tick* of **semantic render-state** produced
by the runtime/bridge — NOT a pre-rendered RGB frame. The native backend owns the
actual rendering: it receives indexed (palette-independent) layers + the palette +
semantic object/scroll state, and colorizes/composes/interpolates itself, with
caches, presenting at the display cadence. Everything here is plain data — no VM,
no pygame — so the seam is testable and the backend never reaches into the emulator.

Tailored to OVERKILL: the playfield is the composited source page ``[9598]`` decoded
to 4-bit indices (the L1, palette-independent layer); the backend colorizes it via
the palette (L2, keyed by ``palette_version``) and caches the colorized frame by
``(playfield_version, palette_version)`` so the held presents at high refresh hit
the cache. Sprites are carried semantically for future object interpolation; the
HUD/page-baked chrome is a separate persisted layer (added as it is lifted).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Optional, Tuple

if TYPE_CHECKING:  # avoid importing numpy/domain at module import for the core runner
    import numpy as np
    from overkill.recovered.domain.frame_snapshot import FrameSnapshot, SpriteDraw

RGB = Tuple[int, int, int]


class SceneKind(Enum):
    """Which kind of screen a snapshot represents (drives layer composition)."""

    GAMEPLAY = "gameplay"
    MENU = "menu"
    TITLE = "title"
    TALLY = "tally"
    TRANSITION = "transition"
    OTHER = "other"


@dataclass(frozen=True, eq=False)
class SpriteBlock:
    """One decoded sprite-compositor block, drawn by the native sprite layer at ``di``
    (offset from the present cursor).

    ``kind`` selects the composite op:

    * ``"mask"`` (default) — a masked sprite: ``pixels`` are the indexed colours, ``opaque``
      the where-it-draws mask; the layer does opaque-replace (2E6E/2F81/2FB6).
    * ``"or_inverted"`` — a 2F40/2ECB OR-inverted block: ``pixels`` holds the per-pixel OR
      *delta* (``0xF ^ src``) and the layer ORs it into the background (``opaque`` is unused,
      kept full-True for shape). This op is background-dependent, so draw order matters."""

    di: int
    pixels: "np.ndarray"   # (h, w) uint8 colour indices, or the OR delta for kind="or_inverted"
    opaque: "np.ndarray"   # (h, w) bool
    kind: str = "mask"


@dataclass(frozen=True, eq=False)
class SnapshotSprite:
    """One on-screen object's drawable sprite: stable identity (so its position
    interpolates between source ticks), sprite id / animation phase (texture cache
    key), the reference destination ``screen_di``, and its decoded texture
    block(s). Produced by the sprite-draw extractor; the native sprite layer draws
    the blocks, the interpolator shifts them by the object's per-tick motion."""

    identity: int
    sprite_id: int
    anim_phase: int
    screen_di: int
    blocks: "Tuple[SpriteBlock, ...]"


@dataclass(frozen=True, eq=False)
class RenderSnapshot:
    """One game-tick of semantic render-state the backend renders (and interpolates).

    ``composed_indices`` is the palette-independent ``(200,320)`` uint8 indexed
    image — the game's composed page (background + HUD/chrome + baked sprites)
    decoded by the extractor; the backend colorizes it for the faithful baseline.
    ``composed_version`` is its content id (drives the colorize cache).
    ``palette``/``palette_version`` are the current 16-colour palette + its id (for
    OVERKILL the palette is fixed, so ``palette_version`` is constant — but the model
    carries it so fades/cache-invalidation work). ``scroll_cursor`` is the present
    source cursor (the monotonic camera scroll).

    ``playfield_indices`` is the optional *scrolling playfield sublayer* (the source
    page ``[9598]`` alone, ``x∈[0,208), y∈[4,196)``); it is carried for camera/object
    interpolation (Stage 3+), overlaid on ``composed_indices`` only when interpolation
    is on. ``sprites`` is the semantic object list (future per-object interpolation);
    ``snapshot`` keeps the full recovered model for reference/debug.
    """

    frame_id: int
    timestamp: float
    scene_kind: SceneKind
    composed_indices: "np.ndarray"
    composed_version: int
    palette: Tuple[RGB, ...]
    palette_version: int
    scroll_cursor: int
    playfield_indices: "Optional[np.ndarray]" = None
    playfield_version: int = 0
    sprites: "Tuple[SpriteDraw, ...]" = ()
    frame_sprites: "Tuple[SnapshotSprite, ...]" = ()
    snapshot: "Optional[FrameSnapshot]" = None


@dataclass(frozen=True, eq=False)
class PresentedFrame:
    """What the backend hands the display for one present (one monitor refresh).

    ``rgb`` is the ``(200, 320, 3)`` rendered image. ``source_frame_id`` / ``alpha``
    describe which source snapshot(s) it derives from (``alpha`` is the interpolation
    fraction toward the next snapshot, 0.0 when held). ``from_cache`` is true when the
    colorized result was served from the render cache (a held present)."""

    rgb: "np.ndarray"
    source_frame_id: int
    alpha: float = 0.0
    held: bool = True
    from_cache: bool = False


@dataclass(frozen=True)
class BackendConfig:
    """The native backend's persisted settings (whether the native backend is used
    at all is the ``play.py --backend vm|native`` selector's job, not a field here).

    These are the toggles the in-game settings overlay flips and saves to the
    config file (``native_video/config.py``). The default is conservative: faithful
    passthrough, no interpolation, no VM-framebuffer fallback."""

    camera_interpolation: bool = False
    object_interpolation: bool = False
    smooth_palette_fades: bool = False
    smooth_transitions: bool = False
    cache_diagnostics: bool = False
    debug_compare: bool = False
    present_vsync: bool = True
    target_present_hz: Optional[int] = None


@dataclass
class BackendDiagnostics:
    """Live presentation diagnostics (rules: every interpolation/cache decision must
    be visible here, no silent fallback)."""

    source_fps: float = 0.0           # source tick rate
    present_fps: float = 0.0          # present rate
    native_render_ms: float = 0.0     # total render time for the last present
    colorize_ms: float = 0.0          # palette colorize cost
    texture_upload_ms: float = 0.0    # SDL/pygame upload cost (display adapter)
    cache_hits: int = 0
    cache_misses: int = 0
    frame_hold_count: int = 0
    interpolation_alpha: float = 0.0
    source_snapshot_age_ms: float = 0.0
    camera_interpolation_active: bool = False
    object_interpolation_active: bool = False
    interpolated_objects: int = 0
    snapped_objects: int = 0
    compare_diff: Optional[float] = None
