"""The AFD8 contact-step worker (enemy locomotion) -- the pure ``B022`` direction handlers.

``1010:AFD8`` is the shared worker 21 behavior-zoo handlers call: "try to move this object ONE PIXEL
in the direction of its ``+0x06`` field, with terrain collision (the recovered ``5073``/``505B``
tilemap probes) and a contact scan (``BDD0``); return no-contact as ZF, with ``DS:A430`` as the
blocked/contact flag".  This module recovers the per-direction step handlers dispatched through
``CS:B022`` (cold-loaded by ``adapters/contact_step_dispatch_adapter``) as pure functions.

The tile-offset domain: ``dx`` is the ``5073`` coordinate->tile offset of the object's probe point;
``+1`` = one tile row down, ``-0xD`` = one tile column right (the plane is column-major with 13-row
columns).  ``DS:215A`` (low nibble) is the X SUB-TILE sample counter the X handlers maintain (+X
increments, -X decrements; a wrap shifts ``dx`` one column) and the Y handlers read (a nonzero value
means the probe straddles two columns, so the second column is checked too).  ``[bp+4] & 0xF`` is
the Y sub-tile position, checked symmetrically.  Terrain rule: tile class 0 = walkable, else the
step is REFUSED (``blocked``); after a step the ``contact_at`` scan may UNDO it and set ``blocked``
(the original pushes the step, runs ``BDD0``, and reverts on carry).

Deliberately caller-owned: the ``tile_class_at(tile_offset) -> int`` read (compose from
``systems/tilemap.lookup_tile_class_505b`` over the level plane) and the ``contact_at() -> bool``
scan (the ``BDD0`` walk over the effect pool -- its pure predicate is a separate leaf; the driven
oracle exercises the no-contact path against the real BDD0 on a cleared pool).  Diagonals COMPOSE
the axis handlers exactly like the original (``call axis1`` then fall into axis2): a refused first
axis still attempts the second, with ``blocked`` accumulating.
"""
from __future__ import annotations

import dataclasses

from overkill.recovered.domain.contact_step import ContactStepState
from overkill.recovered.islands import recovered_island

TILE_COLUMN_STRIDE = 0x0D    # one tile column in the 5073 offset space
SUBTILE_MASK = 0x0F


def _blocked(state: ContactStepState) -> ContactStepState:
    return dataclasses.replace(state, blocked=True)


def _step_pos_x(state: ContactStepState, tile_class_at, contact_at) -> ContactStepState:
    """``1010:B03C`` -- step +X (direction key 4)."""
    probe = state.tile_offset - TILE_COLUMN_STRIDE          # the leading (right) column
    if tile_class_at(probe) != 0:
        return _blocked(state)
    if state.y_word & SUBTILE_MASK:                          # straddling two rows -> check both
        if tile_class_at(probe + 1) != 0:
            return _blocked(state)
    stepped = dataclasses.replace(state, x_word=(state.x_word + 1) & 0xFFFF,
                                  mirror_dx_x=state.mirror_dx_x + 1)
    if contact_at():
        return _blocked(dataclasses.replace(state))          # undo the step, flag contact
    sample = (state.sample_215a + 1) & SUBTILE_MASK
    off = stepped.tile_offset - (TILE_COLUMN_STRIDE if sample == 0 else 0)
    return dataclasses.replace(stepped, sample_215a=sample, tile_offset=off)


def _step_neg_x(state: ContactStepState, tile_class_at, contact_at) -> ContactStepState:
    """``1010:B07D`` -- step -X (direction key 0)."""
    if (state.sample_215a & SUBTILE_MASK) == 0:              # at a column boundary -> check terrain
        probe = state.tile_offset + TILE_COLUMN_STRIDE       # the leading (left) column
        if tile_class_at(probe) != 0:
            return _blocked(state)
        if state.y_word & SUBTILE_MASK:
            if tile_class_at(probe + 1) != 0:
                return _blocked(state)
    stepped = dataclasses.replace(state, x_word=(state.x_word - 1) & 0xFFFF,
                                  mirror_dx_x=state.mirror_dx_x - 1)
    if contact_at():
        return _blocked(dataclasses.replace(state))
    sample = (state.sample_215a - 1) & SUBTILE_MASK
    off = stepped.tile_offset + (TILE_COLUMN_STRIDE if sample == SUBTILE_MASK else 0)
    return dataclasses.replace(stepped, sample_215a=sample, tile_offset=off)


