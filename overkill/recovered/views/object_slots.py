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
# Index (x16 stride) into the DS:2078 linked-counter table; FFFFh = unlinked.
# On the object's death the deactivation path decrements/clears that counter, and
# completion effects fire when it reaches zero (the precise grouping is inferred).
OFF_LINKED_COUNTER_INDEX = 0x28
# Signed per-object movement deltas (object position minus target): computed by
# the 5E1B delta helper and consumed by the 5E42 steer routine's step logic.
OFF_MOVE_DELTA_X = 0x2A
OFF_MOVE_DELTA_Y = 0x2C
# Per-object movement step-error accumulator (Bresenham-style): the 5E42 steer
# routine adds the minor-axis delta here each step and subtracts the major delta
# when it overflows, to decide when the minor axis advances.  Cleared to 0 when a
# slot is (re)initialised.
OFF_MOVE_STEP_ERROR = 0x2E
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

# --- Living memory map of the object record -------------------------------
# Discovery status of every 16-bit word in the 0x38-byte record.  This makes the
# map honest: unmapped bytes are explicit "unknown" rows instead of silent gaps,
# and inferred names are visibly marked rather than reading as settled fact.
# Offsets reference the OFF_* constants above (no re-typed numbers); the rows
# with no constant are the not-yet-named gaps.  Single status source consumed by
# scripts/source_port_status.py and checked by tests/test_recovered_semantics.py.
#
# Status convention:
#   "known"   - role established by direct evidence; stable name.
#   "guessed" - offset proven but role inferred (names often carry _OR_ or a
#               context alias); promote to "known" as evidence firms up.
#   "unknown" - byte belongs to the record but is not yet identified.
FIELD_KNOWN = "known"
FIELD_GUESSED = "guessed"
FIELD_UNKNOWN = "unknown"

OBJECT_RECORD_FIELDS: tuple[tuple[int, str, str], ...] = (
    (OFF_ACTIVE_WORD, "active_word", FIELD_KNOWN),
    (OFF_X, "x", FIELD_KNOWN),
    (OFF_Y, "y", FIELD_KNOWN),
    (OFF_DIRECTION_OR_STEP, "direction_or_step", FIELD_GUESSED),
    (OFF_SPRITE_OR_STATE, "sprite_or_state", FIELD_GUESSED),
    (OFF_GATE_OR_LAYER, "gate_or_layer", FIELD_GUESSED),
    (OFF_DRAW_SCRATCH_OR_DI, "draw_scratch_or_di", FIELD_GUESSED),
    (OFF_LINK_KEY, "link_key", FIELD_GUESSED),
    (0x10, "", FIELD_UNKNOWN),
    (OFF_ROW_OR_PHASE, "row_or_phase", FIELD_GUESSED),
    (OFF_SCAN_FLAG, "scan_flag / object_type", FIELD_GUESSED),
    (OFF_HAZARD_CLASS, "hazard_class / draw_layer", FIELD_GUESSED),
    (OFF_LOGIC_ID, "logic_id", FIELD_KNOWN),
    (OFF_PREVIOUS_LOGIC_ID, "previous_logic_id", FIELD_KNOWN),
    (OFF_SUBSTATE, "substate", FIELD_GUESSED),
    (OFF_SCAN_ENABLE_OR_SOLID, "scan_enable_or_solid", FIELD_GUESSED),
    (OFF_COUNTER_20, "counter_20", FIELD_GUESSED),
    (OFF_TRANSITION_LATCH, "transition_latch", FIELD_GUESSED),
    (OFF_VARIANT, "variant", FIELD_GUESSED),
    (0x26, "", FIELD_UNKNOWN),
    (OFF_LINKED_COUNTER_INDEX, "linked_counter_index", FIELD_GUESSED),
    (OFF_MOVE_DELTA_X, "move_delta_x", FIELD_KNOWN),
    (OFF_MOVE_DELTA_Y, "move_delta_y", FIELD_KNOWN),
    (OFF_MOVE_STEP_ERROR, "move_step_error", FIELD_KNOWN),
    (OFF_ACQUIRED_TARGET_PTR, "acquired_target_ptr", FIELD_GUESSED),
    (OFF_TARGET_Y, "target_y", FIELD_KNOWN),
    (OFF_TARGET_X, "target_x", FIELD_KNOWN),
    (0x36, "", FIELD_UNKNOWN),
)


