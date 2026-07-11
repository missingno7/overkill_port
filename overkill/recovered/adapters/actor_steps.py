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

from overkill.recovered.adapters.behavior_walk import (
    DS,
    _b729_seek,
    _bdd0_contact_at,
    _spawn_enemy_shot_7476,
)
from overkill.recovered.domain.tilemap import LevelTileContext
from overkill.recovered.systems.contact_step import contact_probe_afd8

ANIM_TABLE_96D2 = 0x96D2      # sprite = [96D2 + [233C]*2] + add (the 96D2 anim ring)
ANIM_CLOCK_233C = 0x233C


class Step:
    """One actor verb.  ``run`` mutates the record in ``mem``; return True to STOP the step-list
    (a failed guard), else None/False to continue -- the 88CF handlers' early ``return`` on a guard."""

    def run(self, mem, rec: int, tiles: LevelTileContext, ctx: dict) -> "bool | None":
        raise NotImplementedError


@dataclass(frozen=True)
class SetSprite(Step):
    """``[rec+8] = value`` -- a fixed sprite id."""
    value: int

    def run(self, mem, rec, tiles, ctx):
        mem.ww(DS, (rec + 0x08) & 0xFFFF, self.value & 0xFFFF)


@dataclass(frozen=True)
class SetSpriteAnim(Step):
    """``[rec+8] = [table + [233C]*2] + add`` -- the shared 233C anim-ring sprite (0x3D's 8AC7)."""
    table: int
    add: int

    def run(self, mem, rec, tiles, ctx):
        anim = mem.rw(DS, (self.table + (mem.rw(DS, ANIM_CLOCK_233C) & 0xFFFF) * 2) & 0xFFFF)
        mem.ww(DS, (rec + 0x08) & 0xFFFF, (anim + self.add) & 0xFFFF)


@dataclass(frozen=True)
class GuardXEq(Step):
    """Continue ONLY while ``[rec+2] == value``; otherwise stop (0x3C's ``x != 0xB0 -> return``)."""
    value: int

    def run(self, mem, rec, tiles, ctx):
        return mem.rw(DS, (rec + 0x02) & 0xFFFF) != (self.value & 0xFFFF)


@dataclass(frozen=True)
class SoundGated(Step):
    """``if [98C0]: [BEFF] = id`` -- the 98C0-gated sound-event write."""
    sound_id: int

    def run(self, mem, rec, tiles, ctx):
        if mem.rb(DS, 0x98C0):
            mem.wb(DS, 0xBEFF, self.sound_id & 0xFF)


@dataclass(frozen=True)
class MorphBehavior(Step):
    """``[rec+0x18] += delta`` -- advance the L2 behaviour id (0x3C morphs 0x3C -> 0x3D)."""
    delta: int

    def run(self, mem, rec, tiles, ctx):
        mem.ww(DS, (rec + 0x18) & 0xFFFF, (mem.rw(DS, (rec + 0x18) & 0xFFFF) + self.delta) & 0xFFFF)


@dataclass(frozen=True)
class SetDir(Step):
    """``[rec+6] = value`` -- set the direction/phase field."""
    value: int

    def run(self, mem, rec, tiles, ctx):
        mem.ww(DS, (rec + 0x06) & 0xFFFF, self.value & 0xFFFF)


class TripleBounce(Step):
    """The 88CF body 0x33/0x3D/0x3C all tail into: THREE chained AFD8 contact-steps in the record's
    direction; the first blocked step stops the chain and flips the vertical phase (``dir ^= 2``)."""

    def run(self, mem, rec, tiles, ctx):
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


# --- control + field verbs: the shared primitives the waypoint/formation CONTROL family needs -------
# (docs/overkill/actor_model.md §7.6 -- the seek->arrival->substate shape the report flagged as the
#  one control shape the bounce-cluster vocab didn't name; these are reused across that whole family.)

@dataclass(frozen=True)
class SetSeekMode2308(Step):
    """``[2308] = planet0 if [2356]==0 else other`` -- the seek-mode global the B729 seek reads."""
    planet0: int
    other: int

    def run(self, mem, rec, tiles, ctx):
        mem.ww(DS, 0x2308, self.planet0 if mem.rw(DS, 0x2356) == 0 else self.other)


