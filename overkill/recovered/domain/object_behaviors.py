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

