"""The 7948 TILE-CUE spawner -- terrain actors spawned from special tile ids as rows scroll in.

``A81B`` (the scroll's row pull) calls ``7948`` for every pulled plane row when
``row_base <= 0xE52``: 13 plane bytes are walked (``si = [A408]``, ``[A40A] += 0x10`` per tile)
and each tile id is dispatched through the PLANET-KEYED handler table ``DS:[95DE + planet*2]``.
A matching id spawns a record: the id's stub consumes the cue (a 2x2 plane clear at the id
cell), allocates via the RECOVERED 7524 effect-pool allocator, stamps the common fields, and
sets the behavior/sprite/direction.  Without this system the native runtime never spawns
terrain-cued actors (crawlers, turrets, the deployer) -- invisible to the walk shadow, which
replays VM states with the spawns already present.

PLANET 1 (handler ``1010:7977``) is implemented here, byte-verified by
``verify_native_tile_cues`` driving the ORIGINAL 7948 on the planet-1 snapshot; the other
planets' handlers fail loud until each is decoded and driven the same way.

The spawn commons, from the disassembly (the driven gate pins every byte):

* ``81E9``: 7524 alloc -> the ``8209`` stamp block {+28=FFFF, +00=1, +0A=1, +02=[bp+2],
  +34=[bp+2], +04=[bp+4], +32=[bp+4], +06=4, +14=1, +16=4, +18=0x14, +20=4, +24=0} -- the
  ``[bp+2]/[bp+4]`` reads leak the CALLER's frame (reproduced from the driven oracle);
* ``81CC`` (= the tail of 81C9): 81E9 then OVERRIDES {+04=[A40A], +02=0x10, +0A=0};
* ``81C9``: ``call 7E58`` first (a pre-hook, no record effect observed in the drive) then 81CC;
* ``819E``: 81C9 then the linked-counter tail (``[209A] != FFFF``: ``inc [[209A]]``,
  ``[[209A]+1] = [2070]``, ``+28 = [2098]``);
* ``7A40``: the alternate stamp {+16=4, +04=[A40A], +00=1, +0A=0, +02=0, +14=2, +24=0,
  +20=0x0A, +28=FFFF} used by the 79BA/79D6/79F7 stub family (not planet 1's ids).
"""
from __future__ import annotations

from overkill.recovered.adapters.behavior_walk import (EFFECT_POOL_BASE, EFFECT_POOL_WRAP,
                                                       EFFECT_SLOTS, _alloc)
from overkill.recovered.domain.gaps import RecoveryGap

DS = 0x25CC
CS = 0x1010
TILES_PER_ROW = 13
ROW_GATE = 0x0E52          # A831: rows above this never run the cue walk


def run_tile_cue_row_7948(mem, row_base: int, leak_32: int = 0, leak_34: int = 0) -> "list[int]":
    """Walk one pulled plane row's 13 tiles and run the planet's cue handler per id.

    Returns the spawned record offsets (possibly empty).  Mirrors 7948 exactly: the plane is
    read AND MUTATED through the image's own plane segment (the consume writes), ``[A40A]``
    steps 0x10 per tile.  Fails loud for planets whose handler is not yet recovered."""
    planet = mem.rw(DS, 0x2356)
    if planet == 0:
        raise RecoveryGap("tile-cue handler for planet 0 (1010:7BCB)",
                          "the mothership's cue handler far-calls deeper overlay machinery -- "
                          "decode + drive it before scrolling its terrain")
    plane_seg = mem.rw(CS, 0x9592)
    spawned: list[int] = []
    mem.ww(DS, 0xA408, row_base & 0xFFFF)
    for k in range(TILES_PER_ROW):
        si = (row_base + k) & 0xFFFF
        tile_id = mem.rb(plane_seg, si)
        y_a40a = (k * 0x10) & 0xFFFF
        mem.ww(DS, 0xA40A, y_a40a)
        cue = {1: _planet1_cue, 2: _planet2_cue, 3: _planet3_cue,
               4: _planet4_cue, 5: _planet5_cue}[planet]
        rec = cue(mem, plane_seg, si, tile_id, y_a40a, leak_32, leak_34)
        if rec is not None:
            spawned.append(rec)
    mem.ww(DS, 0xA40A, (TILES_PER_ROW * 0x10) & 0xFFFF)   # the loop's final += 0x10
    return spawned


