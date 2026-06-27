"""The seam between the recovered model and the native presentation backend.

A :class:`NativeSourceFrame` is one *source-frame* of presentation input produced
by the runtime/bridge at the game cadence. The native backend consumes a stream of
these and presents at the display cadence (holding or interpolating between them).
Everything here is plain data — no VM, no pygame — so the seam is testable and the
backend never reaches back into the emulator.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:  # avoid importing numpy/domain at module import for the core runner
    import numpy as np
    from overkill.recovered.domain.frame_snapshot import FrameSnapshot


@dataclass(frozen=True, eq=False)
class NativeSourceFrame:
    """One game-cadence source frame the backend presents (and interpolates).

    ``frame_id`` is a monotonic source-frame index; ``timestamp`` is the wall-clock
    time the runtime produced it (seconds). ``playfield_rgb`` is the faithful
    decoded playfield baseline (``(200, 320, 3)`` uint8, HUD region black — see
    ``page_raster``). ``snapshot`` is the semantic model (sprite identities/
    positions, camera, present cursor) the backend uses for optional interpolation;
    ``source_cursor`` is hoisted out for cheap camera-scroll interpolation.
    """

    frame_id: int
    timestamp: float
    playfield_rgb: "np.ndarray"
    source_cursor: int
    snapshot: "Optional[FrameSnapshot]" = None


@dataclass(frozen=True, eq=False)
class PresentedFrame:
    """What the backend hands the display for one present (one monitor refresh).

    ``rgb`` is the ``(200, 320, 3)`` image to blit. ``source_frame_id`` /
    ``alpha`` describe which source frame(s) it derives from (``alpha`` is the
    interpolation fraction toward the next source frame, 0.0 when held).
    """

    rgb: "np.ndarray"
    source_frame_id: int
    alpha: float = 0.0
    held: bool = True


@dataclass(frozen=True)
class BackendConfig:
    """The native backend's persisted settings (whether the native backend is used
    at all is the ``play.py --backend vm|native`` selector's job, not a field here).

    These are the toggles the in-game settings overlay flips and saves to the
    config file (``native_video/config.py``). The default is conservative: faithful
    passthrough, no interpolation, no VM-framebuffer fallback. ``present_vsync`` /
    ``target_present_hz`` drive the presentation clock (``None`` = follow the
    monitor refresh)."""

    camera_interpolation: bool = False
    object_interpolation: bool = False
    smooth_palette_fades: bool = False
    debug_compare: bool = False
    present_vsync: bool = True
    target_present_hz: Optional[int] = None


@dataclass
class BackendDiagnostics:
    """Live presentation diagnostics (rules: every interpolation decision must be
    visible here, no silent fallback)."""

    source_fps: float = 0.0
    present_fps: float = 0.0
    frame_hold_count: int = 0
    interpolation_alpha: float = 0.0
    source_snapshot_age_ms: float = 0.0
    camera_interpolation_active: bool = False
    object_interpolation_active: bool = False
    interpolated_objects: int = 0
    snapped_objects: int = 0
    native_render_ms: float = 0.0
    compare_diff: Optional[float] = None
