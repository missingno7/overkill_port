"""OVERKILL collision and object-overlap gameplay helpers.

This module contains bounded gameplay/collision routines lifted from the
original DOS code.  They are specific to OVERKILL's object-record layout and are
kept outside the generic VM and outside the hook-registration module.
"""
from __future__ import annotations

from dos_re.cpu import CF
from overkill.gameplay.view_window import _run_view_window_check_aa46

SIG_PLAYER_HAZARD_OBJECT_SCAN_BDE3 = bytes.fromhex(
    "83 3f 00 74 4d 83 7f 0a 01 74 47 83 7f 14 01 75 41"
)


SIG_COLLISION_STC_RET_5059 = bytes.fromhex("f9 c3")

SIG_TILE_LOOKUP_505B = bytes.fromhex(
    "be aa c3 2e 8e 06 92 95 26 8a 07 32 e4 03 f0 8a 04 0a c0 c3"
)

SIG_TILE_PROBE_5073 = bytes.fromhex(
    "a1 4e 23 03 46 02 a3 5a 21 78 f1 d1 e8 d1 e8 d1 e8 d1 e8"
)

SIG_TILE_CONTACT_PROBE_4FF9 = bytes.fromhex(
    "8b 76 08 83 fe 03 73 58 d1 e6 d1 e6 81 c6 4e 21"
    "ff 76 02 ff 76 04 ad 01 46 02 ad 01 46 04 e8 59 00"
    "83 c3 0d a1 5a 21 25 0f 00 3d 0a 00 b9 01 00 76 03"
    "b9 02 00 51 53 e8 28 00 75 1c f7 46 04 0f 00 74 06"
    "43 e8 1b 00 75 0f 5b 83 eb 0d 59 e2 e5 8f 46 04 8f"
    "46 02 f8 c3 5b 59 8f 46 04 8f 46 02 f9 c3"
)

SIG_OBJECT_SLOT_SCAN_GUARD_AC81 = bytes.fromhex("83 3e ac bd 01 75 03 e9 b9 fd b9 23 00 bb b4 23 8b 46 04 8b 7e 02")

SIG_TILE_COLLISION_PROBE_AC28 = bytes.fromhex(
    "83 3e 7c a4 00 74 03 e9 12 fe 83 3e ac bd 01 75 03 e9 08 fe "
    "e8 34 a4 83 c3 0d e8 16 a4 75 0f f7 46 04 0f 00 74 06 43 "
    "e8 09 a4 75 02 f8 c3 80 3e c0 98 00 74 05 c6 06 ff be 0e "
    "c7 46 24 05 00 83 3e dc be 00 75 07 83 3e 24 23 01 75 df "
    "ff 4e 20 75 da c7 46 24 00 00 f9 c3"
)


def _signed16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def _cmp_word(cpu, a: int, b: int) -> None:
    a &= 0xFFFF
    b &= 0xFFFF
    cpu.set_sub_flags(a, b, a - b, 16)


def run_postmove_y_clamp_bcb1(cpu) -> None:
    """Clamp the BC4B post-move Y coordinate and return to BC4E.

    The original helper compares SS:[BP+4] against 00C0h and 0000h, clamps the
    stored Y into the inclusive 0..00C0h range, then returns to the BC4E
    continuation.  This is a tiny hot leaf that is repeatedly executed from
    the object post-move path.
    """
    s = cpu.s
    mem = cpu.mem
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF
    y = mem.rw(ss, (bp + 0x04) & 0xFFFF)
    _cmp_word(cpu, y, 0x00C0)
    sy = _signed16(y)
    if sy > 0x00C0:
        mem.ww(ss, (bp + 0x04) & 0xFFFF, 0x00C0)
    else:
        _cmp_word(cpu, y, 0)
        if sy < 0:
            mem.ww(ss, (bp + 0x04) & 0xFFFF, 0)
    s.ip = cpu.pop()


