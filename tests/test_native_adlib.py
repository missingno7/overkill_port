"""VM-free AdLib driver (segment 2032) recovery -- unit tests for the transcribed slices."""
from __future__ import annotations

from overkill.native_audio.adlib import AdlibDriver, OPL_BASE_PORT_CELL


def _driver(base: int = 0x388) -> AdlibDriver:
    ram = bytearray(0x600)
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
