"""Small OVERKILL decoded-asset table helpers.

These are not byte-stream decoders themselves; they are loader-side table scans
that run immediately after asset materialization and decide whether the decoded
asset is already present in the resident cache/list.
"""
from __future__ import annotations


def search_decoded_asset_table_c713(cpu) -> None:
    """Replace the table-search loop at 1010:C713.

    Original loop::

        C713  lodsw
        C714  cmp ax,[21AA]
        C718  jne C71B
        C71A  ret
        C71B  cmp ax,FFFFh
        C71E  jne C713
        C720  ... allocate/cache decoded asset

    Entry SI is live: the first call normally arrives from C710 with SI=14D0,
    but loop-back iterations also re-enter at C713 with SI already advanced.
    On a matching asset id, this consumes the caller return address.  On the
    FFFF terminator, it leaves the stack untouched and continues at C720.
    """
    ds = cpu.s.ds & 0xFFFF
    si = cpu.s.si & 0xFFFF
    target = cpu.mem.rw(ds, 0x21AA)

    for _ in range(0x8000):
        ax = cpu.mem.rw(ds, si)
        si = (si + 2) & 0xFFFF
        cpu.s.ax = ax
        cpu.s.si = si

        cpu.set_sub_flags(ax, target, ax - target, 16)  # CMP AX,[21AA]
        if ax == target:
            cpu.s.ip = cpu.pop()
            return

        cpu.set_sub_flags(ax, 0xFFFF, ax - 0xFFFF, 16)  # CMP AX,FFFFh
        if ax == 0xFFFF:
            cpu.s.ip = 0xC720
            return

    raise RuntimeError("OVERKILL C713 decoded-asset table search did not reach match or FFFF terminator")
