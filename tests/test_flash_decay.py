"""Fast (VM-free) tests for the A846 hit-flash decay logic (native_frame._flash_decay_a846).

These pin the per-record slot-count arithmetic and the active/anim gating that decides how far each
drawn record's +0x24 hit-flash ticks down.  The byte-exact-vs-the-original proof over a real demo
(inject +0x24 into every record, run one VM frame, diff) is the probe
``overkill.probes.verify_native_flash_decay`` (PASS: 7070 record-compares, 0 diverged).
"""
from __future__ import annotations

from overkill.native_frame import (
    ANCHOR,
    _drawn_slot_count,
    _flash_decay_a846,
)
from overkill.recovered.adapters.flat_memory import MutFlatMemory

DS = 0x25CC
STRIDE = 0x38
GP0 = 0x2B5C            # first gameplay-pool record
F_ACTIVE, F_SPRITE, F_SLOT0C, F_SLOT10, F_ANIM, F_DRAWTYPE, F_FLASH = (
    0x00, 0x08, 0x0C, 0x10, 0x12, 0x14, 0x24)


def test_drawn_slot_count_draw_type_2_counts_both_onscreen_slots():
    # 75A6: two slots, each drawn only when its destination is not the 0xFFFF off-screen sentinel.
    assert _drawn_slot_count(sprite_id=5, draw_type=2, slot_0c=0x100, slot_10=0x200) == 2
    assert _drawn_slot_count(sprite_id=5, draw_type=2, slot_0c=0x100, slot_10=0xFFFF) == 1
    assert _drawn_slot_count(sprite_id=5, draw_type=2, slot_0c=0xFFFF, slot_10=0xFFFF) == 0


def test_drawn_slot_count_single_slot_routines():
    # 768E (type 1) and 7746 (type 0) each draw one slot, gated on slot_0c being on-screen.
    assert _drawn_slot_count(sprite_id=5, draw_type=1, slot_0c=0x100, slot_10=0) == 1
    assert _drawn_slot_count(sprite_id=5, draw_type=1, slot_0c=0xFFFF, slot_10=0) == 0
    assert _drawn_slot_count(sprite_id=5, draw_type=0, slot_0c=0x100, slot_10=0) == 1
    assert _drawn_slot_count(sprite_id=5, draw_type=0, slot_0c=0xFFFF, slot_10=0) == 0


def test_drawn_slot_count_out_of_range_index_draws_nothing():
    # a sprite index at/past its frame-table length falls off the end -> no compositor call.
    assert _drawn_slot_count(sprite_id=0x500, draw_type=2, slot_0c=0x100, slot_10=0x100) == 0
    assert _drawn_slot_count(sprite_id=0x200, draw_type=1, slot_0c=0x100, slot_10=0) == 0
    assert _drawn_slot_count(sprite_id=0x100, draw_type=0, slot_0c=0x100, slot_10=0) == 0
    assert _drawn_slot_count(sprite_id=5, draw_type=3, slot_0c=0x100, slot_10=0x100) == 0


def _put(mem, base, *, active=1, sprite=5, s0c=0x100, s10=0x200, anim=0, dtype=2, flash=6):
    for off, val in ((F_ACTIVE, active), (F_SPRITE, sprite), (F_SLOT0C, s0c), (F_SLOT10, s10),
                     (F_ANIM, anim), (F_DRAWTYPE, dtype), (F_FLASH, flash)):
        mem.ww(DS, (base + off) & 0xFFFF, val)


def test_active_enemy_flash_decays_by_slot_count():
    mem = MutFlatMemory(bytes(0x100000))
    _put(mem, GP0, dtype=2, s0c=0x100, s10=0x200, flash=6)      # two on-screen slots -> dec 2
    _flash_decay_a846(mem)
    assert mem.rw(DS, GP0 + F_FLASH) == 4


def test_inactive_or_animating_enemy_flash_does_not_decay():
    mem = MutFlatMemory(bytes(0x100000))
    _put(mem, GP0, active=0, flash=6)                          # inactive -> no compositor call
    _flash_decay_a846(mem)
    assert mem.rw(DS, GP0 + F_FLASH) == 6

    mem2 = MutFlatMemory(bytes(0x100000))
    _put(mem2, GP0, active=1, anim=3, flash=6)                 # anim != 0 -> the 7688 no-draw stub
    _flash_decay_a846(mem2)
    assert mem2.rw(DS, GP0 + F_FLASH) == 6


def test_flash_floors_at_zero():
    mem = MutFlatMemory(bytes(0x100000))
    _put(mem, GP0, dtype=2, s0c=0x100, s10=0x200, flash=1)     # dec 2 but only 1 left -> floor 0
    _flash_decay_a846(mem)
    assert mem.rw(DS, GP0 + F_FLASH) == 0


def test_anchor_still_decays_like_before():
    # the player anchor (draw type 2, both slots on screen) decays by 2 -- the pre-fix behaviour,
    # preserved (the lockstep gate still passes 8292/8292 with zero divergence).
    mem = MutFlatMemory(bytes(0x100000))
    _put(mem, ANCHOR, dtype=2, s0c=0x100, s10=0x200, flash=8)
    _flash_decay_a846(mem)
    assert mem.rw(DS, ANCHOR + F_FLASH) == 6
