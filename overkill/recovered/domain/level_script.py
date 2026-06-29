"""Pure domain records for the recovered OVERKILL scroll-script / level-event system."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ScrollScriptStep:
    """Pure result of one 1010:D0D4 scroll-script interpreter step.

    The interpreter counts down the per-command delay DS:BE08; while it is still
    running the step just decrements it (no command fires).  When it expires the delay
    reloads (0064h), the script index DS:BE06 advances by one, and the new 6-byte entry
    at DS:BE1A[index*6] is read -- its two words publish to DS:95FA / DS:BE16 unless the
    entry's first word is the FFFFh end marker.  ``entry_updated`` is False on the
    timer-running and end-marker paths (95FA/BE16 keep their previous values).  The 859E
    status render and the per-index command dispatch (``cs:[D112 + index*2]``) are side
    effects the adapter owns; this record is the pure script-state transition.
    """

    new_delay: int
    new_index: int
    entry_updated: bool
    command_w0: int
    command_w1: int
