"""Recovered object-record overlay for OVERKILL's DOS memory image.

``ObjectSlotView`` is deliberately a view, not an owned Python entity.  It is a
thin typed lens over the original segment:offset bytes used by the verified ASM
hooks.  This keeps the DOS memory image as the single source of truth while we
let a source-like object record crystallise from repeated evidence.
"""
from __future__ import annotations

from dataclasses import dataclass

from overkill.recovered.domain.coords import i16

# Evidence-backed object/effect slot tables.
#
# DS:23B4 is the compact/effect/contact table walked by BDD0/BDE3/AC81.
# DS:2B5C is the main gameplay object table whose entries are commonly reached
# through the DS:32CA pointer table and allocator cursor DS:95DA.  Both use the
# same 0x38-byte record shape for the fields recovered so far.
OBJECT_TABLE_SEGMENT_IS_DS = True
EFFECT_OBJECT_TABLE_BASE = 0x23B4
EFFECT_OBJECT_TABLE_COUNT = 0x23
GAMEPLAY_OBJECT_TABLE_BASE = 0x2B5C
GAMEPLAY_OBJECT_TABLE_COUNT = 0x22
OBJECT_SLOT_STRIDE = 0x38
EFFECT_OBJECT_TABLE_END = EFFECT_OBJECT_TABLE_BASE + EFFECT_OBJECT_TABLE_COUNT * OBJECT_SLOT_STRIDE
GAMEPLAY_OBJECT_LAST_SLOT_BASE = GAMEPLAY_OBJECT_TABLE_BASE + (GAMEPLAY_OBJECT_TABLE_COUNT - 1) * OBJECT_SLOT_STRIDE
GAMEPLAY_OBJECT_TABLE_END = GAMEPLAY_OBJECT_TABLE_BASE + GAMEPLAY_OBJECT_TABLE_COUNT * OBJECT_SLOT_STRIDE
# 1010:7573 compares against the first word past the recovered 0x22 gameplay
# records before wrapping to DS:2B5C. Keep this named separately so allocator
# code does not confuse it with the last valid slot base.
GAMEPLAY_OBJECT_ALLOCATOR_WRAP_SENTINEL = GAMEPLAY_OBJECT_TABLE_END

# Legacy aliases for the first table; existing hooks/tests use these names for
# the BDD0/BDE3/AC81 scan family.
OBJECT_TABLE_BASE = EFFECT_OBJECT_TABLE_BASE
OBJECT_TABLE_COUNT = EFFECT_OBJECT_TABLE_COUNT

# Field offsets that are already repeatedly observed in movement/collision/
# rendering/object-dispatch hooks.  These are layout facts, not a claim that
# every table uses the same semantic name at that byte.  Some offsets have
# context aliases below because the original source likely reused the same
# 0x38-byte record shape for effect/contact slots and gameplay object slots.
OFF_ACTIVE_WORD = 0x00
OFF_X = 0x02
OFF_Y = 0x04
OFF_DIRECTION_OR_STEP = 0x06
OFF_SPRITE_OR_STATE = 0x08
OFF_GATE_OR_LAYER = 0x0A
OFF_DRAW_SCRATCH_OR_DI = 0x0C
OFF_LINK_KEY = 0x0E
OFF_ROW_OR_PHASE = 0x12
OFF_SCAN_FLAG = 0x14
OFF_HAZARD_CLASS = 0x16
OFF_LOGIC_ID = 0x18
OFF_PREVIOUS_LOGIC_ID = 0x1A
OFF_SUBSTATE = 0x1C
OFF_SCAN_ENABLE_OR_SOLID = 0x1E
OFF_COUNTER_20 = 0x20
OFF_TRANSITION_LATCH = 0x22
OFF_VARIANT = 0x24
OFF_ACQUIRED_TARGET_PTR = 0x30
OFF_TARGET_Y = 0x32
OFF_TARGET_X = 0x34

# Context aliases.  Keep these aliases together so future renames are evidence
# driven instead of creating parallel magic constants in hook bodies.
OFF_OBJECT_TYPE = OFF_SCAN_FLAG
OFF_DRAW_LAYER = OFF_HAZARD_CLASS
OFF_EFFECT_SCAN_FLAG = OFF_SCAN_FLAG
OFF_EFFECT_HAZARD_CLASS = OFF_HAZARD_CLASS
OFF_PRESENT_SI = OFF_LINK_KEY


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
    def direction_or_step(self) -> int:
        return self.u16(OFF_DIRECTION_OR_STEP)

    @direction_or_step.setter
    def direction_or_step(self, value: int) -> None:
        self.set_u16(OFF_DIRECTION_OR_STEP, value)

    @property
    def sprite_or_state(self) -> int:
        return self.u16(OFF_SPRITE_OR_STATE)

    @sprite_or_state.setter
    def sprite_or_state(self, value: int) -> None:
        self.set_u16(OFF_SPRITE_OR_STATE, value)

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

    @logic_id.setter
    def logic_id(self, value: int) -> None:
        self.set_u16(OFF_LOGIC_ID, value)

    @property
    def previous_logic_id(self) -> int:
        return self.u16(OFF_PREVIOUS_LOGIC_ID)

    @previous_logic_id.setter
    def previous_logic_id(self, value: int) -> None:
        self.set_u16(OFF_PREVIOUS_LOGIC_ID, value)

    @property
    def transition_latch(self) -> int:
        return self.u16(OFF_TRANSITION_LATCH)

    @transition_latch.setter
    def transition_latch(self, value: int) -> None:
        self.set_u16(OFF_TRANSITION_LATCH, value)

    @property
    def target_y_word(self) -> int:
        """Observed target Y copied by the 1010:B729 movement prelude."""
        return self.u16(OFF_TARGET_Y)

    @target_y_word.setter
    def target_y_word(self, value: int) -> None:
        self.set_u16(OFF_TARGET_Y, value)

    @property
    def target_x_word(self) -> int:
        """Observed target X copied by the 1010:B729 movement prelude."""
        return self.u16(OFF_TARGET_X)

    @target_x_word.setter
    def target_x_word(self, value: int) -> None:
        self.set_u16(OFF_TARGET_X, value)

    def advanced(self, count: int = 1) -> "ObjectSlotView":
        """Return a view over a later slot using the observed 0x38 stride."""
        return type(self)(self.mem, self.seg, (self.base + count * OBJECT_SLOT_STRIDE) & 0xFFFF)
