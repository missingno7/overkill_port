"""Object post-move tails for the OVERKILL object runtime.

Architecture layer: **lifted**.  The BC45 post-move prelude and the BC4B
post-move hub carved out of ``object_runtime.py``.  BC4B is the junction the
object behaviours jump to after moving: it runs the view-window/contact-window
checks, fans out to the 62F6 overlap scan and 9E69 post-contact tails
(``contact_side_effects.py``), and routes into the death/deactivation tails
(``object_deactivation.py``).  Bodies relocated verbatim; conservative names.
"""
from __future__ import annotations

from dos_re.cpu import CF
from overkill.asm import _add_mem_word, _cmp_word
from overkill.gameplay.collision import run_postmove_contact_window_aa71
from overkill.gameplay.contact_side_effects import (
    _run_object_overlap_scan_62f6,
    _run_post_contact_9e69_observed,
)
from overkill.gameplay.object_deactivation import (
    _run_collision_death_tail_bfc7,
    _run_deactivate_bd17_observed,
)
from overkill.gameplay.object_runtime_common import (
    _call_verified_child_near,
    _remember_balanced_push_scratch,
)
from overkill.gameplay.view_window import _run_view_window_check_aa46
from overkill.recovered.views.object_slots import OFF_LOGIC_ID, OFF_OBJECT_TYPE, OFF_X, OFF_Y



def _call_aa71(cpu, return_ip: int) -> None:
    _call_verified_child_near(cpu, 0xAA71, run_postmove_contact_window_aa71, return_ip)


