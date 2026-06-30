"""Prove the level tile-map data path end to end: container -> decode -> the live map buffer.

decode_level_tile_map(container, level) decodes LEV{n}MAP.BIC; the MAP loader (1010:0B3E -> C679 -> 0248)
writes that straight into the tile-map buffer at CS:[9592]:0.  This compares the pure decode against the
live buffer in fresh level-load snapshots across all six levels: the map *body* [12:3682] must be
byte-exact.  (The first row + a trailing footer are rewritten by post-load init -- a border -- so they
are excluded; mid-gameplay snapshots also mutate the body via destructible terrain and are not used.)
"""
from __future__ import annotations

import pathlib
import struct

import pytest

from overkill.asset_codecs import TILE_MAP_SIZE, decode_level_tile_map

ROOT = pathlib.Path(__file__).resolve().parent.parent
OVERKILL = ROOT / "assets" / "OVERKILL"
DEMOS = ROOT / "artifacts" / "demos"

CS = 0x1010
MAP_DEST_SEG_VAR = 0x9592  # CS:[9592] holds the tile-map buffer segment
BODY_START, BODY_END = 12, 3682  # the decoded-map region not rewritten by post-load border init

# Fresh level-load snapshots (map decoded, not yet mutated by play), one per level 0..5.
FRESH_SNAPSHOTS = {
    1: "demo_play_tandy_L1_start_20260618_143947",
    2: "demo_play_tandy_L2_full_20260617_180221",
    3: "demo_play_tandy_L3_full_20260617_202520",
    4: "demo_play_tandy_L4_full_20260618_185155",
    5: "demo_play_tandy_L5_start_20260618_185923",
    0: "demo_play_tandy_L6_begin_20260618_225537",
}


@pytest.mark.skipif(not OVERKILL.is_file(), reason="assets/OVERKILL not present")
def test_decode_level_tile_map_size():
    data = OVERKILL.read_bytes()
    for level in range(6):
        assert len(decode_level_tile_map(data, level)) == TILE_MAP_SIZE, level


@pytest.mark.skipif(not OVERKILL.is_file(), reason="assets/OVERKILL not present")
def test_tile_map_body_matches_live_buffer_for_every_level():
    container = OVERKILL.read_bytes()
    checked = 0
    for level, snap_dir in FRESH_SNAPSHOTS.items():
        snap = DEMOS / snap_dir / "snapshot" / "memory_1mb.bin"
        if not snap.is_file():
            continue
        img = snap.read_bytes()
        # Sanity: the snapshot really is on this level.
        assert struct.unpack_from("<H", img, 0x25CC * 16 + 0x2356)[0] == level, snap_dir
        map_seg = struct.unpack_from("<H", img, CS * 16 + MAP_DEST_SEG_VAR)[0]
        base = map_seg * 16
        decoded = decode_level_tile_map(container, level)
        live = img[base : base + len(decoded)]
        assert decoded[BODY_START:BODY_END] == live[BODY_START:BODY_END], (level, snap_dir)
        checked += 1
    assert checked >= 4, f"too few level snapshots present ({checked})"