#: planet 1's id -> (behavior +0x18, sprite +0x08 or None, direction +0x06 or None) stamps,
#: applied AFTER the 81C9/819E common (the 7977..79A5 dispatch).
_PLANET1_STAMPS = {
    0x04: (0x8B, None, None),          # 7A6E: the ground crawler (A952 = -1 family)
    0x07: (0x8C, None, None),          # 7A7A: the ground crawler (+1 family)
    0x6C: (0x24, 0x8F, 0x06),          # 7AAE
    0x6D: (0x25, 0x90, 0x02),          # 7AC4
    0xAC: (0x90, 0x89, 0x06),          # 7ADA
    0xB1: (0x91, 0x8C, 0x02),          # 7AF0
    0xC9: (0x28, 0x1C, 0x00),          # 7A11: the deployer (a 4-cell consume, beh 0x28)
}


def _planet1_cue(mem, plane_seg: int, si: int, tile_id: int, y_a40a: int,
                 leak_32: int, leak_34: int) -> "int | None":
    if tile_id not in _PLANET1_STAMPS:
        return None
    beh, spr, direction = _PLANET1_STAMPS[tile_id]
    if tile_id == 0xC9:
        # 7A11: the deployer consumes its 2x2 with DISTINCT ids 26/27/28/29 (still non-cue values)
        mem.wb(plane_seg, (si + 13) & 0xFFFF, 0x26)
        mem.wb(plane_seg, (si + 14) & 0xFFFF, 0x27)
        mem.wb(plane_seg, si, 0x28)
        mem.wb(plane_seg, (si + 1) & 0xFFFF, 0x29)
        slot = _alloc(mem, 0x95D8, EFFECT_POOL_BASE, EFFECT_POOL_WRAP, EFFECT_SLOTS)
        if slot == 0xFFFF:
            return None
        _stamp_7a40(mem, slot, y_a40a)
        mem.ww(DS, slot + 0x18, beh)
        mem.ww(DS, slot + 0x08, spr)
        mem.ww(DS, slot + 0x06, direction)
        return slot
    # ids 0x04/0x07 go through 81C9 = 7E58 (consume: plane[si] = 1) + 81CC; the others call
    # 81CC DIRECTLY (no consume).  Then the 8209 block + the 81CC overrides.
    if tile_id in (0x04, 0x07):
        mem.wb(plane_seg, si, 0x01)
    slot = _alloc(mem, 0x95D8, EFFECT_POOL_BASE, EFFECT_POOL_WRAP, EFFECT_SLOTS)
    if slot == 0xFFFF:
        return None
    _stamp_8209(mem, slot, leak_32, leak_34)
    mem.ww(DS, slot + 0x04, y_a40a)      # 81CC overrides
    mem.ww(DS, slot + 0x02, 0x0010)
    mem.ww(DS, slot + 0x0A, 0x0000)
    mem.ww(DS, slot + 0x18, beh)
    if spr is not None:
        mem.ww(DS, slot + 0x08, spr)
    if direction is not None:
        mem.ww(DS, slot + 0x06, direction)
    return slot


def _stamp_8209(mem, slot: int, leak_32: int, leak_34: int) -> None:
    """The 81E9 -> 8209 common stamp.  ``+0x32``/``+0x34`` are the ASM's ``[bp+4]``/``[bp+2]``
    CALLER-FRAME reads (a leak; the caller supplies the frame's live values -- the driven gate
    pins them byte-exact, see verify_native_tile_cues)."""
    mem.ww(DS, slot + 0x32, leak_32)
    mem.ww(DS, slot + 0x34, leak_34)
    mem.ww(DS, slot + 0x28, 0xFFFF)
    mem.ww(DS, slot + 0x00, 0x0001)
    mem.ww(DS, slot + 0x0A, 0x0001)
    mem.ww(DS, slot + 0x06, 0x0004)
    mem.ww(DS, slot + 0x14, 0x0001)
    mem.ww(DS, slot + 0x16, 0x0004)
    mem.ww(DS, slot + 0x18, 0x0014)
    mem.ww(DS, slot + 0x20, 0x0004)
    mem.ww(DS, slot + 0x24, 0x0000)


