"""CONVERGENCE slice B: the level ROM (overkill.recovered.adapters.level_rom) -- 384 bytes standing
in for the exe image in load_native_level.

extract_level_rom pulls the two small data-segment ranges load_native_level actually reads
(the class-override table + the tile-plane footer) out of the exe-derived bundle; the ROM-based
loader must reproduce load_native_level's output byte-for-byte for every level, from the 384-byte
blob + the container alone -- no exe_image.
"""
from __future__ import annotations

import pathlib

import pytest

from overkill.asset_codecs import load_native_level
from overkill.asset_codecs.native_level import load_native_level_from_rom
from overkill.recovered.adapters.level_rom import LEVEL_ROM_SIZE, extract_level_rom

ROOT = pathlib.Path(__file__).resolve().parent.parent
OVERKILL = ROOT / "assets" / "OVERKILL"
BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"

_HAVE = OVERKILL.exists() and BUNDLE.is_file()


def test_level_rom_is_the_measured_384_bytes():
    assert LEVEL_ROM_SIZE == 384


@pytest.mark.skipif(not _HAVE, reason="bundle / container not present")
def test_rom_loader_matches_exe_loader_for_every_level():
    bundle = BUNDLE.read_bytes()
    container = OVERKILL.read_bytes()
    rom = extract_level_rom(bundle)
    assert len(rom) == LEVEL_ROM_SIZE
    for level in range(6):
        ref = load_native_level(bundle, container, level)
        got = load_native_level_from_rom(rom, container, level)
        assert got.class_table == ref.class_table, f"level {level}: class_table diverged"
        assert got.tile_plane == ref.tile_plane, f"level {level}: tile_plane diverged"
        assert got.blocks == ref.blocks and got.graphics == ref.graphics
