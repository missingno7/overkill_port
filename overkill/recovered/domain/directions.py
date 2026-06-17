"""Pure direction constants shared by recovered movement and collision systems."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

DirectionComponent = Literal["left", "down", "right", "up"]


@dataclass(frozen=True, slots=True)
class Direction8:
    """One entry of OVERKILL's recovered clockwise 8-way direction table."""

    index: int
    dx_unit: int
    dy_unit: int
    components: tuple[DirectionComponent, ...]


# Recovered clockwise direction order shared by 5DB2 movement stepping and B00D
# tile-sweep decomposition.  The diagonal tile-sweep entries use component
# order as executed by the original CALL+fallthrough table.
DIRECTIONS_8: tuple[Direction8, ...] = (
    Direction8(0, -1, 0, ("left",)),
    Direction8(1, -1, 1, ("left", "down")),
    Direction8(2, 0, 1, ("down",)),
    Direction8(3, 1, 1, ("down", "right")),
    Direction8(4, 1, 0, ("right",)),
    Direction8(5, 1, -1, ("right", "up")),
    Direction8(6, 0, -1, ("up",)),
    Direction8(7, -1, -1, ("up", "left")),
)


def direction8(direction: int) -> Direction8:
    """Return a recovered 8-way direction entry or raise for invalid input."""
    if direction < 0 or direction >= len(DIRECTIONS_8):
        raise ValueError(f"unsupported recovered 8-way direction {direction!r}")
    entry = DIRECTIONS_8[direction]
    if entry.index != direction:
        raise AssertionError("DIRECTIONS_8 index table is corrupt")
    return entry