def _stamp_7a40(mem, slot: int, y_a40a: int, write_28: bool = True) -> None:
    mem.ww(DS, slot + 0x16, 0x0004)
    mem.ww(DS, slot + 0x04, y_a40a)
    mem.ww(DS, slot + 0x00, 0x0001)
    mem.ww(DS, slot + 0x0A, 0x0000)
    mem.ww(DS, slot + 0x02, 0x0000)
    mem.ww(DS, slot + 0x14, 0x0002)
    mem.ww(DS, slot + 0x24, 0x0000)
    mem.ww(DS, slot + 0x20, 0x000A)
    if write_28:
        mem.ww(DS, slot + 0x28, 0xFFFF)


def _planet2_cue(mem, plane_seg: int, si: int, tile_id: int, y_a40a: int,
                 leak_32: int, leak_34: int) -> "int | None":
    """Planet 2's ``1010:7B06`` handler: id 0x30 -> the 0x2A turret (a direct 7524 alloc + the
    inline 7A40-shape stamp, NO consume/leak); id 0x5A -> beh 0x2E with ``x -= 6``; id 0xC4 ->
    beh 0x8F spr 0xBF dir 6 (spr 0xC2 dir 2 when the spawned ``y <= 0x60``) -- both via the
    81C9 common (consume + alloc + the 8209 leak stamp + the 81CC overrides)."""
    if tile_id == 0x30:                          # 7B13
        slot = _alloc(mem, 0x95D8, EFFECT_POOL_BASE, EFFECT_POOL_WRAP, EFFECT_SLOTS)
        if slot == 0xFFFF:
            return None
        _stamp_7a40(mem, slot, y_a40a, write_28=False)   # 7B1C..: the inline stamp, no +28 write
        mem.ww(DS, slot + 0x18, 0x002A)
        mem.ww(DS, slot + 0x08, 0x001C)
        mem.ww(DS, slot + 0x06, 0x0000)
        return slot
    if tile_id not in (0x5A, 0xC4):
        return None
    # the 81C9 common: 7E58 consume + 81E9 (alloc + the 8209 block) + the 81CC overrides
    mem.wb(plane_seg, si, 0x01)
    slot = _alloc(mem, 0x95D8, EFFECT_POOL_BASE, EFFECT_POOL_WRAP, EFFECT_SLOTS)
    if slot == 0xFFFF:
        return None
    _stamp_8209(mem, slot, leak_32, leak_34)
    mem.ww(DS, slot + 0x04, y_a40a)
    mem.ww(DS, slot + 0x02, 0x0010)
    mem.ww(DS, slot + 0x0A, 0x0000)
    if tile_id == 0x5A:                          # 7B54
        mem.ww(DS, slot + 0x18, 0x002E)
        mem.ww(DS, slot + 0x02, (mem.rw(DS, slot + 0x02) - 6) & 0xFFFF)
        return slot
    # 0xC4 (7B64): beh 0x8F spr 0xBF dir 6; y <= 0x60 -> spr 0xC2 dir 2
    mem.ww(DS, slot + 0x18, 0x008F)
    mem.ww(DS, slot + 0x08, 0x00BF)
    mem.ww(DS, slot + 0x06, 0x0006)
    if mem.rw(DS, slot + 0x04) <= 0x0060:
        mem.ww(DS, slot + 0x08, 0x00C2)
        mem.ww(DS, slot + 0x06, 0x0002)
    return slot