def run_postmove_contact_window_aa71(cpu) -> None:
    """Model the observed AA71 contact-window helper used from BC4B.

    The snapshot path entered this helper with an object that already passed the
    BC4B clamp/bounds logic.  The observed branch checks the signed X position
    against the top-of-window guard at DS:2380 and returns via AA44 on the
    current gameplay path.  The same snapshot also exercises the higher
    AAAB->AA44 tail that reuses the X+18 compare against DS:237E.  Negative X
    still goes back to the AA46 helper.
    """
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF

    x = mem.rw(ss, (bp + 0x02) & 0xFFFF)
    _cmp_word(cpu, x, 0)
    if _signed16(x) < 0:
        _run_view_window_check_aa46(cpu)
        s.ip = cpu.pop()
        return

    y = mem.rw(ss, (bp + 0x04) & 0xFFFF)
    guard = mem.rw(ds, 0x2380)
    upper = (y + 0x0018) & 0xFFFF
    s.ax = upper
    cpu.set_add_flags(y, 0x0018, y + 0x0018, 16)
    _cmp_word(cpu, upper, guard)
    if _signed16(upper) < _signed16(guard):
        cpu.set_flag(CF, False)
        s.ip = cpu.pop()
        return

    lower = (upper - 0x002C) & 0xFFFF
    s.ax = lower
    cpu.set_sub_flags(upper, 0x002C, upper - 0x002C, 16)
    _cmp_word(cpu, lower, guard)
    if _signed16(lower) > _signed16(guard):
        cpu.set_flag(CF, False)
        s.ip = cpu.pop()
        return

    a8c2 = mem.rw(ds, 0xA8C2)
    _cmp_word(cpu, a8c2, 0x0001)
    if a8c2 == 0x0001:
        raise RuntimeError("unverified original-code path reached in 1010:AA71: A8C2=0001 branch")

    upper = (x + 0x0018) & 0xFFFF
    s.ax = upper
    cpu.set_add_flags(x, 0x0018, x + 0x0018, 16)
    view_guard = mem.rw(ds, 0x237E)
    _cmp_word(cpu, upper, view_guard)
    if _signed16(upper) < _signed16(view_guard):
        cpu.set_flag(CF, False)
        s.ip = cpu.pop()
        return

    cpu.set_flag(CF, False)
    s.ip = cpu.pop()
    return


def run_object_deactivate_logic_dispatch_c054(cpu) -> None:
    """Model the observed BD17 -> C054 variant dispatcher.

    The original disassembler prints this field as ``[BP+24]`` because the
    displacement is decimal 24; in the object record this is offset 18h, the
    logic id.  C054 first handles the live-counter family and otherwise falls
    through a selector-to-AX chain whose final/default value is A4E4h.
    """
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF
    selector = mem.rw(ss, (bp + 0x18) & 0xFFFF)

    for value, ax in (
        (0x0076, 0xA79C),
        (0x0077, 0xA6F0),
        (0x0078, 0xA83E),
        (0x0079, 0xA82A),
    ):
        _cmp_word(cpu, selector, value)
        if selector == value:
            s.ax = ax
            return

    c14f_ids = (
        0x0061, 0x0062, 0x0065,
        0x0014, 0x0016, 0x0017, 0x0018,
        0x007F, 0x0080, 0x0081,
        0x0093,
        0x001D, 0x001E, 0x0020, 0x0021, 0x0022,
    )
    for value in c14f_ids:
        _cmp_word(cpu, selector, value)
        if selector == value:
            if selector == 0x0093:
                mem.wb(ds, 0x98A8, 0x01)
            old = mem.rw(ds, 0xA47E)
            result = (old - 1) & 0xFFFF
            mem.ww(ds, 0xA47E, result)
            cpu.set_sub_flags(old, 1, old - 1, 16)
            return

    for value, ax in (
        (0x007E, 0xA79C),
        (0x007D, 0xA6F0),
        (0x001F, 0xA83E),
        (0x001C, 0xA82A),
        (0x0015, 0xA5C0),
        (0x0013, 0xA4E4),
    ):
        _cmp_word(cpu, selector, value)
        s.ax = ax
        if selector == value:
            return



