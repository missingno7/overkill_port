"""CONVERGENCE slice B: the tile-plane ROM (overkill.recovered.adapters.plane_rom).

extract_plane_rom/apply_plane_rom round-trip the measured 347-byte set (read-before-write over 3,000
gameplay frames on all 6 levels; see the module docstring) and reproduce it exactly on a blank plane
segment, with the one per-level-varying byte (the planet id) patched per level.  NOT YET WIRED into
cold_level_start's live path (that needs the same blank-base equivalence gate the level-ROM piece got,
still in progress -- see docs/overkill/campaigns/convergence.md); this locks the extraction itself.
"""
from __future__ import annotations

import pathlib

import pytest

from overkill.recovered.adapters.cold_level_start import build_cold_level_start_image
from overkill.recovered.adapters.flat_memory import MutFlatMemory
from overkill.recovered.adapters.plane_rom import (
    LEVEL_INDEX_TO_PLANET,
    PLANE_ROM_SIZE,
    PLANET_ID_OFFSET,
    apply_plane_rom,
    extract_plane_rom,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
OVERKILL = ROOT / "assets" / "OVERKILL"
BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"

_HAVE = OVERKILL.exists() and BUNDLE.is_file()


def test_plane_rom_is_the_measured_347_bytes():
    assert PLANE_ROM_SIZE == 347


@pytest.mark.skipif(not _HAVE, reason="bundle / container not present")
def test_apply_onto_blank_reproduces_the_bundle_bytes_for_every_level():
    bundle = BUNDLE.read_bytes()
    container = OVERKILL.read_bytes()
    seed0 = build_cold_level_start_image(bundle, 0, container)
    plane_seg = seed0.rw(0x1010, 0x9592)
    rom = extract_plane_rom(bundle, plane_seg)
    assert len(rom) == PLANE_ROM_SIZE

    for level in range(6):
        seed = build_cold_level_start_image(bundle, level, container)
        expected_planet_byte = seed.data[plane_seg * 16 + PLANET_ID_OFFSET]
        assert expected_planet_byte == LEVEL_INDEX_TO_PLANET[level]

        blank = MutFlatMemory(bytes(len(bundle)))
        apply_plane_rom(blank, plane_seg, rom, level)
        got = extract_plane_rom(bytes(blank.data), plane_seg)
        # every byte matches EXCEPT the planet-id offset is patched to THIS level's planet, not
        # whatever level 0's bundle capture happened to record there.
        want = bytearray(rom)
        planet_local = None
        base = plane_seg * 16
        off = 0
        from overkill.recovered.adapters.plane_rom import PLANE_ROM_RANGES
        for a, b in PLANE_ROM_RANGES:
            if a <= PLANET_ID_OFFSET <= b:
                planet_local = off + (PLANET_ID_OFFSET - a)
            off += b - a + 1
        want[planet_local] = LEVEL_INDEX_TO_PLANET[level]
        assert got == bytes(want)
