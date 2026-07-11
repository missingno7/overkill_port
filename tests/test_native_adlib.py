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
