"""VM-free unit tests for the pure 1010:7420 linked-effect spawn template.

Pins the field values the BFC7 death/spawn tail stamps into a freshly allocated effect slot
(``object_spawn_seed_7420``): the computed X (source + scroll offset), the Y floor clamp, the
sprite bias, the raw source type at +26h, and the constants -- the synthetic oracle behind the
demo-level ``overkill.probes.verify_native_object_spawn_seed_7420`` produced-vs-VM witness.
"""
from __future__ import annotations

from overkill.recovered.domain.object_slots import LinkedEffectSpawnSeed7420
from overkill.recovered.systems.objects import (
    OBJECT_SPAWN_SEED_7420_Y_FLOOR,
    object_spawn_seed_7420,
)


def test_spawn_seed_7420_basic_fields():
    seed = object_spawn_seed_7420(source_x=0x0100, source_y=0x0050, source_type=0x0010, x_offset=0x0008)
    assert seed == LinkedEffectSpawnSeed7420(
        active_word=0x0001,
        x_word=0x0108,            # 0x0100 + 0x0008
        y_word=0x0050,            # < floor, unclamped
        transition_latch=0x0000,
        scan_flag=0x0001,
        hazard_class=0x0005,
        logic_id=0x0000,
        linked_counter_index=0xFFFF,
        variant=0x0000,
        slot_field_26=0x0010,     # raw source type
        sprite_or_state=0x0056,   # 0x0010 + 0x46
        gate_or_layer=0x0000,
    )


def test_spawn_seed_7420_y_clamps_to_floor_strictly_above():
    # The clamp is `> 00C0h`, so exactly the floor is left unchanged.
    assert object_spawn_seed_7420(0, OBJECT_SPAWN_SEED_7420_Y_FLOOR, 0, 0).y_word == OBJECT_SPAWN_SEED_7420_Y_FLOOR
    assert object_spawn_seed_7420(0, OBJECT_SPAWN_SEED_7420_Y_FLOOR + 1, 0, 0).y_word == OBJECT_SPAWN_SEED_7420_Y_FLOOR
    assert object_spawn_seed_7420(0, 0x00D0, 0, 0).y_word == OBJECT_SPAWN_SEED_7420_Y_FLOOR
    assert object_spawn_seed_7420(0, 0x00BF, 0, 0).y_word == 0x00BF


def test_spawn_seed_7420_x_and_sprite_wrap_16bit():
    seed = object_spawn_seed_7420(source_x=0xFFFF, source_y=0x0000, source_type=0xFFFF, x_offset=0x0002)
    assert seed.x_word == 0x0001            # (0xFFFF + 2) & 0xFFFF
    assert seed.sprite_or_state == 0x0045   # (0xFFFF + 0x46) & 0xFFFF
    assert seed.slot_field_26 == 0xFFFF     # raw type unmodified
