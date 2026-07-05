"""The walk's composed 62F6 combat chain (kill / survive / no-hit), memory-shaped."""
from __future__ import annotations

import pathlib

import pytest

from overkill.recovered.adapters.flat_memory import MutFlatMemory
from overkill.recovered.adapters.behavior_walk import DS, _postmove_bc45
from overkill.recovered.domain.tilemap import LevelTileContext

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"
SCANNER = 0x2424          # an effect-pool record cell
CANDIDATE = 0x2B5C        # gameplay slot 0


def _arena(scanner_hp: int, cand_x: int) -> MutFlatMemory:
    mem = MutFlatMemory(BUNDLE.read_bytes())
    for cell in (0xA47C, 0xA8C2, 0xBEDC, 0xA278):
        mem.ww(DS, cell, 0)
    mem.ww(DS, 0x2384, 3)                     # anchor pose >= 3 -> the BCCB touch never fires
    for off in range(0, 0x38, 2):
        mem.ww(DS, SCANNER + off, 0)
        mem.ww(DS, CANDIDATE + off, 0)
    for off, val in {0x00: 1, 0x02: 0x6C, 0x04: 0xBC, 0x0A: 1, 0x14: 1, 0x16: 4,
                     0x18: 0x20, 0x20: scanner_hp, 0x28: 0xFFFF}.items():
        mem.ww(DS, SCANNER + off, val)
    for off, val in {0x00: 1, 0x02: cand_x, 0x04: 0xBC, 0x08: 0x32, 0x16: 2,
                     0x18: 2, 0x1E: 1}.items():
        mem.ww(DS, CANDIDATE + off, val)
    return mem


def _tiles() -> LevelTileContext:
    return LevelTileContext(origin_x_word=0, row_base_word=0,
                            tile_plane=bytes(0x4000), class_table=(0,) * 256)


@pytest.mark.skipif(not BUNDLE.is_file(), reason="static runtime bundle not present")
def test_shot_kills_the_scanner_and_is_consumed():
    mem = _arena(scanner_hp=4, cand_x=0x6C)    # BEDC=0, sprite 32h -> BF2D entry: 4 decrements
    _postmove_bc45(mem, SCANNER, _tiles(), with_drift=False)
    assert mem.rw(DS, SCANNER + 0x18) == 1              # the dying stamp
    assert mem.rw(DS, SCANNER + 0x1A) == 0x20           # previous behavior latched
    assert mem.rw(DS, SCANNER + 0x20) == 0
    assert mem.rw(DS, SCANNER + 0x08) == 0              # key-1 death sprite
    assert mem.rw(DS, CANDIDATE) == 0                   # variant 2 clears the candidate directly


@pytest.mark.skipif(not BUNDLE.is_file(), reason="static runtime bundle not present")
def test_shot_damage_survival_stamps_the_hit_react():
    mem = _arena(scanner_hp=0x14, cand_x=0x6C)
    _postmove_bc45(mem, SCANNER, _tiles(), with_drift=False)
    assert mem.rw(DS, SCANNER + 0x18) == 0x20           # still alive
    assert mem.rw(DS, SCANNER + 0x20) == 0x10           # 4 decrements
    assert mem.rw(DS, SCANNER + 0x24) == 5              # BF25's [bp+36 dec] = +24h hit-react
    assert mem.rw(DS, CANDIDATE) == 0


@pytest.mark.skipif(not BUNDLE.is_file(), reason="static runtime bundle not present")
def test_no_overlap_means_no_interaction():
    mem = _arena(scanner_hp=4, cand_x=0x100)
    _postmove_bc45(mem, SCANNER, _tiles(), with_drift=False)
    assert mem.rw(DS, SCANNER + 0x18) == 0x20
    assert mem.rw(DS, SCANNER + 0x20) == 4
    assert mem.rw(DS, CANDIDATE) == 1
