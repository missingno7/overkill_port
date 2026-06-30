"""Native object-update driver -- the VM-free per-frame object pass (pillar 2 skeleton).

This is the first piece of the native runtime that *drives* the recovered systems instead of the
coverage gate merely checking them: given a :class:`NativeGameState` and the per-frame
:class:`ObjectUpdateGlobals`, it walks each object pool and, for every active slot whose ``logic_id``
has a native whole-slot transform, produces the slot's next record -- with no VM.  Slots whose
behaviour is not yet native are left unchanged (the hybrid VM still owns them), so this composes
cleanly with the existing per-slot coverage gate that proves each wired handler byte-exact.

Wired today: the handlers with complete pure systems -- AE09 (0x0C) and AED8 (0x02).  Handlers that
tail-jump to BC4B (B86D/B9F0) join once their movement half is extracted to a pure system and composed
with ``object_postmove_bc4b``; the BC4B contact path (sprite/logic_id) is the remaining post-move work.
"""
from __future__ import annotations

import dataclasses

from overkill.recovered.domain.native_game_state import NativeGameState
from overkill.recovered.domain.object_slots import ObjectPool
from overkill.recovered.domain.object_update import ObjectUpdateGlobals
from overkill.recovered.systems.collision import object_postmove_bc4b, resolve_moving_object_collision
from overkill.recovered.systems.objects import (
    object_update_ae09,
    object_update_aed8,
    object_update_b86d,
    object_update_b9f0,
)

# Record field offsets the driver writes back.  These are intrinsic record-field positions (cf.
# overkill.recovered.views.object_slots); the pure systems layer cannot import the bridge ``views``,
# so the small set the driver writes is named here.
_OFF_ACTIVE = 0x00
_OFF_X = 0x02
_OFF_Y = 0x04
_OFF_DIRECTION = 0x06
_OFF_SPRITE = 0x08
_OFF_OBJECT_TYPE = 0x14
_OFF_LOGIC_ID = 0x18
_OFF_SUBSTATE = 0x1C
_OFF_COUNTER_20 = 0x20


def _collide_post_move(pool: ObjectPool, i: int, g: ObjectUpdateGlobals, updates: dict):
    """Run the BC4B contact scan over a B86D/B9F0 slot's post-move ``updates``.

    Returns ``(updates, collision_result_or_None)``: the original BC4B runs the 62F6 object-vs-object
    scan only when DS:A47C (``global_disable``) is zero, so with no ``candidate_pool``, A47C != 0, or a
    dead slot the contact death is left to the VM and the result is ``None``.  Otherwise it composes
    ``resolve_moving_object_collision`` over the slot's *post-move* position (62F6 runs after movement)
    and folds the scanner's collision death (sprite + logic_id 1 + counter_20) or damage (counter) into
    ``updates`` -- and returns the full result so a caller can also apply the candidate's deactivation.
    """
    if g.candidate_pool is None or g.global_disable != 0:
        return updates, None
    if updates.get(_OFF_ACTIVE, pool.active_word(i)) == 0:
        return updates, None
    result = resolve_moving_object_collision(
        scanner_active_word=updates.get(_OFF_ACTIVE, pool.active_word(i)),
        scanner_x_word=updates.get(_OFF_X, pool.x_word(i)),
        scanner_y_word=updates.get(_OFF_Y, pool.y_word(i)),
        scanner_draw_layer=pool.draw_layer(i),
        scanner_logic_id=pool.logic_id(i),
        scanner_object_type=pool.word_at(i, _OFF_OBJECT_TYPE),
        scanner_counter_20=pool.word_at(i, _OFF_COUNTER_20),
        candidates=g.candidate_pool, a8c2_boss_mode=g.a8c2_boss_mode, bedc=g.bedc,
    )
    if not result.collided or result.unclassified:
        return updates, result
    if result.died:
        return ({**updates, _OFF_SPRITE: result.death_transition.sprite_or_state,
                 _OFF_LOGIC_ID: result.death_transition.logic_id,
                 _OFF_COUNTER_20: result.new_counter_20}, result)
    return ({**updates, _OFF_COUNTER_20: result.new_counter_20}, result)


def _fold_bc4b_collision(pool: ObjectPool, i: int, g: ObjectUpdateGlobals, updates: dict) -> dict:
    """The per-slot driver's collision fold: the scanner's BC4B contact outcome only (the candidate's
    deactivation is the order-dependent pass's concern -- see ``native_object_pass_in_place``)."""
    return _collide_post_move(pool, i, g, updates)[0]