def run_object_slot_scan_guard_ac81(cpu, self_disable_if_patched) -> None:
    """Guard/setup wrapper around the shared AC97 object-slot overlap scan.

    AC81 is not a separate collision algorithm; it gates the scan on DS:BDAC,
    initializes the AC97 loop registers from the current object slot, then lets
    ``run_object_slot_scan_ac97`` own the real overlap walk.
    """
    if self_disable_if_patched(cpu, 0xAC81, SIG_OBJECT_SLOT_SCAN_GUARD_AC81, "overkill_object_slot_scan_guard_ac81"):
        return
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF
    bdac = mem.rw(ds, 0xBDAC)
    _cmp_word(cpu, bdac, 0x0001)
    if bdac == 0x0001:
        cpu.set_flag(CF, False)
        s.ip = cpu.pop()
        return
    s.cx = 0x0023
    s.bx = 0x23B4
    s.ax = mem.rw(ss, (bp + 0x04) & 0xFFFF)
    s.di = mem.rw(ss, (bp + 0x02) & 0xFFFF)
    run_object_slot_scan_ac97(cpu)


def run_object_slot_scan_ac97(cpu) -> None:
    """Collapse the hot 1010:AC97 object-record scan loop.

    AC97 is the inner scan body entered after the caller has initialized
    ``BX=23B4h``, ``CX=23h``, ``AX=SS:[BP+4]``, and ``DI=SS:[BP+2]``.  The
    original body either walks all slots and returns with ``CLC``, or exits the
    lifted loop at ``ACD9`` when it finds a candidate slot that must continue
    through the still-interpreted collision/reaction tail.

    Keep the boundary the verifier expects: one hook invocation consumes the
    whole scan up to the original ``RET`` or the exact ``ACD9`` continuation,
    rather than re-entering the hook one slot at a time.
    """
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF
    bx = s.bx & 0xFFFF
    cx = s.cx & 0xFFFF
    ax = s.ax & 0xFFFF
    di = s.di & 0xFFFF

    # 8086 LOOP decrements CX before testing it, so an initial CX=0000 means
    # 65536 iterations.  Captured gameplay uses CX=0023, but preserve the CPU
    # semantics for verifier/oracle fixtures.
    if cx == 0:
        cx = 0x10000

    while cx:
        value = mem.rw(ds, bx)
        _cmp_word(cpu, value, 0)
        if value != 0:
            state_24 = mem.rw(ds, (bx + 0x18) & 0xFFFF)
            _cmp_word(cpu, state_24, 1)
            if state_24 != 1:
                state_20 = mem.rw(ds, (bx + 0x14) & 0xFFFF)
                _cmp_word(cpu, state_20, 1)
                if state_20 == 1:
                    si0 = mem.rw(ds, (bx + 0x02) & 0xFFFF)
                    si = (si0 + 0x0010) & 0xFFFF
                    s.si = si
                    cpu.set_add_flags(si0, 0x0010, si0 + 0x0010, 16)
                    _cmp_word(cpu, di, si)
                    if _signed16(di) <= _signed16(si):
                        si_before = si
                        si = (si - 0x0020) & 0xFFFF
                        s.si = si
                        cpu.set_sub_flags(si_before, 0x0020, si_before - 0x0020, 16)
                        _cmp_word(cpu, di, si)
                        if _signed16(di) >= _signed16(si):
                            si0 = mem.rw(ds, (bx + 0x04) & 0xFFFF)
                            si = (si0 + 0x0010) & 0xFFFF
                            s.si = si
                            cpu.set_add_flags(si0, 0x0010, si0 + 0x0010, 16)
                            _cmp_word(cpu, ax, si)
                            if _signed16(ax) <= _signed16(si):
                                si_before = si
                                si = (si - 0x0020) & 0xFFFF
                                s.si = si
                                cpu.set_sub_flags(si_before, 0x0020, si_before - 0x0020, 16)
                                _cmp_word(cpu, ax, si)
                                if _signed16(ax) >= _signed16(si):
                                    # 8B 76 0E / 3B 77 0E:
                                    #     MOV SI, SS:[BP+0Eh]
                                    #     CMP SI, DS:[BX+0Eh]
                                    si = mem.rw(ss, (bp + 0x0E) & 0xFFFF)
                                    s.si = si
                                    other = mem.rw(ds, (bx + 0x0E) & 0xFFFF)
                                    _cmp_word(cpu, si, other)
                                    if si != other:
                                        # ACD9 is not always a terminal collision
                                        # continuation.  The hot gameplay path
                                        # usually proves that the candidate is not
                                        # an actionable type-4/type-5 overlap and
                                        # then jumps straight back to ACD2 to keep
                                        # scanning.  Consuming that tiny tail here
                                        # keeps AC97 as one whole slot-scan hook
                                        # instead of bouncing through interpreted
                                        # ACD9/ACD2 glue for every rejected overlap.
                                        kind_16 = mem.rw(ds, (bx + 0x16) & 0xFFFF)
                                        _cmp_word(cpu, kind_16, 0x0005)
                                        if kind_16 == 0x0005:
                                            s.ax = ax
                                            s.bx = bx
                                            s.cx = cx & 0xFFFF
                                            s.di = di
                                            s.ip = 0xACD9
                                            return

                                        state_20 = mem.rw(ds, (bx + 0x14) & 0xFFFF)
                                        _cmp_word(cpu, state_20, 0x0001)
                                        if state_20 != 0x0001:
                                            s.ax = ax
                                            s.bx = bx
                                            s.cx = cx & 0xFFFF
                                            s.di = di
                                            cpu.set_flag(CF, True)
                                            s.ip = cpu.pop()
                                            return

                                        _cmp_word(cpu, kind_16, 0x0004)
                                        if kind_16 == 0x0004:
                                            s.ax = ax
                                            s.bx = bx
                                            s.cx = cx & 0xFFFF
                                            s.di = di
                                            s.ip = 0xACD9
                                            return
                                        # Otherwise mirror ACD9 -> ACD2 and keep
                                        # scanning from the next slot below.

        old_bx = bx
        bx = (bx + 0x0038) & 0xFFFF
        cpu.set_add_flags(old_bx, 0x0038, old_bx + 0x0038, 16)
        cx = (cx - 1) & 0xFFFF

        s.bx = bx
        s.cx = cx
        s.ax = ax
        s.di = di
        if cx == 0:
            break

    # AC97 falls through to F8 C3 when LOOP exhausts: CLC ; RET.  CLC only
    # changes CF, preserving the ADD flags from the final slot advance.
    cpu.set_flag(CF, False)
    s.ip = cpu.pop()


