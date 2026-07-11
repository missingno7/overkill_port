"""Equivalence gate for the actor step-list SPIKE: each bounce-cluster step-list must reproduce its
native `_step_*` handler byte-for-byte over the same record state (the actor_model.md §8 method).

If this passes, a behaviour expressed as DATA (a step-list over the closed verb set) run by the one
shared `run_actor_steps` interpreter is provably identical to the hand-written handler -- the claim the
actor model rests on, demonstrated on the 88CF triple-AFD8 bouncers (0x33 / 0x3D / 0x3C).
"""
from __future__ import annotations

import pytest

from overkill.recovered.adapters.actor_steps import (
    BOUNCE_BEHAVIORS,
    CONTROLLER_BEHAVIORS,
    SHOOTER_BEHAVIORS,
    SPAWNER_BEHAVIORS,
    run_actor_steps,
)
from overkill.recovered.adapters.behavior_walk import (
    DS,
    _step_bounce_sprite_3d,
    _step_bouncer_33,
    _step_burster_49,
    _step_diver_16_17,
    _step_lurker_3c,
    _step_spawn_child_sprite,
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


def _seed_diver(px, py, tx, ty, sub, beh, a7a0, planet) -> MutFlatMemory:
    mem = MutFlatMemory(bytes(0x100000))
    mem.ww(DS, REC + 0x00, 1)
    mem.ww(DS, REC + 0x02, px)
    mem.ww(DS, REC + 0x04, py)
    mem.ww(DS, REC + 0x06, 3)          # direction
    mem.ww(DS, REC + 0x18, beh)        # 0x16 or 0x17
    mem.ww(DS, REC + 0x1C, sub)        # the arrival substate counter
    mem.ww(DS, REC + 0x32, ty)         # own target (B729 seeks +0x32/+0x34)
    mem.ww(DS, REC + 0x34, tx)
    mem.ww(DS, 0x2356, planet)
    mem.ww(DS, 0xA7A0, a7a0)
    return mem


# states exercising: on-target arrival (px==tx,py==ty), the +0x1C==0 A7A0 morph gate, the countdown
# reaching/not reaching 0, the 0x16 vs 0x17 variant, planet 0 vs not.
_DIVER_STATES = [
    (0x40, 0x40, 0x40, 0x40, 0, 0x16, 0x31, 0),   # arrived, +0x1C==0, A7A0==0x31 -> morph 0x18
    (0x40, 0x40, 0x40, 0x40, 0, 0x16, 0x20, 0),   # arrived, +0x1C==0, A7A0!=0x31 -> no morph
    (0x40, 0x40, 0x40, 0x40, 1, 0x16, 0x00, 0),   # arrived, +0x1C 1->0 -> +0x34=0x20 (0x16 variant)
    (0x40, 0x40, 0x40, 0x40, 1, 0x17, 0x00, 1),   # arrived, +0x1C 1->0, 0x17 variant -> +0x34=0x40
    (0x40, 0x40, 0x40, 0x40, 5, 0x17, 0x00, 1),   # arrived, +0x1C 5->4 (no zero)
    (0x20, 0x30, 0x80, 0x90, 3, 0x16, 0x00, 0),   # far from target (may not arrive) -- equivalence still
]


@pytest.mark.parametrize("beh", sorted(CONTROLLER_BEHAVIORS))
@pytest.mark.parametrize("state", _DIVER_STATES)
def test_diver_step_list_matches_native(beh, state):
    px, py, tx, ty, sub, _behstate, a7a0, planet = state
    native = _seed_diver(px, py, tx, ty, sub, beh, a7a0, planet)
    _step_diver_16_17(native, REC)

    step = _seed_diver(px, py, tx, ty, sub, beh, a7a0, planet)
    run_actor_steps(CONTROLLER_BEHAVIORS[beh], step, REC, _tiles())

    a = bytes(native.data[BASE:BASE + 0x10000])
    b = bytes(step.data[BASE:BASE + 0x10000])
    diff = [o for o in range(0x10000) if a[o] != b[o]]
    assert not diff, (f"diver {beh:#04x} state {state}: diverges at "
                      + ", ".join(f"{o:04X}(nat={a[o]:02X}/step={b[o]:02X})" for o in diff[:8]))


def _seed_shooter(x, y, beat232a, cursor95da) -> MutFlatMemory:
    mem = MutFlatMemory(bytes(0x100000))
    mem.ww(DS, REC + 0x00, 1)
    mem.ww(DS, REC + 0x02, x)
    mem.ww(DS, REC + 0x04, y)
    mem.ww(DS, REC + 0x06, 0)
    mem.ww(DS, 0x232A, beat232a)     # the [232A]==0xF radial-burst beat
    mem.ww(DS, 0x95DA, cursor95da)   # the gameplay-pool alloc cursor the 7476 shot uses
    mem.ww(DS, 0x237E, 0x60)         # player view-anchor x/y (the shot aim deltas)
    mem.ww(DS, 0x2380, 0x50)
    mem.ww(DS, 0xA8C2, 0)
    return mem


@pytest.mark.parametrize("beat", [0x0F, 0x0E])   # 0x0F fires the 8-shot radial; 0x0E does not
def test_radial_burster_step_list_matches_native(beat):
    native = _seed_shooter(0x40, 0x50, beat, 0)
    _step_burster_49(native, REC)

    step = _seed_shooter(0x40, 0x50, beat, 0)
    run_actor_steps(SHOOTER_BEHAVIORS[0x49], step, REC, _tiles())

    a = bytes(native.data[BASE:BASE + 0x10000])
    b = bytes(step.data[BASE:BASE + 0x10000])
    diff = [o for o in range(0x10000) if a[o] != b[o]]
    assert not diff, ("radial burster: diverges at "
                      + ", ".join(f"{o:04X}(nat={a[o]:02X}/step={b[o]:02X})" for o in diff[:8]))


_SPAWNER_SPRITE = {0x24: 0x1E, 0x25: 0x1A}


def _seed_spawner(beh, beat232c, bedc, a956, cursor95da) -> MutFlatMemory:
    mem = MutFlatMemory(bytes(0x100000))
    mem.ww(DS, REC + 0x00, 1)
    mem.ww(DS, REC + 0x02, 0x50)
    mem.ww(DS, REC + 0x04, 0x40)
    mem.ww(DS, REC + 0x06, 3)
    mem.ww(DS, REC + 0x18, beh)
    mem.ww(DS, 0x232C, beat232c)     # 0x1F fires the C237 child
    mem.ww(DS, 0xBEDC, bedc)         # difficulty -> the child-spawn throttle
    mem.wb(DS, 0xA956, a956)         # the BYTE throttle counter
    mem.ww(DS, 0x95DA, cursor95da)   # the gameplay-pool alloc cursor
    mem.wb(DS, 0x98C0, 1)            # sound enabled
    return mem


@pytest.mark.parametrize("beh", sorted(SPAWNER_BEHAVIORS))
@pytest.mark.parametrize("beat,bedc,a956", [
    (0x1F, 0, 0), (0x1F, 1, 0), (0x1F, 2, 0), (0x1F, 0, 3),   # fire, various throttle/difficulty
    (0x1E, 0, 0),                                             # off-beat: no spawn
])
def test_child_spawner_step_list_matches_native(beh, beat, bedc, a956):
    native = _seed_spawner(beh, beat, bedc, a956, 0)
    _step_spawn_child_sprite(native, REC, beh, _SPAWNER_SPRITE[beh])

    step = _seed_spawner(beh, beat, bedc, a956, 0)
    run_actor_steps(SPAWNER_BEHAVIORS[beh], step, REC, _tiles())

    a = bytes(native.data[BASE:BASE + 0x10000])
    b = bytes(step.data[BASE:BASE + 0x10000])
    diff = [o for o in range(0x10000) if a[o] != b[o]]
    assert not diff, (f"spawner {beh:#04x} beat={beat:#x} bedc={bedc}: diverges at "
                      + ", ".join(f"{o:04X}(nat={a[o]:02X}/step={b[o]:02X})" for o in diff[:8]))
