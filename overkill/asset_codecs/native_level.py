"""Cold-boot level loader -- assemble a complete native level state from the EXE image + container.

This is the capstone of the VM-free level data load.  Given the unpacked OVERKILL EXE image (the source
of the level-init data-segment constants -- the same bytes a real boot has after the self-extracting EXE
unpacks, i.e. ``static_runtime_bundle/memory_1mb.bin`` or ``unpack(OVERKILL.EXE)``) and the asset
container (``assets/OVERKILL``), :func:`load_native_level` produces a :class:`NativeLevel` carrying every
per-level buffer the recovered systems need -- each already verified byte-for-byte against the live VM:

* ``tile_plane``   -- the byte-exact `CS:[9592]` tile grid (decoded map + the post-load border);
* ``class_table``  -- the `DS:C3AA` raw-tile -> class map;
* ``blocks``       -- the de-planarized `LEV{n}BLX.BIC` block graphics (`CS:[959A]`);
* ``graphics``     -- the de-planarized `G{n}.BIC` sprite bank + mask (`CS:[95AE]`).

The recovered tile probe consumes a :class:`~overkill.recovered.domain.tilemap.LevelTileContext` built
from ``tile_plane`` + ``class_table`` plus the per-frame scroll; this loader owns the static half.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

from overkill.recovered.adapters.level_rom import class_override_pairs_from_rom, footer_from_rom

from .level_assets import (
    TILE_PLANE_FOOTER_SIZE,
    build_level_class_table,
    decode_level_blocks,
    decode_level_graphics,
    decode_level_tile_map,
    finalize_level_tile_plane,
)

#: The OVERKILL runtime data segment; the level-init constants live here in the unpacked image.
DATA_SEGMENT = 0x25CC
_FOOTER_OFFSET = 0xD1BC          # DS:D1BC -- the 65-byte tile-plane footer constant
_CLASS_PTR_TABLE_OFFSET = 0xC4AA  # DS:C4AA[level] -> offset of that level's {index,class} override list


def _data_linear(offset: int) -> int:
    return DATA_SEGMENT * 16 + offset


@dataclass(frozen=True)
class NativeLevel:
    """A cold-loaded level's static data buffers, each byte-verified against the live VM."""

    level: int
    tile_plane: bytes
    class_table: bytes
    blocks: bytes
    graphics: bytes


def _read_class_override_pairs(exe_image, level: int) -> bytes:
    pointer = struct.unpack_from("<H", exe_image, _data_linear(_CLASS_PTR_TABLE_OFFSET) + level * 2)[0]
    out = bytearray()
    cursor = _data_linear(pointer)
    while True:
        index = exe_image[cursor]
        out.append(index)
        cursor += 1
        if index == 0xFF:
            return bytes(out)
        out.append(exe_image[cursor])
        cursor += 1


def load_native_level(exe_image, container, level: int) -> NativeLevel:
    """Load + decode + finalize all of level ``level``'s data buffers, fully VM-free.

    ``exe_image`` is the unpacked OVERKILL EXE image (the level-init data-segment constants); ``container``
    is the ``assets/OVERKILL`` bytes.  Every returned buffer is byte-for-byte identical to the
    corresponding live VM buffer (see tests/test_native_level.py).
    """
    footer = bytes(exe_image[_data_linear(_FOOTER_OFFSET) : _data_linear(_FOOTER_OFFSET) + TILE_PLANE_FOOTER_SIZE])
    tile_plane = finalize_level_tile_plane(decode_level_tile_map(container, level), footer)
    class_table = build_level_class_table(_read_class_override_pairs(exe_image, level))
    return NativeLevel(
        level=level,
        tile_plane=tile_plane,
        class_table=class_table,
        blocks=decode_level_blocks(container, level),
        graphics=decode_level_graphics(container, level),
    )


def load_native_level_from_rom(level_rom: bytes, container, level: int) -> NativeLevel:
    """:func:`load_native_level`'s CONVERGENCE counterpart: the same result, sourced from the compact
    384-byte :mod:`overkill.recovered.adapters.level_rom` blob instead of the 1 MB exe image -- no
    ``exe_image``, no data-segment-shaped scratch buffer.  Byte-identical to ``load_native_level`` fed
    the exe the ROM was extracted from (see ``tests/test_level_rom.py``)."""
    footer = footer_from_rom(level_rom)
    tile_plane = finalize_level_tile_plane(decode_level_tile_map(container, level), footer)
    class_table = build_level_class_table(class_override_pairs_from_rom(level_rom, level))
    return NativeLevel(
        level=level,
        tile_plane=tile_plane,
        class_table=class_table,
        blocks=decode_level_blocks(container, level),
        graphics=decode_level_graphics(container, level),
    )
