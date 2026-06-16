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
