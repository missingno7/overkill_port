"""Contact / overlap selector subsystem for OVERKILL object behaviors.

Several object behaviors reach a shared selector after a movement helper
returns.  These selectors all follow the same shape:

    predicate  ->  fanout  ->  side effect  ->  tail selection

The canonical instance is the ``1010:B250`` overlap/contact selector.  It tests
whether the active object slot overlaps a reference box, and on a hit emits one,
three, or five status/contact side-effect calls before routing to the contact
tail; a miss routes to the no-contact tail.

This module owns only the *selector* shape (the overlap predicate and the
save/restore fanout loop).  The raw per-call status/counter mutation lives in
the original ``1010:9E19`` helper, which the caller injects through ``near_call``
so this module stays free of the larger object-runtime import graph and so the
contact side-effect call remains a verifier-visible boundary rather than a
silently re-implemented one.

Naming is deliberately conservative (``overlap``/``contact``/``selector``): the
reference box and the 1/3/5 fanout count are proven from the disassembly, but
the gameplay meaning (what kind of object, what the contact represents) is not,
so no ``enemy``/``bullet``/``weapon`` semantics are asserted here.
"""
from __future__ import annotations

from typing import Callable

from overkill.asm import _add_reg16, _cmp_word, _sub_reg16
from overkill.recovered.views.object_slots import (
    OFF_LOGIC_ID,
    OFF_SCAN_ENABLE_OR_SOLID,
    OFF_X,
    OFF_Y,
)

# ---------------------------------------------------------------------------
# Proven layout facts for the B250 overlap/contact selector.
# ---------------------------------------------------------------------------

# DS-relative reference box the active object slot is tested against.  The box
# is anchored at (237E, 2380) and is 0x14 wide/high after the -2 inset on X.
OVERLAP_REF_BOX_X = 0x237E
OVERLAP_REF_BOX_Y = 0x2380
OVERLAP_BOX_X_INSET = 0x0002
OVERLAP_BOX_SPAN = 0x0014

# Object-slot flag at SS:[bp+1E]: when it is 1 the selector short-circuits
# straight to the no-contact tail without testing the box.  This is the same
# record word object_slots maps as OFF_SCAN_ENABLE_OR_SOLID (a "guessed" field in
# OBJECT_RECORD_FIELDS); the two lifts named its role differently.  Aliased to the
# canonical offset so there is one source for the number -- the local name stays
# until evidence settles whether "skip-overlap" and "scan-enable/solid" are one
# role, then this collapses to a single name.
OFF_SUBSTATE_1E = OFF_SCAN_ENABLE_OR_SOLID
SUBSTATE_SKIP_OVERLAP = 0x0001

# DS global that scales the contact fanout count (1, 3, or 5 side-effect calls)
# when the slot's logic id is 3.
CONTACT_FANOUT_SELECTOR = 0xBEDC

# Original target IPs the selector chooses between, plus the injected side
# effect helper and the IP execution resumes at after it returns.
TAIL_NO_CONTACT = 0xAD5A
TAIL_CONTACT = 0xADC9
CONTACT_SIDE_EFFECT_IP = 0x9E19
CONTACT_SIDE_EFFECT_RETURN_IP = 0xB29C

NearCall = Callable[..., None]


