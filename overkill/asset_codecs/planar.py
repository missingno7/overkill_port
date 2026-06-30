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

#: The sprite transparent palette index (CS:[0000] in the runtime); a nibble equal to it is masked out.
GRAPHICS_TRANSPARENT_COLOR = 5


def _ror_right(value: int, count: int) -> int:
    count &= 7
    if count == 0:
        return value & 0xFF
    return ((value >> count) | (value << (8 - count))) & 0xFF


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


def deplanarize_tandy(
    planar,
    *,
    sprite_mode: bool,
    emit_item_headers: bool = False,
    transparent_color: int = GRAPHICS_TRANSPARENT_COLOR,
) -> bytes:
    """Full 1010:33AF Tandy graphics load transform: 4-plane planar image(s) -> 4bpp chunky bytes.

    The VM-free form of the mode-2 (Tandy) handler reached from 5BAC.  The input is a sequence of items,
    each a ``{width, stride}`` 2-word header (44D7) followed by ``width`` rows of four planes ``stride``
    bytes each; a ``{0, 0}`` header terminates.  For each of the ``stride`` columns in a row it reads one
    byte from each plane (``si``, ``si+stride``, ``si+2*stride``, ``si+3*stride``), de-planarizes the 8
    pixels through :func:`pack_planes_344b` four times (rotating the planes by two per call), and emits
    them in the routine's byte order:

    * **block mode** (``sprite_mode`` False, the 0CC8/BLX path): four chunky bytes ``cl4,cl3,cl2,cl1``;
    * **sprite mode** (``sprite_mode`` True, the 0CD8/G path): eight bytes interleaving the per-call
      transparency mask and pixels ``ch4,ch3,cl4,cl3,ch2,ch1,cl2,cl1``.

    ``emit_item_headers`` selects the third (``bd8``) variant -- the 0CB8 path used for multi-item
    directory assets (e.g. THEND/PANEL): each item's ``{width, stride}`` (little-endian words) is written
    into the output ahead of its de-planarized data, so the result is self-describing.  (The original also
    records each item's output offset in a separate CS:[0BE0] directory; that index is derivable from the
    emitted headers and is not produced here.)

    Verified byte-for-byte against the live dest buffers: CS:[959A] blocks / CS:[95AE] graphics for all
    six levels (block + sprite), and the directory-mode CS:[95B2]/[95B4] (THEND/PANEL).
    """
    src = bytes(planar)
    out = bytearray()
    si = 0

    def u16(i: int) -> int:
        return src[i] | (src[i + 1] << 8)

    while si + 4 <= len(src):
        if (u16(si) | u16(si + 2)) == 0:  # {0,0} terminator (44D7)
            break
        width = u16(si)
        si += 2
        stride = u16(si)
        si += 2
        if emit_item_headers:  # bd8 directory mode: prefix each item with its dimensions
            out += bytes((width & 0xFF, width >> 8, stride & 0xFF, stride >> 8))
        for _row in range(width):
            for _col in range(stride):
                p0, p1, p2, p3 = src[si], src[si + stride], src[si + 2 * stride], src[si + 3 * stride]
                cl = []
                ch = []
                for k in range(4):
                    shift = 2 * k
                    chunk, mask = pack_planes_344b(
                        _ror_right(p0, shift),
                        _ror_right(p1, shift),
                        _ror_right(p2, shift),
                        _ror_right(p3, shift),
                        sprite_mode=sprite_mode,
                        transparent_color=transparent_color,
                    )
                    cl.append(chunk)
                    ch.append(mask)
                if sprite_mode:
                    out += bytes((ch[3], ch[2], cl[3], cl[2], ch[1], ch[0], cl[1], cl[0]))
                else:
                    out += bytes((cl[3], cl[2], cl[1], cl[0]))
                si += 1
            si += 3 * stride
    return bytes(out)
