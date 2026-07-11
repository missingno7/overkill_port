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

RECOVERY STATUS: the leaf ``2032:0557`` (register write), the tick spine ``2032:0063`` and the page
gate / pattern loader ``2032:0409`` (with its ``0291`` sequencer-silence + ``04A4`` operator-reset
helpers) are transcribed + tested below.  The remaining slice is the per-channel bytecode sequencer
``2032:00CD`` and its command callees (set-instrument 0181, note/frequency 024F, mod A/B 02C9/02F6,
helpers 0244/02AA) -- see docs/overkill/campaigns/audio.md for the ordered plan and the oracle gate.
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

#: 2032:0409 page-gate geometry (the music-page dispatcher / pattern loader).
PAGE_REQUEST = 0x0008         # [0008]: the game writes the requested music page here
PAGE_ACTIVE = 0x0009          # [0009]: the page currently playing
PAGE_PENDING = 0x005F         # [005F]: the gate's latched pending page
PAGE_LOAD_COUNT = 0x0060      # [0060]: channels the loaded page drives (descriptor byte +1)
PAGE_TABLE = 0x0947           # word[PAGE_TABLE + page*2] -> the page descriptor pointer
INIT_TABLE = 0x04B1           # 2032:04B1: the (reg,val)-word operator-silence table, 0-word terminated
MAX_MUSIC_PAGE = 0x0A         # pages 1..0x0A load; > 0x0A is a stop (silence all + clear request)
#: channel-state field offsets (stride 0x20 from CHANNEL_STATE_BASE).
CH_DELAY = 0x01               # +0x01: the sequencer countdown
CH_INSTRUMENT = 0x04          # +0x04: the loaded instrument (0xFF = none)
CH_KEYOFF = 0x08             # +0x08: the YM3812 key-off (reg, val) word
CH_BYTECODE_PTR = 0x0A        # +0x0A: the running bytecode pointer
CH_BYTECODE_CUR = 0x0C        # +0x0C: the current bytecode word
CH_ACTIVE = 0x10             # +0x10: nonzero => the channel sequencer runs


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

    def _rw(self, off: int) -> int:
        return self.ram[off & 0xFFFF] | (self.ram[(off + 1) & 0xFFFF] << 8)

    def _ww(self, off: int, val: int) -> None:
        self.ram[off & 0xFFFF] = val & 0xFF
        self.ram[(off + 1) & 0xFFFF] = (val >> 8) & 0xFF

    def _init_table_04a4(self) -> None:
        """``2032:04A4`` -- walk the ``04B1`` (reg, val)-word table, emitting each YM3812 write until a
        zero word terminates it (the operator level/attenuation reset that silences every voice)."""
        si = INIT_TABLE
        w = self._rw(si)                                 # 04A7 lodsw
        while True:
            self.write_opl_2032_0557(w & 0xFF, w >> 8)   # 04A8 call 0557
            si = (si + 2) & 0xFFFF
            w = self._rw(si)                             # 04AB lodsw
            if w == 0:                                   # 04AC/04AE or ax,ax ; jnz
                break

    def _sequencer_silence_0291(self) -> None:
        """``2032:0291`` -- silence all nine channels: emit each channel's key-off word (``+0x08``) and
        clear its active flag (``+0x10``), then clear the page request word ``[0008]`` (a WORD store, so
        it also clears ``[0009]``)."""
        di = CHANNEL_STATE_BASE
        for _ in range(CHANNEL_COUNT):                                       # 0294 cx=9
            self.write_opl_2032_0557(self.ram[(di + CH_KEYOFF) & 0xFFFF],    # 0297/029A
                                     self.ram[(di + CH_KEYOFF + 1) & 0xFFFF])
            self.ram[(di + CH_ACTIVE) & 0xFFFF] = 0                          # 029D mov [di+16],ch
            di = (di + CHANNEL_STATE_STRIDE) & 0xFFFF
        self._ww(PAGE_REQUEST, 0)                                            # 02A5 mov [0008],cx (cx=0)

    def _page_gate_0409(self) -> None:
        """``2032:0409`` -- the music-page dispatcher run once per tick.  It latches a pending page
        (``[0008]`` request -> ``[005F]`` when no page is active), and on a real request either STOPS
        (page > 0x0A -> the ``0291`` silence) or LOADS the page: the ``04A4`` operator reset, a nine-
        channel key-off, then the page descriptor (``0947[page]``) sets the tick divider reload
        ``[000C]``, the channel count ``[0060]`` and each channel's bytecode pointer, finally arming the
        card (BD/08).  With no pending page it is a clean no-op (the common per-tick case)."""
        ram = self.ram
        if ram[PAGE_ACTIVE] == 0:                        # 040B cmp ah,[0009]
            ram[PAGE_PENDING] = ram[PAGE_REQUEST]        # 0411/0414 [005F]=[0008]
        page = ram[PAGE_PENDING]                         # 0417 al=[005F]
        if page == 0:                                    # 041C jnz ; else 041E jmp 04A3 (ret)
            return
        ram[PAGE_REQUEST] = 0                            # 0421 [0008]=ah(0)
        ram[PAGE_PENDING] = 0                            # 0425 [005F]=ah(0)
        if page > MAX_MUSIC_PAGE:                        # 0429/042B cmp al,0Ah ; jbe
            self._sequencer_silence_0291()               # 042D jmp 0291
            return
        # 0430: LOAD page (1..0x0A)
        self._init_table_04a4()                          # 0431 call 04A4
        di = CHANNEL_STATE_BASE                           # 0434
        for _ in range(CHANNEL_COUNT):                    # 0437 cx=9 -- key-off every channel
            self.write_opl_2032_0557(ram[(di + CH_KEYOFF) & 0xFFFF],        # 043A/043D
                                     ram[(di + CH_KEYOFF + 1) & 0xFFFF])
            ram[(di + CH_ACTIVE) & 0xFFFF] = 0            # 0440
            di = (di + CHANNEL_STATE_STRIDE) & 0xFFFF
        ram[PAGE_ACTIVE] = page                          # 0449 [0009]=al
        desc = self._rw(PAGE_TABLE + ((page << 1) & 0xFF))   # 044C shl al,1 (8-bit) ; 0451/0453 lodsw
        si = desc
        ram[TICK_DIVIDER_RELOAD] = ram[si]               # 0456/0457 [000C]=[desc]
        count = ram[(si + 1) & 0xFFFF]                    # 045A lodsb -> cl
        self._ww(PAGE_LOAD_COUNT, count)                  # 045B/045F [0060]=cx (ch=0)
        ram[TICK_DIVIDER] = 0x01                          # 0463/0466 dx=01FF ; [000D]=dh(0x01)
        si = (si + 2) & 0xFFFF
        di = CHANNEL_STATE_BASE                            # 046A
        for _ in range(count):                             # loop cx=count ([0060])
            block = self._rw(si)                           # 046D lodsw -> bx
            si = (si + 2) & 0xFFFF
            first = self._rw(block)                        # 0470 mov ax,[bx]
            self._ww(di + CH_BYTECODE_PTR, (block + 2) & 0xFFFF)   # 0472/0473 inc bx x2 ; 0474 [di+0x0A]=bx
            self._ww(di + CH_BYTECODE_CUR, first)          # 0477 [di+0x0C]=ax
            for off in (0x13, 0x19, 0x1D, 0x1A, 0x1B):     # 047A..0486 clear (ch=0)
                ram[(di + off) & 0xFFFF] = 0
            ram[(di + CH_DELAY) & 0xFFFF] = 0x01           # 0489 [di+1]=dh(1)
            ram[(di + CH_ACTIVE) & 0xFFFF] = 0x01          # 048C [di+16]=dh(1) -> arm the channel
            ram[(di + CH_INSTRUMENT) & 0xFFFF] = 0xFF      # 048F [di+4]=dl(0xFF) -> no instrument yet
            di = (di + CHANNEL_STATE_STRIDE) & 0xFFFF
        self.write_opl_2032_0557(0xBD, 0x00)               # 0497/049A ax=00BD
        self.write_opl_2032_0557(0x08, 0x00)               # 049D/04A0 ax=0008

    def _channel_tick_00cd(self, state_off: int) -> None:
        """``2032:00CD`` -- advance ONE channel's sequencer and emit its YM3812 writes (via
        :meth:`write_opl_2032_0557`).  The driver's core; NEXT SLICE (not yet transcribed)."""
        raise NotImplementedError("2032:00CD channel tick -- next AdLib recovery slice")

    def drain(self) -> "list[tuple[int, int]]":
        """Take the accumulated ``(reg, val)`` writes since the last drain (for the host OPL sink)."""
        out = self.writes
        self.writes = []
        return out