#: planet 3's parsed cue stubs (the 7C6A jump table, ids 0xCE..0xEB; mechanically parsed from
#: the stub bodies and pinned by the driven gate): id -> (common, writes, y<=0x60 writes).
#: common "819E" adds the linked-counter tail over "81C9".
_PLANET3_CUES = {
    0xCE: ("81C9", ((0x06, 6), (0x18, 0x86), (0x08, 0xC8)), ((0x08, 0xDA), (0x06, 2))),
    0xCF: ("81C9", ((0x06, 6), (0x18, 0x86), (0x08, 0xC8)), ((0x08, 0xDA), (0x06, 2))),
    0xD0: ("81C9", ((0x06, 7), (0x18, 0x54), (0x08, 0xF5)), ((0x06, 1), (0x08, 0xF4))),
    0xD1: ("81C9", ((0x06, 7), (0x18, 0x54), (0x08, 0xF5)), ((0x06, 1), (0x08, 0xF4))),
    0xD2: ("81C9", ((0x06, 6), (0x18, 0x87), (0x08, 0xE0)), ((0x06, 2), (0x08, 0xDD))),
    0xD3: ("81C9", ((0x06, 6), (0x18, 0x87), (0x08, 0xE0)), ((0x06, 2), (0x08, 0xDD))),
    0xD4: ("81C9", ((0x18, 0x55), (0x08, 0x77)), None),
    0xD5: ("819E", ((0x18, 0x83),), None),
    0xD6: ("81C9", ((0x06, 6), (0x18, 0x5F)), ((0x06, 2),)),
    0xD7: ("81C9", ((0x06, 2), (0x18, 0x63), (0x08, 0xE7)), None),
    0xD8: ("81C9", ((0x06, 7), (0x18, 0x59), (0x08, 0xE3)), ((0x06, 1),)),
    0xD9: ("81C9", ((0x18, 0x58), (0x08, 0x99), (0x06, 2)), None),
    0xDA: ("81C9", ((0x18, 0x57), (0x08, 0x9B), (0x06, 6)), None),
    0xDB: ("819E", ((0x18, 0x19),), None),
    0xDC: ("819E", ((0x18, 0x89),), None),
    0xDD: ("81C9", ((0x18, 0x8C),), None),
    0xDE: ("81C9", ((0x18, 0x8B),), None),
    0xE0: ("81C9", ((0x18, 0x4F),), None),
    0xE1: ("819E", ((0x18, 0x37),), None),
    0xE2: ("819E", ((0x06, 0), (0x18, 0x2D)), None),
    0xE3: ("819E", ((0x06, 4), (0x18, 0x5E), (0x08, 0x27)), None),
    0xE4: ("819E", ((0x06, 4), (0x18, 0x5D), (0x08, 0x77)), None),
    0xE5: ("81C9", ((0x18, 0x34),), None),
    0xE6: ("81C9", ((0x18, 0x34),), None),
    0xE7: ("81C9", ((0x06, 0), (0x18, 0x5B), (0x08, 0x74)), None),
    0xE8: ("819E", ((0x06, 6), (0x18, 0x47)), None),
    0xE9: ("819E", ((0x18, 0x35),), None),
}
#: planet-3 ids whose targets are NOT the regular stub shape (special machinery) -- fail loud.
_PLANET3_SPECIAL = {0xDF: 0x44AF, 0xEA: 0xAC3C, 0xEB: 0x0375}


def _linked_counter_alloc_1f8f0163(mem) -> None:
    """The far ``1F8F:0163`` common: when the column key ``[2070]`` is ZERO the alloc SKIPS
    straight to FFFF (0165: ``cmp [2070],0; jz -> bx=FFFF`` -- key-0 columns get no linked
    counter); otherwise scan the 16-entry ``2078`` byte-slot table for a free one; ``[2098]`` =
    the index walked, ``[209A]`` = the slot pointer (FFFF when full)."""
    if mem.rw(DS, 0x2070) == 0:
        mem.ww(DS, 0x209A, 0xFFFF)
        return
    count = 0
    ptr = None
    for idx in range(16):
        p = 0x2078 + idx * 2
        if mem.rb(DS, p) == 0:
            ptr = p
            break
        count += 1
    mem.ww(DS, 0x2098, count)
    mem.ww(DS, 0x209A, 0xFFFF if ptr is None else ptr)


