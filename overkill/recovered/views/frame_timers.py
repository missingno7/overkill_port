"""Recovered per-frame countdown-timer table overlay for OVERKILL's DOS memory.

``FrameTimersView`` is a thin typed lens over the six 16-bit countdown counters
at ``DS:2368..2372`` (ending at the ``DS:2374`` sentinel) scanned by 1010:61C7.
Like :class:`~overkill.recovered.views.object_slots.ObjectSlotView` it is a view,
not an owned entity: every read/write goes straight to the original VM memory, so
the DOS image stays the single source of truth.
"""
from __future__ import annotations

from dataclasses import dataclass

from overkill.recovered.views.object_slots import (
    FRAME_TIMER_COUNT,
    FRAME_TIMER_TABLE_BASE,
)


@dataclass
class FrameTimersView:
    """Typed overlay for the six per-frame countdown timers in DOS memory.

    Indexing reads/writes one 16-bit counter through live memory; the table is
    never copied.  ``base``/:meth:`end`/:meth:`address_of` expose the DS-relative
    addresses so the 61C7 scan can keep its exact ``DI`` register contract.
    """

    mem: object
    seg: int
    base: int = FRAME_TIMER_TABLE_BASE
    count: int = FRAME_TIMER_COUNT

    @classmethod
    def from_ds(cls, cpu) -> "FrameTimersView":
        """The countdown table addressed by the current ``DS``."""
        return cls(cpu.mem, cpu.s.ds & 0xFFFF)

    @property
    def end(self) -> int:
        """DS-relative sentinel one past the last counter (the DI terminator)."""
        return (self.base + self.count * 2) & 0xFFFF

    def address_of(self, index: int) -> int:
        """DS-relative address of counter ``index`` (matches the scan's ``DI``)."""
        if not 0 <= index < self.count:
            raise IndexError(index)
        return (self.base + index * 2) & 0xFFFF

    def __len__(self) -> int:
        return self.count

    def __getitem__(self, index: int) -> int:
        return self.mem.rw(self.seg, self.address_of(index))

    def __setitem__(self, index: int, value: int) -> None:
        self.mem.ww(self.seg, self.address_of(index), value & 0xFFFF)

    def values(self) -> tuple[int, ...]:
        """Snapshot all counters left-to-right as plain ints (no copy held)."""
        return tuple(
            self.mem.rw(self.seg, (self.base + i * 2) & 0xFFFF) for i in range(self.count)
        )