def object_record_field_status() -> dict[str, int]:
    """Object-record words counted by discovery status (known/guessed/unknown).

    A small queryable coverage summary; the status dashboard is the live consumer
    that keeps :data:`OBJECT_RECORD_FIELDS` honest as fields get promoted.
    """
    counts = {FIELD_KNOWN: 0, FIELD_GUESSED: 0, FIELD_UNKNOWN: 0}
    for _offset, _name, status in OBJECT_RECORD_FIELDS:
        counts[status] += 1
    return counts


# Per-frame countdown-timer table scanned by 1010:61C7 (six 16-bit counters,
# DS:2368..2372, ending at the 2374h sentinel) and the packed-BCD score written
# by 1010:5F0D (DS:2314, five bytes).  Canonical DS-relative layout facts so the
# 61C7 adapter and the game-state decoder share one source.
FRAME_TIMER_TABLE_BASE = 0x2368
FRAME_TIMER_COUNT = 6
FRAME_TIMER_TABLE_END = FRAME_TIMER_TABLE_BASE + FRAME_TIMER_COUNT * 2  # 0x2374
SCORE_BCD_BASE = 0x2314
SCORE_BCD_LENGTH = 5


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

    @active_word.setter
    def active_word(self, value: int) -> None:
        self.set_u16(OFF_ACTIVE_WORD, value)

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

    @gate_or_layer.setter
    def gate_or_layer(self, value: int) -> None:
        self.set_u16(OFF_GATE_OR_LAYER, value)

    @property
    def link_key(self) -> int:
        return self.u16(OFF_LINK_KEY)

    @link_key.setter
    def link_key(self, value: int) -> None:
        self.set_u16(OFF_LINK_KEY, value)

    @property
    def scan_flag(self) -> int:
        return self.u16(OFF_SCAN_FLAG)

    @scan_flag.setter
    def scan_flag(self, value: int) -> None:
        self.set_u16(OFF_SCAN_FLAG, value)

    @property
    def hazard_class(self) -> int:
        return self.u16(OFF_HAZARD_CLASS)

    @hazard_class.setter
    def hazard_class(self, value: int) -> None:
        # OFF_HAZARD_CLASS is the writable base of the draw_layer read alias.
        self.set_u16(OFF_HAZARD_CLASS, value)

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

    # Context aliases over the shared 0x38-byte record (effect vs gameplay slots
    # reuse the same layout): the scan flag doubles as object type, the hazard
    # class doubles as draw layer.  Read-only - the writers use the base name.
    @property
    def object_type(self) -> int:
        return self.u16(OFF_OBJECT_TYPE)

    @property
    def draw_layer(self) -> int:
        return self.u16(OFF_DRAW_LAYER)

    @property
    def row_or_phase(self) -> int:
        return self.u16(OFF_ROW_OR_PHASE)

    @row_or_phase.setter
    def row_or_phase(self, value: int) -> None:
        self.set_u16(OFF_ROW_OR_PHASE, value)

    @property
    def draw_scratch_or_di(self) -> int:
        return self.u16(OFF_DRAW_SCRATCH_OR_DI)

    @draw_scratch_or_di.setter
    def draw_scratch_or_di(self, value: int) -> None:
        self.set_u16(OFF_DRAW_SCRATCH_OR_DI, value)

    @property
    def substate(self) -> int:
        return self.u16(OFF_SUBSTATE)

    @substate.setter
    def substate(self, value: int) -> None:
        self.set_u16(OFF_SUBSTATE, value)

    @property
    def scan_enable_or_solid(self) -> int:
        return self.u16(OFF_SCAN_ENABLE_OR_SOLID)

    @scan_enable_or_solid.setter
    def scan_enable_or_solid(self, value: int) -> None:
        self.set_u16(OFF_SCAN_ENABLE_OR_SOLID, value)

    @property
    def counter_20(self) -> int:
        return self.u16(OFF_COUNTER_20)

    @counter_20.setter
    def counter_20(self, value: int) -> None:
        self.set_u16(OFF_COUNTER_20, value)

    @property
    def variant(self) -> int:
        return self.u16(OFF_VARIANT)

    @variant.setter
    def variant(self, value: int) -> None:
        self.set_u16(OFF_VARIANT, value)

    @property
    def linked_counter_index(self) -> int:
        return self.u16(OFF_LINKED_COUNTER_INDEX)

    @linked_counter_index.setter
    def linked_counter_index(self, value: int) -> None:
        self.set_u16(OFF_LINKED_COUNTER_INDEX, value)

    @property
    def move_delta_x(self) -> int:
        """Signed X movement delta (object X - target X); set by the 5E1B helper."""
        return self.u16(OFF_MOVE_DELTA_X)

    @property
    def move_delta_y(self) -> int:
        """Signed Y movement delta (object Y - target Y); set by the 5E1B helper."""
        return self.u16(OFF_MOVE_DELTA_Y)

    @property
    def move_step_error(self) -> int:
        """Bresenham-style movement step-error accumulator.  The 5E42 steer
        routine mutates it through flag-affecting add/sub helpers; slot resets
        clear it via the setter."""
        return self.u16(OFF_MOVE_STEP_ERROR)

    @move_step_error.setter
    def move_step_error(self, value: int) -> None:
        self.set_u16(OFF_MOVE_STEP_ERROR, value)

    @property
    def acquired_target_ptr(self) -> int:
        return self.u16(OFF_ACQUIRED_TARGET_PTR)

    @acquired_target_ptr.setter
    def acquired_target_ptr(self, value: int) -> None:
        self.set_u16(OFF_ACQUIRED_TARGET_PTR, value)

    def record_bytes(self) -> bytes:
        """The whole 0x38-byte slot record, read once from live memory.

        Byte-for-byte the original record at ``seg:base`` - used where a snapshot
        needs the raw bytes for exact fidelity alongside the named fields.
        """
        return bytes(self.u8(i) for i in range(OBJECT_SLOT_STRIDE))

    def advanced(self, count: int = 1) -> "ObjectSlotView":
        """Return a view over a later slot using the observed 0x38 stride."""
        return type(self)(self.mem, self.seg, (self.base + count * OBJECT_SLOT_STRIDE) & 0xFFFF)