def run_player_hazard_object_scan_bde3(cpu, self_disable_if_patched) -> None:
    """Lift the hot BDE3..BE3B player/hazard object scan loop.

    The surrounding BDD0 helper initializes BX/CX/AX/DI, then this loop scans
    the 35 object records at DS:23B4 looking for active layer-1 type-4 objects
    in the 82h..94h range that overlap the player probe point.  On no hit it
    falls through to CLC/RET.  On a hit it jumps to 1010:5059 with the current
    object in BX, exactly like the original.
    """
    if self_disable_if_patched(cpu, 0xBDE3, SIG_PLAYER_HAZARD_OBJECT_SCAN_BDE3, "overkill_player_hazard_object_scan_bde3"):
        return

    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF
    bx = s.bx & 0xFFFF
    cx = s.cx & 0xFFFF
    ax = s.ax & 0xFFFF
    di = s.di & 0xFFFF
    if cx == 0:
        cx = 0x10000

    while cx:
        value = mem.rw(ds, bx)
        _cmp_word(cpu, value, 0)
        if value != 0:
            value = mem.rw(ds, (bx + 0x0A) & 0xFFFF)
            _cmp_word(cpu, value, 1)
            if value != 1:
                value = mem.rw(ds, (bx + 0x14) & 0xFFFF)
                _cmp_word(cpu, value, 1)
                if value == 1:
                    value = mem.rw(ds, (bx + 0x16) & 0xFFFF)
                    _cmp_word(cpu, value, 4)
                    if value == 4:
                        obj_id = mem.rw(ds, (bx + 0x18) & 0xFFFF)
                        _cmp_word(cpu, obj_id, 0x0082)
                        if obj_id >= 0x0082:
                            _cmp_word(cpu, obj_id, 0x0094)
                            if obj_id <= 0x0094:
                                si0 = mem.rw(ds, (bx + 0x02) & 0xFFFF)
                                si = (si0 + 0x0010) & 0xFFFF
                                s.si = si
                                cpu.set_add_flags(si0, 0x0010, si0 + 0x0010, 16)
                                _cmp_word(cpu, di, si)
                                if _signed16(di) < _signed16(si):
                                    si_before = si
                                    si = (si - 0x0020) & 0xFFFF
                                    s.si = si
                                    cpu.set_sub_flags(si_before, 0x0020, si_before - 0x0020, 16)
                                    _cmp_word(cpu, di, si)
                                    if _signed16(di) > _signed16(si):
                                        si0 = mem.rw(ds, (bx + 0x04) & 0xFFFF)
                                        si = (si0 + 0x0010) & 0xFFFF
                                        s.si = si
                                        cpu.set_add_flags(si0, 0x0010, si0 + 0x0010, 16)
                                        _cmp_word(cpu, ax, si)
                                        if _signed16(ax) < _signed16(si):
                                            si_before = si
                                            si = (si - 0x0020) & 0xFFFF
                                            s.si = si
                                            cpu.set_sub_flags(si_before, 0x0020, si_before - 0x0020, 16)
                                            _cmp_word(cpu, ax, si)
                                            if _signed16(ax) > _signed16(si):
                                                si = mem.rw(ss, (bp + 0x0E) & 0xFFFF)
                                                s.si = si
                                                other = mem.rw(ds, (bx + 0x0E) & 0xFFFF)
                                                _cmp_word(cpu, si, other)
                                                if si != other:
                                                    s.bx = bx
                                                    s.cx = cx
                                                    s.ax = ax
                                                    s.di = di
                                                    s.ip = 0x5059
                                                    return

        old_bx = bx
        bx = (bx + 0x0038) & 0xFFFF
        cpu.set_add_flags(old_bx, 0x0038, old_bx + 0x0038, 16)
        cx = (cx - 1) & 0xFFFF
        if cx == 0:
            break

    s.bx = bx
    s.cx = 0
    s.ax = ax
    s.di = di
    cpu.set_flag(CF, False)
    s.ip = cpu.pop()


