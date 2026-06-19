"""OVERKILL collision and object-overlap gameplay helpers.

This module contains bounded gameplay/collision routines lifted from the
original DOS code.  They are specific to OVERKILL's object-record layout and are
kept outside the generic VM and outside the hook-registration module.
"""
from __future__ import annotations

from collections.abc import Callable

from dos_re.cpu import CF
from overkill.asm import _and_mem_byte, _dec_mem_word_preserve_cf
from overkill.recovered.adapters.asm_flags import cmp_byte as _cmp_byte, cmp_word as _cmp_word, set_carry_and_return
from overkill.recovered.adapters.collision_adapter import (
    mark_tile_sweep_blocked,
    run_object_overlap_candidate_checks_ac97,
    run_player_hazard_candidate_checks_bde3,
    run_postmove_contact_window_aa71_body,
    run_postmove_y_clamp_bcb1_body,
    run_tile_collision_probe_ac28_body,
    run_tile_contact_probe_4ff9_body,
    run_signed_center_rect_test_8331,
    run_tile_lookup_505b_body,
    run_tile_probe_5073_body,
    view_contact_centers,
)
from overkill.recovered.adapters.object_behavior_adapter import run_object_deactivate_logic_dispatch_c054_body
from overkill.recovered.adapters.object_slot_adapter import read_object_slot_record
from overkill.recovered.views.object_slots import (
    OBJECT_SLOT_STRIDE,
    OBJECT_TABLE_BASE,
    OBJECT_TABLE_COUNT,
    OFF_X,
    OFF_Y,
    ObjectSlotView,
)

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

SIG_FRAME_CONTACT_PROBE_FANOUT_9CB6 = bytes.fromhex(
    "e8 40 b3 72 01 c3 55 83 3e dc be 00 74 0d 83"
    "3e dc be 01 74 03 e8 4b 01 e8 48 01 e8 45 01"
    "e8 42 01 5d c3"
)

SIG_POST_CONTACT_STATUS_HELPER_9E19 = bytes.fromhex(
    "83 3e 7c a4 01 75 01 c3 83 3e 84 23 03 72 01 c3"
    "83 3e 5a a9 ff 75 01 c3 c7 06 a0 23 08 00 80 3e"
    "c0 98 00 74 05 c6 06 ff be 0f 83 3e dc be 00 74"
    "13 83 3e dc be 01 74 06 ff 0e 5c a9 74 0c ff 0e"
    "5c a9 74 06 ff 0e 5c a9 75 5f c7 06 5c a9 18 00"
    "83 3e 7c a4 01 75 01 c3 83 3e 84 23 03 72 01 c3"
    "80 3e c0 98 00 74 05 c6 06 ff be 03 83 3e dc be"
    "00 75 0c fe 06 62 a3 80 26 62 a3 01 74 01 c3 ff"
    "0e 5a a9 83 3e 5a a9 ff 75 1f c7 06 5c a9 00 00"
    "80 3e 91 97 01 74 27 c7 06 84 23 03 00 80 3e c0"
    "98 00 74 05 c6 06 ff be 19 e8 17 c3 2e 83 3e bc 95"
    "01 75 09 e8 4f b2 e8 09 c3 e8 49 b2 c3"
)

RunOriginalNearCall = Callable[..., None]

SIG_OBJECT_SLOT_SCAN_GUARD_AC81 = bytes.fromhex("83 3e ac bd 01 75 03 e9 b9 fd b9 23 00 bb b4 23 8b 46 04 8b 7e 02")

SIG_OBJECT_TILE_SWEEP_BLOCKED_B032 = bytes.fromhex("c7 06 30 a4 01 00 c3")

SIG_PLAYER_HAZARD_SCAN_GUARD_BDD0 = bytes.fromhex(
    "83 7e 0a 01 74 64 b9 23 00 bb b4 23 a1 36 a4 8b 3e 38 a4"
)

