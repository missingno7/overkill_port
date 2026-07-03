"""OVERKILL file checksum loader routine.

This module corresponds to the hot checksum loop at 1010:C916.  The algorithm is
not a generic checksum library; it preserves the exact register and flag result
that OVERKILL's loader expects after validating data files.
"""
from __future__ import annotations

from ._flags import CF
from .asm_adapters import loop_count


def compute_overkill_file_checksum(cpu) -> None:
    """Replace the loop body at 1010:C916 and continue at 1010:C91F.

    Original loop:

        mov dl, [si]
        add ax, dx
        add ah, al
        inc si
        loop C916

    The routine is called with ordinary 8086 LOOP semantics, so CX=0 means
    65536 iterations.  The final CF must be the one produced by ADD AH,AL, while
    the other live flags are from the final INC SI.
    """
    count = loop_count(cpu.s.cx)

    ax = cpu.s.ax & 0xFFFF
    dh_part = cpu.s.dx & 0xFF00
    ds_base = (cpu.s.ds & 0xFFFF) << 4
    off = cpu.s.si & 0xFFFF
    remaining = count
    data = cpu.mem.data
    last_b = cpu.s.dx & 0xFF
    carry_after_ah_add = cpu.get_flag(CF)

    while remaining:
        chunk = min(remaining, 0x10000 - off)
        start = (ds_base + off) & 0xFFFFF
        for b in data[start:start + chunk]:
            last_b = b
            ax = (ax + (dh_part | b)) & 0xFFFF
            al = ax & 0xFF
            ah = (ax >> 8) & 0xFF
            sum8 = ah + al
            carry_after_ah_add = sum8 > 0xFF
            ax = ((sum8 & 0xFF) << 8) | al
        off = (off + chunk) & 0xFFFF
        remaining -= chunk

    old_si = (cpu.s.si + count - 1) & 0xFFFF
    final_si = (cpu.s.si + count) & 0xFFFF
    cpu.s.ax = ax & 0xFFFF
    cpu.s.dx = dh_part | last_b
    cpu.s.si = final_si
    cpu.s.cx = 0

    cpu.set_add_flags(old_si, 1, old_si + 1, 16)
    cpu.set_flag(CF, carry_after_ah_add)
    cpu.s.ip = 0xC91F