def run_tile_collision_probe_ac28(cpu, self_disable_if_patched) -> None:
    """Lift the runtime-patched AC28 tile collision probe.

    The ABxx object behaviours call this helper after preparing an object probe
    point.  It checks the tile under/near the object through the existing 5073
    coordinate-to-tile and 505B tile-id lookup helpers.  On clear space it
    returns with CF clear; on an actionable collision it decrements the object
    countdown at BP+20h and returns with CF set only when that counter reaches
    zero.  Global gates A47C or BDAC jump to AA44 exactly like the patched ASM.
    """
    if self_disable_if_patched(cpu, 0xAC28, SIG_TILE_COLLISION_PROBE_AC28, "overkill_tile_collision_probe_ac28"):
        return

    def no_patch_guard(*_args) -> bool:
        return False

    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF

    _cmp_word(cpu, mem.rw(ds, 0xA47C), 0)
    if not cpu.get_flag(0x0040):  # JZ not taken -> JMP AA44.
        s.ip = 0xAA44
        return
    _cmp_word(cpu, mem.rw(ds, 0xBDAC), 1)
    if cpu.get_flag(0x0040):  # JNE not taken -> JMP AA44.
        s.ip = 0xAA44
        return

    cpu.push(0xAC3F)
    run_tile_probe_5073(cpu, no_patch_guard)
    # 5073 returns to AC3F.
    old_bx = s.bx & 0xFFFF
    s.bx = (old_bx + 0x000D) & 0xFFFF
    cpu.set_add_flags(old_bx, 0x000D, old_bx + 0x000D, 16)
    cpu.push(0xAC45)
    run_tile_lookup_505b(cpu, no_patch_guard)
    if not cpu.get_flag(0x0040):  # JNE AC56
        collided = True
    else:
        cpu.set_logic_flags(mem.rw(ss, (bp + 0x04) & 0xFFFF) & 0x000F, 16)  # TEST [BP+4],000Fh
        if cpu.get_flag(0x0040):
            collided = False
        else:
            old_bx = s.bx & 0xFFFF
            old_cf = cpu.get_flag(CF)
            s.bx = (old_bx + 1) & 0xFFFF
            cpu.set_add_flags(old_bx, 1, old_bx + 1, 16)
            cpu.set_flag(CF, old_cf)  # INC preserves CF.
            cpu.push(0xAC52)
            run_tile_lookup_505b(cpu, no_patch_guard)
            collided = not cpu.get_flag(0x0040)

    if not collided:
        cpu.set_flag(CF, False)
        s.ip = cpu.pop()
        return

    _cmp_word(cpu, mem.rb(ds, 0x98C0), 0)
    if not cpu.get_flag(0x0040):
        mem.wb(ds, 0xBEFF, 0x0E)
    mem.ww(ss, (bp + 0x24) & 0xFFFF, 0x0005)
    _cmp_word(cpu, mem.rw(ds, 0xBEDC), 0)
    if cpu.get_flag(0x0040):
        _cmp_word(cpu, mem.rw(ds, 0x2324), 1)
        if not cpu.get_flag(0x0040):
            cpu.set_flag(CF, False)
            s.ip = cpu.pop()
            return

    old = mem.rw(ss, (bp + 0x20) & 0xFFFF)
    old_cf = cpu.get_flag(CF)
    result_full = old - 1
    mem.ww(ss, (bp + 0x20) & 0xFFFF, result_full & 0xFFFF)
    cpu.set_sub_flags(old, 1, result_full, 16)
    cpu.set_flag(CF, old_cf)  # DEC preserves CF.
    if not cpu.get_flag(0x0040):
        cpu.set_flag(CF, False)
        s.ip = cpu.pop()
        return

    mem.ww(ss, (bp + 0x24) & 0xFFFF, 0x0000)
    cpu.set_flag(CF, True)
    s.ip = cpu.pop()