def run_object_postmove_prelude_bc45(cpu, *, parent: str = "1010:BC45", chain: str = "BC45 -> BC4B", cx_value: int | None = None) -> None:
    """Run the tiny 1010:BC45 prelude and the shared BC4B postmove chain.

    Several object behaviours jump to ``BC45`` instead of calling ``BC4B``
    directly.  The prelude reloads ``AX`` from the global vertical delta
    ``DS:A278`` and adds it into ``SS:[BP+02]`` before falling through to BC4B.
    Keep this as a wrapper around the single BC4B implementation so the
    collision/postmove tail is not duplicated.
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    cpu.s.ax = cpu.mem.rw(ds, 0xA278)
    _add_mem_word(cpu, ss, (bp + OFF_X) & 0xFFFF, cpu.s.ax)
    if cx_value is None:
        cx_value = cpu.s.cx & 0xFFFF
    _run_object_postmove_bc4b(cpu, parent=parent, chain=chain, cx_value=cx_value & 0xFFFF)
    cpu.s.ip = cpu.pop()


def _run_object_postmove_bc4b(cpu, *, parent: str, chain: str, cx_value: int, clamp_y: bool = True) -> None:
    """Run the observed BC4B post-move/bounds/collision helper path."""
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    if clamp_y:
        # BCB1: clamp Y into the 0..C0h range.  Some callers jump directly to
        # BC4F, after this call; those use clamp_y=False.
        y = mem.rw(ss, (bp + OFF_Y) & 0xFFFF)
        _cmp_word(cpu, y, 0x00C0)
        sy = y if y < 0x8000 else y - 0x10000
        if sy > 0x00C0:
            mem.ww(ss, (bp + OFF_Y) & 0xFFFF, 0x00C0)
        else:
            _cmp_word(cpu, y, 0)
            if sy < 0:
                mem.ww(ss, (bp + OFF_Y) & 0xFFFF, 0)
        _remember_balanced_push_scratch(cpu, 0xBC4E)

    global_disable = mem.rw(ds, 0xA47C)
    _cmp_word(cpu, global_disable, 0)
    skip_precise_x = global_disable != 0 or mem.rw(ss, (bp + OFF_LOGIC_ID) & 0xFFFF) in (0, 0x48, 0x26, 0x86, 0x28, 0x29, 0x34)
    x = mem.rw(ss, (bp + OFF_X) & 0xFFFF)
    sx = x if x < 0x8000 else x - 0x10000
    if not skip_precise_x:
        _cmp_word(cpu, x, 0xFF40)
        if sx < -0x00C0:
            _run_deactivate_bd17_observed(cpu, parent=parent, chain=f"{chain} -> BC4B", cx_value=cx_value, pop_return=False)
            return
        _cmp_word(cpu, x, 0x00F0)
        if sx >= 0x00F0:
            _run_deactivate_bd17_observed(cpu, parent=parent, chain=f"{chain} -> BC4B", cx_value=cx_value, pop_return=False)
            return
    else:
        _cmp_word(cpu, x, 0xFFEC)
        if sx < -0x0014:
            _run_deactivate_bd17_observed(cpu, parent=parent, chain=f"{chain} -> BC4B", cx_value=cx_value, pop_return=False)
            return
        _cmp_word(cpu, x, 0x00F0)
        if sx >= 0x00F0:
            _run_deactivate_bd17_observed(cpu, parent=parent, chain=f"{chain} -> BC4B", cx_value=cx_value, pop_return=False)
            return

    _cmp_word(cpu, global_disable, 0)
    if global_disable == 0:
        # BC4B reaches the contact checks through CALL BCCB.  Even though BCCB
        # balances SP before returning, its nested CALLs leave return-address
        # scratch below SP; keep the real BCAD call frame live while modelling
        # BCCB so later nested calls land at the same stack offsets.
        bccb_sp = cpu.s.sp & 0xFFFF
        cpu.push(0xBCAD)
        try:
            # BCCB early exits for inactive/exempt objects; otherwise it may call
            # the view-window helper and only continues into hit logic if CF is set.
            _cmp_word(cpu, mem.rw(ss, bp), 0)
            if mem.rw(ss, bp) != 0:
                for off, bad in ((0x16, 5), (0x18, 0), (0x18, 1)):
                    _cmp_word(cpu, mem.rw(ss, (bp + off) & 0xFFFF), bad)
                    if mem.rw(ss, (bp + off) & 0xFFFF) == bad:
                        break
                else:
                    obj_type = mem.rw(ss, (bp + OFF_OBJECT_TYPE) & 0xFFFF)
                    _cmp_word(cpu, obj_type, 1)
                    if obj_type == 1:
                        # BCF4 CALL AA46 leaves BCF7 below BCCB's live frame.
                        saved_sp = cpu.s.sp & 0xFFFF
                        cpu.push(0xBCF7)
                        _run_view_window_check_aa46(cpu)
                        cpu.s.sp = saved_sp
                    elif obj_type == 2:
                        # BCF9 CALL AA71 leaves BCFC below BCCB's live frame.
                        saved_sp = cpu.s.sp & 0xFFFF
                        _call_aa71(cpu, 0xBCFC)
                        cpu.s.sp = saved_sp
                    else:
                        return
                    if cpu.get_flag(CF):
                        _cmp_word(cpu, mem.rw(ds, 0xA8C2), 0x0001)
                        if mem.rw(ds, 0xA8C2) != 0x0001:
                            cpu.push(0xBD09)
                            _run_collision_death_tail_bfc7(
                                cpu,
                                parent=parent,
                                chain=f"{chain} -> BCCB",
                                cx_value=cx_value,
                            )
                        # BD09 CALL 9E69 must run with BD0C on the stack, not
                        # merely written below the current SP.  The 9E69 -> 9E98
                        # display tail calls 61DC, whose nested scratch is part
                        # of the verifier-visible freed stack bytes.
                        saved_sp = cpu.s.sp & 0xFFFF
                        cpu.push(0xBD0C)
                        _run_post_contact_9e69_observed(
                            cpu,
                            parent=parent,
                            chain=f"{chain} -> BCCB -> BD09",
                            cx_value=cx_value,
                        )
                        cpu.s.sp = saved_sp
        finally:
            cpu.s.sp = bccb_sp
        # BCAD CALL 62F6 leaves the BCB0 return word as stack scratch below SP.
        saved_sp = cpu.s.sp & 0xFFFF
        cpu.push(0xBCB0)
        _run_object_overlap_scan_62f6(cpu, parent=parent, chain=f"{chain} -> BC4B", cx_value=cx_value)
        cpu.s.sp = saved_sp
