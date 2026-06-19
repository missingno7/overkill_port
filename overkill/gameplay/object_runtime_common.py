"""Shared low-level infrastructure for the OVERKILL object runtime.

Architecture layer: **lifted**.  Leaf helpers used across the object-runtime
feature modules (spawns, deactivation, behaviors, postmove, movement): tiny
ALU shims, the fail-fast ``_raise_unverified_path`` guard, object-context
formatting for diagnostics, and the bounded verifier-visible near-call helpers.
It depends only on the VM hook bridge and the proven slot-field offsets, so it
sits below every feature module and breaks what would otherwise be import
cycles between them.  No new behavior; bodies relocated verbatim.
"""
from __future__ import annotations

from dos_re.hooks import call_installed_hook_like_near_call
from overkill.recovered.views.object_slots import (
    OFF_ACQUIRED_TARGET_PTR,
    OFF_ACTIVE_WORD,
    OFF_DRAW_LAYER,
    OFF_GATE_OR_LAYER,
    OFF_LOGIC_ID,
    OFF_OBJECT_TYPE,
    OFF_SPRITE_OR_STATE,
    OFF_SUBSTATE,
    OFF_TARGET_X,
    OFF_TARGET_Y,
)



def _or_mem_word(cpu, seg: int, off: int, value: int) -> int:
    result = cpu.mem.rw(seg, off) | (value & 0xFFFF)
    cpu.mem.ww(seg, off, result)
    cpu.set_logic_flags(result, 16)
    return result


def _neg_reg16(cpu, reg_idx: int) -> None:
    value = cpu.get_reg16(reg_idx)
    result = (-value) & 0xFFFF
    cpu.set_sub_flags(0, value, -value, 16)
    cpu.set_reg16(reg_idx, result)


def _signed16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def _format_object_context(cpu, bp: int | None = None, cx_value: int | None = None) -> str:
    parts = [
        f"CS:IP={cpu.s.cs & 0xFFFF:04X}:{cpu.s.ip & 0xFFFF:04X}",
        f"DS={cpu.s.ds & 0xFFFF:04X}",
        f"SS={cpu.s.ss & 0xFFFF:04X}",
        f"SP={cpu.s.sp & 0xFFFF:04X}",
        f"CX={cpu.s.cx & 0xFFFF:04X}",
    ]
    if cx_value is not None:
        parts.append(f"scan_cx={cx_value & 0xFFFF:04X}")
    if bp is not None:
        ss = cpu.s.ss & 0xFFFF
        bp &= 0xFFFF
        parts.append(f"BP={bp:04X}")
        for off, name in (
            (OFF_ACTIVE_WORD, "active"),
            (OFF_SPRITE_OR_STATE, "sprite_state"),
            (OFF_GATE_OR_LAYER, "layer_gate"),
            (0x0C, "draw_scratch_di"),
            (0x0E, "present_si_or_link"),
            (0x12, "row_phase"),
            (OFF_OBJECT_TYPE, "object_type_or_scan_flag"),
            (OFF_DRAW_LAYER, "draw_layer_or_hazard_class"),
            (OFF_LOGIC_ID, "logic_id"),
            (OFF_SUBSTATE, "substate"),
            (0x24, "variant"),
            (OFF_ACQUIRED_TARGET_PTR, "acquired_target_ptr"),
            (OFF_TARGET_Y, "target_y"),
            (OFF_TARGET_X, "target_x"),
        ):
            parts.append(f"{name}@+{off:02X}={cpu.mem.rw(ss, (bp + off) & 0xFFFF):04X}")
    return "; ".join(parts)


def _raise_unverified_path(
    cpu,
    *,
    parent: str,
    chain: str,
    target_ip: int | None = None,
    bp: int | None = None,
    cx_value: int | None = None,
) -> None:
    target = "immediate-ret" if target_ip is None else f"{target_ip:04X}"
    raise RuntimeError(
        f"unverified original-code path reached in {parent}: {chain} -> {target}. "
        f"Fail-fast is intentional; reverse and hook this target instead of "
        f"falling back to interpreted ASM. {_format_object_context(cpu, bp, cx_value)}"
    )


