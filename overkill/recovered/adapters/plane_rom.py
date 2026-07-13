"""The tile-plane ROM: the small set of CS-plane-segment bytes the frame reads that the recovered
level load does NOT produce (the "border rows" item flagged in convergence.md).

CONVERGENCE slice B (docs/overkill/campaigns/convergence.md).  A prior estimate put this at ~9,925
bytes from a raw content-diff against a blank baseline -- that overcounts hugely, the same way the
CS-segment slice-read investigation found "239 diverging bytes" that turned out to be dead
video/save-under content, not a real code dependency.  The RIGHT measurement is read-before-write
over actual gameplay (the same methodology `scripts/measure_rom_footprint.py` uses for the whole
image), scoped to the tile-PLANE segment (`CS:[9592]`) outside the map-body region the container
already fills: **347 bytes across 111 small runs**, measured over 3,000 synthetic gameplay frames on
each of the 6 levels (plateaus quickly -- 300 frames already found 259-279 of the 347).

Every byte matches across all 6 levels **except one** (`0x3A76`), which is exactly the level's own
PLANET id (1,2,3,4,5,0 for levels 0..5) -- a value the cold-start seed already computes, not a real
per-level ROM entry.  So this is a single shared constant blob PLUS one already-known patched byte.
"""
from __future__ import annotations

#: the tile-plane segment pointer cell (CS:[9592] holds the segment number).
PLANE_SEGMENT_POINTER_CELL = 0x9592
CS_SEGMENT = 0x1010

#: byte OFFSET RUNS within the plane segment the frame reads-before-write (inclusive), measured via
#: read-before-write tracking over 3,000 gameplay frames on each of the 6 levels (union of all six).
PLANE_ROM_RANGES: tuple[tuple[int, int], ...] = (
    (0x0000, 0x000B), (0x1730, 0x1731), (0x1774, 0x1774), (0x2BE0, 0x2BE9),
    (0x37C6, 0x37E7), (0x37EA, 0x37F3), (0x37F6, 0x37FF), (0x385E, 0x3865),
    (0x386E, 0x3871), (0x3A32, 0x3A37), (0x3A44, 0x3A65), (0x3A68, 0x3A69),
    (0x3A6C, 0x3A71), (0x3A76, 0x3A79), (0x3A9C, 0x3AA1), (0x3AA4, 0x3AA5),
    (0x3AAA, 0x3AAB), (0x3AAE, 0x3AB1), (0x3AC0, 0x3AC1), (0x3AD4, 0x3AD5),
    (0x3ADE, 0x3ADF), (0x3AE2, 0x3AE3), (0x3AE8, 0x3AED), (0x3AF8, 0x3AF9),
    (0x3B0C, 0x3B0D), (0x3B1A, 0x3B1B), (0x3B30, 0x3B31), (0x3B44, 0x3B45),
    (0x3B52, 0x3B53), (0x3B68, 0x3B69), (0x3B72, 0x3B73), (0x3B7C, 0x3B7D),
    (0x3B8A, 0x3B8B), (0x3BA0, 0x3BA1), (0x3BAA, 0x3BAB), (0x3BB4, 0x3BB5),
    (0x3BC2, 0x3BC3), (0x3BD8, 0x3BD9), (0x3BE2, 0x3BE3), (0x3BEC, 0x3BED),
    (0x3BFA, 0x3BFB), (0x3C10, 0x3C11), (0x3C1A, 0x3C1B), (0x3C24, 0x3C25),
    (0x3C32, 0x3C33), (0x3C48, 0x3C49), (0x3C52, 0x3C53), (0x3C5C, 0x3C5D),
    (0x3C6A, 0x3C6B), (0x3C80, 0x3C81), (0x3C8A, 0x3C8B), (0x3C94, 0x3C95),
    (0x3CA2, 0x3CA3), (0x3CB8, 0x3CB9), (0x3CC2, 0x3CC3), (0x3CCC, 0x3CCD),
    (0x3CDA, 0x3CDB), (0x3CF0, 0x3CF1), (0x3CFA, 0x3CFB), (0x3D04, 0x3D05),
    (0x3D12, 0x3D13), (0x3D28, 0x3D29), (0x3D32, 0x3D33), (0x3D3C, 0x3D3D),
    (0x3D4A, 0x3D4B), (0x3D60, 0x3D61), (0x3D6A, 0x3D6B), (0x3D74, 0x3D75),
    (0x3D82, 0x3D83), (0x3D98, 0x3D99), (0x3DA2, 0x3DA3), (0x3DAC, 0x3DAD),
    (0x3DBA, 0x3DBB), (0x3DD0, 0x3DD1), (0x3DDA, 0x3DDB), (0x3DE4, 0x3DE5),
    (0x3DF2, 0x3DF3), (0x3E08, 0x3E09), (0x3E12, 0x3E13), (0x3E1C, 0x3E1D),
    (0x3E2A, 0x3E2B), (0x3E40, 0x3E41), (0x3E4A, 0x3E4B), (0x3E54, 0x3E55),
    (0x3E62, 0x3E63), (0x3E78, 0x3E79), (0x3E82, 0x3E83), (0x3E8C, 0x3E8D),
    (0x3E9A, 0x3E9B), (0x3EB0, 0x3EB1), (0x3EBA, 0x3EBB), (0x3EC4, 0x3EC5),
    (0x3ED2, 0x3ED3), (0x3EE8, 0x3EE9), (0x3EF2, 0x3EF3), (0x3EFC, 0x3EFD),
    (0x3F0A, 0x3F0B), (0x3F20, 0x3F21), (0x3F2A, 0x3F2B), (0x3F34, 0x3F35),
    (0x3F42, 0x3F43), (0x3F58, 0x3F59), (0x3F6C, 0x3F6D), (0x3F7A, 0x3F7B),
    (0x3F90, 0x3F91), (0x3FA4, 0x3FA5), (0x3FB2, 0x3FB3), (0x3FC8, 0x3FC9),
    (0x3FD2, 0x3FD3), (0x3FDC, 0x3FDD), (0x3FEA, 0x3FEB),
)

PLANE_ROM_SIZE = sum(b - a + 1 for a, b in PLANE_ROM_RANGES)

#: the single per-level-varying byte: it holds the level's own PLANET id (1,2,3,4,5,0 for levels
#: 0..5), a value the cold-start seed already computes elsewhere -- not a real per-planet ROM entry.
PLANET_ID_OFFSET = 0x3A76
LEVEL_INDEX_TO_PLANET = (1, 2, 3, 4, 5, 0)


def extract_plane_rom(data_image: bytes, plane_segment: int) -> bytes:
    """Copy the plane-ROM ranges out of a plane-segment-shaped image, concatenated in range order."""
    base = plane_segment * 16
    return b"".join(bytes(data_image[base + a: base + b + 1]) for a, b in PLANE_ROM_RANGES)


def apply_plane_rom(mem, plane_segment: int, rom: bytes, level_index: int) -> None:
    """Write the plane-ROM bytes into ``mem`` at ``plane_segment`` (a MutFlatMemory), patching the one
    per-level byte to ``level_index``'s own planet id."""
    base = plane_segment * 16
    off = 0
    for a, b in PLANE_ROM_RANGES:
        n = b - a + 1
        mem.data[base + a: base + b + 1] = rom[off: off + n]
        off += n
    planet = LEVEL_INDEX_TO_PLANET[level_index % len(LEVEL_INDEX_TO_PLANET)]
    mem.data[base + PLANET_ID_OFFSET] = planet
