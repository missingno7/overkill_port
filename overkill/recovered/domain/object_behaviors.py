"""Pure object-behavior domain records recovered from dispatcher hooks."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ObjectDeactivateDispatchDecision:
    """Pure classification for the recovered 1010:C054 deactivate dispatcher.

    ``kind`` is intentionally narrow and address-rooted.  It names the observed
    dispatcher families without claiming a complete enemy/boss archetype model.
    ``ax_script`` is populated only for the family where C054 selects an AX
    script address for the caller's follow-up tail.
    """

    kind: str
    ax_script: int | None = None


@dataclass(frozen=True, slots=True)
class Ab10Update:
    """Pure result of the 1010:AB10 per-frame object update (logic_id=6 path).

    The object deactivates when the level frame phase (DS:2384) or the global
    disable counter (DS:A47C) has advanced to ``0003h``; otherwise it samples its
    animation frame and view-relative position. ``deactivate`` true means the slot
    is cleared (active=0) and the other fields are unused. The adapter owns the DOS
    reads + the original CMP/ADD flag replay; this owns the gameplay decision."""

    deactivate: bool
    sprite: int = 0
    x: int = 0
    y: int = 0


@dataclass(frozen=True, slots=True)
class B73ETargetReachedResolution:
    """Pure 4-way dispatch for B73E once an object is already at its target.

    Recovered from the B7BD/B808 tail.  After the object reaches its waypoint and
    the optional B800 formation spawn, B73E chooses how to continue from three
    globals.  ``kind`` is one of:

    - ``"reset_target_check_2324"``: low ``DS:A47E`` -> reset the target row with
      the B7C7 ``DS:2324`` guard.
    - ``"reset_target_direct"``: low ``DS:2340`` counter -> reset the target row
      directly through B7CE.
    - ``"postmove"``: ``DS:232E`` is not the ``003Fh`` sentinel -> join the shared
      BC4B post-move tail.
    - ``"waypoint_loop"``: otherwise -> enter the B82D waypoint-table loop.

    Names the branch decision without owning the reset side effects, the BC4B
    tail, or the waypoint loop body.
    """

    kind: str

@dataclass(frozen=True, slots=True)
class ObjectBoundsTileDecision:
    """Pure classification for the recovered 1010:AD60 bounds/tile tail.

    AD60 first tests the moved object against the play-field bounds, then decides
    whether the object is eligible for the under-object tile probe.  ``kind`` is
    one of:

    - ``"deactivate"``: the object left the play-field box and AD60 routes it to
      the BD17 deactivate tail.
    - ``"skip"``: the object stayed in bounds but is not a tile-probing family
      (wrong draw layer, non-probing logic id, or the BDAC probe-suppress flag),
      so AD60 just returns.
    - ``"tile_probe"``: an in-bounds probing family with BDAC clear, so AD60 runs
      the 5073/505B tile probe tail.

    This names the AD60 branch decision without owning the deactivate side
    effects, the tile-probe sampling, or any DOS memory.
    """

    kind: str

@dataclass(frozen=True, slots=True)
class BossGroupSlotTransition:
    """Pure state update performed by the recovered C194 boss-part helper.

    C194 stores the previous logic id before switching a sibling boss part into
    the shared death/transition state.  This record names those final field
    values without knowing DOS memory, stack scratch, or debug globals.
    """

    previous_logic_id: int
    logic_id: int
    transition_latch: int
    sprite_or_state: int

