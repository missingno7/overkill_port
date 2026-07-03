"""VM-free unit tests for the object -> sprite-block bridge (native_video.object_sprites).

The byte-exact-vs-VM proof (destination + descriptor offset match 1010:75A6 across levels) is
``overkill/probes/verify_native_object_sprites.py``; this pins the pure selection/skip logic + the
descriptor-table lookup headlessly.
"""
from __future__ import annotations

import numpy as np

from overkill.native_video.object_sprites import (
    COMMON_BANK_THRESHOLD,
    TANDY_ROWS,
    TANDY_WORDS_PER_ROW,
    level_object_sprite_blocks,
)
from overkill.recovered.domain.object_slots import ObjectPool

_STRIDE = 0x38
_WORDS = _STRIDE // 2
_SPRITE_BYTES = TANDY_WORDS_PER_ROW * TANDY_ROWS * 4   # 512


def _slot(*, active=1, sprite_id=COMMON_BANK_THRESHOLD, di=0x00A0, anim=0):
    w = [0] * _WORDS
    w[0x00 >> 1] = active
    w[0x08 >> 1] = sprite_id
    w[0x0C >> 1] = di
    w[0x12 >> 1] = anim
    return tuple(w)


def _pool(slots):
    return ObjectPool(base=0x2B5C, stride=_STRIDE, slots=tuple(slots))


def _bank_with_cell(offset, fill):
    bank = bytearray(offset + _SPRITE_BYTES)
    # interleaved (mask,data) words: mask=0 (opaque) everywhere, data nibbles = fill
    for k in range(offset, offset + _SPRITE_BYTES, 4):
        bank[k] = 0x00        # mask lo (0 -> opaque)
        bank[k + 1] = 0x00    # mask hi
        bank[k + 2] = fill    # data lo
        bank[k + 3] = fill    # data hi
    return bytes(bank)


def test_level_bank_object_becomes_one_block_at_di():
    descriptor = [0x0000] + [0] * 0x20             # descriptor[0] -> offset 0
    bank = _bank_with_cell(0, 0x33)
    blocks = level_object_sprite_blocks(_pool([_slot(sprite_id=0x1C, di=0x00A0)]), bank, descriptor)
    assert len(blocks) == 1
    b = blocks[0]
    assert b.di == 0x00A0
    assert b.pixels.shape == (TANDY_ROWS, TANDY_WORDS_PER_ROW * 4)
    assert bool(b.opaque.all())                    # mask 0 -> fully opaque
    assert int(b.pixels[0, 0]) == 0x3              # data nibble 0x33 -> pixel index 3


def test_descriptor_table_is_read_not_computed():
    # non-linear table entry: sprite_id 0x1E -> table[2] = 0x40 (not (0x1E-0x1C)*0x400)
    descriptor = [0, 0, 0x40] + [0] * 0x20
    bank = _bank_with_cell(0x40, 0x77)
    blocks = level_object_sprite_blocks(_pool([_slot(sprite_id=0x1E, di=0x0200)]), bank, descriptor)
    assert len(blocks) == 1 and blocks[0].di == 0x0200
    assert int(blocks[0].pixels[0, 0]) == 0x7


def test_skips_common_bank_offscreen_inactive_and_anim():
    descriptor = [0] * 0x40
    bank = _bank_with_cell(0, 0x11)
    pool = _pool([
        _slot(sprite_id=0x01, di=0x00A0),                 # common bank -> skip
        _slot(sprite_id=0x1C, di=0xFFFF),                 # off-screen -> skip
        _slot(active=0, sprite_id=0x1C, di=0x00A0),       # inactive -> skip
        _slot(sprite_id=0x1C, di=0x00A0, anim=1),         # anim != 0 -> skip
    ])
    assert level_object_sprite_blocks(pool, bank, descriptor) == []
