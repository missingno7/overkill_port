"""Pure object-slot records recovered from repeated object-table evidence."""
from __future__ import annotations

from dataclasses import dataclass

from overkill.recovered.domain.coords import i16


@dataclass(frozen=True, slots=True)
class ObjectSlotRecord:
    """Copied source-like record for one OVERKILL object slot.

    Unlike ``ObjectSlotView``, this record does not own or reference DOS memory.
    It is safe to pass to pure systems and, later, to a native source-port
    runtime.  Field names are intentionally conservative until more independent
    evidence promotes them.
    """

    active_word: int
    x_word: int
    y_word: int
    gate_or_layer: int
    link_key: int
    scan_flag: int
    hazard_class: int
    logic_id: int
    # Enriched native-state fields (Phase 2): the slot's target position (offsets 34h/32h).
    # Defaulted so existing 8-field constructors stay valid; the view/pool projections
    # populate them so rules can take native target state instead of loose ints.
    target_x_word: int = 0x0000
    target_y_word: int = 0x0000

    @property
    def x(self) -> int:
        return i16(self.x_word)

    @property
    def y(self) -> int:
        return i16(self.y_word)

    @property
    def target_x(self) -> int:
        return i16(self.target_x_word)

    @property
    def target_y(self) -> int:
        return i16(self.target_y_word)


@dataclass(frozen=True, slots=True)
class ObjectPool:
    """A native snapshot of one OVERKILL object-slot table.

    Holds every slot's full ``stride``-byte record as a tuple of 16-bit words --
    including the still-unknown bytes -- so the snapshot is byte-faithful to the VM
    table without referencing DOS memory.  This is the VM-free counterpart of the
    DS-relative effect table (DS:23B4) or gameplay table (DS:2B5C) that a standalone
    runtime will own.  ``base`` is the table's DS offset and ``stride`` its record size
    (kept so the snapshot can be mirrored/round-tripped against the VM); the slot count
    is ``len(pool)``.  Frozen: a mutation produces a new pool.
    """

    base: int
    stride: int
    slots: tuple[tuple[int, ...], ...]

    def __len__(self) -> int:
        return len(self.slots)

    def words(self, index: int) -> tuple[int, ...]:
        """The raw 16-bit words of slot ``index`` (faithful, incl. unknown bytes)."""
        return self.slots[index]

    def word_at(self, index: int, offset: int) -> int:
        """The 16-bit word at byte ``offset`` within slot ``index``."""
        return self.slots[index][offset >> 1]

    def active_word(self, index: int) -> int:
        """Slot ``index``'s active word (the first record word); zero means the slot is free."""
        return self.slots[index][0]

    def x_word(self, index: int) -> int:
        """Slot ``index``'s X position word (record byte +02)."""
        return self.slots[index][0x02 >> 1]

    def y_word(self, index: int) -> int:
        """Slot ``index``'s Y position word (record byte +04)."""
        return self.slots[index][0x04 >> 1]

    def sprite_word(self, index: int) -> int:
        """Slot ``index``'s sprite/state word (record byte +08)."""
        return self.slots[index][0x08 >> 1]

    def direction_word(self, index: int) -> int:
        """Slot ``index``'s direction/step word (record byte +06)."""
        return self.slots[index][0x06 >> 1]

    def draw_layer(self, index: int) -> int:
        """Slot ``index``'s draw-layer word (record byte +16; the AA2B/AD60 family selector)."""
        return self.slots[index][0x16 >> 1]

    def substate(self, index: int) -> int:
        """Slot ``index``'s substate/timer word (record byte +1C)."""
        return self.slots[index][0x1C >> 1]

    def substate_1e(self, index: int) -> int:
        """Slot ``index``'s +1E word (the B250 overlap-skip / solid flag)."""
        return self.slots[index][0x1E >> 1]

    def logic_id(self, index: int) -> int:
        """Slot ``index``'s logic-id word (record byte +18; the EFC4 behaviour selector)."""
        return self.slots[index][0x18 >> 1]

    def move_delta_x(self, index: int) -> int:
        """Slot ``index``'s signed X movement delta (record byte +2A)."""
        return self.slots[index][0x2A >> 1]

    def move_delta_y(self, index: int) -> int:
        """Slot ``index``'s signed Y movement delta (record byte +2C)."""
        return self.slots[index][0x2C >> 1]

    def move_step_error(self, index: int) -> int:
        """Slot ``index``'s 5E42 Bresenham step-error accumulator (record byte +2E)."""
        return self.slots[index][0x2E >> 1]

    def target_y_word(self, index: int) -> int:
        """Slot ``index``'s target Y word (record byte +32)."""
        return self.slots[index][0x32 >> 1]

    def target_x_word(self, index: int) -> int:
        """Slot ``index``'s target X word (record byte +34)."""
        return self.slots[index][0x34 >> 1]

    def with_word(self, index: int, offset: int, value: int) -> "ObjectPool":
        """A new pool with slot ``index``'s word at byte ``offset`` set to ``value``."""
        words = list(self.slots[index])
        words[offset >> 1] = value & 0xFFFF
        slots = self.slots[:index] + (tuple(words),) + self.slots[index + 1:]
        return ObjectPool(base=self.base, stride=self.stride, slots=slots)


