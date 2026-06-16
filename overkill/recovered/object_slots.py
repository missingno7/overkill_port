"""Compatibility imports for recovered object-slot views.

New code should import DOS-memory overlays from ``overkill.recovered.views`` and
pure records from ``overkill.recovered.domain``.
"""
from __future__ import annotations

from overkill.recovered.domain.object_slots import ObjectSlotRecord
from overkill.recovered.views.object_slots import *  # noqa: F403

__all__ = [name for name in globals() if name.startswith("OBJECT_") or name.startswith("OFF_")] + [
    "ObjectSlotRecord",
    "ObjectSlotView",
]
