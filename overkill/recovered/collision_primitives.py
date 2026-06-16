"""Compatibility imports for recovered collision helpers.

New code should use:
  - ``overkill.recovered.domain`` for pure records,
  - ``overkill.recovered.systems`` for portable logic,
  - ``overkill.recovered.adapters`` for DOS/ASM projection.
"""
from __future__ import annotations

from overkill.recovered.adapters.asm_flags import set_carry_and_return
from overkill.recovered.adapters.collision_adapter import (
    TILE_SWEEP_BLOCKED_FLAG,
    VIEW_CONTACT_CENTER_X,
    VIEW_CONTACT_CENTER_Y,
    mark_tile_sweep_blocked,
    read_view_contact_center,
    run_signed_center_rect_test_8331,
    view_contact_centers,
)
from overkill.recovered.domain.collision import RectContactResult, ViewContactCenter
from overkill.recovered.systems.collision import view_contact_rect_test

__all__ = [
    "RectContactResult",
    "TILE_SWEEP_BLOCKED_FLAG",
    "VIEW_CONTACT_CENTER_X",
    "VIEW_CONTACT_CENTER_Y",
    "ViewContactCenter",
    "mark_tile_sweep_blocked",
    "read_view_contact_center",
    "run_signed_center_rect_test_8331",
    "set_carry_and_return",
    "view_contact_centers",
    "view_contact_rect_test",
]
