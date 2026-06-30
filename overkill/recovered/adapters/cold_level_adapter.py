"""Adapter: build the recovered tile-probe context from a cold-loaded NativeLevel.

This is the bridge from the VM-free level data load (``asset_codecs.load_native_level`` ->
:class:`~overkill.asset_codecs.native_level.NativeLevel`) to the recovered tile-probe domain
(:class:`~overkill.recovered.domain.tilemap.LevelTileContext`).  The static halves -- the byte-exact
tile plane (the VM's ``CS:[9592]`` grid) and class table (``DS:C3AA``) -- come straight from the cold
``NativeLevel``; the scroll (``DS:234E`` origin-x, ``DS:2350`` row-base) is dynamic per-frame gameplay
state and is supplied by the caller.  Feeding the result to the recovered probes runs them on cold-loaded
data with no VM.
"""
from __future__ import annotations

from overkill.asset_codecs.native_level import NativeLevel
from overkill.recovered.domain.tilemap import LevelTileContext


def level_tile_context_from_native(level: NativeLevel, origin_x_word: int, row_base_word: int) -> LevelTileContext:
    """Build a :class:`LevelTileContext` from a cold ``NativeLevel`` + the per-frame scroll words."""
    return LevelTileContext(
        origin_x_word=origin_x_word & 0xFFFF,
        row_base_word=row_base_word & 0xFFFF,
        tile_plane=level.tile_plane,
        class_table=level.class_table,
    )
