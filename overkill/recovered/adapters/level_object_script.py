"""The LEVEL OBJECT SCRIPT walker (``1010:4A65``) -- the scene-content spawner, memory-shaped.

Each planet has a STATIC spawn script (cold == live, test-pinned): the pointer table
``DS:C5E9 + planet*2`` names a CURSOR CELL (``C5F5..C5FF``) holding the current script position
(cold value = the script head ``C85C/C8DE/CA02/CC36/CC80/CCAA``).  Entries fire as the level
scrolls: each is ``(trigger_row, [optional FFFF flag], groupdef_ptr, x_base, y_base)`` and fires
when ``trigger_row == DS:A978`` (the scroll row counter); multiple entries can fire on one row
(the walker loops until the next trigger differs).  The groupdef is ``(scan +0x14, gate +0x0A,
behavior +0x18, count)`` followed by ``count`` position word-pairs.

Per spawn (``7524`` alloc; an alloc failure aborts the group and moves to the next entry):
the record stamp (type 4, +2 = pair[1]+y_base, +4/+0x32 = pair[0]+x_base, +6 = 4, HP +0x20 =
planet+1 or 0x0C when scan != 1, +0x24 = 0), the ``2078`` completion-counter registration
(``1F8F:0163``: first free of 16 byte-pair slots when the entry KIND -- ``C81A[trigger & 0x3F]``
-- is nonzero; the member count in the low byte, the kind in the high; ``+0x28`` = the slot index,
consumed by the recovered BFC7 completion-drop), and for CONTROLLER behaviors the ``1F8F:0209``
init with the behavior's SPAWN schedule (0x1F -> A82E etc. -- distinct from the C054 death-chain
bases), HP 0x14, ``A47E = 1``, ``A480 = 0x64``.

The GROUND-object path (scan == 1 AND gate != 1: 16px tile snap + the 209C/20A0 tile prep,
``1010:4B4A..4BE7``) is a declared gap until its decode lands -- fail-loud, never guessed.
Called from the frame flow at ``1010:A83C``; verified by ``probes/verify_native_level_script``.
"""
from __future__ import annotations

from overkill.recovered.domain.gaps import RecoveryGap

DS = 0x25CC
SCRIPT_PTR_TABLE_C5E9 = 0xC5E9
KIND_TABLE_C81A = 0xC81A
COUNTER_TABLE_2078 = 0x2078
COUNTER_SLOTS = 0x10
#: spawn-time controller schedules (1F8F:0209), distinct from the C054 death-chain bases
CONTROLLER_SPAWN_SCHEDULES = {0x13: 0xA484, 0x15: 0xA4E8, 0x1C: 0xA7A2, 0x1F: 0xA82E,
                              0x7D: 0xA638, 0x7E: 0xA6F4}

EFFECT_POOL_BASE, EFFECT_POOL_WRAP, EFFECT_SLOTS = 0x23B4, 0x2B5C, 0x23


def _alloc_7524(mem) -> int:
    cur = mem.rw(DS, 0x95D8)
    for _ in range(EFFECT_SLOTS):
        if mem.rw(DS, cur) == 0:
            mem.ww(DS, 0x95D8, cur)
            return cur
        cur = cur + 0x38
        if cur == EFFECT_POOL_WRAP:
            cur = EFFECT_POOL_BASE
    return 0xFFFF


def _counter_prep_0163(mem) -> None:
    """``1F8F:0163``: pick the first free 2078 completion-counter slot when the kind is nonzero."""
    if mem.rw(DS, 0x2070) != 0:
        addr = COUNTER_TABLE_2078
        for idx in range(COUNTER_SLOTS):
            if mem.rb(DS, addr) == 0:
                mem.ww(DS, 0x2098, idx)
                mem.ww(DS, 0x209A, addr)
                return
            addr += 2
    mem.ww(DS, 0x209A, 0xFFFF)


