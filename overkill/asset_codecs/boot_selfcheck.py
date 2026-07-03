"""Pure form of OVERKILL's boot file-verification checksum (1010:C8DC-C923).

At cold boot, before the game runs, ``1010:C8DC`` reads a file in 5120-byte blocks (``int 21h``
``ah=3Fh``) and runs a running 16-bit checksum over every byte (the ``1010:C916`` inner loop),
storing the accumulator at ``CS:[C890]``.  The inner loop, per byte ``b`` at ``DS:SI`` (with
``DH=0``):

    add ax,dx      ; ax = (ax + b) & 0xFFFF        (dx == b, dh cleared at C914)
    add ah,al      ; ah = (ah + al) & 0xFF

This module is the VM-free form of that per-byte accumulation.  It is READ-ONLY (a checksum, not
a decrypt), which is why a cold-boot witness harness can safely *accelerate* the ``C916`` loop --
compute the block checksum here in one pass instead of single-stepping 65535 interpreted
iterations per block -- to get past the (multi-million-instruction) boot self-check cheaply.  The
per-byte accumulation is pinned byte-exact against the original ``C916`` opcodes by
``tests/test_boot_selfcheck.py`` (synthetic-ASM oracle).
"""
from __future__ import annotations


def boot_selfcheck_checksum(seed_ax: int, data: bytes) -> int:
    """Run the 1010:C916 running checksum over ``data``, starting from ``seed_ax`` (16-bit AX).

    Returns the 16-bit accumulator the loop leaves in AX.  Per byte: ``ax = (ax + b) & 0xFFFF``
    then ``ah = (ah + al) & 0xFF`` (AL is the low byte of the post-add AX).
    """
    ax = seed_ax & 0xFFFF
    for b in data:
        ax = (ax + b) & 0xFFFF
        al = ax & 0xFF
        ax = (((((ax >> 8) + al) & 0xFF) << 8) | al) & 0xFFFF
    return ax
