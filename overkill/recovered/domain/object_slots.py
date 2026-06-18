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

    @property
    def x(self) -> int:
        return i16(self.x_word)

    @property
    def y(self) -> int:
        return i16(self.y_word)


@dataclass(frozen=True, slots=True)
class ObjectSpawnSeed:
    """Pure field values stamped into a freshly allocated slot by 1010:8209.

    Recovered from the straight-line MOV sequence at 8209..8247 that initialises
    a new effect slot.  Most fields are constants; ``x_word``/``target_x_word``
    and ``y_word``/``target_y_word`` come from the caller's source position.
    ``field_28`` is the one slot field with no proven name yet (offset 0x28),
    kept explicit so the seed stays byte-faithful to the original stamp.
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
    field_28: int
