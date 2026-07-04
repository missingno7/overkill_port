"""The type-6 companion handler (systems/companion.step_companion_ab10)."""
from __future__ import annotations

from overkill.recovered.systems.companion import step_companion_ab10

ANIM = (0, 1, 2, 3, 4, 3, 2, 1)
OFFSETS = {0: (0x19, 8), 1: (0x10, 12), 2: (-13 & 0xFFFF, 8)}


def _step(**over):
    base = dict(scripted_a47c=0, divider_2336=0, anchor_x=0xC0, anchor_y=0x58,
                anchor_sprite=0, anim_table=ANIM, offset_pair_at=OFFSETS.__getitem__)
    base.update(over)
    return step_companion_ab10(**base)


def test_follows_the_anchor_with_the_pose_offset_and_divider_sprite():
    r = _step(divider_2336=4, anchor_sprite=2)
    assert not r.deactivate
    assert r.sprite == ANIM[4] + 9
    assert (r.x_word, r.y_word) == ((0xC0 - 13) & 0xFFFF, 0x58 + 8)


def test_hides_when_the_ship_pose_or_the_scripted_mode_gate_is_up():
    # DS:2384 IS the anchor's +0x08 sprite (the aliasing the driven oracle caught): pose >= 3 hides
    assert _step(anchor_sprite=3).deactivate
    assert _step(anchor_sprite=4).deactivate
    assert _step(scripted_a47c=3).deactivate
    assert not _step(scripted_a47c=2, anchor_sprite=2).deactivate
