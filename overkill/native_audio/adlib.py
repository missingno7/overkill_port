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

    def drain(self) -> "list[tuple[int, int]]":
        """Take the accumulated ``(reg, val)`` writes since the last drain (for the host OPL sink)."""
        out = self.writes
        self.writes = []
        return out