SIG_VIEW_CONTACT_RECT_TEST_8331 = bytes.fromhex(
    "8b 36 f2 95 83 c6 10 39 76 02 7f 1e 83 ee 20 39 76 02 "
    "7c 16 8b 36 f4 95 83 c6 10 39 76 04 7f 0a 83 ee 20 "
    "39 76 04 7c 02 f9 c3 f8 c3"
)

SIG_COLLISION_CLC_RET_835B = bytes.fromhex("f8 c3")

SIG_TILE_COLLISION_PROBE_AC28 = bytes.fromhex(
    "83 3e 7c a4 00 74 03 e9 12 fe 83 3e ac bd 01 75 03 e9 08 fe "
    "e8 34 a4 83 c3 0d e8 16 a4 75 0f f7 46 04 0f 00 74 06 43 "
    "e8 09 a4 75 02 f8 c3 80 3e c0 98 00 74 05 c6 06 ff be 0e "
    "c7 46 24 05 00 83 3e dc be 00 75 07 83 3e 24 23 01 75 df "
    "ff 4e 20 75 da c7 46 24 00 00 f9 c3"
)


def run_postmove_y_clamp_bcb1(cpu) -> None:
    """Lift 1010:BCB1, the shared BC4B post-move Y clamp leaf.

    The portable clamp decision lives in ``recovered.systems.collision`` and
    the exact CMP/FLAGS/store choreography lives in the collision adapter.
    This address-facing wrapper only owns the original near-return boundary.
    """
    run_postmove_y_clamp_bcb1_body(cpu, pop_return=True)


def run_postmove_contact_window_aa71(cpu) -> None:
    """Lift 1010:AA71, the BC4B post-move contact-window helper.

    The gameplay predicate now lives in ``recovered.systems.collision`` and the
    ASM-compatible compare/flags sequence lives in the collision adapter.  This
    address-facing wrapper only preserves the original hook name and boundary.
    """
    run_postmove_contact_window_aa71_body(cpu)


def run_object_deactivate_logic_dispatch_c054(cpu) -> None:
    """Model the observed BD17/BFC7 -> C054 variant dispatcher.

    C054 is now split the same way as other recovered source-like helpers:
    the pure object system classifies the logic-id family, the object-behavior
    adapter replays the original CMP/order/side effects, and this exported
    function remains only the address-facing entry used by parent hooks.
    """
    run_object_deactivate_logic_dispatch_c054_body(cpu)



def run_object_tile_sweep_blocked_b032(cpu, self_disable_if_patched) -> None:
    """Lift 1010:B032, the shared tile-sweep blocked sentinel tail.

    Directional branches in the B00D tile-response table jump here when a probe
    finds a blocking/contact tile.  The routine only marks ``DS:A430`` and
    returns to the original B00D caller; keep it as a raw scratch flag, not as a
    semantic collision event.
    """
    if self_disable_if_patched(cpu, 0xB032, SIG_OBJECT_TILE_SWEEP_BLOCKED_B032, "overkill_object_tile_sweep_blocked_b032"):
        return
    mark_tile_sweep_blocked(cpu)
    cpu.s.ip = cpu.pop()

def run_collision_clc_ret_835b(cpu, self_disable_if_patched) -> None:
    """Lift OVERKILL 1010:835B ``CLC ; RET`` view/contact miss helper."""
    if self_disable_if_patched(cpu, 0x835B, SIG_COLLISION_CLC_RET_835B, "overkill_collision_clc_ret_835b"):
        return
    set_carry_and_return(cpu, False)


def run_view_contact_rect_test_8331(cpu, self_disable_if_patched) -> None:
    """Lift 1010:8331, the raw object-vs-view contact rectangle test.

    The address-facing hook now delegates to the recovered source-layer
    primitive.  That primitive still mutates SI/FLAGS exactly like the ASM
    instruction sequence, while the wrapper owns the final STC/CLC RET tail.
    """
    if self_disable_if_patched(cpu, 0x8331, SIG_VIEW_CONTACT_RECT_TEST_8331, "overkill_view_contact_rect_test_8331"):
        return

    center_x, center_y = view_contact_centers(cpu)
    hit = run_signed_center_rect_test_8331(
        cpu,
        ObjectSlotView.from_ss_bp(cpu),
        center_x=center_x,
        center_y=center_y,
    )
    set_carry_and_return(cpu, hit)