class SeekB729(Step):
    """``_b729_seek`` toward the record's own +0x32/+0x34 target; record ``arrived`` (=blocked) in ctx."""

    def run(self, mem, rec, tiles, ctx):
        ctx["arrived"] = _b729_seek(mem, rec)


@dataclass(frozen=True)
class SpriteFromDir(Step):
    """``[rec+8] = [rec+6] + add`` -- sprite from the direction field."""
    add: int

    def run(self, mem, rec, tiles, ctx):
        mem.ww(DS, (rec + 0x08) & 0xFFFF, (mem.rw(DS, (rec + 0x06) & 0xFFFF) + self.add) & 0xFFFF)


@dataclass(frozen=True)
class WhenArrived(Step):
    """Run the arrival sub-list ONLY if the last Seek arrived (blocked) -- the shared on-arrival gate."""
    steps: tuple

    def run(self, mem, rec, tiles, ctx):
        if ctx.get("arrived"):
            run_actor_steps(self.steps, mem, rec, tiles, ctx)


@dataclass(frozen=True)
class IfFieldZero(Step):
    """Branch on ``[rec+off] == 0`` into one of two sub-lists (a nested guard stops only that branch)."""
    off: int
    then: tuple
    otherwise: tuple = ()

    def run(self, mem, rec, tiles, ctx):
        branch = self.then if mem.rw(DS, (rec + self.off) & 0xFFFF) == 0 else self.otherwise
        run_actor_steps(branch, mem, rec, tiles, ctx)


@dataclass(frozen=True)
class GuardGlobalEq(Step):
    """Continue only while ``[addr] == value`` (a global gate, e.g. the A7A0 wave clock)."""
    addr: int
    value: int

    def run(self, mem, rec, tiles, ctx):
        return mem.rw(DS, self.addr) != self.value


@dataclass(frozen=True)
class GuardFieldNe(Step):
    """Continue only while ``[rec+off] != value``."""
    off: int
    value: int

    def run(self, mem, rec, tiles, ctx):
        return mem.rw(DS, (rec + self.off) & 0xFFFF) == self.value


@dataclass(frozen=True)
class SetField(Step):
    """``[rec+off] = value``."""
    off: int
    value: int

    def run(self, mem, rec, tiles, ctx):
        mem.ww(DS, (rec + self.off) & 0xFFFF, self.value & 0xFFFF)


@dataclass(frozen=True)
class MorphTo(Step):
    """``[rec+0x18] = value`` -- morph to a fixed behaviour id."""
    value: int

    def run(self, mem, rec, tiles, ctx):
        mem.ww(DS, (rec + 0x18) & 0xFFFF, self.value & 0xFFFF)


@dataclass(frozen=True)
class DecFieldThen(Step):
    """``[rec+off] -= 1``; if it REACHES 0, run the ``when_zero`` sub-list (the +0x1C countdown)."""
    off: int
    when_zero: tuple

    def run(self, mem, rec, tiles, ctx):
        v = (mem.rw(DS, (rec + self.off) & 0xFFFF) - 1) & 0xFFFF
        mem.ww(DS, (rec + self.off) & 0xFFFF, v)
        if v == 0:
            run_actor_steps(self.when_zero, mem, rec, tiles, ctx)


# --- emit verbs: a PROJECTILE is another actor; "shoot" is the spawn verb, the shot TYPE its operand -
# (docs/overkill/actor_model.md §5.2 shoot -- the 7476 base bullet is behaviour 0x0B player-aimed;
#  variants re-stamp the spawned slot's behaviour/direction, e.g. the 8-shot radial -> behaviour 0x04.)

@dataclass(frozen=True)
class AddX(Step):
    """``[rec+2] += delta`` -- horizontal drift."""
    delta: int

    def run(self, mem, rec, tiles, ctx):
        mem.ww(DS, (rec + 0x02) & 0xFFFF, (mem.rw(DS, (rec + 0x02) & 0xFFFF) + self.delta) & 0xFFFF)


@dataclass(frozen=True)
class OnClockBeat(Step):
    """Run the sub-list only on the shared-clock beat ``[addr] == value`` (else fall through)."""
    addr: int
    value: int
    steps: tuple

    def run(self, mem, rec, tiles, ctx):
        if mem.rw(DS, self.addr) == self.value:
            run_actor_steps(self.steps, mem, rec, tiles, ctx)


