"""Compose the native sprite draw list from a NativeGameState's object pools (Bucket C).

This is the brief's "compose the FrameSnapshot sprites from recovered state instead of
capturing the VM page" step.  It walks ``NativeGameState``'s object pools in the present scan's
order -- the leading view-anchor ``special_pool`` (DS:237C) first, then the gameplay table
(DS:8D12 -> 2B5C), then the effect table (DS:32CA -> 23B4); the order proven witnessed-exact by
``frame_snapshot_adapter``/``witness_draw_order`` -- takes the active slots, and projects each
through the recovered draw placement (:func:`project_object_screen_di`, the 35CC ``+0C``
composition, verified byte-exact vs the VM at ~17k draws), dropping culled objects.  The result
is the ``(sprite, screen_di)`` draw list the backend blits via ``composite_sprites`` -- computed
from recovered state with no VM read of ``+0C``.

Native render host: composes the pure projection (``native_video``) over the object-pool records
(``recovered.domain``), reading fields through the pool's named accessors -- no VM-facing
``views``/``adapters`` import, so the native runtime depends only on recovered domain/systems.
"""
from __future__ import annotations

from overkill.native_video.projection import build_native_sprite_layer


def native_sprite_draws(game_state, column_table, scroll) -> tuple:
    """Build the native sprite draw list from ``game_state`` (a NativeGameState).

    ``column_table`` is the DS:99C8 per-column base (indexed by object X; the static
    0F0B-built table); ``scroll`` is the present cursor DS:234C.  Walks ``special_pool`` then
    ``object_pool`` then ``effect_pool`` (the witnessed-exact present/draw order), takes each
    active slot (``+00 != 0``), and composes its ``(sprite_or_state, x, y)`` through
    :func:`build_native_sprite_layer` (which projects via the recovered 35CC ``+0C`` formula and
    drops off-screen culls).  Returns ``((sprite, screen_di), ...)`` in draw order -- the
    complete native draw list, no VM read.
    """
    objects = []
    for pool in (game_state.special_pool, game_state.object_pool, game_state.effect_pool):
        for i in range(len(pool.slots)):
            if pool.active_word(i) != 0:
                objects.append((
                    pool.sprite_word(i),
                    pool.x_word(i),
                    pool.y_word(i),
                ))
    return build_native_sprite_layer(objects, column_table, scroll)