def run_level_object_script_4a65(mem) -> None:
    """Fire every script entry whose trigger row equals ``DS:A978`` (in place over ``mem``)."""
    planet = mem.rw(DS, 0x2356)
    cell = mem.rw(DS, (SCRIPT_PTR_TABLE_C5E9 + planet * 2) & 0xFFFF)
    while True:
        si = mem.rw(DS, cell)
        trigger = mem.rw(DS, si)
        mem.ww(DS, 0x20A4, trigger)
        if trigger == 0xFFFF or trigger != mem.rw(DS, 0xA978):
            return
        si += 2
        flag = 1
        w = mem.rw(DS, si)
        if w == 0xFFFF:
            flag = 0
            si += 2
            w = mem.rw(DS, si)
        mem.wb(DS, 0x20A2, flag)
        group = w
        mem.ww(DS, 0x206C, mem.rw(DS, si + 2))
        mem.ww(DS, 0x206E, mem.rw(DS, si + 4))
        kind = mem.rb(DS, (KIND_TABLE_C81A + (trigger & 0x3F)) & 0xFFFF)
        mem.ww(DS, 0x2070, kind)
        mem.ww(DS, cell, si + 6)          # the cursor advances past this entry (4AB6)
        # the groupdef
        scan = mem.rw(DS, group)
        gate = mem.rw(DS, group + 2)
        beh = mem.rw(DS, group + 4)
        count = mem.rw(DS, group + 6)
        mem.ww(DS, 0x2072, scan)
        mem.ww(DS, 0x2074, gate)
        mem.ww(DS, 0x2076, beh)
        _counter_prep_0163(mem)
        pos = group + 8
        for _ in range(count):
            slot = _alloc_7524(mem)
            if slot == 0xFFFF:
                break                      # 4C70: abort the group, next entry
            counter_addr = mem.rw(DS, 0x209A)
            if counter_addr != 0xFFFF:
                mem.wb(DS, counter_addr, mem.rb(DS, counter_addr) + 1)
                mem.wb(DS, counter_addr + 1, mem.rw(DS, 0x2070) & 0xFF)
                mem.ww(DS, slot + 0x28, mem.rw(DS, 0x2098))
            else:
                mem.ww(DS, slot + 0x28, 0xFFFF)
            mem.ww(DS, slot + 0x00, 1)
            mem.ww(DS, slot + 0x0A, gate)
            mem.ww(DS, slot + 0x08, 0)
            mem.ww(DS, slot + 0x02, (mem.rw(DS, pos + 2) + mem.rw(DS, 0x206E)) & 0xFFFF)
            y = (mem.rw(DS, pos) + mem.rw(DS, 0x206C)) & 0xFFFF
            mem.ww(DS, slot + 0x04, y)
            mem.ww(DS, slot + 0x32, y)
            mem.ww(DS, slot + 0x34, 0)
            mem.ww(DS, slot + 0x06, 4)
            mem.ww(DS, slot + 0x14, scan)
            mem.ww(DS, slot + 0x16, 4)
            mem.ww(DS, slot + 0x18, beh)
            if gate != 1 and scan == 1:
                raise RecoveryGap(f"ground-object tile snap (behavior {beh:#x})",
                                  "the 4B4A..4BE7 snap + 209C/20A0 tile prep is not decoded yet")
            # the 4BE7 tail
            hp = (planet + 1) & 0xFFFF if scan == 1 else 0x000C
            mem.ww(DS, slot + 0x20, hp)
            mem.ww(DS, slot + 0x24, 0)
            if beh in CONTROLLER_SPAWN_SCHEDULES:
                mem.ww(DS, 0xA482, CONTROLLER_SPAWN_SCHEDULES[beh])
                mem.ww(DS, 0xA842, 0xA844)
                mem.ww(DS, slot + 0x20, 0x0014)
                mem.ww(DS, 0xA47E, 1)
                mem.ww(DS, 0xA480, 0x0064)
                mem.ww(DS, 0x2342, 1)      # the 0223.. wave-state flags + the wave-clock reset
                mem.ww(DS, 0x2344, 1)
                mem.ww(DS, 0x2346, 0)
                mem.ww(DS, 0x2348, 0)
                mem.ww(DS, 0xA7A0, 0)
            elif beh == 0x21:
                raise RecoveryGap("script-spawned wave driver (behavior 0x21)",
                                  "the 4C03 path calls 1F8F:0209 with a leftover-ax schedule")
            pos += 4
