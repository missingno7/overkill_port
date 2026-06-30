"""OVERKILL graphics load transform -- 4-plane planar -> 4bpp chunky (the 5BAC/33AF/344B family).

Blocks (`LEV{n}BLX.BIC`) and graphics (`G{n}.BIC`) are decoded into a temp buffer and then run through a
video-mode-dispatched relayout (1010:5BAC) before reaching their final buffers.  For the Tandy path
(mode 2) that relayout is a classic 4-plane planar -> 4bpp chunky de-planarize: the 33AF loop reads four
plane bytes spaced by a stride and feeds them to the 344B bit-interleaver recovered here.

This module holds the verified core packer.  The surrounding 33AF loop geometry (item walk via 44D7,
stride `CS:[5B9C]` / count `CS:[5B9E]`, the ES:DI output addressing and its mode-gated byte order) is the
remaining piece of the full transform.
"""
from __future__ import annotations


def pack_planes_344b(
    plane0: int,
    plane1: int,
    plane2: int,
    plane3: int,
    *,
    sprite_mode: bool,
    transparent_color: int = 0,
    mask_in: int = 0,
) -> tuple[int, int]:
    """Mirror 1010:344B: interleave one bit-column of 4 planes into two 4bpp chunky pixels (+ mask).

    Reads **bit 0 and bit 1** of each plane byte (the 33AF loop rotates the planes by two between calls,
    so successive calls consume successive pixel columns).  ``plane0..plane3`` are the four plane bytes in
    LSB..MSB order: each output pixel nibble is ``plane3<<3 | plane2<<2 | plane1<<1 | plane0``.  The two
    pixels are packed with the second in the high nibble and the first in the low nibble (the routine's
    closing ``ROR cl,4``).

    Returns ``(chunky, mask)``:

    * **block mode** (``sprite_mode`` False, the 347B early return -- ``CS:[0BD6]==0``, opaque blocks):
      ``chunky`` is the packed pixels and ``mask`` is ``mask_in`` passed through untouched;
    * **sprite mode** (``sprite_mode`` True, the 347C..34AC tail -- ``CS:[0BD6]!=0``, transparent
      graphics): each nibble equal to ``transparent_color`` is zeroed in ``chunky`` and flagged in the
      returned per-nibble ``mask`` (``0x0F`` low pixel transparent, ``0xF0`` high pixel transparent).

    Verified byte-for-byte against the interpreted ASM for both modes (tests/test_asset_planar.py).
    """
    planes = [plane3 & 0xFF, plane2 & 0xFF, plane1 & 0xFF, plane0 & 0xFF]  # interleave order dh,dl,ah,al
    chunky = 0
    for _ in range(2):  # two pixels: plane bit 0, then bit 1
        for i in range(4):
            value = planes[i]
            bit = value & 1
            planes[i] = ((value >> 1) | (bit << 7)) & 0xFF  # ROR plane,1
            chunky = ((chunky << 1) | bit) & 0xFF           # RCL chunky,1
    chunky = ((chunky >> 4) | (chunky << 4)) & 0xFF         # ROR chunky,4 -> swap the two pixel nibbles

    if not sprite_mode:
        return chunky, mask_in & 0xFF

    transparent = transparent_color & 0xFF
    mask = 0
    if (chunky & 0x0F) == transparent:
        mask |= 0x0F
        chunky &= 0xF0
    if ((chunky & 0xF0) >> 4) == transparent:
        mask |= 0xF0
        chunky &= 0x0F
    return chunky, mask
