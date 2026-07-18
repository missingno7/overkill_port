"""Gate the overlay-menu key wait predicate against the DISASSEMBLED loop.

`1F8F:0989..0A30`, decoded with `scripts/lindis.py` over a snapshot captured at the real wedge
(frame 1236 of `demo_coldspine_20260718_211150`, parked `1F8F:09A2`):

    099B 990F / 09A2 990C / 09A9 990D / 09B0 98D2             -> 09E9  (move UP)
    09B7 9911 / 09BE 9914 / 09C5 9915 / 09CC 98FD / 09D3 98E0 -> 0A03  (move DOWN)
    09DA 98C5: jnz -> 099B   (loops back; if SET, falls to the 09E1 release spin, then ret far)

    09E9: cmp [BED4],0000h ; jz 099B    -- UP waits iff the cursor is ALREADY AT THE TOP
    0A03: bx=([BED4]+1)*2 ; cmp [bx+si],FFFFh ; jz 099B
                                        -- DOWN waits iff the NEXT entry is the FFFF terminator

The two handlers are structurally symmetric but their loop-back conditions are UNRELATED, so the
two tempting shortcuts -- "any set flag means waiting" and "09E9 mirrors 0A03" -- are both wrong.
These tests pin that, and pin the regression guard: with no flag set the predicate must still agree
with the original `all(flag != 1)` form it replaced.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))

from overkill import input_waits as iw  # noqa: E402

GOOD_SIG = bytes.fromhex("80 3e 0f 99 01 74 47")
BAD_SIG = bytes(7)
TABLE_BASE = 0xBE92
#: the wedge's own measured menu table: cursor on index 4, whose NEXT entry is the terminator.
WEDGE_ENTRIES = {0xBE9C: 0xFFFF}
NOT_TERMINATOR = {0xBE9C: 0x1350}
ALL_FLAGS = (0x990F, 0x990C, 0x990D, 0x98D2, 0x9911,
             0x9914, 0x9915, 0x98FD, 0x98E0, 0x98C5)


class _Mem:
    def __init__(self, sig=GOOD_SIG, flags=None, index=0, entries=None):
        self._sig = sig
        self._flags = flags or {}
        self._index = index
        self._entries = entries or {}

    def block(self, cs, off, n):
        return self._sig

    def rb(self, ds, off):
        return self._flags.get(off, 0)

    def rw(self, ds, off):
        if off == iw._OVERLAY_MENU_INDEX:
            return self._index
        if off == iw._OVERLAY_MENU_TABLE:
            return TABLE_BASE
        return self._entries.get(off, 0x1234)


class _State:
    def __init__(self, ds=0x25CC):
        self.ds = ds


class _CPU:
    def __init__(self, cs, ip, mem):
        self._addr = (cs, ip)
        self.mem = mem
        self.s = _State()

    def addr(self):
        return self._addr


def _spinning(flags, index, entries):
    return iw._overlay_menu_key_wait_spinning(_Mem(GOOD_SIG, flags, index, entries), 0x25CC)


# -- the decoded loop-back conditions ------------------------------------------------------

def test_no_navigation_flag_set_is_a_wait():
    """The chain falls through 09DA's `jnz 099B` and loops."""
    assert _spinning({}, 4, WEDGE_ENTRIES) is True


def test_up_flag_at_top_of_list_waits():
    """09E9: `cmp [BED4],0000h ; jz 099B` -- cannot move up, so it loops back."""
    for flag in iw._OVERLAY_MENU_UP_FLAGS:
        assert _spinning({flag: 1}, 0, {}) is True, hex(flag)


def test_up_flag_not_at_top_acts_and_is_not_a_wait():
    """Off the top the handler ACTS (five 50C9 retrace waits, then `dec [BED4]`)."""
    for flag in iw._OVERLAY_MENU_UP_FLAGS:
        assert _spinning({flag: 1}, 4, {}) is False, hex(flag)


