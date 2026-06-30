"""The MAP post-load processing (border + class table) -- the LevelTileContext companions.

finalize_level_tile_plane applies the 1010:0BB9-0BD2 border (head fill + footer copy) so the decoded
tile map matches the live CS:[9592] buffer byte-for-byte; build_level_class_table builds the 256-entry
DS:C3AA raw-tile -> class map (1010:0B8E-0BB7).  The real-file test proves both against the live VM
buffers across all six levels, reading the game's footer (DS:D1BC) and per-level override (C4AA[level])
constants out of the snapshot image.
"""
from __future__ import annotations

import pathlib
import struct

import pytest

from overkill.asset_codecs import (
    TILE_MAP_SIZE,
    build_level_class_table,
    decode_level_tile_map,
    finalize_level_tile_plane,
)
from overkill.asset_codecs.level_assets import (
    TILE_PLANE_FOOTER_OFFSET,
    TILE_PLANE_FOOTER_SIZE,
    TILE_PLANE_HEAD_FILL,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
OVERKILL = ROOT / "assets" / "OVERKILL"
DEMOS = ROOT / "artifacts" / "demos"

CS = 0x1010
DS = 0x25CC
MAP_DEST_VAR = 0x9592
CLASS_TABLE_OFF = 0xC3AA
FOOTER_SRC_OFF = 0xD1BC
CLASS_PTR_TABLE_OFF = 0xC4AA

FRESH_SNAPSHOTS = {
    1: "demo_play_tandy_L1_start_20260618_143947",
    2: "demo_play_tandy_L2_full_20260617_180221",
    3: "demo_play_tandy_L3_full_20260617_202520",
    4: "demo_play_tandy_L4_full_20260618_185155",
    5: "demo_play_tandy_L5_start_20260618_185923",
    0: "demo_play_tandy_L6_begin_20260618_225537",
}


def test_finalize_tile_plane_unit():
    plane = finalize_level_tile_plane(bytes([0x55]) * TILE_MAP_SIZE, bytes([0xAB]) * TILE_PLANE_FOOTER_SIZE)
    assert len(plane) == TILE_MAP_SIZE
    assert plane[:TILE_PLANE_HEAD_FILL] == b"\x01" * TILE_PLANE_HEAD_FILL
    assert plane[TILE_PLANE_HEAD_FILL] == 0x55  # body untouched past the head
    end = TILE_PLANE_FOOTER_OFFSET + TILE_PLANE_FOOTER_SIZE
    assert plane[TILE_PLANE_FOOTER_OFFSET:end] == b"\xAB" * TILE_PLANE_FOOTER_SIZE
    assert plane[end:] == b"\x55" * (TILE_MAP_SIZE - end)


def test_build_class_table_unit():
    table = build_level_class_table(bytes([5, 0x10, 200, 0x0C, 0xFF]))
    assert len(table) == 256
    assert table[5] == 0x10 and table[200] == 0x0C
    assert table[0] == 0x01 and table[6] == 0x01  # defaults


def _read_override_pairs(img, level):
    ptr = struct.unpack_from("<H", img, DS * 16 + CLASS_PTR_TABLE_OFF + level * 2)[0]
    out = bytearray()
    i = DS * 16 + ptr
    while True:
        index = img[i]
        out.append(index)
        i += 1
        if index == 0xFF:
            return bytes(out)
        out.append(img[i])
        i += 1


@pytest.mark.skipif(not OVERKILL.is_file(), reason="assets/OVERKILL not present")
def test_tile_plane_and_class_table_match_live_buffers():
    container = OVERKILL.read_bytes()
    checked = 0
    for level, snap_dir in FRESH_SNAPSHOTS.items():
        snap = DEMOS / snap_dir / "snapshot" / "memory_1mb.bin"
        if not snap.is_file():
            continue
        img = snap.read_bytes()
        assert struct.unpack_from("<H", img, DS * 16 + 0x2356)[0] == level, snap_dir

        footer = img[DS * 16 + FOOTER_SRC_OFF : DS * 16 + FOOTER_SRC_OFF + TILE_PLANE_FOOTER_SIZE]
        plane = finalize_level_tile_plane(decode_level_tile_map(container, level), footer)
        map_seg = struct.unpack_from("<H", img, CS * 16 + MAP_DEST_VAR)[0]
        assert img[map_seg * 16 : map_seg * 16 + TILE_MAP_SIZE] == plane, (level, "tile_plane")

        class_table = build_level_class_table(_read_override_pairs(img, level))
        assert img[DS * 16 + CLASS_TABLE_OFF : DS * 16 + CLASS_TABLE_OFF + 256] == class_table, (level, "class_table")
        checked += 1
    assert checked >= 4, f"too few level snapshots present ({checked})"
