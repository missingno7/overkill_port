"""The planet-keyed wave-driver dispatch + leaves (frame_loop B556/B468/B58A)."""
from __future__ import annotations

from overkill.recovered.systems.frame_loop import (
    ENEMY_TYPE_16,
    WAVE_DRIVER_BOSS_A7A0,
    WAVE_DRIVER_PER_PLANET_A7A0,
    boss_transform_stamp_b58a,
    count_active_enemies_b468,
    wave_driver_dispatch_b556,
)


def test_wave_driver_dispatch_is_planet_keyed_then_a7a0_phased():
    # the three special planets ignore the wave clock entirely
    for a7a0 in (0x00, 0xC8, 0xF0, 0xFFFF):
        assert wave_driver_dispatch_b556(4, a7a0) == "planet4_family"
        assert wave_driver_dispatch_b556(3, a7a0) == "phase_machine"
        assert wave_driver_dispatch_b556(0, a7a0) == "leader_group"
    # every other planet phases on A7A0: per-planet spawn -> pause -> boss transform
    for planet in (1, 2, 5):
        assert wave_driver_dispatch_b556(planet, 0x00) == "per_planet"
        assert wave_driver_dispatch_b556(planet, WAVE_DRIVER_PER_PLANET_A7A0 - 1) == "per_planet"
        assert wave_driver_dispatch_b556(planet, WAVE_DRIVER_PER_PLANET_A7A0) == "none"
        assert wave_driver_dispatch_b556(planet, WAVE_DRIVER_BOSS_A7A0 - 1) == "none"
        assert wave_driver_dispatch_b556(planet, WAVE_DRIVER_BOSS_A7A0) == "boss_transform"


def test_count_active_enemies_counts_only_active_type_4_records():
    assert ENEMY_TYPE_16 == 4
    records = [
        (1, 4),   # active enemy -> counted
        (0, 4),   # inactive enemy -> no
        (1, 6),   # active companion (type 6) -> no
        (1, 4),   # counted
        (0, 0),   # empty slot -> no
    ]
    assert count_active_enemies_b468(records) == 2
    assert count_active_enemies_b468([]) == 0


def test_boss_transform_stamp_scales_hp_with_the_planet_index():
    stamp = boss_transform_stamp_b58a(1)
    assert stamp == {0x18: 0x0022, 0x08: 0x0071, 0x20: 0x0014, 0x04: 0x0060}
    # HP = 10 * (planet + 1)
    assert boss_transform_stamp_b58a(5)[0x20] == 60
