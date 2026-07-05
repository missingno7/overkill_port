"""The native OBJECT FRAME over a DGROUP image -- the runtime composition play_native ticks.

This is the wiring seam between the recovered pieces and the running game: given a ``MutFlatMemory``
DGROUP image and the level tile context, advance one object frame the way the VM's gameplay loop
does -- the per-frame counter cascade (``advance_frame_counters_5f61``, the enemy phase clocks) then
the whole behaviour walk (``run_behavior_walk_a9d3``, every active object's AI) -- and project the
result back into a :class:`NativeGameState` the renderer + exit detector already consume.

The image is the single source of truth for the OBJECT POOLS (enemies / shots / effects); the caller
(play_native) still owns the player anchor via ``NativeGame`` and SYNCS it into the image each tick
(``sync_player_anchor``) so the companion + enemies track the player.  Fully VM-free.
"""
from __future__ import annotations

from overkill.recovered.adapters.behavior_walk import run_behavior_walk_a9d3
from overkill.recovered.adapters.native_game_state_adapter import read_native_game_state
from overkill.recovered.domain.native_game_state import NativeGameState
from overkill.recovered.domain.tilemap import LevelTileContext
from overkill.recovered.systems.frame_loop import (
    FRAME_COUNTER_CELLS,
    advance_frame_counters_5f61,
)

DS = 0x25CC
CODE_SEG = 0x1010
TILE_PLANE_SEG_CELL = 0x9592
ANCHOR_RECORD = 0x237C          # the player view-anchor object record
VIEW_X_237E, VIEW_Y_2380 = 0x237E, 0x2380
ACTIVE_ENEMY_COUNT_A47E = 0xA47E


def level_tiles(image) -> LevelTileContext:
    """Build the level tile context the object walk samples from the image (the CS:[9592] plane +
    the DS:C3AA class table)."""
    plane_seg = image.rw(CODE_SEG, TILE_PLANE_SEG_CELL)
    return LevelTileContext(
        origin_x_word=image.rw(DS, 0x234E), row_base_word=image.rw(DS, 0x2350),
        tile_plane=bytes(image.data[plane_seg * 16:plane_seg * 16 + 0x4000]),
        class_table=tuple(image.rb(DS, (0xC3AA + i) & 0xFFFF) for i in range(256)))


def sync_player_anchor(image, x_word: int, y_word: int, sprite_word: int) -> None:
    """Write the player's live position into the image's anchor record + the view globals, so the
    companion follows and the enemies aim at the player.  ``sprite_word`` also drives DS:2384 (which
    aliases the anchor's +0x08 -- the companion/pickup pose gate)."""
    image.ww(DS, ANCHOR_RECORD + 0x02, x_word & 0xFFFF)
    image.ww(DS, ANCHOR_RECORD + 0x04, y_word & 0xFFFF)
    image.ww(DS, ANCHOR_RECORD + 0x08, sprite_word & 0xFFFF)
    image.ww(DS, VIEW_X_237E, x_word & 0xFFFF)
    image.ww(DS, VIEW_Y_2380, y_word & 0xFFFF)


GAMEPLAY_POOL_BASE = 0x2B5C
GAMEPLAY_SLOTS = 0x22
RECORD_STRIDE = 0x38


def sync_new_gameplay_records(image, pool) -> int:
    """Copy records the dataclass-side fan-out CREATED this tick into the image's gameplay pool
    (ADR-1: the image is the state; anything mutated outside it must flow in within the tick).

    Without this, a fired player shot lives only in the dataclass pool and is DESTROYED when the
    walked image is projected back over it (the dual-state bug).  A record is 'new' when the
    dataclass slot is active but the image's same-index slot is not; the full 0x38-byte record is
    copied.  Returns how many records were synced."""
    synced = 0
    for i in range(min(len(pool), GAMEPLAY_SLOTS)):
        if pool.active_word(i) == 0:
            continue
        rec = GAMEPLAY_POOL_BASE + i * RECORD_STRIDE
        if image.rw(DS, rec) != 0:
            continue
        for w in range(RECORD_STRIDE // 2):
            image.ww(DS, rec + w * 2, pool.word_at(i, w * 2))
        synced += 1
    return synced


def advance_object_frame(image, tiles: LevelTileContext) -> None:
    """Advance one native object frame IN PLACE over ``image``: the per-frame counter cascade (when
    enemies are alive) then the whole behaviour walk.  Fail-loud on any unrecovered object (the walk
    raises ``RecoveryGap``)."""
    if image.rw(DS, ACTIVE_ENEMY_COUNT_A47E) != 0:
        cells = {off: image.rw(DS, off) for off in FRAME_COUNTER_CELLS}
        for off, val in advance_frame_counters_5f61(cells).items():
            image.ww(DS, off, val)
    run_behavior_walk_a9d3(image, tiles)


def project_state(image) -> NativeGameState:
    """Project the image's object pools + camera + HUD into a :class:`NativeGameState` for render."""
    return read_native_game_state(image, DS)
