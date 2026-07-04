"""Cold-load the object-pass dispatch tables (behavior_dispatch_adapter)."""
from __future__ import annotations

import pathlib

import pytest

from overkill.recovered.adapters.behavior_dispatch_adapter import (
    BEHAVIOR_DISPATCH_COUNT,
    BEHAVIOR_DISPATCH_ENTRY,
    BEHAVIOR_EXIT_BC45,
    TYPE_DISPATCH_COUNT,
    load_behavior_dispatch_table,
    load_object_type_dispatch,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"

pytestmark = pytest.mark.skipif(not BUNDLE.is_file(), reason="static runtime bundle not present")


def test_object_type_dispatch_routes_enemy_types_to_the_behavior_dispatch():
    table = load_object_type_dispatch(BUNDLE.read_bytes())
    assert len(table) == TYPE_DISPATCH_COUNT == 8
    # types 2 and 4 (the enemy family) both route to the EFAE behavior dispatch
    assert table[2] == table[4] == BEHAVIOR_DISPATCH_ENTRY == 0xEFAE
    # type 0 is the common no-op exit
    assert table[0] == BEHAVIOR_EXIT_BC45


def test_behavior_dispatch_table_maps_the_known_wave_behaviors():
    table = load_behavior_dispatch_table(BUNDLE.read_bytes())
    assert len(table) == BEHAVIOR_DISPATCH_COUNT == 0x95
    # entry 0 = the no-op exit; the known wave-machinery behaviors (driven-oracle-confirmed:
    # verify_native_wave_driver_dispatch pins the (+0x18 << 1) + EFC4 indexing on the original bytes)
    assert table[0x00] == BEHAVIOR_EXIT_BC45
    assert table[0x1D] == 0xB86D  # the B86D formation family (b86d_formation_spawn_tick_index)
    assert table[0x21] == 0xB556  # the planet-keyed wave driver (wave_driver_dispatch_b556)
    assert table[0x20] == 0xB73E  # the per-planet wave enemy (live in the L1 pool)
    assert table[0x1F] == 0x8D4F  # the L1 escort/controller object observed in the L1_start pool
    assert table[0x61] == 0xF394  # the formation-snake enemy (formation_enemy_stamp_b5e6 spawns these)
    assert table[0x78] == 0xF762  # the planet-0 formation leader (B4A2 transforms the driver into it)
    # every entry points into the game code segment (a real handler or the BC45 exit)
    assert all(0x1000 <= off <= 0xF7FF for off in table)
