"""Pure runtime-world records projected from recovered OVERKILL memory views.

These records intentionally contain gameplay-facing values only.  They do not
own DOS memory, CPU registers, segment addresses, or verifier continuations, so
future source-port tooling can consume them without importing the emulator.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RuntimeObjectSlot:
    """Source-port-safe snapshot of one recovered object/effect slot."""

    table: str
    index: int
    active_word: int
    x_word: int
    y_word: int
    gate_or_layer: int
    link_key: int
    scan_flag: int
    hazard_class: int
    logic_id: int
    target_x_word: int
    target_y_word: int

    @property
    def active(self) -> bool:
        return self.active_word != 0


@dataclass(frozen=True, slots=True)
class RuntimePointerEntry:
    """Pointer-table entry resolved to a known slot table when possible."""

    table: str
    index: int
    value: int
    object_slot_table: str | None
    object_slot_index: int | None


@dataclass(frozen=True, slots=True)
class RuntimeWorldProjection:
    """Small, source-like projection of the live OVERKILL runtime state."""

    objects: tuple[RuntimeObjectSlot, ...]
    pointer_entries: tuple[RuntimePointerEntry, ...]
    logic_counts: tuple[tuple[int, int], ...]
    active_logic_counts: tuple[tuple[int, int], ...]
