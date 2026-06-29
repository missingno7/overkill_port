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
from overkill.recovered.systems.objects import object_update_ae09, object_update_aed8

# Record field offsets the driver writes back.  These are intrinsic record-field positions (cf.
# overkill.recovered.views.object_slots); the pure systems layer cannot import the bridge ``views``,
# so the small set the driver writes is named here.
_OFF_ACTIVE = 0x00
_OFF_X = 0x02
_OFF_Y = 0x04
_OFF_DIRECTION = 0x06
_OFF_SPRITE = 0x08
_OFF_SUBSTATE = 0x1C


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


# logic_id -> per-slot advance.  Grow as handlers gain complete pure systems.
NATIVE_OBJECT_HANDLERS = {0x0C: _advance_ae09, 0x02: _advance_aed8}


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