def run_collision_stc_ret_5059(cpu, self_disable_if_patched) -> None:
    """Lift OVERKILL 1010:5059 ``STC ; RET`` collision-hit helper."""
    if self_disable_if_patched(cpu, 0x5059, SIG_COLLISION_STC_RET_5059, "overkill_collision_stc_ret_5059"):
        return
    cpu.set_flag(CF, True)
    cpu.s.ip = cpu.pop()


def run_tile_lookup_505b(cpu, self_disable_if_patched) -> None:
    """Lift OVERKILL 1010:505B tile-id lookup helper.

    The helper maps the tile-plane byte at ES:[BX] through DS:C3AA and leaves
    ZF/SF/PF from ``OR AL,AL``.  It is hot in collision/object movement paths
    and was previously only modeled as a private helper inside larger object
    behavior hooks, so direct interpreted calls still showed up as ``505B``
    hotspots.
    """
    if self_disable_if_patched(cpu, 0x505B, SIG_TILE_LOOKUP_505B, "overkill_tile_lookup_505b"):
        return

    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    ds = s.ds & 0xFFFF

    s.si = 0xC3AA
    s.es = mem.rw(cs, 0x9592)
    tile_index = mem.rb(s.es & 0xFFFF, s.bx & 0xFFFF)
    s.ax = tile_index & 0x00FF  # MOV AL / XOR AH,AH
    old_si = s.si
    s.si = (old_si + s.ax) & 0xFFFF
    cpu.set_add_flags(old_si, s.ax, old_si + s.ax, 16)
    cpu.set_reg8(0, mem.rb(ds, s.si & 0xFFFF))
    cpu.set_logic_flags(cpu.get_reg8(0), 8)
    s.ip = cpu.pop()


