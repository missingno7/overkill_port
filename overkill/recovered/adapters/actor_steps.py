"""A SPIKE: the actor-model step-list interpreter, proven byte-exact on the bounce cluster.

`docs/overkill/actor_model.md` argues each recovered behaviour is `guards -> primitive(operands) ->
tail` over a CLOSED verb set (evidenced across ~75 handlers), and that a behaviour can be re-represented
as a DATA step-list run by one shared interpreter -- legal ONLY because a shadow gate proves the
step-list reproduces the native handler byte-for-byte.

This module is the first concrete proof of that claim on the cleanest cluster (the 88CF triple-AFD8
bouncers): behaviours 0x33 / 0x3D / 0x3C, which the hand-written handlers already show are pure
re-parameterisations of one another.  Each `Step` is a thin verb over an existing recovered worker
(no new semantics); `run_actor_steps` composes them; `tests/test_actor_steps.py` gates each step-list
against its native `_step_*` handler over constructed record states (identical DGROUP effect).

It is a SPIKE, deliberately scoped to one cluster -- per the doc, the production interpreter waits
until the whole zoo carries its decomposition tag.  It exists to validate the verb set + the
equivalence-gate method, not to replace the walk.
"""
from __future__ import annotations

from dataclasses import dataclass

from overkill.recovered.adapters.behavior_walk import DS, _bdd0_contact_at
from overkill.recovered.domain.tilemap import LevelTileContext
from overkill.recovered.systems.contact_step import contact_probe_afd8

ANIM_TABLE_96D2 = 0x96D2      # sprite = [96D2 + [233C]*2] + add (the 96D2 anim ring)
ANIM_CLOCK_233C = 0x233C


class Step:
    """One actor verb.  ``run`` mutates the record in ``mem``; return True to STOP the step-list
    (a failed guard), else None/False to continue -- the 88CF handlers' early ``return`` on a guard."""

    def run(self, mem, rec: int, tiles: LevelTileContext) -> "bool | None":
        raise NotImplementedError


@dataclass(frozen=True)
class SetSprite(Step):
    """``[rec+8] = value`` -- a fixed sprite id."""
    value: int

    def run(self, mem, rec, tiles):
        mem.ww(DS, (rec + 0x08) & 0xFFFF, self.value & 0xFFFF)


@dataclass(frozen=True)
class SetSpriteAnim(Step):
    """``[rec+8] = [table + [233C]*2] + add`` -- the shared 233C anim-ring sprite (0x3D's 8AC7)."""
    table: int
    add: int

    def run(self, mem, rec, tiles):
        anim = mem.rw(DS, (self.table + (mem.rw(DS, ANIM_CLOCK_233C) & 0xFFFF) * 2) & 0xFFFF)
        mem.ww(DS, (rec + 0x08) & 0xFFFF, (anim + self.add) & 0xFFFF)


@dataclass(frozen=True)
class GuardXEq(Step):
    """Continue ONLY while ``[rec+2] == value``; otherwise stop (0x3C's ``x != 0xB0 -> return``)."""
    value: int

    def run(self, mem, rec, tiles):
        return mem.rw(DS, (rec + 0x02) & 0xFFFF) != (self.value & 0xFFFF)


@dataclass(frozen=True)
class SoundGated(Step):
    """``if [98C0]: [BEFF] = id`` -- the 98C0-gated sound-event write."""
    sound_id: int

    def run(self, mem, rec, tiles):
        if mem.rb(DS, 0x98C0):
            mem.wb(DS, 0xBEFF, self.sound_id & 0xFF)


@dataclass(frozen=True)
class MorphBehavior(Step):
    """``[rec+0x18] += delta`` -- advance the L2 behaviour id (0x3C morphs 0x3C -> 0x3D)."""
    delta: int

    def run(self, mem, rec, tiles):
        mem.ww(DS, (rec + 0x18) & 0xFFFF, (mem.rw(DS, (rec + 0x18) & 0xFFFF) + self.delta) & 0xFFFF)


@dataclass(frozen=True)
class SetDir(Step):
    """``[rec+6] = value`` -- set the direction/phase field."""
    value: int

    def run(self, mem, rec, tiles):
        mem.ww(DS, (rec + 0x06) & 0xFFFF, self.value & 0xFFFF)


class TripleBounce(Step):
    """The 88CF body 0x33/0x3D/0x3C all tail into: THREE chained AFD8 contact-steps in the record's
    direction; the first blocked step stops the chain and flips the vertical phase (``dir ^= 2``)."""

    def run(self, mem, rec, tiles):
        for _ in range(3):
            result = contact_probe_afd8(mem.rw(DS, rec + 0x02), mem.rw(DS, rec + 0x04),
                                        mem.rw(DS, rec + 0x06), mem.rw(DS, 0xA278),
                                        tiles, _bdd0_contact_at(mem, rec))
            mem.ww(DS, rec + 0x02, result.x_word)
            mem.ww(DS, rec + 0x04, result.y_word)
            mem.ww(DS, 0xA430, 1 if result.blocked else 0)
            mem.ww(DS, 0xA432, result.snap_x)
            mem.ww(DS, 0xA434, result.snap_y)
            mem.ww(DS, 0xA436, result.mirror_y)
            mem.ww(DS, 0xA438, result.mirror_x)
            mem.ww(DS, 0x215A, result.sample_215a)
            if result.blocked:
                mem.ww(DS, rec + 0x06, mem.rw(DS, rec + 0x06) ^ 0x0002)
                return


def run_actor_steps(steps, mem, rec: int, tiles: LevelTileContext) -> None:
    """Run a behaviour's step-list over the actor record -- stop early on a failed guard."""
    for step in steps:
        if step.run(mem, rec, tiles):
            return


#: The bounce cluster as DATA step-lists over the verbs above -- each equals its native handler
#: (tests/test_actor_steps.py gates it).  0x3D = anim + the body; 0x3C = wait, sound, morph, then 0x3D.
BOUNCE_BEHAVIORS = {
    0x33: (TripleBounce(),),
    0x3D: (SetSpriteAnim(ANIM_TABLE_96D2, 0xC5), TripleBounce()),
    0x3C: (SetSprite(0xC5), GuardXEq(0xB0), SoundGated(0x1D), MorphBehavior(1), SetDir(7),
           SetSpriteAnim(ANIM_TABLE_96D2, 0xC5), TripleBounce()),
}
