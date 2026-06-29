"""Pure tilemap-domain records recovered from 5073/505B helpers."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TileProbeInput:
    """Copied inputs for the recovered 1010:5073 coordinate-to-tile probe.

    ``origin_x_word`` is the raw DS:234E addend; ``row_base_word`` is the raw
    DS:2350 base used after converting adjusted X to a 13-column stride;
    ``object_x_word``/``object_y_word`` are the probed record coordinates.
    """

    origin_x_word: int
    row_base_word: int
    object_x_word: int
    object_y_word: int


@dataclass(frozen=True, slots=True)
class TileProbeResult:
    """Portable result of the recovered 1010:5073 tile-offset computation."""

    adjusted_x_word: int
    tile_offset_word: int
    negative_adjusted_x: bool


@dataclass(frozen=True, slots=True)
class TileLookupInput:
    """Copied inputs for the recovered 1010:505B tile-class lookup."""

    raw_tile_byte: int
    class_table: Sequence[int]


@dataclass(frozen=True, slots=True)
class TileLookupResult:
    """Portable result of the recovered 1010:505B tile-class lookup."""

    raw_tile_byte: int
    class_byte: int


@dataclass(frozen=True, slots=True)
class LevelTileContext:
    """The level tile-map inputs the AD60 tile-probe samples (a seed of the native LevelState).

    ``origin_x_word`` (DS:234E) + ``row_base_word`` (DS:2350) are the 5073 probe globals; ``tile_plane``
    is the raw tile-byte grid (the CS:[9592] segment, indexed by the 5073 tile offset); ``class_table``
    is the 256-entry DS:C3AA raw-tile -> class map.  The hybrid path reads these from VM memory; the
    standalone path owns them as part of LevelState."""

    origin_x_word: int
    row_base_word: int
    tile_plane: Sequence[int]
    class_table: Sequence[int]


@dataclass(frozen=True, slots=True)
class TileContactProbePlan:
    """Pure plan for the recovered 1010:4FF9 tile/contact probe.

    ``valid_side`` names the original ``[BP+8] < 3`` gate.  ``offset_table_index``
    is the side selector used to pick a 4-byte dx/dy pair from DS:214E.
    ``column_sample_count`` is recovered from DS:215A low nibble after 5073:
    4FF9 samples one tile column when the adjusted X nibble is <= 0Ah and two
    columns otherwise.  ``probe_adjacent_y`` names the ``[BP+4] & 0Fh`` gate
    that optionally checks the neighboring tile in the same column sample.
    """

    valid_side: bool
    offset_table_index: int
    column_sample_count: int
    probe_adjacent_y: bool


@dataclass(frozen=True, slots=True)
class TileCollisionProbePlan:
    """Pure sampling plan for the recovered 1010:AC28 tile-collision probe.

    AC28 is a narrower collision probe than 4FF9.  After 5073 maps the object
    point to a tile offset, AC28 samples the tile one row below (``+13``).  If
    the probed Y coordinate is not 16-pixel aligned, it also samples the
    adjacent Y tile (``+1``).  The adapter owns the live 505B lookups and object
    countdown side effects; this record captures only the portable sampling
    shape.
    """

    row_delta: int
    probe_adjacent_y: bool