def _planet3_cue(mem, plane_seg: int, si: int, tile_id: int, y_a40a: int,
                 leak_32: int, leak_34: int) -> "int | None":
    """Planet 3's ``1010:7C3F`` handler: ids 0xCE..0xEB through the 7C6A jump table.  The head
    runs a COMMON pre-step for every in-range id: ``[2070] = [0xC81A + (si & 0x3F)]`` (the
    per-column key) + the ``1F8F:0163`` linked-counter alloc; then the id's stub."""
    if not (0xCE <= tile_id <= 0xEB):
        return None
    if tile_id in _PLANET3_SPECIAL:
        raise RecoveryGap(f"planet-3 tile cue {tile_id:#04x} -> 1010:{_PLANET3_SPECIAL[tile_id]:04X}",
                          "a non-stub special cue target -- decode it before this terrain row")
    mem.ww(DS, 0x2070, mem.rb(DS, (0xC81A + (si & 0x3F)) & 0xFFFF))
    _linked_counter_alloc_1f8f0163(mem)
    common, writes, y_writes = _PLANET3_CUES[tile_id]
    # 81C9/819E: 7E58 consume + 81E9 (alloc + the 8209 block) + the 81CC overrides
    mem.wb(plane_seg, si, 0x01)
    slot = _alloc(mem, 0x95D8, EFFECT_POOL_BASE, EFFECT_POOL_WRAP, EFFECT_SLOTS)
    if slot == 0xFFFF:
        return None
    _stamp_8209(mem, slot, leak_32, leak_34)
    mem.ww(DS, slot + 0x04, y_a40a)
    mem.ww(DS, slot + 0x02, 0x0010)
    mem.ww(DS, slot + 0x0A, 0x0000)
    if common == "819E":                 # the 81A7 linked-counter tail
        ptr = mem.rw(DS, 0x209A)
        if ptr != 0xFFFF:
            mem.wb(DS, ptr, (mem.rb(DS, ptr) + 1) & 0xFF)
            mem.wb(DS, (ptr + 1) & 0xFFFF, mem.rw(DS, 0x2070) & 0xFF)
            mem.ww(DS, slot + 0x28, mem.rw(DS, 0x2098))
        else:
            mem.ww(DS, slot + 0x28, 0xFFFF)
    for off, val in writes:
        mem.ww(DS, slot + off, val)
    if y_writes is not None and mem.rw(DS, slot + 0x04) <= 0x0060:
        for off, val in y_writes:
            mem.ww(DS, slot + off, val)
    return slot


