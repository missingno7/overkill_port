"""Per-level asset mapping -- which container assets each OVERKILL level loads.

Derived from the level-init data tables read out of the runtime image: the MAP-pointer table at DS:14C0
(LEV0MAP..LEV7MAP), the {graphics, blocks} list at DS:14E8 walked by the per-level loader 1010:0E9C
(loads LEV{n}BLX.BIC -> dest seg CS:[959A], G{n}.BIC -> dest seg CS:[95AE]), and the MAP supplied from
14C0.  For the six real levels (0..5) the names follow ``LEV{n}MAP.BIC`` / ``LEV{n}BLX.BIC`` / ``G{n}.BIC``
-- confirmed both by those tables and by every name resolving to a container asset that decodes
(tests/test_level_assets.py).  Level slots 6/7 in the MAP table alias earlier levels and are not real
game levels.

This is the "what to load" half of a level load; the "where it lands in NativeGameState" half (the dest
segments -> tile map / block / graphics buffers) is the next step and is not modelled here yet.
"""
from __future__ import annotations

from dataclasses import dataclass

#: The number of real, distinct OVERKILL levels.
LEVEL_COUNT = 6

#: Asset roles in a level load (in the order the level-init touches them).
ROLE_MAP = "map"          # LEV{n}MAP.BIC  -- the level tile map (layout)
ROLE_BLOCKS = "blocks"    # LEV{n}BLX.BIC  -- the block / tile-index definitions
ROLE_GRAPHICS = "graphics"  # G{n}.BIC      -- the tile/graphics pixel bank


@dataclass(frozen=True)
class LevelAsset:
    """One asset a level pulls from the container: its name and its role in the level."""

    name: str
    role: str


def overkill_level_assets(level: int) -> list[LevelAsset]:
    """The per-level assets (map, blocks, graphics) for real level ``level`` (0..5)."""
    if not 0 <= level < LEVEL_COUNT:
        raise ValueError(f"level {level} out of range 0..{LEVEL_COUNT - 1}")
    return [
        LevelAsset(f"LEV{level}MAP.BIC", ROLE_MAP),
        LevelAsset(f"LEV{level}BLX.BIC", ROLE_BLOCKS),
        LevelAsset(f"G{level}.BIC", ROLE_GRAPHICS),
    ]
