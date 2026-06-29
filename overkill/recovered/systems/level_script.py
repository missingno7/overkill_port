"""Pure recovered OVERKILL scroll-script / level-event interpreter logic.

No CPU, memory, DOS segment, or hook state -- the portable state transition the standalone
runtime advances each frame.  The 859E status render and the per-command dispatch
(``cs:[D112 + index*2]`` into the D14D..D2xx handlers) are side effects the adapter/runtime
owns; this owns only the script-state step recovered from the 1010:D0D4 interpreter.
"""
from __future__ import annotations

from overkill.recovered.domain.level_script import ScrollScriptStep

# 1010:D0D4 scroll-script interpreter constants.
SCROLL_SCRIPT_DELAY_RELOAD = 0x0064   # DS:BE08 reload when a command fires
SCROLL_SCRIPT_END_MARKER = 0xFFFF     # script entry word0 == FFFFh terminates the table
SCROLL_SCRIPT_ENTRY_STRIDE = 6        # bytes per DS:BE1A entry (index*6)


def scroll_script_step(delay: int, index: int, next_entry_w0: int, next_entry_w1: int) -> ScrollScriptStep:
    """Pure 1010:D0D4 scroll-script state transition.

    ``delay`` is DS:BE08 and ``index`` is DS:BE06 at the interpreter's entry; ``next_entry_w0``
    / ``next_entry_w1`` are the two words of the script entry at DS:BE1A[(index+1)*6] (the
    adapter reads them; only used when the delay expires).  Returns the post-step
    ``DS:BE08``/``DS:BE06`` and, when a fresh entry is read, the words published to
    ``DS:95FA``/``DS:BE16``.  Matches the interpreter: decrement the delay; if it is still
    non-zero, nothing else happens (the command stays the same -- the original RETs at D0DA);
    otherwise reload the delay, advance the index, and read the entry, skipping the 95FA/BE16
    publish when the entry is the FFFFh end marker.
    """
    new_delay = (delay - 1) & 0xFFFF
    if new_delay != 0:
        return ScrollScriptStep(new_delay=new_delay, new_index=index & 0xFFFF,
                                entry_updated=False, command_w0=0, command_w1=0)
    new_index = (index + 1) & 0xFFFF
    if (next_entry_w0 & 0xFFFF) == SCROLL_SCRIPT_END_MARKER:
        return ScrollScriptStep(new_delay=SCROLL_SCRIPT_DELAY_RELOAD, new_index=new_index,
                                entry_updated=False, command_w0=0, command_w1=0)
    return ScrollScriptStep(new_delay=SCROLL_SCRIPT_DELAY_RELOAD, new_index=new_index,
                            entry_updated=True, command_w0=next_entry_w0 & 0xFFFF,
                            command_w1=next_entry_w1 & 0xFFFF)
