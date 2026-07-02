"""Pure port of 1010:A66F's world-scroll gate + 1010:A6FE's forward-scroll tick (+ A74E/A746).

Faithful 1:1 port of the already-VM-verified hybrid hooks
``overkill.gameplay.object_movement.run_object_scroll_forward_step_a6fe`` /
``run_object_scroll_forward_row_a74e`` / ``run_object_scroll_row_wrap_forward_a746`` -- mechanical
translation, not new disassembly, since the ASM is already fully understood and hooked.

Two real side effects from the original ASM are declined (not modelled) because neither is consumed
by any currently-recovered gameplay system:

* A7EB (Tandy tile-strip build + shift) -- rendering only; already lifted separately for the
  level-LOADING scroll context in :mod:`overkill.rendering.tandy`, not (yet) reused for in-gameplay
  scrolling. :class:`~overkill.recovered.domain.tilemap.LevelTileContext` only reads DS:234E/DS:2350,
  neither of which A7EB touches, so omitting it does not affect tile-probing/collision.
* CB1C (a sound/transition notify fired when DS:A978 reaches 4) -- audio-only.

A KNOWN, DELIBERATE GAP: A6FE's own body has a SECOND DS:234E==0 check (after the decrement+mask,
not the same tick as the first) that does an extra DS:2350/A978 advance gated on DS:2354 != 0 -- this
only fires when the LAST row-pull was BACKWARD (DS:2354 is set by A7D0, the backward chain, which is
not yet ported -- see the project's scroll-recovery task list). Forward-only play never leaves
DS:2354 non-zero (A74E always resets it to 0/forward), so this is unreachable for a forward-only
session and is intentionally omitted here rather than guessed. A live-VM verify probe should catch
this if a tested demo ever reverses scroll direction.
"""
from __future__ import annotations

from overkill.recovered.domain.scroll import ScrollState, ScrollTickOutcome

# CS-relative level constants A6FE/A74E/A746 read every tick. Confirmed FIXED (not level-varying)
# via a live-VM spot-check across 3 different levels (L1/L4/L5's own cold-start snapshots all read
# identical values at CS:95BE/95C0/959E).
ROW_SOURCE_WRAP_THRESHOLD = 0x0680  # CS:95BE -- compared against DS:234C to decide the A746 wrap
ROW_SOURCE_WRAP_RESET = 0x5B00      # CS:95C0 -- the value A746 resets DS:234C to on wrap
ROW_SOURCE_DECREMENT = 0x0068       # CS:959E -- subtracted from DS:234C every tick, post-wrap-check

FORWARD_ROW_STRIDE = 0x000D  # A74E: DS:2350 += 13 per pulled tile row
SUB_ROW_PHASE_MASK = 0x000F  # A6FE: DS:234E wraps mod 16


def step_scroll_forward_a6fe(scroll: ScrollState) -> ScrollTickOutcome:
    """Pure port of 1010:A6FE + its A74E/A746 children -- one forward world-scroll tick.

    DS:234E is decremented and wrapped mod 16 every tick; when it WAS already 0 at entry, a tile
    row is "pulled" this tick (DS:2350 advances by 13, DS:A978 decrements, DS:2354 resets to
    forward) -- the real ASM's A7EB strip-copy would run here too (declined, see module docstring).
    DS:234C (rendering-only) advances/wraps every tick regardless of whether a row was pulled.
    """
    pull_row = scroll.origin_x == 0

    row_base = scroll.row_base
    rows_to_milestone = scroll.rows_to_milestone
    forward_last = scroll.forward_last
    if pull_row:
        row_base = (row_base + FORWARD_ROW_STRIDE) & 0xFFFF
        rows_to_milestone = (rows_to_milestone - 1) & 0xFFFF
        forward_last = True

    origin_x = (scroll.origin_x - 1) & SUB_ROW_PHASE_MASK

    row_source = scroll.row_source
    if row_source == ROW_SOURCE_WRAP_THRESHOLD:
        row_source = ROW_SOURCE_WRAP_RESET
    row_source = (row_source - ROW_SOURCE_DECREMENT) & 0xFFFF

    new_state = ScrollState(
        origin_x=origin_x, row_base=row_base, row_source=row_source,
        rows_to_milestone=rows_to_milestone, forward_last=forward_last,
    )
    return ScrollTickOutcome(state=new_state, pulled_row=pull_row)


# A66F milestones checked only on the tick a row is pulled (origin_x wraps to 0) -- both rare,
# once-per-level events, neither yet modelled (see step_scroll_world_progress_gate_a66f).
BOSS_MATERIALIZE_ROW_BASE = 0x0EA0  # DS:2350 == this -> A66F sets A47C=1, spawns the boss (62AA/7524)
UNKNOWN_MILESTONE_ROW_BASE = 0x0E52  # DS:2350 == this -> A66F calls C591, purpose not yet understood


def step_scroll_world_progress_gate_a66f(
    scroll: ScrollState, *, a47c: int, a47e: int, a480: int,
) -> ScrollTickOutcome | None:
    """Pure port of 1010:A66F's gate + forward-scroll dispatch (the vertical-scroll/world-progress
    gate the frame loop calls every tick before A067).

    Real ASM: if DS:A47C/A47E/A480 are not ALL zero, A66F is a same-tick no-op (returns with the
    scroll state untouched -- modelled here as ``ScrollTickOutcome(scroll, pulled_row=False)``, a
    CONFIRMED outcome, not a decline). Otherwise it runs the forward scroll tick
    (:func:`step_scroll_forward_a6fe`); ``None`` is returned only when THAT tick pulled a new row
    AND the resulting DS:2350 lands on one of two rare, once-per-level milestones neither yet
    modelled: :data:`BOSS_MATERIALIZE_ROW_BASE` (spawns the boss via 62AA/7524, a whole separate
    subsystem) or :data:`UNKNOWN_MILESTONE_ROW_BASE` (calls C591, whose purpose is not yet
    understood -- never lifted even as a hybrid hook). A caller getting ``None`` should stay
    VM-owned for that one tick, matching every other "decline" in this project.
    """
    if a47c != 0 or a47e != 0 or a480 != 0:
        return ScrollTickOutcome(state=scroll, pulled_row=False)

    outcome = step_scroll_forward_a6fe(scroll)
    if outcome.pulled_row and outcome.state.row_base in (BOSS_MATERIALIZE_ROW_BASE, UNKNOWN_MILESTONE_ROW_BASE):
        return None
    return outcome