#: planets 4/5: parsed like planet 3 (the same stub shapes; pinned by the driven gate).
_PLANET4_CUES = {
    0xCE: ("81C9", ((0x18, 0x8C),), None),
    0xCF: ("81C9", ((0x18, 0x8B),), None),
    0xD0: ("81C9", ((0x18, 0x58), (0x08, 0x99), (0x06, 2)), None),
    0xD1: ("81C9", ((0x18, 0x57), (0x08, 0x9B), (0x06, 6)), None),
    0xD4: ("81C9", ((0x06, 6), (0x18, 0x5F)), ((0x06, 2),)),
    0xD5: ("819E", ((0x06, 4), (0x18, 0x8A)), None),
    0xD6: ("81C9", ((0x18, 0x4F),), None),
    0xD7: ("81C9", ((0x06, 7), (0x18, 0x59), (0x08, 0xE3)), ((0x06, 1),)),
    0xD8: ("819E", ((0x18, 0x83),), None),
    0xD9: ("819E", ((0x06, 4), (0x18, 0x5D), (0x08, 0x77)), None),
    0xDA: ("81C9", ((0x18, 0x38), (0x06, 3)), None),
    0xDB: ("81C9", ((0x18, 0x38), (0x06, 5)), None),
    0xDC: ("81C9", ((0x18, 0x34),), None),
    0xDE: ("81C9", ((0x18, 0x69),), None),
    0xDF: ("819E", ((0x18, 0x35),), None),
    0xE0: ("819E", ((0x06, 4), (0x18, 0x5E), (0x08, 0x27)), None),
}
_PLANET5_CUES = {
    0xD7: ("819E", ((0x18, 0x8D),), None),
    0xD8: ("819E", ((0x18, 0x8E),), None),
    0xDA: ("81C9", ((0x18, 0x92), (0x08, 0x15A), (0x06, 2)), None),
    0xDB: ("81C9", ((0x18, 0x92), (0x08, 0x15B), (0x06, 6)), None),
    0xDE: ("81C9", ((0x06, 6), (0x18, 0x87), (0x08, 0xE0)), ((0x06, 2), (0x08, 0xDD))),
    0xDF: ("81C9", ((0x06, 6), (0x18, 0x87), (0x08, 0xE0)), ((0x06, 2), (0x08, 0xDD))),
    0xE0: ("819E", ((0x06, 4), (0x18, 0x5D), (0x08, 0x77)), None),
    0xE3: ("81C9", ((0x06, 2), (0x18, 0x63), (0x08, 0xE7)), None),
    0xE4: ("81C9", ((0x08, 0x46), (0x18, 0x30), (0x06, 4)), None),
    0xE5: ("81C9", ((0x18, 0x58), (0x08, 0x99), (0x06, 2)), None),
    0xE6: ("81C9", ((0x18, 0x57), (0x08, 0x9B), (0x06, 6)), None),
    0xE7: ("81C9", ((0x18, 0x19), (0x06, 2)), None),
    0xE8: ("819E", ((0x18, 0x89),), None),
    0xE9: ("819E", ((0x06, 6), (0x18, 0x47)), None),
    0xEA: ("819E", ((0x18, 0x35),), None),
    0xEC: ("81C9", ((0x18, 0x4F),), None),
    0xED: ("819E", ((0x18, 0x37),), None),
    0xEE: ("819E", ((0x06, 0), (0x18, 0x2D)), None),
    0xEF: ("819E", ((0x06, 4), (0x18, 0x5E), (0x08, 0x27)), None),
    # the planet-5 inline stubs (7D70/7D86/7D9C/7DB2)
    0xBA: ("81C9", ((0x06, 0), (0x18, 0x84), (0x08, 0x156)), None),
    0xBB: ("81C9", ((0x06, 2), (0x18, 0x84), (0x08, 0x157)), None),
    0xBC: ("81C9", ((0x06, 4), (0x18, 0x84), (0x08, 0x158)), None),
    0xB6: ("81C9", ((0x06, 6), (0x18, 0x84), (0x08, 0x159)), None),
}
#: the 7D2A/7D4D planet-conditional stubs (0x54 divers; the alt sprite when planet != 4).
_DIVER_STUBS = {0x7D2A: (1, 0x172, 0x17A), 0x7D4D: (7, 0x173, 0x17B)}


def _run_cue_common(mem, plane_seg, si, y_a40a, leak_32, leak_34,
                    common, writes, y_writes) -> "int | None":
    """The shared 81C9/819E executor (consume + alloc + 8209 + 81CC + optional link + stamps)."""
    mem.wb(plane_seg, si, 0x01)
    slot = _alloc(mem, 0x95D8, EFFECT_POOL_BASE, EFFECT_POOL_WRAP, EFFECT_SLOTS)
    if slot == 0xFFFF:
        return None
    _stamp_8209(mem, slot, leak_32, leak_34)
    mem.ww(DS, slot + 0x04, y_a40a)
    mem.ww(DS, slot + 0x02, 0x0010)
    mem.ww(DS, slot + 0x0A, 0x0000)
    if common == "819E":
        _link_81a7(mem, slot)
    for off, val in writes:
        mem.ww(DS, slot + off, val)
    if y_writes is not None and mem.rw(DS, slot + 0x04) <= 0x0060:
        for off, val in y_writes:
            mem.ww(DS, slot + off, val)
    return slot


