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
bases), HP 0x14, ``A47E = 1``, ``A480 = 0x64``, plus the two calls 0209 makes at its tail:
``0854`` (the 98A2..98AC controller-counter reset) and ``0918`` (the wave-cursor rewind).

The GROUND-object path (scan == 1 AND gate != 1, ``1010:4B4A..4BE7``): snap X/Y to 16px, then
search that tile COLUMN of the level plane for the ground surface (the recovered ``5073``-shape
offset ``row_base + 0xD - x_tile*0xD + y_tile`` into the ``CS:[9592]`` plane, classified through the
``DS:C3AA`` table) -- stepping the tile row toward the surface (Y<0x60 down, else up, wrapping the
0..0xC column) until an open tile, then Y = row<<4.  So scenery sits ON the terrain.
Called from the frame flow at ``1010:A83C``; verified by ``probes/verify_native_level_script``.
"""
from __future__ import annotations

from overkill.recovered.domain.gaps import RecoveryGap

DS = 0x25CC
CODE_SEG = 0x1010
TILE_PLANE_SEG_CELL = 0x9592     # CS:[9592] -- the level tile-plane segment
TILE_CLASS_TABLE_C3AA = 0xC3AA   # DS:C3AA -- the 256-entry raw-tile -> class map (as in 505B)
TILE_COLUMN_STRIDE = 0x0D
GROUND_SEARCH_SPLIT = 0x60       # 20A0 (snapped Y) < this searches DOWN, else UP
GROUND_COLUMN_ROWS = 0x0D        # the tile-row index wraps over 0..0xC
SCRIPT_PTR_TABLE_C5E9 = 0xC5E9
KIND_TABLE_C81A = 0xC81A
COUNTER_TABLE_2078 = 0x2078
COUNTER_SLOTS = 0x10
#: spawn-time controller schedules (1F8F:0209), distinct from the C054 death-chain bases
CONTROLLER_SPAWN_SCHEDULES = {0x13: 0xA484, 0x15: 0xA4E8, 0x1C: 0xA7A2, 0x1F: 0xA82E,
                              0x7D: 0xA638, 0x7E: 0xA6F4}

EFFECT_POOL_BASE, EFFECT_POOL_WRAP, EFFECT_SLOTS = 0x23B4, 0x2B5C, 0x23

#: the overlay segment holding the controller/starfield code (``1010:A9B8`` far-calls ``1F8F:081D``)
OVERLAY_SEG = 0x1F8F
#: ``1F8F:0920`` -- a CODE-SEGMENT word: the wave-schedule cursor, walked with ``lodsw`` at 08AF
#: (``mov si,cs:[0920]``) and advanced by ``add word cs:[0920],4`` at 08DE.  ``0918`` rewinds it.
WAVE_CURSOR_CELL = 0x0920
WAVE_SCHEDULE_HEAD = 0x9828


def _controller_counter_reset_0854(mem) -> None:
    """``1F8F:0854`` -- the controller COUNTER-BLOCK reset, called from ``0209`` (at 0241).

    The two counters this arms are the pair that paces the wave controller: ``98A5`` (the fast one,
    reloaded at ``1010:A982..A9B3`` from the 10/6/4/1 speed bucket) and ``98A7`` (the slow one,
    reloaded by the far ``1F8F:081D`` that A9B8 calls, from the 0x78/0x64/0x50/0x3C/0x28 bucket).
    Both buckets key off ``[A47E]``, which ``0209`` has just set to 1.  ``98A3``/``98A6`` are their
    run-length companions; ``98AA``/``98AC`` head an FFFF-terminated list.

    Missing this reset was the lockstep gate's last non-transition divergence: the spawn frame left
    ``98A5``/``98A7`` at 0, so ``081D``'s ``dec`` underflowed to 0xFF instead of counting 1 -> 0.
    """
    for cell in (0x98A2, 0x98A3, 0x98A4, 0x98A6, 0x98A8, 0x98A9):
        mem.wb(DS, cell, 0)
    mem.wb(DS, 0x98A5, 1)
    mem.wb(DS, 0x98A7, 1)
    mem.ww(DS, 0x98AA, 2)
    mem.ww(DS, 0x98AC, 0xFFFF)


def _wave_cursor_rewind_0918(mem) -> None:
    """``1F8F:0918`` -- ``mov word [cs:0920], 9828``: rewind the wave-schedule cursor to its head.

    The cursor lives in the OVERLAY'S CODE SEGMENT, not DGROUP, so the DGROUP lockstep gate is blind
    to it; it is written here because that is what ``0209`` does, and because its consumer (``08AB``,
    still unrecovered) reads the live value.  Faithful now beats archaeology later.
    """
    mem.ww(OVERLAY_SEG, WAVE_CURSOR_CELL, WAVE_SCHEDULE_HEAD)

#: the six per-planet script CURSOR cells (C5F5..C5FF) and the script HEAD each resets to --
#: exactly the first six writes of ``1010:0B3E`` (the level-data initializer, run at level load AND
#: at the death moment via ``4DBF``): the cursors REWIND to the heads, so a respawned level replays
#: its spawn script from the top.
SCRIPT_CURSOR_HEADS_0B3E = ((0xC5F5, 0xC85C), (0xC5F7, 0xC8D6), (0xC5F9, 0xCA02),
                            (0xC5FB, 0xCC36), (0xC5FD, 0xCC80), (0xC5FF, 0xCCAA))


def rewind_level_scripts_0b3e(mem) -> None:
    """``1010:0B3E``'s script-cursor rewind: reset all six planets' cursor cells to their heads."""
    for cell, head in SCRIPT_CURSOR_HEADS_0B3E:
        mem.ww(DS, cell, head)


def _ground_snap_4b4a(mem, rec: int) -> None:
    """``1010:4B4A..4BE6``: snap X/Y to the 16px grid, then drop the object onto the terrain surface
    by searching its tile column of the level plane (in place; writes the 209C/209E/20A0 scratch)."""
    x = mem.rw(DS, rec + 0x02) & 0xFFF0
    mem.ww(DS, rec + 0x02, x)
    y = mem.rw(DS, rec + 0x04) & 0xFFF0
    mem.ww(DS, rec + 0x04, y)
    mem.ww(DS, 0x20A0, y)
    mem.ww(DS, 0x209C, (y >> 4) & 0xFFFF)
    plane_seg = mem.rw(CODE_SEG, TILE_PLANE_SEG_CELL)
    # the tile-column base for this X (row_base + 0xD - x_tile*0xD), computed the 4B6D loop's way
    col = (mem.rw(DS, 0x2350) + TILE_COLUMN_STRIDE) & 0xFFFF
    ax = x
    if ax & 0x8000:
        while ax != 0:
            col = (col + TILE_COLUMN_STRIDE) & 0xFFFF
            ax = (ax + 0x10) & 0xFFFF
    else:
        while ax != 0:
            col = (col - TILE_COLUMN_STRIDE) & 0xFFFF
            ax = (ax - 0x10) & 0xFFFF
    mem.ww(DS, 0x209E, col)
    # search the column for the first open tile (class 0), stepping toward the surface
    for _ in range(2 * GROUND_COLUMN_ROWS + 1):
        rowidx = mem.rw(DS, 0x209C)
        tile = mem.rb(plane_seg, (col + rowidx) & 0xFFFF)
        if mem.rb(DS, (TILE_CLASS_TABLE_C3AA + tile) & 0xFFFF) == 0:
            mem.ww(DS, rec + 0x04, (rowidx << 4) & 0xFFFF)
            return
        if mem.rw(DS, 0x20A0) < GROUND_SEARCH_SPLIT:
            rowidx = (rowidx + 1) & 0xFFFF
            if rowidx >= GROUND_COLUMN_ROWS:
                rowidx = 0
        else:
            rowidx = (rowidx - 1) & 0xFFFF
            if rowidx == 0xFFFF:
                rowidx = GROUND_COLUMN_ROWS - 1
        mem.ww(DS, 0x209C, rowidx)
    raise RecoveryGap("ground-object tile search found no open tile",
                      "the level column has no class-0 tile -- unexpected for real level data")


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
                _ground_snap_4b4a(mem, slot)
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
                _controller_counter_reset_0854(mem)
                _wave_cursor_rewind_0918(mem)
            elif beh == 0x21:
                raise RecoveryGap("script-spawned wave driver (behavior 0x21)",
                                  "the 4C03 path calls 1F8F:0209 with a leftover-ax schedule")
            pos += 4
