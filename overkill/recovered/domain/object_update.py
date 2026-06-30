"""Domain records for the native object-update driver (the VM-free runtime's per-frame pass).

The per-slot behaviours are pure functions of the slot record plus a small set of per-frame DS globals
(the view-anchor box, the global X bias, the tile-probe-suppress flag, the level tile context).  This
record carries those globals into the driver so it can advance the pool without reading VM memory.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from overkill.recovered.domain.object_slots import ObjectPool
from overkill.recovered.domain.tilemap import LevelTileContext


@dataclass(frozen=True, slots=True)
class ObjectUpdateGlobals:
    """Per-frame globals the native object-update handlers consume (projected once per frame).

    ``ref_box_x``/``ref_box_y`` are the DS:237E/2380 view-anchor box (the B250 overlap reference and
    the 5E1B/edge-steer target); ``a278`` is the DS:A278 global X bias the AD5A tail adds; ``tile_probe
    _suppressed`` is the DS:BDAC flag (true suppresses the AD60 tile probe); ``tiles`` is the level
    tile context the tile probe samples.  These are the only non-slot inputs AE09/AED8 need.
    """

    ref_box_x: int
    ref_box_y: int
    a278: int
    tile_probe_suppressed: bool
    tiles: LevelTileContext
    # B86D movement + BC4B post-move extras (default-safe: AE09/AED8 do not consume them).
    ref_box_scan: int = 0          # DS:237C+14 view-anchor scan flag (5E1B pad selector)
    a47e: int = 0                  # DS:A47E early-global guard (<=2 -> B8F8 edge-steer)
    a7a0: int = 0                  # DS:A7A0 phase gate (<0x28 -> the A7A0 5DB2 seek)
    vertical_delta: int = 0        # DS:2342 global vertical delta (fall-through drift)
    phase_2328: int = 0            # DS:2328 phase word (==7 -> +1 X nudge)
    step_mode: int = 0             # DS:2312 5E42 step mode
    direction_table: tuple = ()    # DS:A348 16-byte direction-bits -> direction map
    global_disable: int = 0        # DS:A47C BC4B X-bounds gate / contact-path gate
    # B9F0 movement extras (default-safe: AE09/AED8/B86D do not consume them).
    a482: int = 0                  # DS:A482 (== A4E4h -> the movement paths, else sprite-refresh)
    frame_233c: int = 0            # DS:233C global frame -> the BA67 sprite refresh
    horizontal_delta: int = 0      # DS:2346 global X delta added to target_x (+34)
    difficulty: int = 0            # DS:BEDC difficulty -> periodic-helper tick mask
    tick: int = 0                  # DS:2340 tick counter for the periodic BA5A helper
    anim_2326: int = 0             # DS:2326 animation counter (AE2C folds bit 1 into its sprite)
    # BC4B contact-scan inputs (default-safe: only B86D/B9F0 consume them, and only when provided).
    # When ``candidate_pool`` is None the driver leaves the collision death to the VM (the current
    # snapshot behaviour); when given, B86D/B9F0 fold the moving-object collision death/damage in.
    candidate_pool: "ObjectPool | None" = None  # the gameplay pool (DS:2B5C) the 62F6 scan walks
    a8c2_boss_mode: bool = False    # DS:A8C2 == 1 (final-boss gate in the BEC5 reaction)
    bedc: int = 0                   # DS:BEDC difficulty (the BF25 damage-chain extra decrements)
    # B2CD waypoint-seek extras (default-safe: only B2CD consumes them).  ``scroll`` aliases DS:2350 =
    # ``tiles.row_base_word`` and ``bdac`` is ``1 if tile_probe_suppressed`` -- both reused, not re-added.
    level: int = 0                 # DS:2356 current level (B2CD sprite-table selector + seek mode)
    # (ds_off)->word: reads a DS word for B2CD's +0x36 waypoint walk; None -> leave B2CD to the VM.
    waypoint_word_reader: Callable[[int], int] | None = None