def run_tile_probe_5073(cpu, self_disable_if_patched) -> None:
    """Lift OVERKILL 1010:5073 coordinate-to-tile-index helper.

    This converts the current object/probe point into a tilemap byte offset in
    ``BX``.  If the adjusted X coordinate is negative the original jumps into
    the tiny ``MOV BX,FFFFh ; RET`` helper at 506F; that path is modeled here
    instead of using the older partial private helper.
    """
    if self_disable_if_patched(cpu, 0x5073, SIG_TILE_PROBE_5073, "overkill_tile_probe_5073"):
        return

    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF

    s.ax = mem.rw(ds, 0x234E)
    addend = mem.rw(ss, (bp + 0x02) & 0xFFFF)
    old_ax = s.ax
    s.ax = (old_ax + addend) & 0xFFFF
    cpu.set_add_flags(old_ax, addend, old_ax + addend, 16)
    mem.ww(ds, 0x215A, s.ax)
    if s.ax & 0x8000:
        s.bx = 0xFFFF
        s.ip = cpu.pop()
        return

    for _ in range(4):
        s.ax = cpu.shift(5, s.ax, 1, 16)  # SHR AX,1
    s.dx = s.ax

    for _ in range(2):
        s.ax = cpu.shift(4, s.ax, 1, 16)  # SHL AX,1
    s.cx = s.ax
    s.ax = cpu.shift(4, s.ax, 1, 16)
    old_ax = s.ax
    s.ax = (old_ax + s.cx) & 0xFFFF
    cpu.set_add_flags(old_ax, s.cx, old_ax + s.cx, 16)
    old_ax = s.ax
    s.ax = (old_ax + s.dx) & 0xFFFF
    cpu.set_add_flags(old_ax, s.dx, old_ax + s.dx, 16)

    s.bx = mem.rw(ds, 0x2350)
    old_bx = s.bx
    s.bx = (old_bx - s.ax) & 0xFFFF
    cpu.set_sub_flags(old_bx, s.ax, old_bx - s.ax, 16)

    s.ax = mem.rw(ss, (bp + 0x04) & 0xFFFF)
    s.ax &= 0xFFF0
    cpu.set_logic_flags(s.ax, 16)
    for _ in range(4):
        s.ax = cpu.shift(5, s.ax, 1, 16)  # SHR AX,1

    old_bx = s.bx
    s.bx = (old_bx + s.ax) & 0xFFFF
    cpu.set_add_flags(old_bx, s.ax, old_bx + s.ax, 16)
    s.ip = cpu.pop()