def _step_pos_y(state: ContactStepState, tile_class_at, contact_at) -> ContactStepState:
    """``1010:B0CC`` -- step +Y (direction key 2)."""
    probe = state.tile_offset + 1                            # the leading (below) row
    if tile_class_at(probe) != 0:
        return _blocked(state)
    if state.sample_215a & SUBTILE_MASK:                     # straddling two columns -> check both
        if tile_class_at(probe - TILE_COLUMN_STRIDE) != 0:
            return _blocked(state)
    stepped = dataclasses.replace(state, y_word=(state.y_word + 1) & 0xFFFF,
                                  mirror_dx_y=state.mirror_dx_y + 1)
    if contact_at():
        return _blocked(dataclasses.replace(state))
    if (stepped.y_word & SUBTILE_MASK) == 0:                 # crossed a row boundary
        stepped = dataclasses.replace(stepped, tile_offset=stepped.tile_offset + 1)
    return stepped


def _step_neg_y(state: ContactStepState, tile_class_at, contact_at) -> ContactStepState:
    """``1010:B10F`` -- step -Y (direction key 6)."""
    if (state.y_word & SUBTILE_MASK) == 0:                   # at a row boundary -> check terrain
        probe = state.tile_offset - 1                        # the leading (above) row
        if tile_class_at(probe) != 0:
            return _blocked(state)
        if state.sample_215a & SUBTILE_MASK:
            if tile_class_at(probe - TILE_COLUMN_STRIDE) != 0:
                return _blocked(state)
    stepped = dataclasses.replace(state, y_word=(state.y_word - 1) & 0xFFFF,
                                  mirror_dx_y=state.mirror_dx_y - 1)
    if contact_at():
        return _blocked(dataclasses.replace(state))
    if (stepped.y_word & SUBTILE_MASK) == SUBTILE_MASK:      # crossed a row boundary downward
        stepped = dataclasses.replace(stepped, tile_offset=stepped.tile_offset - 1)
    return stepped


#: the CS:B022 dispatch, keys 0..7 (= the record's +0x06 direction field).  Diagonals compose the
#: axis handlers in the ORIGINAL order (call axis1, fall into axis2); a refused/contacted first axis
#: still attempts the second, with ``blocked`` accumulating -- exactly the original control flow
#: (the B032 blocked exit RETURNS from the inner call into the second handler).
_AXIS = {0: _step_neg_x, 2: _step_pos_y, 4: _step_pos_x, 6: _step_neg_y}
_DIAGONAL = {1: (0, 2), 3: (2, 4), 5: (4, 6), 7: (6, 0)}


@recovered_island(
    asm=("1010:B022", "1010:B03C", "1010:B07D", "1010:B0C9", "1010:B0CC", "1010:B039",
         "1010:B10C", "1010:B10F", "1010:B07A"),
    contract="the AFD8 per-direction 1px contact step (B022 dispatch on +0x06): leading-edge tile "
             "checks (class 0 walkable), sub-tile straddle checks, the 215A X sample counter with "
             "column wraps, step + contact-undo, blocked accumulation across diagonal composition",
    status="VERIFIED",
    merge_target="EnemyWaveSystem",
    unknowns="the BDD0 contact predicate is caller-owned (the oracle exercises no-contact on a "
             "cleared pool; the undo branch is unit-tested); the off-map 5073->FFFF early-out is "
             "top-shape (B00D), not this fn",
)
def contact_step_b022(direction: int, state: ContactStepState, tile_class_at,
                      contact_at) -> ContactStepState:
    """Apply one ``B022`` direction-step handler (keys 0..7) to ``state`` (pure)."""
    d = direction & 0x7
    if d in _AXIS:
        return _AXIS[d](state, tile_class_at, contact_at)
    first, second = _DIAGONAL[d]
    mid = _AXIS[first](state, tile_class_at, contact_at)
    return _AXIS[second](mid, tile_class_at, contact_at)
