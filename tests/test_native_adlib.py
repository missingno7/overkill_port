"""VM-free AdLib driver (segment 2032) recovery -- unit tests for the transcribed slices."""
from __future__ import annotations

from overkill.native_audio.adlib import AdlibDriver, OPL_BASE_PORT_CELL


def _driver(base: int = 0x388) -> AdlibDriver:
    ram = bytearray(0x800)   # covers the nine channel states (0x05A9 + 9*0x20)
    ram[OPL_BASE_PORT_CELL] = base & 0xFF
    ram[OPL_BASE_PORT_CELL + 1] = (base >> 8) & 0xFF
    return AdlibDriver(ram)


def test_opl_base_port_read_from_state():
    assert _driver().opl_base == 0x388


def test_write_leaf_emits_register_value_pair():
    # 2032:0557: AL=reg -> 388h, AH=val -> 389h; the 0579 delays are host timing (no state)
    d = _driver()
    d.write_opl_2032_0557(0x20, 0x21)          # e.g. operator 0 AM/VIB/EG/KSR/mult
    d.write_opl_2032_0557(0xA0, 0x98)          # channel 0 F-number low
    assert d.drain() == [(0x20, 0x21), (0xA0, 0x98)]
    assert d.drain() == []                     # drain clears


def test_write_leaf_masks_to_bytes():
    d = _driver()
    d.write_opl_2032_0557(0x120, 0x1FF)
    assert d.drain() == [(0x20, 0xFF)]


def _spine_driver():
    """A driver with the not-yet-recovered sequencer sub-calls stubbed, to test the 0063 SPINE."""
    from overkill.native_audio.adlib import (
        CHANNEL_COUNT, CHANNEL_STATE_BASE, CHANNEL_STATE_STRIDE,
    )
    d = _driver()
    d._page_gate_calls = 0
    d._channel_offs = []
    d._page_gate_0409 = lambda: setattr(d, "_page_gate_calls", d._page_gate_calls + 1)
    d._channel_tick_00cd = lambda off: d._channel_offs.append(off)
    d._geom = (CHANNEL_COUNT, CHANNEL_STATE_BASE, CHANNEL_STATE_STRIDE)
    return d


def test_tick_spine_drives_gate_and_nine_channels():
    from overkill.native_audio.adlib import REENTRY_GUARD, TICK_DIVIDER
    d = _spine_driver()
    d.ram[TICK_DIVIDER] = 3
    d.tick_2032_0063()
    n, base, stride = d._geom
    assert d._page_gate_calls == 1
    assert d._channel_offs == [base + i * stride for i in range(n)]     # nine channels, stride 0x20
    assert d.ram[TICK_DIVIDER] == 2                                     # divider decremented
    assert d.ram[REENTRY_GUARD] == 0                                    # guard cleared at exit


def test_tick_spine_reloads_divider_at_zero_and_guards_reentry():
    from overkill.native_audio.adlib import REENTRY_GUARD, TICK_DIVIDER, TICK_DIVIDER_RELOAD
    d = _spine_driver()
    d.ram[TICK_DIVIDER] = 1
    d.ram[TICK_DIVIDER_RELOAD] = 5
    d.tick_2032_0063()
    assert d.ram[TICK_DIVIDER] == 5                                     # 1 -> 0 -> reloaded from [000C]

    # re-entry guard: a tick already running is a no-op
    d2 = _spine_driver()
    d2.ram[REENTRY_GUARD] = 1
    d2.tick_2032_0063()
    assert d2._page_gate_calls == 0 and d2._channel_offs == []


# --- 2032:0409 page gate / pattern loader + its 0291 / 04A4 helpers ---------------------------------

def test_init_table_04a4_emits_operator_reset_until_zero_word():
    from overkill.native_audio.adlib import INIT_TABLE
    d = _driver()
    # a (reg,val)-word table: (0x40,0x7F),(0x41,0x7F),(0x5D,0x7F) then a 0 word terminator
    tbl = bytes([0x40, 0x7F, 0x41, 0x7F, 0x5D, 0x7F, 0x00, 0x00])
    d.ram[INIT_TABLE:INIT_TABLE + len(tbl)] = tbl
    d._init_table_04a4()
    assert d.drain() == [(0x40, 0x7F), (0x41, 0x7F), (0x5D, 0x7F)]


