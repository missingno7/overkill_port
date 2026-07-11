"""Equivalence gate for the actor step-list SPIKE: each bounce-cluster step-list must reproduce its
native `_step_*` handler byte-for-byte over the same record state (the actor_model.md §8 method).

If this passes, a behaviour expressed as DATA (a step-list over the closed verb set) run by the one
shared `run_actor_steps` interpreter is provably identical to the hand-written handler -- the claim the
actor model rests on, demonstrated on the 88CF triple-AFD8 bouncers (0x33 / 0x3D / 0x3C).
"""
from __future__ import annotations

import pytest

from overkill.recovered.adapters.actor_steps import BOUNCE_BEHAVIORS, run_actor_steps
from overkill.recovered.adapters.behavior_walk import (
    DS,
    _step_bounce_sprite_3d,
    _step_bouncer_33,
    _step_lurker_3c,
)
from overkill.recovered.adapters.flat_memory import MutFlatMemory
from overkill.recovered.domain.tilemap import LevelTileContext

NATIVE = {0x33: _step_bouncer_33, 0x3D: _step_bounce_sprite_3d, 0x3C: _step_lurker_3c}
REC = 0x3000
BASE = DS * 16


def _tiles() -> LevelTileContext:
    # a flat empty plane + all-passable class table: contact_probe_afd8 runs deterministically
    return LevelTileContext(origin_x_word=0, row_base_word=0,
                            tile_plane=bytes(0x10000), class_table=tuple([0] * 256))


def _seed(x: int, y: int, direction: int, beh: int, gate98c0: int, clock233c: int) -> MutFlatMemory:
    mem = MutFlatMemory(bytes(0x100000))
    mem.ww(DS, REC + 0x00, 1)                 # active
    mem.ww(DS, REC + 0x02, x)
    mem.ww(DS, REC + 0x04, y)
    mem.ww(DS, REC + 0x06, direction)
    mem.ww(DS, REC + 0x08, 0)                 # sprite
    mem.ww(DS, REC + 0x18, beh)               # behaviour id
    mem.wb(DS, 0x98C0, gate98c0)
    mem.ww(DS, 0x233C, clock233c)             # the anim ring clock
    mem.ww(DS, 0x96D2 + clock233c * 2, 0x40)  # a non-zero anim sprite so SetSpriteAnim is exercised
    mem.ww(DS, 0xA278, 0)
    return mem


# a spread of pre-states: normal, the 0x3C x==0xB0 guard boundary (and off it), sound gate on/off,
# a couple of directions, and different anim-clock phases.
_STATES = [
    (0x40, 0x50, 0, 0, 3),
    (0xB0, 0x50, 1, 1, 5),
    (0xB1, 0x50, 1, 1, 5),
    (0xB0, 0x50, 7, 0, 2),
    (0x80, 0x30, 3, 1, 7),
    (0x20, 0x70, 5, 0, 0),
]


@pytest.mark.parametrize("beh", sorted(BOUNCE_BEHAVIORS))
@pytest.mark.parametrize("state", _STATES)
def test_step_list_matches_native_handler(beh, state):
    x, y, direction, gate, clock = state
    tiles = _tiles()

    native_mem = _seed(x, y, direction, beh, gate, clock)
    NATIVE[beh](native_mem, REC, tiles)

    step_mem = _seed(x, y, direction, beh, gate, clock)
    run_actor_steps(BOUNCE_BEHAVIORS[beh], step_mem, REC, tiles)

    a = bytes(native_mem.data[BASE:BASE + 0x10000])
    b = bytes(step_mem.data[BASE:BASE + 0x10000])
    diff = [o for o in range(0x10000) if a[o] != b[o]]
    assert not diff, (f"beh {beh:#04x} state {state}: step-list diverges at "
                      + ", ".join(f"{o:04X}(nat={a[o]:02X}/step={b[o]:02X})" for o in diff[:8]))
