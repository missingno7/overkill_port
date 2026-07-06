"""The L1 SCENERY behaviors (the ``4A65`` level-object script's spawns), as pure per-frame decisions.

Scope: [`docs/overkill/campaigns/scene.md`](../../../docs/overkill/campaigns/scene.md) -- 0x1A (a
sprite ramp over the shared BB03 vertical bounce) and 0x19 (a sprite ramp that also emits a C237
child at a fixed direction), plus the BB03 bounce tail itself (shared by both, and structurally
identical to the AED8/B24D/AF60 "step then react" shape, just over the already-recovered AFD8
contact-step primitive instead of the 8-way direction table).
"""
from __future__ import annotations

from dataclasses import dataclass

from overkill.recovered.islands import recovered_island

# 1010:BB03 shared vertical-bounce tail: direction is a 2-phase flag (6 = moving toward Y=0, ANY
# other value treated as the "moving toward Y=0xC0" phase -- the ASM force-normalises to 2).  Each
# frame either flips immediately (already at the boundary) or attempts one AFD8 contact-step and
# flips on block.  AFD8's blocked verdict is DS:A430 != 0 (terrain refusal / contact hit / off-map).
BB03_DOWN_DIRECTION = 0x0006     # toward Y decreasing (Y=0)
BB03_UP_DIRECTION = 0x0002       # toward Y increasing (Y=0xC0)
BB03_Y_MIN = 0x0000
BB03_Y_MAX = 0x00C0


@recovered_island(
    asm=("1010:BB03..BB0D (the immediate Y-boundary flip)",),
    contract="1010:BB03's Y-boundary pre-check: if the CURRENT bounce direction has already reached "
             "its endpoint (dir==6 and Y==0, or dir!=6 and Y==0xC0), flip immediately with no AFD8 "
             "call. Otherwise the caller must attempt one AFD8 contact-step in `direction` and use "
             ":func:`bb03_bounce_after_step` on the result.",
    status="OBSERVED",
    merge_target="SceneSystem",
    unknowns="none -- this is a small, fully-decoded boundary check",
)
def bb03_bounce_boundary(direction: int, y_word: int) -> "int | None":
    """The immediate flip when the bounce is already sitting at its endpoint, else ``None``."""
    d = direction & 0xFFFF
    y = y_word & 0xFFFF
    if d == BB03_DOWN_DIRECTION and y == BB03_Y_MIN:
        return BB03_UP_DIRECTION
    if d != BB03_DOWN_DIRECTION and y == BB03_Y_MAX:
        return BB03_DOWN_DIRECTION
    return None


@recovered_island(
    asm=("1010:BB0E..BB3D",),
    contract="1010:BB03's post-step flip: after the caller's AFD8 contact-step attempt in the "
             "CURRENT bounce direction, flip to the opposite phase iff the step was blocked "
             "(DS:A430 != 0); otherwise the direction (and thus the bounce phase) is unchanged.",
    status="OBSERVED",
    merge_target="SceneSystem",
    unknowns="none",
)
def bb03_bounce_after_step(direction: int, blocked: bool) -> "int | None":
    """The flipped direction if the AFD8 step was blocked, else ``None`` (keep the current phase)."""
    if not blocked:
        return None
    d = direction & 0xFFFF
    return BB03_UP_DIRECTION if d == BB03_DOWN_DIRECTION else BB03_DOWN_DIRECTION


# 1010:BAD4 (behavior 0x1A): a pure sprite ramp -- sprite = table[DS:2338 >> 1] + 0x24 -- then falls
# into the shared BB03 bounce (no gate, every frame).
SCENERY_1A_SPRITE_BIAS = 0x0024


