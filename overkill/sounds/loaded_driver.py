"""Shared facts about OVERKILL's optional loaded sound-driver segment.

The original startup can load an optional AdLib/Roland resident driver into a
stable runtime segment.  In our captured static runtime that segment is
``2032h``.  Many coverage entries inside this segment are not independent game
logic: they are near/far entries, channel sequencer helpers, YM3812 register
writers, or delay/paging helpers belonging to the loaded driver blob.

Keeping this in one module prevents coverage, verifier metadata, and sound
wrappers from each hard-coding their own idea of what ``2032:*`` means.
"""
from __future__ import annotations

from typing import TypeAlias

Addr: TypeAlias = tuple[int, int]

# Observed stable segment for the optional AdLib/Roland driver in the captured
# OVERKILL runtime bundle.  The main game calls it through 1010:06E5/0672/0679
# when the command tail requests an optional music driver.
OPTIONAL_SOUND_DRIVER_SEGMENT = 0x2032
OPTIONAL_SOUND_DRIVER_NAME = "optional_sound_driver_2032"

# Exact helpers that are already lifted/documented.  The whole segment still
# classifies as sound because not every internal near-call target is hooked, but
# this set describes the proof-backed public frontier inside that resident blob.
OPTIONAL_SOUND_DRIVER_HOOK_ADDRS: frozenset[Addr] = frozenset(
    {
        (OPTIONAL_SOUND_DRIVER_SEGMENT, 0x0000),  # far entry called from 1010:06E5
        (OPTIONAL_SOUND_DRIVER_SEGMENT, 0x0063),  # top-level timer tick
        (OPTIONAL_SOUND_DRIVER_SEGMENT, 0x00CD),  # per-channel bytecode tick
        (OPTIONAL_SOUND_DRIVER_SEGMENT, 0x0181),  # instrument select
        (OPTIONAL_SOUND_DRIVER_SEGMENT, 0x0244),  # per-channel accumulator helper
        (OPTIONAL_SOUND_DRIVER_SEGMENT, 0x024F),  # note/frequency update
        (OPTIONAL_SOUND_DRIVER_SEGMENT, 0x02AA),  # pending-note/key-on helper
        (OPTIONAL_SOUND_DRIVER_SEGMENT, 0x02C9),  # modulation helper A
        (OPTIONAL_SOUND_DRIVER_SEGMENT, 0x02F6),  # modulation helper B
        (OPTIONAL_SOUND_DRIVER_SEGMENT, 0x0409),  # page/pause gate
        (OPTIONAL_SOUND_DRIVER_SEGMENT, 0x04E9),  # hardware detect/probe
        (OPTIONAL_SOUND_DRIVER_SEGMENT, 0x0557),  # YM3812 register write
    }
)


def is_optional_sound_driver_addr(addr: Addr) -> bool:
    """Return true for code executing inside the loaded optional sound driver."""
    cs, _ip = addr
    return (cs & 0xFFFF) == OPTIONAL_SOUND_DRIVER_SEGMENT
