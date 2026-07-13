"""The level ROM: the tiny per-level data-segment table set ``native_level.py`` reads from the EXE.

CONVERGENCE slice B (docs/overkill/campaigns/convergence.md).  ``load_native_level`` needs two small
EXE-embedded tables beyond the container's own assets: the per-level CLASS-OVERRIDE table (a 6-word
pointer table plus each level's ``FF``-terminated ``{index, class}`` pair list) and the tile-plane
FOOTER constant -- 384 bytes total, contiguous in two ranges:

  * ``DS:C4AA..C5E8``  -- the class-override pointer table + all six levels' pair lists (319 bytes),
  * ``DS:D1BC..D1FC``  -- the tile-plane footer (65 bytes).

:func:`extract_level_rom` copies these once (byte-verified) out of the exe-derived bundle;
:func:`class_override_pairs_from_rom` / :func:`footer_from_rom` decode straight from that compact
384-byte blob -- no exe_image, no 1 MB scratch buffer -- so a cold level load needs only this ROM +
the recovered init + the container, not the exe.
"""
from __future__ import annotations

DATA_SEGMENT = 0x25CC

#: the data-segment offsets `native_level.py` reads (inclusive), in ROM layout order.
CLASS_TABLE_RANGE = (0xC4AA, 0xC5E8)   # the pointer table + all 6 levels' FF-terminated pair lists
FOOTER_RANGE = (0xD1BC, 0xD1FC)        # the tile-plane footer

LEVEL_ROM_RANGES = (CLASS_TABLE_RANGE, FOOTER_RANGE)
LEVEL_ROM_SIZE = sum(b - a + 1 for a, b in LEVEL_ROM_RANGES)
_CLASS_TABLE_SIZE = CLASS_TABLE_RANGE[1] - CLASS_TABLE_RANGE[0] + 1
_FOOTER_SIZE = FOOTER_RANGE[1] - FOOTER_RANGE[0] + 1


def extract_level_rom(data_image: bytes) -> bytes:
    """Copy the level-ROM ranges out of a data-segment-shaped image (e.g. the bundle), concatenated
    in range order: ``[0:319]`` the class-override span, ``[319:384]`` the footer."""
    base = DATA_SEGMENT * 16
    return b"".join(bytes(data_image[base + a: base + b + 1]) for a, b in LEVEL_ROM_RANGES)


def class_override_pairs_from_rom(rom: bytes, level: int) -> bytes:
    """One level's ``{index, class}`` override pairs, decoded straight from the extracted level-ROM
    blob (no exe_image).  Mirrors ``native_level._read_class_override_pairs`` but over the compact
    ROM layout: the first 12 bytes are the 6 levels' pointers (absolute ``DS`` offsets into the
    original class-table span), and the pair-list data follows at the pointer's ROM-relative offset."""
    table_base = CLASS_TABLE_RANGE[0]
    pointer = int.from_bytes(rom[level * 2: level * 2 + 2], "little")
    cursor = pointer - table_base
    out = bytearray()
    while True:
        index = rom[cursor]
        out.append(index)
        cursor += 1
        if index == 0xFF:
            return bytes(out)
        out.append(rom[cursor])
        cursor += 1


def footer_from_rom(rom: bytes) -> bytes:
    """The tile-plane footer (65 bytes), decoded straight from the extracted level-ROM blob."""
    return bytes(rom[_CLASS_TABLE_SIZE: _CLASS_TABLE_SIZE + _FOOTER_SIZE])
