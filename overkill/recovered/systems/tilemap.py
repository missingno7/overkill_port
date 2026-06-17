"""Pure recovered tilemap systems.

No CPU, memory, DOS segment, or hook state is allowed here.  These functions are
portable source-like forms of the shared 1010:5073 coordinate-to-tile probe and
1010:505B tile-class lookup used by movement/collision gameplay paths.
"""
from __future__ import annotations

from collections.abc import Sequence

from overkill.recovered.domain.coords import u16
from overkill.recovered.domain.tilemap import (
    TileContactProbePlan,
    TileCollisionProbePlan,
    TileLookupInput,
    TileLookupResult,
    TileProbeInput,
    TileProbeResult,
)

TILE_PROBE_PIXEL_SHIFT = 4
TILE_PROBE_COLUMN_STRIDE = 13
TILE_PROBE_NEGATIVE_SENTINEL = 0xFFFF
TILE_PROBE_Y_PIXEL_MASK = 0xFFF0
TILE_CLASS_TABLE_SIZE = 0x0100

# 1010:4FF9 tile/contact probe constants.  The probe reuses 5073/505B but
# adds a small side-offset table and a two-column/two-row sampling plan.
TILE_CONTACT_SIDE_COUNT = 3
TILE_CONTACT_OFFSET_PAIR_STRIDE_BYTES = 4
TILE_CONTACT_ROW_DELTA = TILE_PROBE_COLUMN_STRIDE
TILE_CONTACT_LOW_NIBBLE_MASK = 0x000F
TILE_CONTACT_SECOND_COLUMN_THRESHOLD = 0x000A

# 1010:AC28 tile-collision probe constants.  This routine reuses 5073/505B
# but only samples the tile one map row below the object, plus the neighboring
# Y tile when the probed object Y is not 16-pixel aligned.
TILE_COLLISION_ROW_DELTA = TILE_PROBE_COLUMN_STRIDE
TILE_COLLISION_LOW_NIBBLE_MASK = 0x000F


def compute_tile_probe_5073(inputs: TileProbeInput) -> TileProbeResult:
    """Return the pure coordinate-to-tile offset recovered from 1010:5073.

    The original stores ``origin_x + object_x`` in DS:215A, rejects negative
    adjusted X with ``BX=FFFFh``, otherwise computes::

        x_tile = adjusted_x >> 4
        y_tile = (object_y & FFF0h) >> 4
        BX = row_base - x_tile * 13 + y_tile

    The flag/register choreography remains in the adapter; this function owns
    only the gameplay-shaped arithmetic.
    """
    adjusted_x = u16(inputs.origin_x_word + inputs.object_x_word)
    if adjusted_x & 0x8000:
        return TileProbeResult(
            adjusted_x_word=adjusted_x,
            tile_offset_word=TILE_PROBE_NEGATIVE_SENTINEL,
            negative_adjusted_x=True,
        )

    x_tile = adjusted_x >> TILE_PROBE_PIXEL_SHIFT
    y_tile = (inputs.object_y_word & TILE_PROBE_Y_PIXEL_MASK) >> TILE_PROBE_PIXEL_SHIFT
    tile_offset = u16(inputs.row_base_word - x_tile * TILE_PROBE_COLUMN_STRIDE + y_tile)
    return TileProbeResult(
        adjusted_x_word=adjusted_x,
        tile_offset_word=tile_offset,
        negative_adjusted_x=False,
    )


def lookup_tile_class_505b(inputs: TileLookupInput) -> TileLookupResult:
    """Return the pure tile-class mapping recovered from 1010:505B."""
    raw = inputs.raw_tile_byte & 0x00FF
    if len(inputs.class_table) != TILE_CLASS_TABLE_SIZE:
        raise ValueError(f"tile class table must have 256 entries, got {len(inputs.class_table)}")
    return TileLookupResult(raw_tile_byte=raw, class_byte=inputs.class_table[raw] & 0x00FF)


def lookup_tile_class_byte(raw_tile_byte: int, class_table: Sequence[int]) -> int:
    """Convenience wrapper for the recovered raw-tile -> class-byte mapping."""
    return lookup_tile_class_505b(TileLookupInput(raw_tile_byte & 0x00FF, tuple(class_table))).class_byte




def is_tile_contact_side_valid_4ff9(side_index_word: int) -> bool:
    """Return 4FF9's recovered side-selector gate (``[BP+8] < 3``)."""
    return (side_index_word & 0xFFFF) < TILE_CONTACT_SIDE_COUNT


def tile_contact_probe_plan_4ff9(
    *,
    side_index_word: int,
    adjusted_x_word: int,
    y_word: int,
) -> TileContactProbePlan:
    """Return the portable sampling plan recovered from 1010:4FF9.

    The original routine first gates ``[BP+8]`` to the three entries in the
    DS:214E dx/dy table.  After applying the selected offset and running 5073,
    it samples one or two tile columns according to the adjusted X low nibble.
    For each column, it optionally samples the neighboring Y tile when the
    adjusted Y is not 16-pixel aligned.
    """
    side = side_index_word & 0xFFFF
    valid_side = side < TILE_CONTACT_SIDE_COUNT
    low_nibble = adjusted_x_word & TILE_CONTACT_LOW_NIBBLE_MASK
    column_sample_count = 1 if low_nibble <= TILE_CONTACT_SECOND_COLUMN_THRESHOLD else 2
    return TileContactProbePlan(
        valid_side=valid_side,
        offset_table_index=side if valid_side else side,
        column_sample_count=column_sample_count,
        probe_adjacent_y=(y_word & TILE_CONTACT_LOW_NIBBLE_MASK) != 0,
    )


def tile_contact_offset_table_byte_offset(side_index_word: int) -> int:
    """Return the DS:214E byte offset selected by 4FF9's side index."""
    return (side_index_word & 0xFFFF) * TILE_CONTACT_OFFSET_PAIR_STRIDE_BYTES


def tile_collision_probe_plan_ac28(*, y_word: int) -> TileCollisionProbePlan:
    """Return the portable sampling plan recovered from 1010:AC28."""
    return TileCollisionProbePlan(
        row_delta=TILE_COLLISION_ROW_DELTA,
        probe_adjacent_y=(y_word & TILE_COLLISION_LOW_NIBBLE_MASK) != 0,
    )
