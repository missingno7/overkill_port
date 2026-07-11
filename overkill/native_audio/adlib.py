"""VM-free recovery of the OVERKILL AdLib (YM3812) music driver -- the loaded module at segment 2032.

The original loads a Sound Images FM driver at ``2032:0000`` when started with ``/A`` (AdLib).  It is
real 8086 code that runs in the timer ISR: a per-tick sequencer that reads the game's sound-command
state, walks its channel/instrument tables, and writes the YM3812 registers through ports 388h/389h.
``overkill/sounds/adlib_driver.py`` already LIFTS these routines (VM-coupled hooks, verified against
the interpreter); this module transcribes them to operate on EXPLICIT state so play_native can produce
the OPL register stream with no VM (the project's VM-less principle), verified against the AUDIO ORACLE
``scripts/render_demo_music.py`` (the VM's own 388h/389h writes through ``pynuked_opl3``).

STATE MODEL.  The driver's private memory IS segment 2032 (its data + tables), so :class:`AdlibDriver`
holds it as a mutable image seeded from an AdLib-booted snapshot (the driver is NOT in the PC-speaker
``boot_1010_entry`` image -- use an AdLib demo's snapshot, e.g. ``demo_play_tandy_20260711_120636``,
whose ``2032:0557`` matches ``SIG_ADLIB_WRITE_2032_0557``).  A tick reads the game DGROUP (the sound
queue the D50E engine fills) and appends the frame's YM3812 ``(reg, val)`` writes to :attr:`writes`,
which the host feeds to ``pynuked_opl3``.

RECOVERY STATUS: leaf ``2032:0557`` (the register write) is transcribed + unit-tested below.  The tick
``2032:0063`` and its callees (channel tick 00CD, set-instrument 0181, note/frequency 024F, channel
mod A/B 02C9/02F6, helpers 0244/02AA, page gate 0409) are the remaining slices -- see
docs/overkill/campaigns/audio.md for the ordered plan and the oracle gate.
"""
from __future__ import annotations

OPL_BASE_PORT_CELL = 0x000E   # 2032:000E holds the YM3812 base port (0x388)
DRIVER_TICK = 0x0063          # 2032:0063
DRIVER_WRITE = 0x0557         # 2032:0557

#: 2032:0063 tick spine geometry (from the AdLib-snapshot disasm).
REENTRY_GUARD = 0x0062        # [0062]: !=0 -> a tick is already running, skip
TICK_DIVIDER = 0x000D         # [000D]: decremented each tick, reloaded from [000C] at 0
TICK_DIVIDER_RELOAD = 0x000C
CHANNEL_COUNT = 9             # nine 00CD channel ticks per tick
CHANNEL_STATE_BASE = 0x05A9   # first channel state; stride 0x20
CHANNEL_STATE_STRIDE = 0x20


class AdlibDriver:
    """The AdLib driver's segment-2032 state + the per-tick YM3812 register stream it emits."""

    def __init__(self, seg2032_image: "bytes | bytearray") -> None:
        self.ram = bytearray(seg2032_image)
        self.opl_base = self.ram[OPL_BASE_PORT_CELL] | (self.ram[OPL_BASE_PORT_CELL + 1] << 8)
        self.writes: "list[tuple[int, int]]" = []

    def write_opl_2032_0557(self, reg: int, val: int) -> None:
        """``2032:0557`` -- emit one YM3812 register/value pair (``AL`` = reg -> 388h, ``AH`` = val ->
        389h).  The two ``0579`` PIT/speaker delays it interleaves are host timing with no game-visible
        state, so VM-free this is just the register write recorded onto :attr:`writes`."""
        self.writes.append((reg & 0xFF, val & 0xFF))

    def tick_2032_0063(self) -> None:
        """``2032:0063`` -- ONE driver tick (the timer-ISR entry the game calls each beat).

        The SPINE, transcribed from the disasm: a re-entry guard (``[0062]`` -- skip if a tick is
        already running), the ``0409`` page gate (pick up a new sound-page request), the ``[000D]``
        divider decrement, NINE ``00CD`` channel ticks over the channel states at
        ``0x05A9 + i*0x20``, the divider reload from ``[000C]`` at 0, and clearing the guard.

        The two sub-calls it drives -- :meth:`_page_gate_0409` (the sound-page dispatch into the
        sequencer start ``0291``) and :meth:`_channel_tick_00cd` (the per-channel sequencer that emits
        the YM3812 writes) -- are the remaining recovery slices; see docs/overkill/campaigns/audio.md.
        """
        ram = self.ram
        if ram[REENTRY_GUARD] != 0:                          # 006F
            return
        ram[REENTRY_GUARD] = 1                               # 0074
        self._page_gate_0409()                               # 0076
        ram[TICK_DIVIDER] = (ram[TICK_DIVIDER] - 1) & 0xFF   # 0079
        for i in range(CHANNEL_COUNT):                       # 007D..00B0
            self._channel_tick_00cd((CHANNEL_STATE_BASE + i * CHANNEL_STATE_STRIDE) & 0xFFFF)
        if ram[TICK_DIVIDER] == 0:                           # 00B3
            ram[TICK_DIVIDER] = ram[TICK_DIVIDER_RELOAD]     # 00BA
        ram[REENTRY_GUARD] = 0                               # 00C0

    def _page_gate_0409(self) -> None:
        """``2032:0409`` -- pick up a sound-page change (``[0008]`` request vs ``[005F]`` active) and,
        on a change, enter the sequencer start ``0291``.  NEXT SLICE (not yet transcribed)."""
        raise NotImplementedError("2032:0409 page gate -- next AdLib recovery slice")

    def _channel_tick_00cd(self, state_off: int) -> None:
        """``2032:00CD`` -- advance ONE channel's sequencer and emit its YM3812 writes (via
        :meth:`write_opl_2032_0557`).  The driver's core; NEXT SLICE (not yet transcribed)."""
        raise NotImplementedError("2032:00CD channel tick -- next AdLib recovery slice")

    def drain(self) -> "list[tuple[int, int]]":
        """Take the accumulated ``(reg, val)`` writes since the last drain (for the host OPL sink)."""
        out = self.writes
        self.writes = []
        return out
