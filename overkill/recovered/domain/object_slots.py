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

    def with_word(self, index: int, offset: int, value: int) -> "ObjectPool":
        """A new pool with slot ``index``'s word at byte ``offset`` set to ``value``."""
        words = list(self.slots[index])
        words[offset >> 1] = value & 0xFFFF
        slots = self.slots[:index] + (tuple(words),) + self.slots[index + 1:]
        return ObjectPool(base=self.base, stride=self.stride, slots=slots)


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
