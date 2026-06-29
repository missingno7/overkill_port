"""Domain records for the native object-update driver (the VM-free runtime's per-frame pass).

The per-slot behaviours are pure functions of the slot record plus a small set of per-frame DS globals
(the view-anchor box, the global X bias, the tile-probe-suppress flag, the level tile context).  This
record carries those globals into the driver so it can advance the pool without reading VM memory.
"""
from __future__ import annotations

from dataclasses import dataclass

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