def run_tile_contact_probe_4ff9(cpu, self_disable_if_patched) -> None:
    """Lift OVERKILL 1010:4FF9 tile/contact probe around an object point.

    This helper is a shared mid-level collision primitive.  ``BP`` points at a
    small probe/object record; ``[BP+8]`` selects one of three offset pairs from
    ``DS:214E``.  The helper temporarily offsets ``[BP+2]/[BP+4]``, calls the
    coordinate-to-tile helper ``5073`` and the tile lookup helper ``505B``, then
    restores the original coordinates and returns with ``CF`` clear on empty
    space or set on a blocking/contact tile.

    Keep it as a raw tile/contact probe for now.  It is evidence for the future
    collision-system layer, not a semantic enemy/player rule yet.
    """
    if self_disable_if_patched(cpu, 0x4FF9, SIG_TILE_CONTACT_PROBE_4FF9, "overkill_tile_contact_probe_4ff9"):
        return

    def no_patch_guard(*_args) -> bool:
        return False

    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF

    s.si = mem.rw(ss, (bp + 0x08) & 0xFFFF)
    _cmp_word(cpu, s.si, 0x0003)
    if s.si >= 0x0003:
        cpu.set_flag(CF, True)  # 5059: STC ; RET, preserving non-CF flags.
        s.ip = cpu.pop()
        return

    for _ in range(2):
        s.si = cpu.shift(4, s.si, 1, 16)  # SHL SI,1 twice.
    old_si = s.si
    s.si = (old_si + 0x214E) & 0xFFFF
    cpu.set_add_flags(old_si, 0x214E, old_si + 0x214E, 16)

    cpu.push(mem.rw(ss, (bp + 0x02) & 0xFFFF))
    cpu.push(mem.rw(ss, (bp + 0x04) & 0xFFFF))

    s.ax = mem.rw(ds, s.si)
    s.si = (s.si + 2) & 0xFFFF
    old = mem.rw(ss, (bp + 0x02) & 0xFFFF)
    result = old + s.ax
    mem.ww(ss, (bp + 0x02) & 0xFFFF, result & 0xFFFF)
    cpu.set_add_flags(old, s.ax, result, 16)

    s.ax = mem.rw(ds, s.si)
    s.si = (s.si + 2) & 0xFFFF
    old = mem.rw(ss, (bp + 0x04) & 0xFFFF)
    result = old + s.ax
    mem.ww(ss, (bp + 0x04) & 0xFFFF, result & 0xFFFF)
    cpu.set_add_flags(old, s.ax, result, 16)

    cpu.push(0x501A)
    run_tile_probe_5073(cpu, no_patch_guard)

    old_bx = s.bx & 0xFFFF
    s.bx = (old_bx + 0x000D) & 0xFFFF
    cpu.set_add_flags(old_bx, 0x000D, old_bx + 0x000D, 16)

    s.ax = mem.rw(ds, 0x215A)
    s.ax &= 0x000F
    cpu.set_logic_flags(s.ax, 16)
    _cmp_word(cpu, s.ax, 0x000A)
    s.cx = 0x0001 if s.ax <= 0x000A else 0x0002

    while True:
        cpu.push(s.cx)
        cpu.push(s.bx)
        cpu.push(0x5033)
        run_tile_lookup_505b(cpu, no_patch_guard)
        if not cpu.get_flag(0x0040):  # JNE 5051 after OR AL,AL in 505B.
            s.bx = cpu.pop()
            s.cx = cpu.pop()
            mem.ww(ss, (bp + 0x04) & 0xFFFF, cpu.pop())
            mem.ww(ss, (bp + 0x02) & 0xFFFF, cpu.pop())
            cpu.set_flag(CF, True)
            s.ip = cpu.pop()
            return

        test_value = mem.rw(ss, (bp + 0x04) & 0xFFFF) & 0x000F
        cpu.set_logic_flags(test_value, 16)
        if not cpu.get_flag(0x0040):
            old_cf = cpu.get_flag(CF)
            old_bx = s.bx & 0xFFFF
            s.bx = (old_bx + 1) & 0xFFFF
            cpu.set_add_flags(old_bx, 1, old_bx + 1, 16)
            cpu.set_flag(CF, old_cf)  # INC preserves CF.
            cpu.push(0x5040)
            run_tile_lookup_505b(cpu, no_patch_guard)
            if not cpu.get_flag(0x0040):
                s.bx = cpu.pop()
                s.cx = cpu.pop()
                mem.ww(ss, (bp + 0x04) & 0xFFFF, cpu.pop())
                mem.ww(ss, (bp + 0x02) & 0xFFFF, cpu.pop())
                cpu.set_flag(CF, True)
                s.ip = cpu.pop()
                return

        s.bx = cpu.pop()
        old_bx = s.bx & 0xFFFF
        s.bx = (old_bx - 0x000D) & 0xFFFF
        cpu.set_sub_flags(old_bx, 0x000D, old_bx - 0x000D, 16)
        s.cx = cpu.pop()
        s.cx = (s.cx - 1) & 0xFFFF  # LOOP does not alter flags.
        if s.cx == 0:
            break

    mem.ww(ss, (bp + 0x04) & 0xFFFF, cpu.pop())
    mem.ww(ss, (bp + 0x02) & 0xFFFF, cpu.pop())
    cpu.set_flag(CF, False)
    s.ip = cpu.pop()
