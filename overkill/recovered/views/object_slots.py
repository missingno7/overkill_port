"""Recovered object-record overlay for OVERKILL's DOS memory image.

``ObjectSlotView`` is deliberately a view, not an owned Python entity.  It is a
thin typed lens over the original segment:offset bytes used by the verified ASM
hooks.  This keeps the DOS memory image as the single source of truth while we
let a source-like object record crystallise from repeated evidence.
"""
from __future__ import annotations

from dataclasses import dataclass

from overkill.recovered.domain.coords import i16

# Evidence-backed table shape used by the BDD0/BDE3/AC81 scan families.
OBJECT_TABLE_SEGMENT_IS_DS = True
OBJECT_TABLE_BASE = 0x23B4
OBJECT_TABLE_COUNT = 0x23
OBJECT_SLOT_STRIDE = 0x38

# Field offsets that are already repeatedly observed in movement/collision/
# rendering/object-dispatch hooks.  Conservative aliases are preferred over
# over-specific names until more independent evidence accumulates.
OFF_ACTIVE_WORD = 0x00
OFF_X = 0x02
OFF_Y = 0x04
OFF_GATE_OR_LAYER = 0x0A
OFF_LINK_KEY = 0x0E
OFF_SCAN_FLAG = 0x14
OFF_HAZARD_CLASS = 0x16
OFF_LOGIC_ID = 0x18


@dataclass
class ObjectSlotView:
    """Typed overlay for one object slot in the original OVERKILL memory.

    The view does not copy data.  Every property reads or writes the underlying
    emulated memory at ``seg:base+offset``.  Use this in lifted hooks and
    recovered primitives when the original-compatible execution path must remain
    byte-for-byte grounded in the DOS memory record.
    """

    mem: object
    seg: int
    base: int

    @classmethod
    def from_ss_bp(cls, cpu) -> "ObjectSlotView":
        """Current object record addressed by ``SS:BP``."""
        return cls(cpu.mem, cpu.s.ss & 0xFFFF, cpu.s.bp & 0xFFFF)

    @classmethod
    def from_ds(cls, cpu, base: int) -> "ObjectSlotView":
        """Object record addressed by the current ``DS`` and an offset."""
        return cls(cpu.mem, cpu.s.ds & 0xFFFF, base & 0xFFFF)

    @classmethod
    def table_slot(cls, cpu, index: int) -> "ObjectSlotView":
        """Slot ``index`` in the observed DS:23B4 object table."""
        return cls.from_ds(cpu, OBJECT_TABLE_BASE + index * OBJECT_SLOT_STRIDE)

    def off(self, offset: int) -> int:
        return (self.base + (offset & 0xFFFF)) & 0xFFFF

    def u8(self, offset: int) -> int:
        return self.mem.rb(self.seg, self.off(offset))

    def set_u8(self, offset: int, value: int) -> None:
        self.mem.wb(self.seg, self.off(offset), value & 0xFF)

    def u16(self, offset: int) -> int:
        return self.mem.rw(self.seg, self.off(offset))

    def i16(self, offset: int) -> int:
        return i16(self.u16(offset))

    def set_u16(self, offset: int, value: int) -> None:
        self.mem.ww(self.seg, self.off(offset), value & 0xFFFF)

    @property
    def active_word(self) -> int:
        return self.u16(OFF_ACTIVE_WORD)

    @property
    def x_word(self) -> int:
        return self.u16(OFF_X)

    @x_word.setter
    def x_word(self, value: int) -> None:
        self.set_u16(OFF_X, value)

    @property
    def y_word(self) -> int:
        return self.u16(OFF_Y)

    @y_word.setter
    def y_word(self, value: int) -> None:
        self.set_u16(OFF_Y, value)

    @property
    def x(self) -> int:
        return self.i16(OFF_X)

    @property
    def y(self) -> int:
        return self.i16(OFF_Y)

    @property
    def gate_or_layer(self) -> int:
        return self.u16(OFF_GATE_OR_LAYER)

    @property
    def link_key(self) -> int:
        return self.u16(OFF_LINK_KEY)

    @property
    def scan_flag(self) -> int:
        return self.u16(OFF_SCAN_FLAG)

    @property
    def hazard_class(self) -> int:
        return self.u16(OFF_HAZARD_CLASS)

    @property
    def logic_id(self) -> int:
        return self.u16(OFF_LOGIC_ID)

    def advanced(self, count: int = 1) -> "ObjectSlotView":
        """Return a view over a later slot using the observed 0x38 stride."""
        return type(self)(self.mem, self.seg, (self.base + count * OBJECT_SLOT_STRIDE) & 0xFFFF)