@dataclass(frozen=True, slots=True)
class FreeSlotAllocation:
    """Result of the native ObjectPool allocator (1010:7573).

    ``offset`` is the freed slot's DS offset, or ``None`` when every slot is occupied;
    ``cursor`` is the new allocator cursor (DS:95DA) -- it parks at the freed slot, or is
    left unchanged when the pool is full.
    """

    offset: "int | None"
    cursor: int


@dataclass(frozen=True, slots=True)
class ObjectSpawnSeed:
    """Pure field values stamped into a freshly allocated slot by 1010:8209.

    Recovered from the straight-line MOV sequence at 8209..8247 that initialises
    a new effect slot.  Most fields are constants; ``x_word``/``target_x_word``
    and ``y_word``/``target_y_word`` come from the caller's source position.
    ``linked_counter_index`` (offset 0x28) is the object's index into the DS:2078
    linked-counter table (``FFFFh`` when unlinked); kept explicit so the seed
    stays byte-faithful to the original stamp.
    """

    active_word: int
    gate_or_layer: int
    x_word: int
    y_word: int
    direction_or_step: int
    scan_flag: int
    hazard_class: int
    logic_id: int
    counter_20: int
    variant: int
    target_x_word: int
    target_y_word: int
    linked_counter_index: int


@dataclass(frozen=True, slots=True)
class ObjectSpawnSeedA4EA:
    """Pure field values stamped into a freshly allocated slot by 1010:A4EA.

    Recovered from the straight-line MOV sequence A4ED..A50F that initialises a
    new ``logic_id=2`` object after A4EA's own ``call 7547`` allocates the slot.
    Every field is a constant (A4EA reads nothing from the caller); position is
    left as the allocator returned it and the spawn-action caller customises the
    record afterwards.  Fields are listed in the original stamp order so the seed
    stays byte-faithful.
    """

    active_word: int
    scan_enable_or_solid: int
    direction_or_step: int
    sprite_or_state: int
    scan_flag: int
    hazard_class: int
    logic_id: int
    substate: int


@dataclass(frozen=True, slots=True)
class LinkedEffectSpawnSeed7420:
    """Pure field values stamped into a freshly allocated effect slot by 1010:7420.

    Recovered from the 7420 stamp BFC7 runs when a linked-counter group's last
    member dies: it spawns a short-lived visual effect at the source's staged
    position.  ``x_word`` is the staged source X (DS:2378) plus the scroll/camera
    offset DS:A278; ``y_word`` is the staged source Y (DS:2376) clamped to the
    ``00C0h`` floor; ``sprite_or_state`` is the staged source type (DS:237A) biased
    by ``+46h``; ``slot_field_26`` is that same raw source type written to the
    object record's still-unnamed ``+26h`` word.  The rest are constants, and the
    spawned effect is itself unlinked (``linked_counter_index = FFFFh``).  Fields are
    listed in the original stamp order so the seed stays byte-faithful; the adapter
    owns the leading 7524 allocation and the DOS write order.
    """

    active_word: int
    x_word: int
    y_word: int
    transition_latch: int
    scan_flag: int
    hazard_class: int
    logic_id: int
    linked_counter_index: int
    variant: int
    slot_field_26: int
    sprite_or_state: int
    gate_or_layer: int


@dataclass(frozen=True, slots=True)
class FormationSpawnSeed7476:
    """Pure field values stamped into a freshly allocated slot by 1010:7476.

    Recovered from the B800 -> 7476 formation child spawn stamp: a new object is placed
    relative to the parent slot's position (``y = slot_y + 1Ch``/``0Ch`` and
    ``x = slot_x + 08h``/``0Ch`` -- the larger Y / smaller X offsets apply in final-boss
    mode, DS:A8C2 == 1), stamped as an active ``logic_id=0Bh`` / ``hazard_class=2`` /
    ``sprite_or_state=31h`` object, and given view-relative movement deltas
    (``move_delta_y = y - (DS:2380 + 9)``, ``move_delta_x = x - DS:237E``).  Fields are in
    the original stamp order so the seed stays byte-faithful; the adapter owns the 7573
    allocation, the DS:98C0 -> DS:BEFF side effect, and the DOS write order.
    """

    y_word: int
    x_word: int
    active_word: int
    scan_enable_or_solid: int
    direction_or_step: int
    sprite_or_state: int
    gate_or_layer: int
    scan_flag: int
    hazard_class: int
    logic_id: int
    substate: int
    move_delta_y: int
    move_delta_x: int