def test_down_flag_at_terminator_waits():
    """0A03: next entry is FFFF, so `jz 099B` is taken -- this is the measured wedge."""
    for flag in iw._OVERLAY_MENU_DOWN_FLAGS:
        assert _spinning({flag: 1}, 4, WEDGE_ENTRIES) is True, hex(flag)


def test_down_flag_before_terminator_acts_and_is_not_a_wait():
    """A real entry follows, so the handler moves the cursor instead of looping."""
    for flag in iw._OVERLAY_MENU_DOWN_FLAGS:
        assert _spinning({flag: 1}, 4, NOT_TERMINATOR) is False, hex(flag)


def test_up_and_down_conditions_are_not_interchangeable():
    """The whole reason 09E9 was disassembled rather than assumed to mirror 0A03.

    At index 0 with NO terminator ahead: UP waits (at the top) but DOWN acts (room below).
    """
    assert _spinning({0x990F: 1}, 0, NOT_TERMINATOR) is True
    assert _spinning({0x98FD: 1}, 0, NOT_TERMINATOR) is False


def test_up_is_tested_before_down():
    """099B..09B0 (UP) precede 09B7..09D3 (DOWN), so UP decides when both are set."""
    assert _spinning({0x990F: 1, 0x98FD: 1}, 0, NOT_TERMINATOR) is True   # UP: at top -> wait
    assert _spinning({0x990F: 1, 0x98FD: 1}, 4, WEDGE_ENTRIES) is False   # UP: can move -> act


def test_exit_flag_is_not_reported_as_a_navigation_wait():
    """98C5 set leaves the scan chain for the 09E1 release spin (a different head)."""
    assert _spinning({0x98C5: 1}, 4, WEDGE_ENTRIES) is False


# -- regression guard + the coarse/head-only pairing --------------------------------------

def test_no_flag_case_still_matches_the_original_all_clear_form():
    """Where the old `all(flag != 1)` predicate was already right, behaviour is unchanged."""
    for index in (0, 4):
        for entries in ({}, WEDGE_ENTRIES, NOT_TERMINATOR):
            mem = _Mem(GOOD_SIG, {}, index, entries)
            original = all(mem.rb(0x25CC, off) != 1 for off in ALL_FLAGS)
            assert iw._overlay_menu_key_wait_spinning(mem, 0x25CC) is original


def test_signature_guard_rejects_a_non_matching_loop():
    cpu = _CPU(0x1F8F, 0x09D3, _Mem(BAD_SIG, {}, 4, WEDGE_ENTRIES))
    assert iw.overlay_menu_key_wait(cpu) is False


def test_coarse_form_covers_the_loop_body_and_head_only_form_does_not():
    """play.py samples coarsely; the frame verifier must stop both sides at the identical head."""
    mem = _Mem(GOOD_SIG, {}, 4, WEDGE_ENTRIES)
    for ip in (0x099B, 0x09A2, 0x09D3, 0x09DF):
        assert iw.overlay_menu_key_wait(_CPU(0x1F8F, ip, mem)) is True, hex(ip)
    for ip in (0x099A, 0x09E0):
        assert iw.overlay_menu_key_wait(_CPU(0x1F8F, ip, mem)) is False, hex(ip)
    assert iw._overlay_menu_key_wait_at(_CPU(0x1F8F, 0x099B, mem), head_only=True) is True
    for ip in (0x09A2, 0x09D3, 0x09DF):
        assert iw._overlay_menu_key_wait_at(_CPU(0x1F8F, ip, mem), head_only=True) is False, hex(ip)


def test_frame_verify_adapter_reports_the_head_and_is_not_shadowed_by_the_1f8f_branch():
    """The all-keys branch `return None`s for every other IP in 1F8F -- this must precede it."""
    mem = _Mem(GOOD_SIG, {}, 4, WEDGE_ENTRIES)
    assert iw.frame_verify_input_wait(_CPU(0x1F8F, 0x099B, mem)) == ("wait", (0x1F8F, 0x099B))