def _signed16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def run_overlap_contact_selector_b250(cpu, *, caller: str, post_contact_side_effect: NearCall) -> int:
    """Run the shared ``B250..B2A3`` overlap/contact selector.

    ``caller`` is the symbolic name of the behavior that reached B250 (used only
    for diagnostics).  ``post_contact_side_effect(cpu)`` performs one ``9E19``
    contact side-effect call, leaving IP at :data:`CONTACT_SIDE_EFFECT_RETURN_IP`
    (``B29C``); the caller injects it so this module stays independent of the
    object-runtime helper that owns that boundary.  It is now the *native* lifted
    ``9E19`` helper rather than an interpreted near call (a Phase-2 chain
    collapse), so the hot ``B297`` contact loop runs natively; the demo-replay
    equivalence suite covers the fused flow.

    Returns the selected original tail IP (:data:`TAIL_NO_CONTACT` /
    :data:`TAIL_CONTACT`).  All low-level AX/BX/CX/flag side effects of the
    original selector are preserved; the caller decides whether to compose the
    selected tail or stop at that frontier.
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    # B250: substate 1 skips the overlap test entirely.
    substate_1e = mem.rw(ss, (bp + OFF_SUBSTATE_1E) & 0xFFFF)
    _cmp_word(cpu, substate_1e, SUBSTATE_SKIP_OVERLAP)
    if substate_1e == SUBSTATE_SKIP_OVERLAP:
        return TAIL_NO_CONTACT

    # B256..B278: reject unless the slot's (X, Y) falls inside the reference box.
    cpu.s.ax = mem.rw(ds, OVERLAP_REF_BOX_X)
    cpu.s.bx = mem.rw(ds, OVERLAP_REF_BOX_Y)
    _sub_reg16(cpu, 0, OVERLAP_BOX_X_INSET)  # B25D: SUB AX,0002h.

    obj_x = mem.rw(ss, (bp + OFF_X) & 0xFFFF)
    _cmp_word(cpu, obj_x, cpu.s.ax)
    if _signed16(obj_x) < _signed16(cpu.s.ax):
        return TAIL_NO_CONTACT

    _add_reg16(cpu, 0, OVERLAP_BOX_SPAN)  # B265: ADD AX,0014h.
    obj_x = mem.rw(ss, (bp + OFF_X) & 0xFFFF)
    _cmp_word(cpu, obj_x, cpu.s.ax)
    if _signed16(obj_x) > _signed16(cpu.s.ax):
        return TAIL_NO_CONTACT

    obj_y = mem.rw(ss, (bp + OFF_Y) & 0xFFFF)
    _cmp_word(cpu, obj_y, cpu.s.bx)
    if obj_y < (cpu.s.bx & 0xFFFF):
        return TAIL_NO_CONTACT

    _add_reg16(cpu, 3, OVERLAP_BOX_SPAN)  # B272: ADD BX,0014h.
    obj_y = mem.rw(ss, (bp + OFF_Y) & 0xFFFF)
    _cmp_word(cpu, obj_y, cpu.s.bx)
    if obj_y > (cpu.s.bx & 0xFFFF):
        return TAIL_NO_CONTACT

    # B27A..B294: fanout count is 1, or 3/5 for logic_id 3 depending on BEDC.
    cpu.s.cx = 0x0001
    logic_id = mem.rw(ss, (bp + OFF_LOGIC_ID) & 0xFFFF)
    _cmp_word(cpu, logic_id, 0x0003)
    if logic_id == 0x0003:
        fanout_selector = mem.rw(ds, CONTACT_FANOUT_SELECTOR)
        _cmp_word(cpu, fanout_selector, 0x0000)
        if fanout_selector != 0:
            cpu.s.cx = 0x0003
            _cmp_word(cpu, fanout_selector, 0x0001)
            if fanout_selector != 0x0001:
                cpu.s.cx = 0x0005

    # B297..B29E: PUSH CX; PUSH BP; CALL 9E19; POP BP; POP CX; LOOP B297.
    # 9E19 owns the raw status/counter side effects; this loop owns only the
    # original save/restore shape and the CX-driven repeat count.
    while True:
        cpu.push(cpu.s.cx)
        cpu.push(cpu.s.bp)
        post_contact_side_effect(cpu)
        if (cpu.s.ip & 0xFFFF) != CONTACT_SIDE_EFFECT_RETURN_IP:
            raise RuntimeError(
                f"9E19 returned to unexpected IP {cpu.s.ip:04X} inside {caller}"
            )
        cpu.s.bp = cpu.pop()
        cpu.s.cx = cpu.pop()

        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF  # LOOP B297: no flags.
        if cpu.s.cx == 0:
            break

    return TAIL_CONTACT