def _advance_ae09(pool: ObjectPool, i: int, g: ObjectUpdateGlobals) -> dict | None:
    u = object_update_ae09(
        pool.substate(i), pool.direction_word(i), pool.x_word(i), pool.y_word(i),
        pool.active_word(i), pool.draw_layer(i), pool.logic_id(i), g.tile_probe_suppressed, g.tiles,
    )
    return {_OFF_SUBSTATE: u.substate, _OFF_DIRECTION: u.direction_or_step, _OFF_SPRITE: u.sprite_or_state,
            _OFF_X: u.x_word, _OFF_Y: u.y_word, _OFF_ACTIVE: u.active_word}


def _advance_aed8(pool: ObjectPool, i: int, g: ObjectUpdateGlobals) -> dict | None:
    u = object_update_aed8(
        pool.substate(i), pool.direction_word(i), pool.x_word(i), pool.y_word(i), pool.active_word(i),
        pool.substate_1e(i), pool.draw_layer(i), pool.logic_id(i),
        g.ref_box_x, g.ref_box_y, g.a278, g.tile_probe_suppressed, g.tiles,
    )
    if u is None:
        return None  # unmodelled sub-path (timer death / out-of-range direction) -> leave to fallback
    return {_OFF_SUBSTATE: u.substate, _OFF_X: u.x_word, _OFF_Y: u.y_word, _OFF_ACTIVE: u.active_word}


def _advance_b86d(pool: ObjectPool, i: int, g: ObjectUpdateGlobals) -> dict | None:
    # B86D tail-jumps to BC4B, so its final slot = the movement half (object_update_b86d) composed with
    # the BC4B post-move (object_postmove_bc4b owns y/active).  The contact path may still override the
    # sprite (+ logic_id) on a collision death -- that is the deferred post-move work, so the sprite the
    # driver writes here is the movement sprite (correct unless a contact death fires).
    mv = object_update_b86d(
        pool.x_word(i), pool.y_word(i), pool.substate(i), pool.direction_word(i), pool.active_word(i),
        pool.target_x_word(i), pool.target_y_word(i), pool.move_step_error(i),
        g.a47e, g.a7a0, g.ref_box_x, g.ref_box_y, g.ref_box_scan,
        g.vertical_delta, g.phase_2328, g.step_mode, g.direction_table,
    )
    pm = object_postmove_bc4b(mv.x_word, mv.y_word, mv.active_word, pool.logic_id(i), g.global_disable)
    updates = {_OFF_DIRECTION: mv.direction_or_step, _OFF_SPRITE: mv.sprite_or_state,
               _OFF_X: mv.x_word, _OFF_Y: pm.y_word, _OFF_ACTIVE: pm.active_word}
    return _fold_bc4b_collision(pool, i, g, updates)


def _advance_b9f0(pool: ObjectPool, i: int, g: ObjectUpdateGlobals) -> dict | None:
    # B9F0, like B86D, tail-jumps to BC4B: final slot = movement half (object_update_b9f0) + the BC4B
    # post-move (object_postmove_bc4b owns y/active).  The contact path may override the sprite on a
    # collision death (deferred), so the sprite written here is the movement sprite.
    mv = object_update_b9f0(
        x_word=pool.x_word(i), y_word=pool.y_word(i), substate=pool.substate(i),
        direction=pool.direction_word(i), active_word=pool.active_word(i), sprite=pool.sprite_word(i),
        target_x=pool.target_x_word(i), target_y=pool.target_y_word(i),
        move_step_error=pool.move_step_error(i), move_delta_x=pool.move_delta_x(i),
        move_delta_y=pool.move_delta_y(i),
        a482=g.a482, frame=g.frame_233c, vertical_delta=g.vertical_delta,
        horizontal_delta=g.horizontal_delta, a47e=g.a47e, difficulty=g.difficulty, tick=g.tick,
        ref_box_x=g.ref_box_x, ref_box_y=g.ref_box_y, ref_box_scan=g.ref_box_scan,
        step_mode=g.step_mode, direction_table=g.direction_table,
    )
    pm = object_postmove_bc4b(mv.x_word, mv.y_word, mv.active_word, pool.logic_id(i), g.global_disable)
    updates = {_OFF_DIRECTION: mv.direction_or_step, _OFF_SPRITE: mv.sprite_or_state,
               _OFF_X: mv.x_word, _OFF_Y: pm.y_word, _OFF_ACTIVE: pm.active_word}
    return _fold_bc4b_collision(pool, i, g, updates)


