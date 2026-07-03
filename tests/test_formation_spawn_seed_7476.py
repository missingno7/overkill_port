"""VM-free unit tests for the pure 1010:7476 formation child spawn template.

Pins the field values 7476 stamps into a freshly allocated formation child
(``formation_spawn_seed_7476``): the parent-relative Y/X with the normal vs final-boss
(DS:A8C2) offset pair, the fixed logic_id=0Bh stamp, and the view-relative move deltas -- the
synthetic oracle behind the demo-level ``overkill.probes.verify_native_formation_spawn_seed_7476``.
"""
from __future__ import annotations

from overkill.recovered.domain.object_slots import FormationSpawnSeed7476
from overkill.recovered.systems.objects import (
    FORMATION_SPAWN_PTR_BASE,
    advance_formation_spawn_ptr,
    formation_spawn_seed_7476,
)


def test_advance_formation_spawn_ptr_steps_by_two():
    assert advance_formation_spawn_ptr(0x20A8) == 0x20AA
    assert advance_formation_spawn_ptr(0x20C4) == 0x20C6


def test_advance_formation_spawn_ptr_wraps_past_last_entry():
    # 0x20C6 + 2 = 0x20C8 >= 0x20C7 -> wrap to base
    assert advance_formation_spawn_ptr(0x20C6) == FORMATION_SPAWN_PTR_BASE
    # exact-threshold edge: 0x20C5 + 2 = 0x20C7 also wraps
    assert advance_formation_spawn_ptr(0x20C5) == 0x20A8


def test_formation_spawn_seed_normal_mode():
    seed = formation_spawn_seed_7476(slot_x=0x100, slot_y=0x80, boss_mode=False,
                                     view_y_2380=0x40, view_x_237e=0x50)
    assert seed == FormationSpawnSeed7476(
        y_word=0x008C,           # 0x80 + 0x0C
        x_word=0x010C,           # 0x100 + 0x0C
        active_word=0x0001,
        scan_enable_or_solid=0x0000,
        direction_or_step=0x0000,
        sprite_or_state=0x0031,
        gate_or_layer=0x0001,
        scan_flag=0x0000,
        hazard_class=0x0002,
        logic_id=0x000B,
        substate=0xFFFF,
        move_delta_y=0x0043,     # 0x8C - (0x40 + 9)
        move_delta_x=0x00BC,     # 0x10C - 0x50
    )


def test_formation_spawn_seed_boss_mode_offsets():
    seed = formation_spawn_seed_7476(slot_x=0x100, slot_y=0x80, boss_mode=True,
                                     view_y_2380=0x40, view_x_237e=0x50)
    assert seed.y_word == 0x009C   # 0x80 + 0x1C (wider Y in boss mode)
    assert seed.x_word == 0x0108   # 0x100 + 0x08 (narrower X in boss mode)
    assert seed.logic_id == 0x000B and seed.sprite_or_state == 0x0031


def test_formation_spawn_seed_deltas_wrap_16bit():
    # view ahead of the child -> the move deltas wrap negative (mod 0x10000).
    seed = formation_spawn_seed_7476(slot_x=0x10, slot_y=0x10, boss_mode=False,
                                     view_y_2380=0x80, view_x_237e=0x90)
    assert seed.y_word == 0x001C and seed.x_word == 0x001C
    assert seed.move_delta_y == (0x1C - (0x80 + 9)) & 0xFFFF   # 0xFF93
    assert seed.move_delta_x == (0x1C - 0x90) & 0xFFFF          # 0xFF8C