def _link_81a7(mem, slot: int) -> None:
    """The 81A7 linked-counter tail over a fresh slot."""
    ptr = mem.rw(DS, 0x209A)
    if ptr != 0xFFFF:
        mem.wb(DS, ptr, (mem.rb(DS, ptr) + 1) & 0xFF)
        mem.wb(DS, (ptr + 1) & 0xFFFF, mem.rw(DS, 0x2070) & 0xFF)
        mem.ww(DS, slot + 0x28, mem.rw(DS, 0x2098))
    else:
        mem.ww(DS, slot + 0x28, 0xFFFF)


def _pre_step(mem, si) -> None:
    mem.ww(DS, 0x2070, mem.rb(DS, (0xC81A + (si & 0x3F)) & 0xFFFF))
    _linked_counter_alloc_1f8f0163(mem)


def _diver_stub(mem, plane_seg, si, y_a40a, leak_32, leak_34, addr) -> "int | None":
    """7D2A/7D4D: 81C9 + dir/beh 0x54/spr, the sprite OVERRIDDEN when planet != 4."""
    direction, spr, spr_alt = _DIVER_STUBS[addr]
    writes = ((0x06, direction), (0x18, 0x54),
              (0x08, spr if mem.rw(DS, 0x2356) == 4 else spr_alt))
    return _run_cue_common(mem, plane_seg, si, y_a40a, leak_32, leak_34,
                           "81C9", writes, None)


def _random_link_stub_8143(mem, plane_seg, si, y_a40a, leak_32, leak_34) -> "int | None":
    """8143: on planet 5 a 4D95 draw picks 819E one time in 16 ((rand & 0xF) == 0xF), else
    81C9; beh 0x68.  The random RING advances."""
    from overkill.recovered.systems.frame_loop import canned_random_next_4d95
    common = "81C9"
    if mem.rw(DS, 0x2356) == 5:
        ring = tuple(mem.rw(DS, 0x20A8 + i * 2) for i in range(16))
        rand, nxt = canned_random_next_4d95(mem.rw(DS, 0x20A6), ring)
        mem.ww(DS, 0x20A6, nxt)
        if (rand & 0xF) == 0xF:
            common = "819E"
    return _run_cue_common(mem, plane_seg, si, y_a40a, leak_32, leak_34,
                           common, ((0x18, 0x68),), None)


def _link_stamp_stub_79ba(mem, plane_seg, si, y_a40a) -> "int | None":
    """79BA (planet 5's 0xD9): the 79A6 2x2 consume (all 1s) + 7524 + the 7A40 stamp +
    beh 0x48 dir 4 + the 81A7 LINK tail."""
    mem.wb(plane_seg, si, 0x01)
    mem.wb(plane_seg, (si + 1) & 0xFFFF, 0x01)
    mem.wb(plane_seg, (si + 13) & 0xFFFF, 0x01)
    mem.wb(plane_seg, (si + 14) & 0xFFFF, 0x01)
    slot = _alloc(mem, 0x95D8, EFFECT_POOL_BASE, EFFECT_POOL_WRAP, EFFECT_SLOTS)
    if slot == 0xFFFF:
        return None
    _stamp_7a40(mem, slot, y_a40a)
    mem.ww(DS, slot + 0x18, 0x0048)
    mem.ww(DS, slot + 0x06, 0x0004)
    _link_81a7(mem, slot)
    return slot