def run_player_hazard_scan_guard_bdd0(cpu, self_disable_if_patched) -> None:
    """Lift 1010:BDD0, guard/setup wrapper around the BDE3 hazard scan.

    BDD0 is the parent of the already-lifted ``BDE3`` object-record scan.  It
    gates on the current object's layer/type field at ``SS:[BP+0Ah]``, prepares
    the scan registers from the A436/A438 probe globals, and then transfers into
    the same BDE3 scan body.
    """
    if self_disable_if_patched(cpu, 0xBDD0, SIG_PLAYER_HAZARD_SCAN_GUARD_BDD0, "overkill_player_hazard_scan_guard_bdd0"):
        return

    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    current = ObjectSlotView.from_ss_bp(cpu)

    gate = current.gate_or_layer
    _cmp_word(cpu, gate, 0x0001)
    if gate == 0x0001:
        set_carry_and_return(cpu, False)
        return

    s.cx = OBJECT_TABLE_COUNT
    s.bx = OBJECT_TABLE_BASE
    s.ax = mem.rw(ds, 0xA436)
    s.di = mem.rw(ds, 0xA438)
    run_player_hazard_object_scan_bde3(cpu, lambda *_args: False)

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
    s.ax = mem.rw(ss, (bp + OFF_Y) & 0xFFFF)
    s.di = mem.rw(ss, (bp + OFF_X) & 0xFFFF)
    run_object_slot_scan_ac97(cpu)