def test_the_measured_wedge_state_is_a_wait():
    """The exact state read off the wedge: 98FD=1, [BED4]=4, [BE9C]=FFFF.

    The old `all(flag != 1)` form returned False here, which is what deadlocked demo replay.
    """
    assert _spinning({0x98FD: 1}, 4, WEDGE_ENTRIES) is True


# -- the 09E1 EXIT-KEY RELEASE spin -------------------------------------------------------
#
#     09E1  cmp ds:[98C5],01h
#     09E6  jz -> 09E1        ; spin WHILE the exit key is held
#     09E8  ret far           ; the loop's only exit
#
# Decoded alongside the scan chain, then OBSERVED to wedge replay at frame 1296 once the
# scan-chain clause cleared the frame-1236 wedge.

EXIT_RELEASE_SIG = bytes.fromhex("80 3e c5 98 01 74 f9")


class _ExitMem(_Mem):
    def block(self, cs, off, n):
        if off == iw._OVERLAY_MENU_EXIT_RELEASE_HEAD:
            return self._sig
        return BAD_SIG


def test_exit_release_spin_waits_while_the_key_is_held():
    mem = _ExitMem(EXIT_RELEASE_SIG, {0x98C5: 1}, 4, WEDGE_ENTRIES)
    assert iw.overlay_menu_exit_release_wait(_CPU(0x1F8F, 0x09E1, mem)) is True


def test_exit_release_spin_is_not_a_wait_once_released():
    """Released -> the `jz` falls through to `ret far`, so it must NOT be reported as a wait."""
    mem = _ExitMem(EXIT_RELEASE_SIG, {0x98C5: 0}, 4, WEDGE_ENTRIES)
    assert iw.overlay_menu_exit_release_wait(_CPU(0x1F8F, 0x09E1, mem)) is False


def test_exit_release_spin_covers_its_two_instructions_only():
    mem = _ExitMem(EXIT_RELEASE_SIG, {0x98C5: 1}, 4, WEDGE_ENTRIES)
    for ip in (0x09E1, 0x09E6):
        assert iw.overlay_menu_exit_release_wait(_CPU(0x1F8F, ip, mem)) is True, hex(ip)
    for ip in (0x09E0, 0x09E8):
        assert iw.overlay_menu_exit_release_wait(_CPU(0x1F8F, ip, mem)) is False, hex(ip)


def test_exit_release_signature_guard():
    mem = _ExitMem(BAD_SIG, {0x98C5: 1}, 4, WEDGE_ENTRIES)
    assert iw.overlay_menu_exit_release_wait(_CPU(0x1F8F, 0x09E1, mem)) is False


def test_frame_verify_adapter_reports_the_exit_release_head():
    mem = _ExitMem(EXIT_RELEASE_SIG, {0x98C5: 1}, 4, WEDGE_ENTRIES)
    assert iw.frame_verify_input_wait(_CPU(0x1F8F, 0x09E1, mem)) == ("wait", (0x1F8F, 0x09E1))


def test_the_two_overlay_waits_do_not_overlap():
    """Distinct heads and distinct IP ranges -- neither may claim the other's park."""
    scan = _Mem(GOOD_SIG, {}, 4, WEDGE_ENTRIES)
    assert iw.overlay_menu_key_wait(_CPU(0x1F8F, 0x099B, scan)) is True
    assert iw.overlay_menu_exit_release_wait(_CPU(0x1F8F, 0x099B, scan)) is False
    exit_mem = _ExitMem(EXIT_RELEASE_SIG, {0x98C5: 1}, 4, WEDGE_ENTRIES)
    assert iw.overlay_menu_key_wait(_CPU(0x1F8F, 0x09E1, exit_mem)) is False
    assert iw.overlay_menu_exit_release_wait(_CPU(0x1F8F, 0x09E1, exit_mem)) is True