def _planet4_cue(mem, plane_seg: int, si: int, tile_id: int, y_a40a: int,
                 leak_32: int, leak_34: int) -> "int | None":
    """Planet 4's ``1010:7CA2``: the planet-1-shared ids (0xAC/0xB1/0xC9) + the 7CE2 table
    (ids 0xCE..0xE0; 0xE1/0xE2 target non-code -- fail loud if ever seen)."""
    if tile_id in (0xAC, 0xB1, 0xC9):
        return _planet1_cue(mem, plane_seg, si, tile_id, y_a40a, leak_32, leak_34)
    if not (0xCE <= tile_id <= 0xE2):
        return None
    if tile_id in (0xE1, 0xE2):
        raise RecoveryGap(f"planet-4 tile cue {tile_id:#04x}",
                          "the 7CE2 table's tail entries point at non-code -- decode before use")
    _pre_step(mem, si)
    if tile_id == 0xD2:
        return _diver_stub(mem, plane_seg, si, y_a40a, leak_32, leak_34, 0x7D2A)
    if tile_id == 0xD3:
        return _diver_stub(mem, plane_seg, si, y_a40a, leak_32, leak_34, 0x7D4D)
    if tile_id == 0xDD:
        return _random_link_stub_8143(mem, plane_seg, si, y_a40a, leak_32, leak_34)
    common, writes, y_writes = _PLANET4_CUES[tile_id]
    return _run_cue_common(mem, plane_seg, si, y_a40a, leak_32, leak_34,
                           common, writes, y_writes)


def _planet5_cue(mem, plane_seg: int, si: int, tile_id: int, y_a40a: int,
                 leak_32: int, leak_34: int) -> "int | None":
    """Planet 5's ``1010:7DC8``: 0x30 shared with planet 2; the inline 0xBA/0xBB/0xBC/0xB6
    stubs; 0xD2 -> the planet-1 0xB1 stub (7AF0); the 7E26 table (ids 0xD7..0xF1; 0xF0/0xF1
    target non-code -- fail loud)."""
    if tile_id == 0x30:
        return _planet2_cue(mem, plane_seg, si, 0x30, y_a40a, leak_32, leak_34)
    if tile_id in (0xBA, 0xBB, 0xBC, 0xB6):
        _pre_step(mem, si)
        common, writes, y_writes = _PLANET5_CUES[tile_id]
        return _run_cue_common(mem, plane_seg, si, y_a40a, leak_32, leak_34,
                               common, writes, y_writes)
    if tile_id == 0xD2:
        return _planet1_cue(mem, plane_seg, si, 0xB1, y_a40a, leak_32, leak_34)
    # the compare CHAIN catches these BEFORE the sub-D7 table (whose index-0/1 entries are dead):
    if tile_id == 0xD7:
        return _planet1_cue(mem, plane_seg, si, 0x07, y_a40a, leak_32, leak_34)   # 7A7A
    if tile_id == 0xD8:
        return _planet1_cue(mem, plane_seg, si, 0x04, y_a40a, leak_32, leak_34)   # 7A6E
    if tile_id == 0xD3:
        return _planet1_cue(mem, plane_seg, si, 0xAC, y_a40a, leak_32, leak_34)   # 7ADA
    if not (0xD7 <= tile_id <= 0xF1):
        return None
    if tile_id in (0xF0, 0xF1):
        raise RecoveryGap(f"planet-5 tile cue {tile_id:#04x}",
                          "the 7E26 table's tail entries point at non-code -- decode before use")
    _pre_step(mem, si)
    if tile_id in (0xE1, 0xE2):                  # 7E58: consume-only, no spawn
        mem.wb(plane_seg, si, 0x01)
        return None
    if tile_id == 0xD9:
        return _link_stamp_stub_79ba(mem, plane_seg, si, y_a40a)
    if tile_id == 0xDC:
        return _diver_stub(mem, plane_seg, si, y_a40a, leak_32, leak_34, 0x7D2A)
    if tile_id == 0xDD:
        return _diver_stub(mem, plane_seg, si, y_a40a, leak_32, leak_34, 0x7D4D)
    if tile_id == 0xEB:
        return _random_link_stub_8143(mem, plane_seg, si, y_a40a, leak_32, leak_34)
    common, writes, y_writes = _PLANET5_CUES[tile_id]
    return _run_cue_common(mem, plane_seg, si, y_a40a, leak_32, leak_34,
                           common, writes, y_writes)
