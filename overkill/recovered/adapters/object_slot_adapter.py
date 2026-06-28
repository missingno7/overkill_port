"""Adapters from DOS object-record views to pure domain records."""
from __future__ import annotations

from overkill.recovered.domain.object_slots import ObjectSlotRecord
from overkill.recovered.views.object_slots import ObjectSlotView


def read_object_slot_record(view: ObjectSlotView) -> ObjectSlotRecord:
    """Copy one DOS-memory object slot view into a pure domain record."""
    return ObjectSlotRecord(
        active_word=view.active_word,
        x_word=view.x_word,
        y_word=view.y_word,
        gate_or_layer=view.gate_or_layer,
        link_key=view.link_key,
        scan_flag=view.scan_flag,
        hazard_class=view.hazard_class,
        logic_id=view.logic_id,
        target_x_word=view.target_x_word,
        target_y_word=view.target_y_word,
    )


def read_current_object_slot_record(cpu) -> ObjectSlotRecord:
    """Copy the current ``SS:BP`` object slot into a pure domain record."""
    return read_object_slot_record(ObjectSlotView.from_ss_bp(cpu))