def test_sequencer_silence_0291_keys_off_all_channels_and_clears_request():
    from overkill.native_audio.adlib import (
        CHANNEL_COUNT, CHANNEL_STATE_BASE, CHANNEL_STATE_STRIDE, CH_KEYOFF, CH_ACTIVE,
        PAGE_REQUEST, PAGE_ACTIVE,
    )
    d = _driver()
    for i in range(CHANNEL_COUNT):
        di = CHANNEL_STATE_BASE + i * CHANNEL_STATE_STRIDE
        d.ram[di + CH_KEYOFF] = 0xB0 + i        # a distinct key-off reg per channel
        d.ram[di + CH_KEYOFF + 1] = 0x02
        d.ram[di + CH_ACTIVE] = 1
    d.ram[PAGE_REQUEST] = 5
    d.ram[PAGE_ACTIVE] = 5
    d._sequencer_silence_0291()
    assert d.drain() == [(0xB0 + i, 0x02) for i in range(CHANNEL_COUNT)]
    assert all(d.ram[CHANNEL_STATE_BASE + i * CHANNEL_STATE_STRIDE + CH_ACTIVE] == 0
               for i in range(CHANNEL_COUNT))
    assert d.ram[PAGE_REQUEST] == 0 and d.ram[PAGE_ACTIVE] == 0   # WORD store clears both


def test_page_gate_no_pending_is_a_noop():
    from overkill.native_audio.adlib import PAGE_ACTIVE, PAGE_REQUEST, PAGE_PENDING
    d = _driver()
    d.ram[PAGE_ACTIVE] = 2      # a page is playing
    d.ram[PAGE_PENDING] = 0     # nothing pending
    d.ram[PAGE_REQUEST] = 0
    d._page_gate_0409()
    assert d.drain() == []      # the common per-tick case: no writes, no work


def test_page_gate_stop_page_silences():
    from overkill.native_audio.adlib import (
        CHANNEL_COUNT, CHANNEL_STATE_BASE, CHANNEL_STATE_STRIDE, CH_KEYOFF, PAGE_ACTIVE, PAGE_REQUEST,
    )
    d = _driver()
    for i in range(CHANNEL_COUNT):
        di = CHANNEL_STATE_BASE + i * CHANNEL_STATE_STRIDE
        d.ram[di + CH_KEYOFF] = 0xB0
        d.ram[di + CH_KEYOFF + 1] = 0x00
    d.ram[PAGE_ACTIVE] = 0
    d.ram[PAGE_REQUEST] = 0x0B          # > 0x0A -> stop
    d._page_gate_0409()
    assert d.drain() == [(0xB0, 0x00)] * CHANNEL_COUNT


def _adlib_snapshot_seg2032():
    import pathlib
    snap = (pathlib.Path(__file__).resolve().parent.parent / "artifacts" / "demos"
            / "demo_play_tandy_20260711_120636" / "snapshot" / "memory_1mb.bin")
    if not snap.is_file():
        return None
    S = 0x2032 * 16
    return bytearray(snap.read_bytes()[S:S + 0x10000])


def test_page_gate_loads_active_page_matching_the_real_snapshot_descriptor():
    """Differential vs the real AdLib snapshot: reloading its own active page must reproduce the
    descriptor-derived scalars the VM left in place ([000C] reload, [0060] count, [0009] active) and
    arm all nine channels, plus emit the operator-reset + per-channel key-off + BD/08 arm writes."""
    from overkill.native_audio.adlib import (
        AdlibDriver, CHANNEL_COUNT, CHANNEL_STATE_BASE, CHANNEL_STATE_STRIDE,
        CH_ACTIVE, CH_INSTRUMENT, PAGE_ACTIVE, PAGE_REQUEST, PAGE_PENDING,
        TICK_DIVIDER_RELOAD, TICK_DIVIDER, PAGE_LOAD_COUNT,
    )
    ram = _adlib_snapshot_seg2032()
    if ram is None:
        return
    page = ram[PAGE_ACTIVE]                       # 2 in this snapshot
    want_reload = ram[TICK_DIVIDER_RELOAD]        # 6
    want_count = ram[PAGE_LOAD_COUNT] | (ram[PAGE_LOAD_COUNT + 1] << 8)   # 9
    d = AdlibDriver(bytes(ram))
    # re-request the same page from a cleared gate state (as the game does when it (re)starts a page)
    d.ram[PAGE_ACTIVE] = 0
    d.ram[PAGE_REQUEST] = page
    d.ram[PAGE_PENDING] = 0
    d._page_gate_0409()
    # the descriptor-derived scalars match what the VM had loaded for this same page
    assert d.ram[PAGE_ACTIVE] == page
    assert d.ram[TICK_DIVIDER_RELOAD] == want_reload
    assert (d.ram[PAGE_LOAD_COUNT] | (d.ram[PAGE_LOAD_COUNT + 1] << 8)) == want_count
    assert d.ram[TICK_DIVIDER] == 0x01
    # every channel the page drives is armed with no instrument yet
    for i in range(min(want_count, CHANNEL_COUNT)):
        di = CHANNEL_STATE_BASE + i * CHANNEL_STATE_STRIDE
        assert d.ram[di + CH_ACTIVE] == 0x01
        assert d.ram[di + CH_INSTRUMENT] == 0xFF
    writes = d.drain()
    assert (0x40, 0x7F) in writes                 # the 04A4 operator reset ran
    assert writes[-2:] == [(0xBD, 0x00), (0x08, 0x00)]   # the card arm closes the load
