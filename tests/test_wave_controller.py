"""The 0x1F wave controller (systems/enemy_behaviors.step_wave_controller_1f)."""
from __future__ import annotations

from overkill.recovered.systems.enemy_behaviors import step_wave_controller_1f

# house fixtures (see test_object_update_b1b0): all-FF = 5DB2 blocked; all-4 = always step +X
_BLOCKED = (0xFF,) * 16
_MOVE_X = (4,) * 16
RING = lambda cursor: ((cursor & 0xFF), 0x30 + (cursor & 0xFF))  # noqa: E731 -- distinct per slot


def test_flying_steps_toward_the_waypoint_and_wears_the_direction_sprite():
    r = step_wave_controller_1f(x_word=0x30, y_word=0x40, direction=0,
                                schedule_x_raw=0x60, schedule_y=0x40,
                                ring_cursor_a842=0xA844, ring_slot_at=RING,
                                direction_table=_MOVE_X)
    assert not r.arrived and r.schedule_advance == 0 and r.spawn_stamps == ()
    assert r.direction == 4 and r.sprite == 4 + 0x3B
    assert r.seek_globals == {0x2304: 0x40, 0x2306: 0x80, 0x2308: 3}
    assert (r.x_word, r.y_word) == (0x38, 0x40)      # the mode-3 8px +X step


def test_arrival_bursts_five_spawns_from_the_ring_without_wrapping():
    r = step_wave_controller_1f(x_word=0x80, y_word=0x40, direction=6,
                                schedule_x_raw=0x60, schedule_y=0x40,
                                ring_cursor_a842=0xA890, ring_slot_at=RING,
                                direction_table=_BLOCKED)
    assert r.arrived and r.schedule_advance == 4
    assert len(r.spawn_stamps) == 5
    assert r.ring_cursor_after == 0xA890 + 0x14      # +4 per spawn, past A894, NO wrap
    assert (r.x_word, r.y_word, r.direction) == (0x80, 0x40, 6)  # blocked seek touches nothing
    assert r.sprite == (6 + 0x3B)
    first = r.spawn_stamps[0]
    assert first[0x18] == 0x20 and first[0x1C] == 0xFFFF        # behavior 0x20, approach substate
    assert first[0x02] == 0x80 and first[0x04] == 0x40          # leader-context = controller pos
    assert first[0x34] == (RING(0xA890)[0] + 0x20) & 0xFFFF     # formation slot from the ring
    assert r.spawn_stamps[1][0x34] == (RING(0xA894)[0] + 0x20) & 0xFFFF
