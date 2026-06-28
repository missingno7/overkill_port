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
    OFF_TARGET_X,
    OFF_TARGET_Y,
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
    # Enriched target-position fields, with signed convenience properties.
    assert rec.target_x_word == pool.word_at(1, OFF_TARGET_X)
    assert rec.target_y_word == pool.word_at(1, OFF_TARGET_Y)
    assert rec.target_x == rec.target_x_word and rec.target_y == rec.target_y_word


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


def _pool_from_active(active_list):
    """An ObjectPool whose slots carry the given active words (other words zero)."""
    base, stride = GAMEPLAY_OBJECT_TABLE_BASE, OBJECT_SLOT_STRIDE
    slots = tuple((a & 0xFFFF,) + (0,) * ((stride >> 1) - 1) for a in active_list)
    return ObjectPool(base=base, stride=stride, slots=slots)


def test_object_pool_find_free_is_pure():
    from overkill.recovered.systems.objects import object_pool_find_free

    base, stride = GAMEPLAY_OBJECT_TABLE_BASE, OBJECT_SLOT_STRIDE
    # First zero-active slot wins; the cursor parks there.
    r = object_pool_find_free(_pool_from_active([1, 1, 0, 1]), base)
    assert r.offset == base + 2 * stride and r.cursor == base + 2 * stride
    # Every slot occupied -> None, cursor unchanged.
    r = object_pool_find_free(_pool_from_active([1, 1, 1]), base)
    assert r.offset is None and r.cursor == base
    # Cursor mid-table wraps at the table end back to a free slot 0.
    r = object_pool_find_free(_pool_from_active([0, 1, 1, 1]), base + 2 * stride)
    assert r.offset == base and r.cursor == base


def test_object_pool_find_free_matches_vm_allocator():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory as _Memory
    from overkill.gameplay.object_spawns import _find_free_object_slot_7573
    from overkill.recovered.systems.objects import object_pool_find_free

    base, stride, count = GAMEPLAY_OBJECT_TABLE_BASE, OBJECT_SLOT_STRIDE, GAMEPLAY_OBJECT_TABLE_COUNT

    def run(free_indices, cursor):
        mem = _Memory()
        cpu = CPU8086(mem, CPUState(cs=0x1010, ds=0x1010, ss=0x3000, bp=0, sp=0x8000, flags=0x0202))
        for i in range(count):
            mem.ww(0x1010, (base + i * stride) & 0xFFFF, 0 if i in free_indices else 1)
        mem.ww(0x1010, 0x95DA, cursor & 0xFFFF)
        pool = read_object_pool(mem, 0x1010, base, count)
        vm_offset = _find_free_object_slot_7573(cpu) & 0xFFFF
        vm_cursor = mem.rw(0x1010, 0x95DA)
        native = object_pool_find_free(pool, cursor)
        return vm_offset, vm_cursor, native

    # First slot free.
    vm_off, vm_cur, nat = run({0}, base)
    assert vm_off != 0xFFFF and nat.offset == vm_off == base and nat.cursor == vm_cur
    # First few occupied, slot 3 free.
    vm_off, vm_cur, nat = run({3}, base)
    assert nat.offset == vm_off == base + 3 * stride and nat.cursor == vm_cur
    # Cursor mid-table, only slot 0 free -> the per-iteration wrap reaches it.
    vm_off, vm_cur, nat = run({0}, base + 5 * stride)
    assert nat.offset == vm_off == base and nat.cursor == vm_cur
    # Every slot occupied -> 0xFFFF / None, cursor unchanged.
    vm_off, vm_cur, nat = run(set(), base)
    assert vm_off == 0xFFFF and nat.offset is None and nat.cursor == base


def test_object_spawn_seed_a4ea_template_values():
    """The pure A4EA spawn template matches the constants the 1010:A4EA stamp
    writes at A4ED..A50F (offsets in comments).  The byte-exact runtime behaviour
    is guarded by test_object_spawn_seed_a4ea_free_path_matches_original; this
    locks the recovered field values in the pure layer, where both the A4EA and
    A4D7 adapters now read them from."""
    from overkill.recovered.systems.objects import object_spawn_seed_a4ea

    seed = object_spawn_seed_a4ea()
    assert seed.active_word == 0x0001           # ds:[bx+00]
    assert seed.scan_enable_or_solid == 0x0001  # ds:[bx+1E]
    assert seed.direction_or_step == 0x0000     # ds:[bx+06]
    assert seed.sprite_or_state == 0x0032       # ds:[bx+08]
    assert seed.scan_flag == 0x0000             # ds:[bx+14]
    assert seed.hazard_class == 0x0002          # ds:[bx+16]
    assert seed.logic_id == 0x0002              # ds:[bx+18]
    assert seed.substate == 0xFFFF              # ds:[bx+1C]