# logic_id -> per-slot advance.  Grow as handlers gain complete pure systems.
NATIVE_OBJECT_HANDLERS = {
    0x0C: _advance_ae09,
    0x02: _advance_aed8,
    0x1D: _advance_b86d,
    0x14: _advance_b9f0,
}


def native_object_update_pool(
    pool: ObjectPool, update_globals: ObjectUpdateGlobals, handlers: dict = NATIVE_OBJECT_HANDLERS
) -> ObjectPool:
    """Advance one object pool VM-free: for each active slot whose ``logic_id`` has a native handler,
    produce its next record; leave every other slot unchanged (the hybrid VM still owns those).

    Each handler reads the slot's pre-state (and the per-frame globals) and returns the changed fields,
    so slots are independent within the pass -- exactly the per-slot movement transform the coverage
    gate verifies byte-exact against the VM.
    """
    out = pool
    for i in range(len(pool)):
        if pool.active_word(i) == 0:
            continue
        handler = handlers.get(pool.logic_id(i))
        if handler is None:
            continue
        updates = handler(pool, i, update_globals)
        if updates is None:
            continue
        for offset, value in updates.items():
            out = out.with_word(i, offset, value)
    return out


def native_object_update(
    state: NativeGameState, update_globals: ObjectUpdateGlobals, handlers: dict = NATIVE_OBJECT_HANDLERS
) -> NativeGameState:
    """Advance every object pool of a ``NativeGameState`` VM-free (the native frame's object pass)."""
    return dataclasses.replace(
        state,
        special_pool=native_object_update_pool(state.special_pool, update_globals, handlers),
        object_pool=native_object_update_pool(state.object_pool, update_globals, handlers),
        effect_pool=native_object_update_pool(state.effect_pool, update_globals, handlers),
    )


_COLLISION_LOGIC_IDS = frozenset((0x001D, 0x0014))  # B86D / B9F0: the BC4B contact-scan handlers


def native_object_pass_in_place(
    walk_pool: ObjectPool,
    candidate_pool: ObjectPool,
    update_globals: ObjectUpdateGlobals,
    *,
    entry_tick: int,
    tick_period: int = 0x05DC,
):
    """The VM's A9E0 object scan as an ORDER-DEPENDENT in-place pass (the runnable native pass).

    Unlike ``native_object_update_pool`` (snapshot, order-independent -- right for movement only), this
    mirrors the VM's loop faithfully for collision: it walks ``walk_pool`` in iteration order (the slots
    the DS:32CA/8D12 pointer table visits), advances each active native slot, and -- because the 62F6
    contact scan reads the live candidate pool -- runs the collision against the *current*
    ``candidate_pool`` and clears a killed candidate's active word so later scanners skip it.  Every walk
    entry consumes one tick (DS:2340 ``inc`` happens before the active check), so the tick is advanced
    per entry and wrapped at ``tick_period`` and fed to each slot's transform.

    Returns ``(walk_pool_out, candidate_pool_out)``.  ``update_globals.tick`` / ``.candidate_pool`` are
    set per slot from ``entry_tick`` and the live pool, so the caller passes the per-frame base globals.
    """
    out = walk_pool
    cands = candidate_pool
    tick = entry_tick & 0xFFFF
    for j in range(len(walk_pool)):
        tick = (tick + 1) % tick_period
        if out.active_word(j) == 0:
            continue
        logic_id = out.logic_id(j)
        handler = NATIVE_OBJECT_HANDLERS.get(logic_id)
        if handler is None:
            continue
        # Movement + post-move only (no fold): the in-place collision is applied below so the candidate
        # deactivation can be threaded back into the live pool.
        updates = handler(out, j, dataclasses.replace(update_globals, tick=tick, candidate_pool=None))
        if updates is None:
            continue
        if logic_id in _COLLISION_LOGIC_IDS:
            g = dataclasses.replace(update_globals, tick=tick, candidate_pool=cands)
            updates, result = _collide_post_move(out, j, g, updates)
            if result is not None and result.candidate_deactivated and result.hit_index is not None:
                cands = cands.with_word(result.hit_index, _OFF_ACTIVE, 0)
        for offset, value in updates.items():
            out = out.with_word(j, offset, value)
    return out, cands
