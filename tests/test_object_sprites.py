"""VM-free unit tests for the object -> sprite-block bridge (native_video.object_sprites).

The byte-exact-vs-VM proof (every 7596-dispatched compositor blit -- routine, di, source offset --
matches across levels) is ``overkill/probes/verify_native_object_sprites.py``; this pins the pure
draw-type dispatch, per-routine bank/table/threshold selection, the 75A6 two-slot split and the
skip rules headlessly.
"""
from __future__ import annotations

from overkill.native_video.object_sprites import (
    OFFSCREEN,
    SpriteDrawContext,
    object_slots,
    object_sprite_blocks,
)
from overkill.recovered.domain.object_slots import ObjectPool

_STRIDE = 0x38
_WORDS = _STRIDE // 2


def _ctx(**over):
    # distinct bank objects so ``slot.bank is ctx.<bank>`` identity checks are meaningful
    base = dict(
        common_bank=bytearray(b"C"), level_bank=bytearray(b"L"), wide_bank=bytearray(b"W"),
        wide_bank_hi=bytearray(b"H"), compact_bank=bytearray(b"P"),
        table_75a6=[0] * 0x40, table_768e=[0] * 0x100, table_7746=[0] * 0x100, half_stride=0x200,
    )
    base.update(over)
    return SpriteDrawContext(**base)


def _slot(*, active=1, sprite_id=0x00, di0c=0x0100, di10=OFFSCREEN, anim=0, dtype=2, variant=0):
    w = [0] * _WORDS
    w[0x00 >> 1] = active
    w[0x08 >> 1] = sprite_id
    w[0x0C >> 1] = di0c
    w[0x10 >> 1] = di10
    w[0x12 >> 1] = anim
    w[0x14 >> 1] = dtype
    w[0x24 >> 1] = variant
    return tuple(w)


def _pool(*slots):
    return ObjectPool(base=0x2000, stride=_STRIDE, slots=tuple(slots))


def test_75a6_common_bank_two_slots():
    # dtype 2, id < 0x1C -> common bank; table[id] gives the offset; both +0C and +10 slots draw.
    ctx = _ctx(table_75a6=[0x40] + [0] * 0x3F, half_stride=0x200)
    slots = object_slots(0x00, 2, 0x0100, 0x0800, ctx)
    assert [(s.comp_ip, s.di, s.src_off, s.words_per_row, s.rows) for s in slots] == [
        (0x2E6E, 0x0100, 0x40, 8, 16),
        (0x2E6E, 0x0800, 0x40 + 0x200, 8, 16),   # second slot at off + half_stride
    ]


def test_75a6_level_bank_uses_id_minus_threshold():
    ctx = _ctx(table_75a6=[0] * 0x04 + [0x900] + [0] * 0x3B)   # level index = id 0x20 - 0x1C = 0x04
    slots = object_slots(0x20, 2, 0x0300, OFFSCREEN, ctx)
    assert len(slots) == 1
    assert (slots[0].comp_ip, slots[0].di, slots[0].src_off) == (0x2E6E, 0x0300, 0x900)
    # id 0x20 >= 0x1C -> level bank, table index 0x20-0x1C = 0x04
    assert slots[0].bank is ctx.level_bank


def test_768e_single_slot_wide_bank_and_threshold():
    ctx = _ctx(table_768e=[0] * 0x1D + [0xC00] + [0] * (0x100 - 0x1E))
    slots = object_slots(0x1D, 1, 0x2020, 0x0000, ctx)   # +10 ignored by 768E (single slot)
    assert len(slots) == 1
    assert (slots[0].comp_ip, slots[0].di, slots[0].src_off, slots[0].words_per_row, slots[0].rows) == (
        0x2F81, 0x2020, 0xC00, 4, 16)
    assert slots[0].bank is ctx.wide_bank
    # id >= 0xFA -> secondary (2X2C) bank, index id-0xFA (= 1 for 0xFB)
    hi_ctx = _ctx(table_768e=[0, 0x10] + [0] * 0xFE)
    hi = object_slots(0xFB, 1, 0x2020, OFFSCREEN, hi_ctx)
    assert hi[0].bank is hi_ctx.wide_bank_hi and hi[0].src_off == 0x10


def test_7746_compact_single_8row_blit():
    ctx = _ctx(table_7746=[0] * 0x32 + [0xC80] + [0] * (0x100 - 0x33))
    slots = object_slots(0x32, 0, 0x467A, OFFSCREEN, ctx)
    assert len(slots) == 1
    assert (slots[0].comp_ip, slots[0].di, slots[0].src_off, slots[0].words_per_row, slots[0].rows) == (
        0x2FB6, 0x467A, 0xC80, 2, 8)
    assert slots[0].bank is ctx.compact_bank


def test_offscreen_and_unknown_drawtype_skip():
    ctx = _ctx()
    assert object_slots(0x1D, 1, OFFSCREEN, 0x10, ctx) == []      # 768E off-screen +0C
    assert object_slots(0x00, 2, OFFSCREEN, OFFSCREEN, ctx) == []  # 75A6 both off-screen
    assert object_slots(0x00, 5, 0x0100, OFFSCREEN, ctx) == []     # dtype 5 not a sprite routine


def test_object_sprite_blocks_anim_skips_variant_whitens():
    # 256-byte 2F81 cell (4 words x 16 rows x 4), fully opaque, data nibble 0x22.
    cell = bytes((0x00, 0x00, 0x22, 0x22)) * (4 * 16)
    ctx = _ctx(wide_bank=cell, table_768e=[0] * 0x100)
    active = _pool(_slot(sprite_id=0, di0c=0x0100, dtype=1))
    assert len(object_sprite_blocks(active, ctx)) == 1
    # anim 1..7 route to the 7688 NO-DRAW stub in every (anim x variant) sub-table -- skipped.
    for skip in (_slot(sprite_id=0, di0c=0x0100, dtype=1, anim=1),
                 _slot(sprite_id=0, di0c=0x0100, dtype=1, active=0)):
        assert object_sprite_blocks(_pool(skip), ctx) == []
    # variant != 0 (anim 0) draws the OR-INVERTED compositor (2F40): dest |= ~mask -- the
    # opaque silhouette saturated to colour 0xF (the hit-flash whiteout).
    flash = object_sprite_blocks(
        _pool(_slot(sprite_id=0, di0c=0x0100, dtype=1, variant=0xFFFF)), ctx)
    assert len(flash) == 1
    assert flash[0].opaque.all()
    assert (flash[0].pixels == 0x0F).all()
