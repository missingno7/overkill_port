"""The level object-script walker (adapters/level_object_script) -- cold-data + spawn shape."""
from __future__ import annotations

import pathlib

import pytest

from overkill.recovered.adapters.flat_memory import MutFlatMemory
from overkill.recovered.adapters.level_object_script import (
    CONTROLLER_SPAWN_SCHEDULES,
    run_level_object_script_4a65,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"
LIVE = ROOT / "artifacts" / "demos" / "demo_play_tandy_L1_start_20260618_143947" / "snapshot" / "memory_1mb.bin"
SCRIPT_HEADS = {0: 0xC85C, 1: 0xC8DE, 2: 0xCA02, 3: 0xCC36, 4: 0xCC80, 5: 0xCCAA}
DS = 0x25CC


@pytest.mark.skipif(not (BUNDLE.is_file() and LIVE.is_file()), reason="artifacts not present")
def test_scripts_and_cursor_cells_are_static_cold_equals_live():
    cold, live = BUNDLE.read_bytes(), LIVE.read_bytes()
    base = DS * 16
    # the per-planet cursor cells point at the script heads, and the scripts are static data
    for planet, head in SCRIPT_HEADS.items():
        assert cold[base + 0xC5E9 + planet * 2] | (cold[base + 0xC5E9 + planet * 2 + 1] << 8) != 0
    assert cold[base + 0xC85C:base + 0xCD00] == live[base + 0xC85C:base + 0xCD00]


@pytest.mark.skipif(not BUNDLE.is_file(), reason="static runtime bundle not present")
def test_controller_entry_spawns_the_wave_driver_and_arms_the_wave_state():
    mem = MutFlatMemory(BUNDLE.read_bytes())
    # planet 0's first entry (trigger 0x0110) spawns the wave controller
    mem.ww(DS, 0x2356, 0)
    mem.ww(DS, mem.rw(DS, 0xC5E9), 0xC85C)   # cursor -> the script head
    mem.ww(DS, 0xA978, 0x0110)
    for cx in range(1, 0x24):                # clear the effect pool via the pointer table
        rec = mem.rw(DS, 0x32CA + cx * 2)
        if rec:
            mem.ww(DS, rec, 0)
    run_level_object_script_4a65(mem)
    # a controller object exists with an armed schedule + the wave-state flags set
    slot = next(mem.rw(DS, 0x32CA + cx * 2) for cx in range(1, 0x24)
                if mem.rw(DS, mem.rw(DS, 0x32CA + cx * 2)) != 0)
    beh = mem.rw(DS, slot + 0x18)
    assert mem.rw(DS, slot + 0x16) == 4                       # enemy type
    assert mem.rw(DS, 0xA482) == CONTROLLER_SPAWN_SCHEDULES.get(beh)
    assert mem.rw(DS, slot + 0x20) == 0x14 and mem.rw(DS, 0xA47E) == 1
    assert mem.rw(DS, 0x2342) == 1 and mem.rw(DS, 0xA7A0) == 0


def test_controller_spawn_schedules_are_the_expected_bases():
    assert CONTROLLER_SPAWN_SCHEDULES[0x1F] == 0xA82E    # distinct from the C054 death-chain A83E
    assert CONTROLLER_SPAWN_SCHEDULES[0x13] == 0xA484