@recovered_island(
    asm=("1010:BAD4..BADF",),
    contract="behavior 0x1A (1010:BAD4): sprite = (DS:2338 >> 1) + 0x24, unconditionally, then falls "
             "into the shared BB03 bounce (1010:BB03) every frame -- no gate of its own.",
    status="OBSERVED",
    merge_target="SceneSystem",
    unknowns="none",
)
def step_scenery_sprite_ramp_1a(clock_2338: int) -> int:
    """The pure sprite for behavior 0x1A (``1010:BAD4``): ``(DS:2338 >> 1) + 0x24``."""
    return (((clock_2338 & 0xFFFF) >> 1) + SCENERY_1A_SPRITE_BIAS) & 0xFFFF


# 1010:BAF0 (behavior 0x19): sprite ramp (a DIFFERENT clock/bias than 0x1A) + a periodic C237 emit
# (via the BAE1 helper, which forces direction=4 for the spawn then restores it) -- then the SAME
# shared BB03 bounce.
SCENERY_19_SPRITE_BIAS = 0x0036
SCENERY_19_EMIT_GATE_232E = 0x003F
SCENERY_19_EMIT_DIRECTION = 0x0004   # BAE1: the spawned child's direction (forced, then restored)


@recovered_island(
    asm=("1010:BAF0..BAFE",),
    contract="behavior 0x19 (1010:BAF0): sprite = DS:233A + 0x36, unconditionally; when "
             "DS:232E==0x3F, emit a C237 child (via 1010:BAE1, which stamps direction=4 for the "
             "spawn regardless of this record's own direction, then restores it) -- then falls into "
             "the shared BB03 bounce every frame.",
    status="OBSERVED",
    merge_target="SceneSystem",
    unknowns="the BAE1 emit's C237 sound/stamp reuses the already-recovered spawn worker verbatim; "
             "no new spawn semantics here.",
)
def step_scenery_emitter_sprite_19(clock_233a: int) -> int:
    """The pure sprite for behavior 0x19 (``1010:BAF0``): ``DS:233A + 0x36``."""
    return (clock_233a + SCENERY_19_SPRITE_BIAS) & 0xFFFF


def scenery_19_should_emit(gate_232e: int) -> bool:
    """Whether behavior 0x19 emits a C237 child this frame (``DS:232E == 0x3F``)."""
    return (gate_232e & 0xFFFF) == SCENERY_19_EMIT_GATE_232E


# 1010:B2A6 (behavior 0x89): the SAME shape as 0x19 -- a sprite ramp + the BAE1 C237 emit (forcing
# direction=4) + the shared BB03 bounce -- but a DIFFERENT clock/bias (DS:233C + 0x1C) and emit gate
# (DS:232C == 0x1F).  Reuses 0x19's BAE1 emit and the BB03 bounce verbatim; no terrain-follow.
SCENERY_89_SPRITE_BIAS = 0x001C
SCENERY_89_EMIT_GATE_232C = 0x001F


@recovered_island(
    asm=("1010:B2A6..B2B9",),
    contract="behavior 0x89 (1010:B2A6): sprite = DS:233C + 0x1C, unconditionally; when DS:232C==0x1F, "
             "emit a C237 child via 1010:BAE1 (the same dir=4 emit 0x19 uses) -- then falls into the "
             "shared BB03 bounce (jmp BB03) every frame.",
    status="OBSERVED",
    merge_target="SceneSystem",
    unknowns="none -- reuses the recovered BAE1 emit + BB03 bounce; only the clock/bias/gate differ.",
)
def step_scenery_emitter_sprite_89(clock_233c: int) -> int:
    """The pure sprite for behavior 0x89 (``1010:B2A6``): ``DS:233C + 0x1C``."""
    return (clock_233c + SCENERY_89_SPRITE_BIAS) & 0xFFFF


def scenery_89_should_emit(gate_232c: int) -> bool:
    """Whether behavior 0x89 emits a C237 child this frame (``DS:232C == 0x1F``)."""
    return (gate_232c & 0xFFFF) == SCENERY_89_EMIT_GATE_232C
