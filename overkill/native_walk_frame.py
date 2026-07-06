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
    """Advance one native object frame IN PLACE over ``image``: the 5F61 head (the A480
    wave-cleared countdown, which runs only while NO enemies are alive; hitting 0 fires the
    planet-track music restart -- CB1C, a host/audio boundary) + the per-frame counter cascade
    (which the ASM runs ALWAYS -- the old ``A47E != 0`` gate here was a smoke-probe shortcut that
    froze every animation clock whenever the field was clear), then the whole behaviour walk.
    Fail-loud on any unrecovered object (the walk raises ``RecoveryGap``)."""
    if image.rw(DS, ACTIVE_ENEMY_COUNT_A47E) == 0:
        a480 = image.rw(DS, 0xA480)
        if a480 != 0:
            image.ww(DS, 0xA480, (a480 - 1) & 0xFFFF)   # 5F6F; ==0 -> CB1C music (host boundary)
    cells = {off: image.rw(DS, off) for off in FRAME_COUNTER_CELLS}
    for off, val in advance_frame_counters_5f61(cells).items():
        image.ww(DS, off, val)
    run_behavior_walk_a9d3(image, tiles)


PROJECTION_COLUMN_TABLE_99C8 = 0x99C8   # DS:99C8 -- the per-X-column page-di base (0F0B-built)
SPECIAL_EFFECT_TABLE_32CA = 0x32CA      # entries 1..0x24 (0x24 = the player anchor 237C)
GAMEPLAY_TABLE_8D12 = 0x8D12            # entries 1..0x22


def sync_screen_projection(image) -> None:
    """The A90C present-scan's PROJECTION half: write every active record's ``+0x0C`` screen-di.

    The sprite compositor places objects from the records' ``+0x0C`` cells, which the original
    A90C/5A92 present scan computes each frame from the object x/y via the ``DS:99C8`` column table
    + the present scroll cursor ``DS:234C`` (the recovered, verify_native_screen_di-proven
    :func:`~overkill.native_video.projection.project_object_screen_di`).  Culled objects get the
    ``0xFFFF`` off-screen sentinel, exactly as the 35CC handler leaves them.  Without this pass a
    cold-booted image renders NOTHING: the walk moves the objects but their projection cells stay
    dead, so every sprite culls (the play_native stars-only bug).  Records whose draw-type (+0x14)
    selects the TWO-SLOT 75A6 sprite routine (draw-type 2 -- the player family) also get ``+0x10``:
    the 356C handler projects the SAME x at ``y + 0x10`` with its OWN cull (``3586 add [bp+2],10h``
    / ``358A call 5A36`` / ``358D/359E mov [bp+16],ax`` with the ``[234C]`` add).  Oracle: live
    anchor records carry ``+0x10 == +0x0C + 0x680`` (16 rows) on every cached frame -- refuting
    this docstring's earlier "+0x10 is always 0" claim (the half-drawn-ship playtest bug).  Loops
    the SAME tables/counts as 1010:A90C (cx=0x24 over 32CA -- entry 0x24 IS the player anchor --
    and cx=0x22 over 8D12)."""
    from overkill.native_video.projection import project_object_screen_di

    scroll = image.rw(DS, 0x234C)
    for table, count in ((SPECIAL_EFFECT_TABLE_32CA, 0x24), (GAMEPLAY_TABLE_8D12, 0x22)):
        for cx in range(1, count + 1):
            rec = image.rw(DS, (table + cx * 2) & 0xFFFF)
            if not rec or image.rw(DS, rec) == 0:
                continue
            x = image.rw(DS, rec + 0x02)
            y = image.rw(DS, rec + 0x04)
            col = image.rw(DS, (PROJECTION_COLUMN_TABLE_99C8 + x * 2) & 0xFFFF) if x < 0x00E0 \
                else 0xFFFF
            di = project_object_screen_di(x, y, col, scroll)
            image.ww(DS, rec + 0x0C, 0xFFFF if di is None else di)
            if image.rw(DS, rec + 0x14) == 2:   # the two-slot 75A6 routine -> the 356C dual cell
                x2 = (x + 0x10) & 0xFFFF        # 3586: [bp+2] += 0x10 -- 16 units ALONG the x axis
                col2 = image.rw(DS, (PROJECTION_COLUMN_TABLE_99C8 + x2 * 2) & 0xFFFF) \
                    if x2 < 0x00E0 else 0xFFFF
                di2 = project_object_screen_di(x2, y, col2, scroll)
                image.ww(DS, rec + 0x10, 0xFFFF if di2 is None else di2)


def project_state(image) -> NativeGameState:
    """Project the image's object pools + camera + HUD into a :class:`NativeGameState` for render."""
    return read_native_game_state(image, DS)