def _run_interpreted_near_call_observed(cpu, target_ip: int, return_ip: int, *, max_steps: int = 20000) -> None:
    """Run a rare original near helper from inside a larger lifted path.

    This is used for non-hot, display/bookkeeping helper tails that have not yet
    been lifted but are needed to keep gameplay moving through an observed path.
    The helper is still bounded and deterministic: it installs the same near-CALL
    return word the ASM would have pushed and steps until that continuation is
    reached.  When hook verification is active we normally keep it active inside
    the bounded call too, so any child hook address reached by the original code
    is verified at that exact VM state.
    """
    cs = cpu.s.cs & 0xFFFF
    target = (cs, return_ip & 0xFFFF)
    saved_verifier = cpu.hook_verifier
    if not getattr(cpu, "hook_verifier_verify_nested_calls", True):
        cpu.hook_verifier = None
    cpu.push(return_ip & 0xFFFF)
    cpu.s.ip = target_ip & 0xFFFF
    try:
        ctx = (
            cpu.coverage_telemetry.bounded_original((cs, target_ip & 0xFFFF), "bounded original near call")
            if cpu.coverage_telemetry is not None
            else None
        )
        if ctx is not None:
            ctx.__enter__()
        try:
            for _ in range(max_steps):
                if cpu.addr() == target:
                    return
                cpu.step()
        finally:
            if ctx is not None:
                ctx.__exit__(None, None, None)
    finally:
        cpu.hook_verifier = saved_verifier
    raise RuntimeError(
        f"interpreted helper 1010:{target_ip & 0xFFFF:04X} did not return to "
        f"1010:{return_ip & 0xFFFF:04X}; now at {cpu.s.cs & 0xFFFF:04X}:{cpu.s.ip & 0xFFFF:04X}"
    )


def _run_original_tail_to_caller(cpu, target_ip: int, *, max_steps: int = 12000) -> None:
    """Run an unlifted in-procedure tail to the current near caller return.

    The original code is not executing a CALL at this point; the caller return
    word is already at SS:SP.  Pop and re-push the same word through the bounded
    near-call helper so the final SP and below-SP scratch remain comparable.
    """
    caller_ret = cpu.pop()
    _run_interpreted_near_call_observed(cpu, target_ip & 0xFFFF, caller_ret, max_steps=max_steps)


def _call_verified_child_near(cpu, ip: int, default_handler, return_ip: int) -> None:
    """Run a lifted child routine through its real ASM hook boundary.

    Parent hooks often inline child helpers for speed/readability.  That is only
    safe for verification if the child call still reaches the hook verifier at
    the original CS:IP with the original near-CALL return word on the stack.
    Otherwise a locally wrong helper can hide inside a larger verified parent and
    only surface later as a frame/state divergence.
    """
    call_installed_hook_like_near_call(
        cpu,
        (cpu.s.cs & 0xFFFF, ip & 0xFFFF),
        default_handler,
        return_ip & 0xFFFF,
    )


def _no_patch_guard(*_args) -> bool:
    return False


def _object_ptr_from_scan_index(cpu, table_base: int, cx_value: int) -> tuple[int, int]:
    """Return (BX, BP) for OVERKILL's descending object-list scan loops."""
    bx = ((cx_value & 0xFFFF) << 1) & 0xFFFF
    bp = cpu.mem.rw(cpu.s.ds & 0xFFFF, (table_base + bx) & 0xFFFF)
    cpu.s.bx = bx
    cpu.s.bp = bp
    return bx, bp


def _push_loop_count_for_interpreted_tail(cpu, cx_value: int) -> None:
    cpu.s.sp = (cpu.s.sp - 2) & 0xFFFF
    cpu.mem.ww(cpu.s.ss & 0xFFFF, cpu.s.sp, cx_value & 0xFFFF)