@dataclass
class ObjectTableView:
    """Typed overlay for a whole object table (effect or gameplay) in DOS memory.

    A live lens, like :class:`ObjectSlotView`: indexing/iterating yields slot
    views over the real VM bytes, so ``table[i].active_word = 0`` writes through.
    No copy of the table is held.
    """

    mem: object
    seg: int
    base: int
    count: int

    @classmethod
    def effect(cls, cpu) -> "ObjectTableView":
        return cls(cpu.mem, cpu.s.ds & 0xFFFF, EFFECT_OBJECT_TABLE_BASE, EFFECT_OBJECT_TABLE_COUNT)

    @classmethod
    def gameplay(cls, cpu) -> "ObjectTableView":
        return cls(cpu.mem, cpu.s.ds & 0xFFFF, GAMEPLAY_OBJECT_TABLE_BASE, GAMEPLAY_OBJECT_TABLE_COUNT)

    def __len__(self) -> int:
        return self.count

    def __getitem__(self, index: int) -> ObjectSlotView:
        if not 0 <= index < self.count:
            raise IndexError(index)
        return ObjectSlotView(self.mem, self.seg, (self.base + index * OBJECT_SLOT_STRIDE) & 0xFFFF)

    def __iter__(self):
        for i in range(self.count):
            yield self[i]

    def active(self):
        """Iterate only the slots whose active word is non-zero."""
        return (slot for slot in self if slot.active_word != 0)
