"""Prove the level BLOCKS + GRAPHICS data path end to end: container -> decode -> de-planarize -> dest.

decode_level_blocks / decode_level_graphics decode LEV{n}BLX.BIC / G{n}.BIC and run the Tandy
de-planarize (1010:33AF/344B).  The level loader (0E9C -> 0CC8/0CD8 -> 5BAC) lands those at CS:[959A]:0
(blocks) and CS:[95AE]:0 (graphics).  Unlike the tile map, these are static banks (no post-load border /
gameplay mutation), so the whole decoded buffer must equal the live buffer byte-for-byte, across all six
levels.
"""
from __future__ import annotations

import pathlib
import struct

import pytest

from overkill.asset_codecs import (
    decode_level_blocks,
    decode_level_graphics,
    decode_level_tile_map,
    load_level_data,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
OVERKILL = ROOT / "assets" / "OVERKILL"
DEMOS = ROOT / "artifacts" / "demos"

CS = 0x1010
BLOCKS_DEST_VAR = 0x959A   # CS:[959A] = blocks buffer segment
GRAPHICS_DEST_VAR = 0x95AE  # CS:[95AE] = graphics buffer segment

FRESH_SNAPSHOTS = {
    1: "demo_play_tandy_L1_start_20260618_143947",
    2: "demo_play_tandy_L2_full_20260617_180221",
    3: "demo_play_tandy_L3_full_20260617_202520",
    4: "demo_play_tandy_L4_full_20260618_185155",
    5: "demo_play_tandy_L5_start_20260618_185923",
    0: "demo_play_tandy_L6_begin_20260618_225537",
}


@pytest.mark.skipif(not OVERKILL.is_file(), reason="assets/OVERKILL not present")
def test_decode_blocks_and_graphics_nonempty():
    data = OVERKILL.read_bytes()
    for level in range(6):
        assert len(decode_level_blocks(data, level)) > 0, level
        assert len(decode_level_graphics(data, level)) > 0, level


@pytest.mark.skipif(not OVERKILL.is_file(), reason="assets/OVERKILL not present")
def test_load_level_data_bundles_the_three_buffers():
    data = OVERKILL.read_bytes()
    bundle = load_level_data(data, 3)
    assert bundle.tile_map == decode_level_tile_map(data, 3)
    assert bundle.blocks == decode_level_blocks(data, 3)
    assert bundle.graphics == decode_level_graphics(data, 3)


@pytest.mark.skipif(not OVERKILL.is_file(), reason="assets/OVERKILL not present")
def test_blocks_and_graphics_match_live_buffers_for_every_level():
    container = OVERKILL.read_bytes()
    checked = 0
    for level, snap_dir in FRESH_SNAPSHOTS.items():
        snap = DEMOS / snap_dir / "snapshot" / "memory_1mb.bin"
        if not snap.is_file():
            continue
        img = snap.read_bytes()
        assert struct.unpack_from("<H", img, 0x25CC * 16 + 0x2356)[0] == level, snap_dir

        for decode, dest_var, role in (
            (decode_level_blocks, BLOCKS_DEST_VAR, "blocks"),
            (decode_level_graphics, GRAPHICS_DEST_VAR, "graphics"),
        ):
            seg = struct.unpack_from("<H", img, CS * 16 + dest_var)[0]
            base = seg * 16
            out = decode(container, level)
            assert img[base : base + len(out)] == out, (level, role, snap_dir)
        checked += 1
    assert checked >= 4, f"too few level snapshots present ({checked})"
