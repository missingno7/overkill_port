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

from .container import load_container_asset
from .planar import deplanarize_tandy

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


#: Decoded level tile-map size, in bytes (a fixed 96 x 39 grid for every level).
TILE_MAP_SIZE = 3744


def decode_level_tile_map(container_data, level: int) -> bytes:
    """Decode level ``level``'s tile map (``LEV{n}MAP.BIC``) -- the level layout grid.

    This is the first per-level destination wired up end to end: the MAP loader at 1010:0B3E reads the
    name from the `DS:14C0` table and decodes it (via `C679` -> `0248`) straight into the tile-map buffer
    at `CS:[9592]:0`.  Verified byte-for-byte: the decoded body matches that live buffer across fresh
    level-load snapshots for all six levels (see tests/test_level_map_placement.py).  The buffer's first
    row and a trailing footer are rewritten by post-load init (a border) and so are not part of the
    decoded map; mid-gameplay the body also mutates (destructible terrain).
    """
    return load_container_asset(container_data, f"LEV{level}MAP.BIC")


def decode_level_blocks(container_data, level: int) -> bytes:
    """Decode + de-planarize level ``level``'s block/tile graphics (``LEV{n}BLX.BIC``).

    Loaded to a temp buffer then run through the Tandy de-planarize (block mode -> opaque chunky); the VM
    lands the result at `CS:[959A]:0`.  Verified byte-for-byte vs that buffer for all six levels
    (see tests/test_level_graphics_placement.py).
    """
    return deplanarize_tandy(load_container_asset(container_data, f"LEV{level}BLX.BIC"), sprite_mode=False)


def decode_level_graphics(container_data, level: int) -> bytes:
    """Decode + de-planarize level ``level``'s sprite/graphics bank (``G{n}.BIC``).

    Like :func:`decode_level_blocks` but sprite mode -- the de-planarize interleaves a per-pixel
    transparency mask with the chunky pixels.  The VM lands the result at `CS:[95AE]:0`.
    """
    return deplanarize_tandy(load_container_asset(container_data, f"G{level}.BIC"), sprite_mode=True)


@dataclass(frozen=True)
class LevelData:
    """A level's fully-loaded data: the three per-level buffers, decoded + placed VM-free."""

    tile_map: bytes   # LEV{n}MAP.BIC  -> the layout grid (VM dest CS:[9592])
    blocks: bytes     # LEV{n}BLX.BIC  -> de-planarized block/tile graphics (VM dest CS:[959A])
    graphics: bytes   # G{n}.BIC       -> de-planarized sprite bank + mask (VM dest CS:[95AE])


def load_level_data(container_data, level: int) -> LevelData:
    """Load + decode + place all three of a level's data buffers from the container, fully VM-free.

    Every byte of this is verified against the live VM buffers (tile-map body, and the whole blocks +
    graphics buffers) across all six levels -- the complete per-level data load for a cold boot.
    """
    return LevelData(
        tile_map=decode_level_tile_map(container_data, level),
        blocks=decode_level_blocks(container_data, level),
        graphics=decode_level_graphics(container_data, level),
    )
