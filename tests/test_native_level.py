"""The cold-boot level loader (asset_codecs.load_native_level) -- a whole level vs the live VM.

load_native_level(exe_image, container, level) assembles a NativeLevel (tile_plane, class_table, blocks,
graphics) from the unpacked EXE image + the asset container -- the complete VM-free per-level data load.
The real-file test proves every buffer byte-for-byte against the live VM buffers for all six levels.
"""
from __future__ import annotations

import pathlib
import struct

import pytest

from overkill.asset_codecs import TILE_MAP_SIZE, load_native_level

ROOT = pathlib.Path(__file__).resolve().parent.parent
OVERKILL = ROOT / "assets" / "OVERKILL"
BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"
DEMOS = ROOT / "artifacts" / "demos"

CS = 0x1010
DS = 0x25CC
MAP_DEST_VAR = 0x9592
BLOCKS_DEST_VAR = 0x959A
GRAPHICS_DEST_VAR = 0x95AE
CLASS_TABLE_OFF = 0xC3AA

FRESH_SNAPSHOTS = {
    1: "demo_play_tandy_L1_start_20260618_143947",
    2: "demo_play_tandy_L2_full_20260617_180221",
    3: "demo_play_tandy_L3_full_20260617_202520",
    4: "demo_play_tandy_L4_full_20260618_185155",
    5: "demo_play_tandy_L5_start_20260618_185923",
    0: "demo_play_tandy_L6_begin_20260618_225537",
}


@pytest.mark.skipif(not OVERKILL.is_file() or not BUNDLE.is_file(), reason="game data not present")
def test_load_native_level_smoke():
    level = load_native_level(BUNDLE.read_bytes(), OVERKILL.read_bytes(), 0)
    assert level.level == 0
    assert len(level.tile_plane) == TILE_MAP_SIZE
    assert len(level.class_table) == 256
    assert len(level.blocks) > 0 and len(level.graphics) > 0


@pytest.mark.skipif(not OVERKILL.is_file(), reason="assets/OVERKILL not present")
def test_native_level_matches_live_vm_buffers_for_every_level():
    container = OVERKILL.read_bytes()
    checked = 0
    for level, snap_dir in FRESH_SNAPSHOTS.items():
        snap = DEMOS / snap_dir / "snapshot" / "memory_1mb.bin"
        if not snap.is_file():
            continue
        img = snap.read_bytes()
        assert struct.unpack_from("<H", img, DS * 16 + 0x2356)[0] == level, snap_dir

        # The same image is both the EXE-constant source and the holder of the live buffers.
        native = load_native_level(img, container, level)

        def seg(var):
            return struct.unpack_from("<H", img, CS * 16 + var)[0] * 16

        assert img[seg(MAP_DEST_VAR) : seg(MAP_DEST_VAR) + len(native.tile_plane)] == native.tile_plane, (level, "tile")
        assert img[DS * 16 + CLASS_TABLE_OFF : DS * 16 + CLASS_TABLE_OFF + 256] == native.class_table, (level, "class")
        assert img[seg(BLOCKS_DEST_VAR) : seg(BLOCKS_DEST_VAR) + len(native.blocks)] == native.blocks, (level, "blocks")
        assert img[seg(GRAPHICS_DEST_VAR) : seg(GRAPHICS_DEST_VAR) + len(native.graphics)] == native.graphics, (level, "gfx")
        checked += 1
    assert checked >= 4, f"too few level snapshots present ({checked})"
