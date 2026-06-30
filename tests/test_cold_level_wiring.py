"""End-to-end wiring: a cold-loaded NativeLevel drives the recovered tile probe identically to the VM.

Builds a LevelTileContext from load_native_level (container + EXE image) via the cold-level adapter, then
runs the recovered AD60 tile-probe (object_tile_probe_deactivates_ad60) over a grid of object positions
and checks it gives the same answer as the same probe over the *live VM tile segment* read from the
snapshot.  This closes the loop: cold data -> adapter -> recovered logic == the real game.
"""
from __future__ import annotations

import pathlib
import struct

import pytest

from overkill.asset_codecs import load_native_level
from overkill.recovered.adapters.cold_level_adapter import level_tile_context_from_native
from overkill.recovered.domain.tilemap import LevelTileContext
from overkill.recovered.systems.objects import object_tile_probe_deactivates_ad60

ROOT = pathlib.Path(__file__).resolve().parent.parent
OVERKILL = ROOT / "assets" / "OVERKILL"
DEMOS = ROOT / "artifacts" / "demos"

CS = 0x1010
DS = 0x25CC
MAP_DEST_VAR = 0x9592
CLASS_TABLE_OFF = 0xC3AA
ORIGIN_X_OFF = 0x234E
ROW_BASE_OFF = 0x2350

SNAP = DEMOS / "demo_play_tandy_L5_start_20260618_185923" / "snapshot" / "memory_1mb.bin"


def test_adapter_fields():
    # The adapter wires the cold buffers + scroll into the right LevelTileContext fields.
    from overkill.asset_codecs.native_level import NativeLevel

    lvl = NativeLevel(level=2, tile_plane=b"\x07" * 3744, class_table=b"\x02" * 256, blocks=b"", graphics=b"")
    ctx = level_tile_context_from_native(lvl, 0x1234, 0x5678)
    assert ctx.origin_x_word == 0x1234 and ctx.row_base_word == 0x5678
    assert ctx.tile_plane is lvl.tile_plane and ctx.class_table is lvl.class_table


@pytest.mark.skipif(not OVERKILL.is_file() or not SNAP.is_file(), reason="game data / snapshot not present")
def test_cold_level_drives_recovered_tile_probe_like_the_vm():
    container = OVERKILL.read_bytes()
    img = SNAP.read_bytes()
    level = struct.unpack_from("<H", img, DS * 16 + 0x2356)[0]
    origin_x = struct.unpack_from("<H", img, DS * 16 + ORIGIN_X_OFF)[0]
    row_base = struct.unpack_from("<H", img, DS * 16 + ROW_BASE_OFF)[0]

    # Cold path: load the level VM-free, build the recovered context through the adapter.
    native = load_native_level(img, container, level)
    cold_ctx = level_tile_context_from_native(native, origin_x, row_base)

    # VM reference: the live tile segment (whole 64 KiB) + class table read from the snapshot.
    map_seg = struct.unpack_from("<H", img, CS * 16 + MAP_DEST_VAR)[0]
    vm_ctx = LevelTileContext(
        origin_x_word=origin_x,
        row_base_word=row_base,
        tile_plane=img[map_seg * 16 : map_seg * 16 + 0x10000],
        class_table=img[DS * 16 + CLASS_TABLE_OFF : DS * 16 + CLASS_TABLE_OFF + 256],
    )

    compared = 0
    deactivations = 0
    for obj_y in range(0, 640, 8):
        for obj_x in range(0, 2048, 8):
            vm_result = object_tile_probe_deactivates_ad60(obj_x, obj_y, vm_ctx)
            try:
                cold_result = object_tile_probe_deactivates_ad60(obj_x, obj_y, cold_ctx)
            except IndexError:
                continue  # position maps past the cold tile plane (3744); VM seg is larger
            assert cold_result == vm_result, (obj_x, obj_y, cold_result, vm_result)
            compared += 1
            deactivations += int(cold_result)

    assert compared > 500, f"too few in-map comparisons ({compared})"
    assert deactivations > 0, "probe never fired -- grid likely missed the map"
