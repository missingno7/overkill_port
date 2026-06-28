"""Phase 2 - native ObjectPool struct + its VM state-mirror verifier.

ObjectPool is the VM-free native snapshot of an OVERKILL object-slot table; the
state-mirror verifier proves the snapshot stays byte-faithful to the live VM table at a
checkpoint -- the invariant a standalone runtime must preserve as it takes ownership.
"""
from __future__ import annotations

import pathlib

from dos_re.memory import Memory
from overkill.recovered.domain.object_slots import ObjectPool
from overkill.recovered.views.object_slots import (
    GAMEPLAY_OBJECT_TABLE_BASE,
    GAMEPLAY_OBJECT_TABLE_COUNT,
    OBJECT_SLOT_STRIDE,
    OFF_ACTIVE_WORD,
    OFF_LOGIC_ID,
    OFF_X,
    OFF_Y,
    object_pool_mirror_mismatches,
    object_pool_slot_record,
    read_object_pool,
)

SEG = 0x1010
IMAGE = pathlib.Path(__file__).resolve().parent.parent / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"


def _planted_memory(base: int, count: int, stride: int = OBJECT_SLOT_STRIDE) -> Memory:
    mem = Memory()
    for i in range(count):
        for w in range(stride >> 1):
            mem.ww(SEG, (base + i * stride + (w << 1)) & 0xFFFF, (i * 0x100 + w) & 0xFFFF)
    return mem


def test_object_pool_is_pure_and_faithful():
    pool = ObjectPool(base=0x2B5C, stride=OBJECT_SLOT_STRIDE, slots=(tuple(range(28)), tuple(range(100, 128))))
    assert len(pool) == 2
    assert pool.words(0) == tuple(range(28))
    assert pool.word_at(0, OFF_Y) == 2          # OFF_Y=4 -> word index 2
    assert pool.word_at(1, 0x00) == 100
    # with_word is functional: returns a new pool, leaves the original untouched.
    pool2 = pool.with_word(0, OFF_Y, 0xBEEF)
    assert pool2.word_at(0, OFF_Y) == 0xBEEF
    assert pool.word_at(0, OFF_Y) == 2
    assert pool2.word_at(1, 0x00) == 100        # other slots shared/unchanged


def test_read_object_pool_snapshots_the_table():
    base, count = 0x2B5C, 4
    mem = _planted_memory(base, count)
    pool = read_object_pool(mem, SEG, base, count)
    assert len(pool) == count
    assert pool.base == base and pool.stride == OBJECT_SLOT_STRIDE
    assert pool.word_at(0, OFF_ACTIVE_WORD) == 0x000  # i=0,w=0
    assert pool.word_at(2, OFF_X) == 0x201            # i=2, OFF_X=2 -> w=1
    assert pool.word_at(3, OFF_LOGIC_ID) == 0x30C     # i=3, OFF_LOGIC_ID=0x18 -> w=12


def test_object_pool_mirror_detects_divergence():
    base, count = 0x2B5C, 3
    mem = _planted_memory(base, count)
    pool = read_object_pool(mem, SEG, base, count)
    # Faithful snapshot -> no mismatches.
    assert object_pool_mirror_mismatches(pool, mem, SEG) == ()
    # Mutate two live words; the verifier reports exactly those, with native vs vm values.
    mem.ww(SEG, (base + 1 * OBJECT_SLOT_STRIDE + OFF_Y) & 0xFFFF, 0xBEEF)
    mem.ww(SEG, (base + 2 * OBJECT_SLOT_STRIDE + OFF_LOGIC_ID) & 0xFFFF, 0xCAFE)
    mismatches = object_pool_mirror_mismatches(pool, mem, SEG)
    assert (1, OFF_Y, pool.word_at(1, OFF_Y), 0xBEEF) in mismatches
    assert (2, OFF_LOGIC_ID, pool.word_at(2, OFF_LOGIC_ID), 0xCAFE) in mismatches
    assert len(mismatches) == 2


def test_object_pool_slot_record_projection():
    base, count = 0x2B5C, 2
    mem = _planted_memory(base, count)
    pool = read_object_pool(mem, SEG, base, count)
    rec = object_pool_slot_record(pool, 1)
    assert rec.active_word == pool.word_at(1, OFF_ACTIVE_WORD)
    assert rec.x_word == pool.word_at(1, OFF_X)
    assert rec.y_word == pool.word_at(1, OFF_Y)
    assert rec.logic_id == pool.word_at(1, OFF_LOGIC_ID)


def test_object_pool_from_real_image_is_byte_faithful():
    if not IMAGE.exists():
        import pytest

        pytest.skip("runtime image artifact not present")
    mem = Memory()
    data = IMAGE.read_bytes()
    mem.data[: len(data)] = data
    pool = read_object_pool(mem, SEG, GAMEPLAY_OBJECT_TABLE_BASE, GAMEPLAY_OBJECT_TABLE_COUNT)
    assert len(pool) == GAMEPLAY_OBJECT_TABLE_COUNT
    # The snapshot mirrors the live image byte-for-byte at this checkpoint.
    assert object_pool_mirror_mismatches(pool, mem, SEG) == ()
    # Mutating the live table is detected against the now-stale snapshot.
    mem.ww(SEG, (GAMEPLAY_OBJECT_TABLE_BASE + OFF_Y) & 0xFFFF, 0x1234)
    mismatches = object_pool_mirror_mismatches(pool, mem, SEG)
    assert (0, OFF_Y, pool.word_at(0, OFF_Y), 0x1234) in mismatches
    # A record projects to plain ints (no VM reference held).
    record = object_pool_slot_record(pool, 0)
    assert isinstance(record.logic_id, int) and isinstance(record.active_word, int)