def run_object_slot_scan_ac97(cpu) -> None:
    """Collapse the hot 1010:AC97 object-overlap scan loop.

    AC97 walks the effect/contact slot table prepared by AC81 and finds object
    overlaps around the current object's probe point.  The pure source-like
    decision now lives in ``recovered.systems.collision``; this lifted routine
    keeps only the scan loop, continuation choices, and ASM-visible register /
    flag state.
    """
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF
    bx = s.bx & 0xFFFF
    cx = s.cx & 0xFFFF
    probe_y = s.ax & 0xFFFF
    probe_x = s.di & 0xFFFF

    # 8086 LOOP decrements CX before testing it, so an initial CX=0000 means
    # 65536 iterations.  Captured gameplay uses CX=0023, but preserve the CPU
    # semantics for verifier/oracle fixtures.
    if cx == 0:
        cx = 0x10000

    current_record = read_object_slot_record(ObjectSlotView(cpu.mem, ss, bp))

    while cx:
        slot = ObjectSlotView(cpu.mem, ds, bx)
        overlaps, actionable, acd9_entry_flags = run_object_overlap_candidate_checks_ac97(
            cpu,
            current_record=current_record,
            slot=slot,
            probe_x=probe_x,
            probe_y=probe_y,
        )
        if overlaps and actionable:
            s.ax = probe_y
            s.bx = bx
            s.cx = cx & 0xFFFF
            s.di = probe_x
            s.flags = acd9_entry_flags
            s.ip = 0xACD9
            return

        old_bx = bx
        bx = (bx + OBJECT_SLOT_STRIDE) & 0xFFFF
        cpu.set_add_flags(old_bx, OBJECT_SLOT_STRIDE, old_bx + OBJECT_SLOT_STRIDE, 16)
        cx = (cx - 1) & 0xFFFF

        s.bx = bx
        s.cx = cx
        s.ax = probe_y
        s.di = probe_x
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

    The object candidate semantics now live in the recovered pure collision
    system; this hook remains the ASM-compatible scan/continuation shell that
    preserves BX/CX/AX/DI/SI/FLAGS for verification.
    """
    if self_disable_if_patched(cpu, 0xBDE3, SIG_PLAYER_HAZARD_OBJECT_SCAN_BDE3, "overkill_player_hazard_object_scan_bde3"):
        return

    s = cpu.s
    ds = s.ds & 0xFFFF
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF
    bx = s.bx & 0xFFFF
    cx = s.cx & 0xFFFF
    probe_y = s.ax & 0xFFFF
    probe_x = s.di & 0xFFFF
    if cx == 0:
        cx = 0x10000

    current_view = ObjectSlotView(cpu.mem, ss, bp)
    current_record = read_object_slot_record(current_view)

    while cx:
        slot = ObjectSlotView(cpu.mem, ds, bx)
        if run_player_hazard_candidate_checks_bde3(
            cpu,
            current_record=current_record,
            slot=slot,
            probe_x=probe_x,
            probe_y=probe_y,
        ):
            s.bx = bx
            s.cx = cx
            s.ax = probe_y
            s.di = probe_x
            # Original BE32 `JMP 1010:5059` (STC; RET).  Land on the 5059 stub
            # rather than collapsing it eagerly: SI and the link-key CMP flags are
            # already set by the candidate check, matching the ASM exactly at the
            # jump target, and the VM (or the child-call drain in object_runtime)
            # then runs 5059's STC;RET to set carry and return to the caller.
            s.ip = 0x5059
            return

        old_bx = bx
        bx = (bx + OBJECT_SLOT_STRIDE) & 0xFFFF
        cpu.set_add_flags(old_bx, OBJECT_SLOT_STRIDE, old_bx + OBJECT_SLOT_STRIDE, 16)
        cx = (cx - 1) & 0xFFFF
        if cx == 0:
            break

    s.bx = bx
    s.cx = 0
    s.ax = probe_y
    s.di = probe_x
    cpu.set_flag(CF, False)
    s.ip = cpu.pop()


def run_tile_collision_probe_ac28(cpu, self_disable_if_patched) -> None:
    """Lift the runtime-patched AC28 tile collision probe.

    The recovered tilemap layer owns the pure row-below/adjacent-Y sampling
    plan, and the collision adapter owns the ASM-compatible 5073/505B calls,
    global gates, object countdown side effects, and carry/continuation
    semantics.  Keep this wrapper as the patch guard and original hook entry
    point only.
    """
    if self_disable_if_patched(cpu, 0xAC28, SIG_TILE_COLLISION_PROBE_AC28, "overkill_tile_collision_probe_ac28"):
        return
    run_tile_collision_probe_ac28_body(cpu)

def run_collision_stc_ret_5059(cpu, self_disable_if_patched) -> None:
    """Lift OVERKILL 1010:5059 ``STC ; RET`` collision-hit helper."""
    if self_disable_if_patched(cpu, 0x5059, SIG_COLLISION_STC_RET_5059, "overkill_collision_stc_ret_5059"):
        return
    cpu.set_flag(CF, True)
    cpu.s.ip = cpu.pop()


def run_tile_lookup_505b(cpu, self_disable_if_patched) -> None:
    """Lift OVERKILL 1010:505B tile-id lookup helper.

    The shared adapter owns the exact instruction-shaped body and validates it
    against the pure recovered tile-class mapping.  Keep this wrapper as the
    patch guard and original hook entry point only.
    """
    if self_disable_if_patched(cpu, 0x505B, SIG_TILE_LOOKUP_505B, "overkill_tile_lookup_505b"):
        return
    run_tile_lookup_505b_body(cpu, pop_return=True)


def run_tile_probe_5073(cpu, self_disable_if_patched) -> None:
    """Lift OVERKILL 1010:5073 coordinate-to-tile-index helper.

    The shared adapter owns the exact instruction-shaped body and validates it
    against the pure recovered tile-offset formula.  Keep this wrapper as the
    patch guard and original hook entry point only.
    """
    if self_disable_if_patched(cpu, 0x5073, SIG_TILE_PROBE_5073, "overkill_tile_probe_5073"):
        return
    run_tile_probe_5073_body(cpu, pop_return=True)


def run_tile_contact_probe_4ff9(cpu, self_disable_if_patched) -> None:
    """Lift OVERKILL 1010:4FF9 tile/contact probe around an object point.

    The recovered tilemap system now owns the pure sampling plan: three
    side-offset entries from DS:214E, one/two column samples based on DS:215A
    low nibble, and optional adjacent-Y sampling.  The adapter preserves the
    original stack restore, BX/CX loop, and CF result.  Keep this wrapper as the
    patch guard and original hook entry point only.
    """
    if self_disable_if_patched(cpu, 0x4FF9, SIG_TILE_CONTACT_PROBE_4FF9, "overkill_tile_contact_probe_4ff9"):
        return
    run_tile_contact_probe_4ff9_body(cpu)


def run_post_contact_status_helper_9e19(
    cpu,
    self_disable_if_patched,
    run_original_near_call: RunOriginalNearCall,
) -> None:
    """Lift 1010:9E19, the post-contact/status counter helper.

    This helper is reached by the lifted ``9CB6`` contact fanout and by the
    ``B24D`` overlap branch.  The proven behavior is still raw state/counter
    management, not a semantic damage/player-health model: it gates on
    ``A47C``, ``2384`` and ``A95A``, decrements ``A95C`` by a BEDC-dependent
    amount, occasionally decrements ``A95A``, emits raw ``BEFF`` event bytes,
    and calls the existing status/display children ``61DC``/``511F``.
    """
    if self_disable_if_patched(
        cpu,
        0x9E19,
        SIG_POST_CONTACT_STATUS_HELPER_9E19,
        "overkill_post_contact_status_helper_9e19",
    ):
        return

    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    ds = s.ds & 0xFFFF

    def ret() -> None:
        s.ip = cpu.pop()

    def call(ip: int, ret_ip: int, *, max_steps: int = 120000) -> None:
        run_original_near_call(cpu, ip & 0xFFFF, ret_ip & 0xFFFF, max_steps=max_steps)
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, ret_ip & 0xFFFF):
            raise RuntimeError(
                f"9E19 expected 1010:{ip & 0xFFFF:04X} to return "
                f"1010:{ret_ip & 0xFFFF:04X}, got "
                f"{s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}"
            )

    def set_beff_when_98c0_nonzero(value: int) -> None:
        v98c0 = mem.rb(ds, 0x98C0)
        _cmp_byte(cpu, v98c0, 0x00)
        if v98c0 != 0:
            mem.wb(ds, 0xBEFF, value & 0xFF)

    def display_status_effects() -> None:
        call(0x61DC, 0x9EC5, max_steps=120000)
        v95bc = mem.rw(cs, 0x95BC)
        _cmp_word(cpu, v95bc, 0x0001)
        if v95bc == 0x0001:
            call(0x511F, 0x9ED0, max_steps=120000)
            call(0x61DC, 0x9ED3, max_steps=120000)
            call(0x511F, 0x9ED6, max_steps=120000)
        ret()

    def reset_short_cooldown_and_ret() -> None:
        mem.ww(ds, 0xA95A, 0x0003)
        mem.ww(ds, 0xA95C, 0x0018)
        ret()

    def active_guard() -> bool:
        v_a47c = mem.rw(ds, 0xA47C)
        _cmp_word(cpu, v_a47c, 0x0001)
        if v_a47c == 0x0001:
            ret()
            return False
        v2384 = mem.rw(ds, 0x2384)
        _cmp_word(cpu, v2384, 0x0003)
        if v2384 >= 0x0003:
            ret()
            return False
        return True

    if not active_guard():
        return

    v_a95a = mem.rw(ds, 0xA95A)
    _cmp_word(cpu, v_a95a, 0xFFFF)
    if v_a95a == 0xFFFF:
        ret()
        return

    mem.ww(ds, 0x23A0, 0x0008)
    set_beff_when_98c0_nonzero(0x0F)

    bedc = mem.rw(ds, 0xBEDC)
    _cmp_word(cpu, bedc, 0x0000)
    if bedc != 0x0000:
        bedc = mem.rw(ds, 0xBEDC)
        _cmp_word(cpu, bedc, 0x0001)
        if bedc != 0x0001:
            dec = _dec_mem_word_preserve_cf(cpu, ds, 0xA95C)
            if dec == 0:
                goto_refill = True
            else:
                goto_refill = False
        else:
            goto_refill = False
        if not goto_refill:
            dec = _dec_mem_word_preserve_cf(cpu, ds, 0xA95C)
            if dec == 0:
                goto_refill = True
    else:
        goto_refill = False

    if not goto_refill:
        dec = _dec_mem_word_preserve_cf(cpu, ds, 0xA95C)
        if dec != 0:
            display_status_effects()
            return

    mem.ww(ds, 0xA95C, 0x0018)
    if not active_guard():
        return

    set_beff_when_98c0_nonzero(0x03)

    bedc = mem.rw(ds, 0xBEDC)
    _cmp_word(cpu, bedc, 0x0000)
    if bedc == 0x0000:
        old_a362 = mem.rb(ds, 0xA362)
        result_a362 = (old_a362 + 1) & 0xFF
        mem.wb(ds, 0xA362, result_a362)
        cpu.set_add_flags(old_a362, 1, old_a362 + 1, 8)
        result_a362 = _and_mem_byte(cpu, ds, 0xA362, 0x01)
        if result_a362 != 0:
            ret()
            return

    dec = _dec_mem_word_preserve_cf(cpu, ds, 0xA95A)
    _cmp_word(cpu, dec, 0xFFFF)
    if dec != 0xFFFF:
        display_status_effects()
        return

    mem.ww(ds, 0xA95C, 0x0000)
    v9791 = mem.rb(ds, 0x9791)
    _cmp_byte(cpu, v9791, 0x01)
    if v9791 == 0x01:
        reset_short_cooldown_and_ret()
        return

    mem.ww(ds, 0x2384, 0x0003)
    set_beff_when_98c0_nonzero(0x19)
    display_status_effects()


def run_frame_contact_probe_fanout_9cb6(
    cpu,
    self_disable_if_patched,
    run_original_near_call: RunOriginalNearCall,
) -> None:
    """Lift 1010:9CB6, the frame-controller contact-probe fanout.

    9CB6 is the small contact side-effect wrapper isolated by the larger 9B2E
    frame-controller lift.  It first runs the recovered 4FF9 tile/contact probe.
    A clear carry returns immediately; a set carry fans out to the still-bounded
    9E19 post-contact/status helper two, three, or four times depending on the
    raw ``DS:BEDC`` selector.

    This is intentionally a frame/collision fanout primitive only.  The helper
    does not name the affected object as player/enemy/projectile; it preserves
    the original BP save/restore, CMP flag choreography, and near-return shape.
    """
    if self_disable_if_patched(
        cpu,
        0x9CB6,
        SIG_FRAME_CONTACT_PROBE_FANOUT_9CB6,
        "overkill_frame_contact_probe_fanout_9cb6",
    ):
        return

    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    ds = s.ds & 0xFFFF

    def ret() -> None:
        s.ip = cpu.pop()

    def call(ip: int, ret_ip: int, *, max_steps: int = 40000) -> None:
        run_original_near_call(cpu, ip & 0xFFFF, ret_ip & 0xFFFF, max_steps=max_steps)
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, ret_ip & 0xFFFF):
            raise RuntimeError(
                f"9CB6 expected 1010:{ip & 0xFFFF:04X} to return "
                f"1010:{ret_ip & 0xFFFF:04X}, got "
                f"{s.cs & 0xFFFF:04X}:{s.ip & 0xFFFF:04X}"
            )

    call(0x4FF9, 0x9CB9, max_steps=80000)
    if not (s.flags & CF):
        ret()
        return

    cpu.push(s.bp & 0xFFFF)
    bedc = mem.rw(ds, 0xBEDC)
    _cmp_word(cpu, bedc, 0x0000)
    if bedc != 0x0000:
        bedc = mem.rw(ds, 0xBEDC)
        _cmp_word(cpu, bedc, 0x0001)
        if bedc != 0x0001:
            call(0x9E19, 0x9CCE, max_steps=120000)
        call(0x9E19, 0x9CD1, max_steps=120000)

    call(0x9E19, 0x9CD4, max_steps=120000)
    call(0x9E19, 0x9CD7, max_steps=120000)
    s.bp = cpu.pop()
    ret()
