"""The native ROM: the tiny CS-segment table set the VM-less engine reads from the code image.

CONVERGENCE slice A (docs/overkill/campaigns/convergence.md).  Measurement proved the native frame
reads the 64 KB code segment (CS = 0x1010) ONLY through these ranges (both `rb/rw` and slice reads):

  * ``8D92..8F91``  -- a 512-byte lookup table (tile-block indices),
  * ``9590..95C4``  -- the segment-pointer + video-mode/row-source constant block,
  * ``EE6C..EE79``  -- a 14-byte lookup.

With the rest of the code segment ZEROED the game logic + DGROUP state stay byte-exact over gameplay
(``tests/test_native_rom.py``).  So these ~580 bytes are the entire code-segment dependency: extract
them once (byte-verified) and the runtime no longer needs the 1 MB exe-derived bundle for its code --
only this ``native_rom`` + the recovered init + the container.  This module carries only the range
ADDRESSES; :func:`extract_native_rom` copies the bytes out of whatever image the caller supplies.
"""
from __future__ import annotations

CS_SEGMENT = 0x1010
CS_SIZE = 0x10000

#: the code-segment offsets the frame reads (inclusive), in address order.
NATIVE_ROM_RANGES: tuple[tuple[int, int], ...] = (
    (0x8D92, 0x8F91),
    (0x9590, 0x95C4),
    (0xEE6C, 0xEE79),
)

NATIVE_ROM_SIZE = sum(b - a + 1 for a, b in NATIVE_ROM_RANGES)


def extract_native_rom(code_image: bytes) -> bytes:
    """Copy the native-ROM ranges out of a code image (e.g. the bundle), concatenated in range order.
    The one-time recovery step; the result is byte-verifiable and replaces the 1 MB bundle's code."""
    base = CS_SEGMENT * 16
    return b"".join(bytes(code_image[base + a: base + b + 1]) for a, b in NATIVE_ROM_RANGES)


def apply_native_rom(mem, rom: bytes) -> None:
    """Zero the CS code segment of ``mem`` (a MutFlatMemory) and write back only the native-ROM ranges
    -- i.e. reconstruct the code image the engine actually needs from ``rom`` alone."""
    base = CS_SEGMENT * 16
    mem.data[base: base + CS_SIZE] = bytearray(CS_SIZE)
    off = 0
    for a, b in NATIVE_ROM_RANGES:
        n = b - a + 1
        mem.data[base + a: base + b + 1] = rom[off: off + n]
        off += n
