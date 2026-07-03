"""The fail-loud recovery-gap marker for the native (VM-less) runtime.

The native skeleton (``overkill.native_app``) encodes the game's recovered high-level structure;
wherever a stage/transition/behaviour is NOT recovered yet, the skeleton must either (a) raise
:class:`RecoveryGap` when the gap is actually reached, or (b) declare it as an :class:`UnmonitoredGap`
entry in its stage map when the native state cannot even detect the trigger.  Both are explicit and
greppable -- the project invariant is *fail loud, never fake*: no silent fallbacks, no guessed
behaviour, no compatibility shims that make the game look like it works while hiding missing logic.
"""
from __future__ import annotations

from dataclasses import dataclass


class RecoveryGap(RuntimeError):
    """Raised when the native runtime reaches behaviour that is not recovered yet.

    ``what`` names the gap (e.g. the original ASM routine), ``detail`` says what state triggered it.
    Callers must NOT catch-and-continue past this to fake progress; the only legitimate handlers stop
    the affected flow visibly (e.g. ``play_native`` holds the last frame and reports the gap).
    """

    def __init__(self, what: str, detail: str = "") -> None:
        super().__init__(f"RECOVERY GAP: {what}" + (f" -- {detail}" if detail else ""))
        self.what = what
        self.detail = detail


@dataclass(frozen=True)
class UnmonitoredGap:
    """A declared gap the native runtime cannot even watch for yet.

    Used in skeleton stage maps for original behaviour whose *trigger state* is not represented in the
    native model (e.g. the gameplay loop's A342/A344/A346 transition flags -- ``NativeGameState`` does
    not carry them, so the native loop cannot notice a level-complete).  Declaring it keeps the boundary
    visible and machine-readable instead of silently absent.
    """

    what: str        # the original routine / flag (e.g. "1010:97B2 A344 -> jmp 9734")
    why_unmonitored: str  # which native state is missing