class Shoot(Step):
    """Fire ONE base enemy bullet (``7476``): behaviour ``0x0B``, sprite ``0x31``, player-aimed -- the
    common shot template.  A no-op when the gameplay pool is full."""

    def run(self, mem, rec, tiles, ctx):
        _spawn_enemy_shot_7476(mem, rec)


@dataclass(frozen=True)
class ShootRadial(Step):
    """Fire a RADIAL burst -- ``count`` base ``7476`` bullets re-stamped to ``behavior`` with
    directions ``count-1 .. 0`` (the 0x49 spread; a full pool aborts the rest)."""
    behavior: int
    count: int

    def run(self, mem, rec, tiles, ctx):
        for cx in range(self.count, 0, -1):
            slot = _spawn_enemy_shot_7476(mem, rec)
            if slot == 0xFFFF:
                return
            mem.ww(DS, slot + 0x18, self.behavior)
            mem.ww(DS, slot + 0x06, cx - 1)


def run_actor_steps(steps, mem, rec: int, tiles: LevelTileContext, ctx: "dict | None" = None) -> None:
    """Run a behaviour's step-list over the actor record -- stop early on a failed guard.  ``ctx``
    carries cross-step state (e.g. the last Seek's ``arrived`` flag the WhenArrived verb reads)."""
    ctx = {} if ctx is None else ctx
    for step in steps:
        if step.run(mem, rec, tiles, ctx):
            return


#: The bounce cluster as DATA step-lists over the verbs above -- each equals its native handler
#: (tests/test_actor_steps.py gates it).  0x3D = anim + the body; 0x3C = wait, sound, morph, then 0x3D.
BOUNCE_BEHAVIORS = {
    0x33: (TripleBounce(),),
    0x3D: (SetSpriteAnim(ANIM_TABLE_96D2, 0xC5), TripleBounce()),
    0x3C: (SetSprite(0xC5), GuardXEq(0xB0), SoundGated(0x1D), MorphBehavior(1), SetDir(7),
           SetSpriteAnim(ANIM_TABLE_96D2, 0xC5), TripleBounce()),
}

#: A CONTROL-class behaviour as a step-list, using the seek->arrival->substate control verbs: the
#: 0x16/0x17 diver (1010:B930).  It equals _step_diver_16_17 (tests/test_actor_steps.py gates it),
#: demonstrating that the waypoint/formation CONTROL family quantizes once the control verbs exist.
_DIVER_16_17 = (
    SetSeekMode2308(2, 1),                      # [2308] = 2 on planet 0 else 1
    SeekB729(),                                 # seek own +0x32/+0x34 target; records arrived
    SpriteFromDir(0x010D),                      # sprite = dir + 0x10D (runs whether or not arrived)
    WhenArrived((                               # on arrival: the +0x1C substate
        IfFieldZero(0x1C,
                    then=(GuardGlobalEq(0xA7A0, 0x31), MorphTo(0x18)),   # +0x1C==0: A7A0==0x31 -> 0x18
                    otherwise=(DecFieldThen(0x1C, when_zero=(            # else: countdown
                        SetField(0x34, 0x20),
                        GuardFieldNe(0x18, 0x16),                        # the 0x17 variant only
                        SetField(0x34, 0x40),
                    )),)),
    )),
)
CONTROLLER_BEHAVIORS = {0x16: _DIVER_16_17, 0x17: _DIVER_16_17}

#: SHOOTERS -- a projectile is another actor, so "shoot" is the spawn verb and the shot TYPE is its
#: operand.  The 0x49 burster is the clean demonstration: sprite/drift, then on the [232A]==0xF beat an
#: 8-shot RADIAL of behaviour-0x04 bullets (vs the Shoot() verb's single behaviour-0x0B aimed bullet).
#: Gated vs _step_burster_49 (tests/test_actor_steps.py).
_BURSTER_49 = (
    SetSprite(0x1D),
    AddX(2),
    OnClockBeat(0x232A, 0x0F, (ShootRadial(behavior=0x04, count=8),)),
)
SHOOTER_BEHAVIORS = {0x49: _BURSTER_49}
