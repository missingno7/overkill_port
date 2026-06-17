"""Project OVERKILL's DOS runtime state into recovered source-like records."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Iterable

from overkill.recovered.domain.world import (
    RuntimeObjectSlot,
    RuntimePointerEntry,
    RuntimeWorldProjection,
)
from overkill.recovered.views.object_slots import (
    EFFECT_OBJECT_TABLE_BASE,
    EFFECT_OBJECT_TABLE_COUNT,
    GAMEPLAY_OBJECT_TABLE_BASE,
    GAMEPLAY_OBJECT_TABLE_COUNT,
    OBJECT_SLOT_STRIDE,
    OBJECT_TABLE_BASE,
    OBJECT_TABLE_COUNT,
    OFF_ACQUIRED_TARGET_PTR,
    OFF_ACTIVE_WORD,
    OFF_COUNTER_20,
    OFF_DIRECTION_OR_STEP,
    OFF_DRAW_SCRATCH_OR_DI,
    OFF_GATE_OR_LAYER,
    OFF_HAZARD_CLASS,
    OFF_LINK_KEY,
    OFF_LOGIC_ID,
    OFF_PREVIOUS_LOGIC_ID,
    OFF_ROW_OR_PHASE,
    OFF_SCAN_ENABLE_OR_SOLID,
    OFF_SCAN_FLAG,
    OFF_SPRITE_OR_STATE,
    OFF_SUBSTATE,
    OFF_TARGET_X,
    OFF_TARGET_Y,
    OFF_TRANSITION_LATCH,
    OFF_VARIANT,
    OFF_X,
    OFF_Y,
    ObjectSlotView,
)


@dataclass(frozen=True, slots=True)
class ObjectSlotTableSpec:
    name: str
    base: int
    count: int


OBJECT_SLOT_TABLE_SPECS: tuple[ObjectSlotTableSpec, ...] = (
    ObjectSlotTableSpec("effect_contact_slots_23b4", EFFECT_OBJECT_TABLE_BASE, EFFECT_OBJECT_TABLE_COUNT),
    ObjectSlotTableSpec("gameplay_object_slots_2b5c", GAMEPLAY_OBJECT_TABLE_BASE, GAMEPLAY_OBJECT_TABLE_COUNT),
)

POINTER_TABLE_SPECS: tuple[tuple[str, int, int], ...] = (
    ("object_update_draw_32ca", 0x32CA, 0x24),
    ("compact_effect_8d12", 0x8D12, 0x22),
)

BOSS_GROUP_POINTERS = (0xA8BA, 0xA8BC, 0xA8BE, 0xA8C0)

RUNTIME_GLOBAL_WORDS: tuple[tuple[str, int], ...] = (
    ("camera_or_view_x_237e", 0x237E),
    ("camera_or_view_y_2380", 0x2380),
    ("view_contact_center_x_95f2", 0x95F2),
    ("view_contact_center_y_95f4", 0x95F4),
    ("effect_allocator_cursor_95d8", 0x95D8),
    ("object_allocator_cursor_95da", 0x95DA),
    ("tile_sweep_blocked_a430", 0xA430),
    ("hazard_probe_x_a436", 0xA436),
    ("hazard_probe_y_a438", 0xA438),
    ("boss_or_object_counter_a47e", 0xA47E),
    ("boss_group_latch_a8c2", 0xA8C2),
)

# Evidence-backed object-slot fields.  This intentionally mirrors the view
# offsets so trace tooling can say "slot 4.logic_id" instead of only
# "effect_contact_slots_23b4 + 0xF8".  Unknown offsets remain explicit and are
# useful evidence: repeated writes to an unknown offset are often the next field
# to crystallise.
OBJECT_SLOT_FIELD_NAMES: dict[int, str] = {
    OFF_ACTIVE_WORD: "active_word",
    OFF_X: "x_word",
    OFF_Y: "y_word",
    OFF_DIRECTION_OR_STEP: "direction_or_step",
    OFF_SPRITE_OR_STATE: "sprite_or_state",
    OFF_GATE_OR_LAYER: "gate_or_layer",
    OFF_DRAW_SCRATCH_OR_DI: "draw_scratch_or_di",
    OFF_LINK_KEY: "link_key_or_present_si",
    OFF_ROW_OR_PHASE: "row_or_phase",
    OFF_SCAN_FLAG: "scan_flag_or_object_type",
    OFF_HAZARD_CLASS: "hazard_class_or_draw_layer",
    OFF_LOGIC_ID: "logic_id",
    OFF_PREVIOUS_LOGIC_ID: "previous_logic_id",
    OFF_SUBSTATE: "substate",
    OFF_SCAN_ENABLE_OR_SOLID: "scan_enable_or_solid",
    OFF_COUNTER_20: "counter_20",
    OFF_TRANSITION_LATCH: "transition_latch",
    OFF_VARIANT: "variant",
    OFF_ACQUIRED_TARGET_PTR: "acquired_target_ptr",
    OFF_TARGET_Y: "target_y_word",
    OFF_TARGET_X: "target_x_word",
}

RUNTIME_GLOBAL_OFFSETS: dict[int, str] = {offset: name for name, offset in RUNTIME_GLOBAL_WORDS}
POINTER_TABLE_BY_NAME: dict[str, tuple[int, int]] = {name: (offset, count) for name, offset, count in POINTER_TABLE_SPECS}



def object_slot_ref_for_offset(offset: int) -> tuple[str, int] | None:
    """Return ``(table_name, index)`` for a recovered object offset, if known."""
    offset &= 0xFFFF
    for spec in OBJECT_SLOT_TABLE_SPECS:
        if offset < spec.base:
            continue
        delta = offset - spec.base
        if delta % OBJECT_SLOT_STRIDE != 0:
            continue
        index = delta // OBJECT_SLOT_STRIDE
        if 0 <= index < spec.count:
            return spec.name, index
    return None


def object_slot_index_for_offset(offset: int) -> int | None:
    """Legacy DS:23B4 slot-index resolver for BDD0/BDE3/AC81 evidence."""
    offset &= 0xFFFF
    if offset < OBJECT_TABLE_BASE:
        return None
    delta = offset - OBJECT_TABLE_BASE
    if delta % OBJECT_SLOT_STRIDE != 0:
        return None
    index = delta // OBJECT_SLOT_STRIDE
    if not 0 <= index < OBJECT_TABLE_COUNT:
        return None
    return index


def _view_for_spec(cpu, spec: ObjectSlotTableSpec, index: int) -> ObjectSlotView:
    return ObjectSlotView.from_ds(cpu, spec.base + index * OBJECT_SLOT_STRIDE)


def read_runtime_object_slot(cpu, index: int, *, spec: ObjectSlotTableSpec | None = None) -> RuntimeObjectSlot:
    table_spec = spec or OBJECT_SLOT_TABLE_SPECS[0]
    view = _view_for_spec(cpu, table_spec, index)
    return RuntimeObjectSlot(
        table=table_spec.name,
        index=index,
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


def read_runtime_object_slots(cpu) -> tuple[RuntimeObjectSlot, ...]:
    slots: list[RuntimeObjectSlot] = []
    for spec in OBJECT_SLOT_TABLE_SPECS:
        slots.extend(read_runtime_object_slot(cpu, index, spec=spec) for index in range(spec.count))
    return tuple(slots)


def read_pointer_table(cpu, *, table: str, offset: int, count: int) -> tuple[RuntimePointerEntry, ...]:
    ds = cpu.s.ds & 0xFFFF
    out: list[RuntimePointerEntry] = []
    for index in range(count):
        value = cpu.mem.rw(ds, (offset + index * 2) & 0xFFFF)
        ref = object_slot_ref_for_offset(value)
        out.append(
            RuntimePointerEntry(
                table=table,
                index=index,
                value=value,
                object_slot_table=None if ref is None else ref[0],
                object_slot_index=None if ref is None else ref[1],
            )
        )
    return tuple(out)


def read_known_pointer_tables(cpu) -> tuple[RuntimePointerEntry, ...]:
    entries: list[RuntimePointerEntry] = []
    for table, offset, count in POINTER_TABLE_SPECS:
        entries.extend(read_pointer_table(cpu, table=table, offset=offset, count=count))
    return tuple(entries)


def _sorted_counts(values: Iterable[int]) -> tuple[tuple[int, int], ...]:
    return tuple(sorted((int(key), int(value)) for key, value in Counter(values).items()))


def project_runtime_world(cpu) -> RuntimeWorldProjection:
    objects = read_runtime_object_slots(cpu)
    return RuntimeWorldProjection(
        objects=objects,
        pointer_entries=read_known_pointer_tables(cpu),
        logic_counts=_sorted_counts(slot.logic_id for slot in objects),
        active_logic_counts=_sorted_counts(slot.logic_id for slot in objects if slot.active),
    )


def read_runtime_globals(cpu) -> dict[str, int]:
    ds = cpu.s.ds & 0xFFFF
    return {name: cpu.mem.rw(ds, offset) for name, offset in RUNTIME_GLOBAL_WORDS}


def read_boss_group_pointer_entries(cpu) -> tuple[RuntimePointerEntry, ...]:
    ds = cpu.s.ds & 0xFFFF
    out: list[RuntimePointerEntry] = []
    for index, offset in enumerate(BOSS_GROUP_POINTERS):
        value = cpu.mem.rw(ds, offset)
        ref = object_slot_ref_for_offset(value)
        out.append(
            RuntimePointerEntry(
                table="boss_group_a8ba",
                index=index,
                value=value,
                object_slot_table=None if ref is None else ref[0],
                object_slot_index=None if ref is None else ref[1],
            )
        )
    return tuple(out)


def object_slot_field_for_offset(field_offset: int) -> tuple[str, int]:
    """Return ``(field_name, byte_offset)`` for an object-record byte offset."""
    field_offset %= OBJECT_SLOT_STRIDE
    for start, name in sorted(OBJECT_SLOT_FIELD_NAMES.items()):
        if start <= field_offset < start + 2:
            return name, field_offset - start
    return f"unknown_0x{field_offset:02X}", 0


def object_slot_field_name_for_offset(field_offset: int) -> str:
    """Return a recovered field name for an object-record byte offset."""
    return object_slot_field_for_offset(field_offset)[0]


def describe_world_write_target(region: str, relative: int, size: int) -> dict[str, object]:
    """Decode a trace-world write target into source-like coordinates.

    The tracer observes linear memory ranges.  This helper maps the region name
    and byte offset back to a recovered runtime-world concept: object slot field,
    pointer-table entry, runtime global, or boss-group pointer.  It deliberately
    returns a JSON-friendly dict because the result is evidence metadata, not a
    source-port runtime record.
    """
    relative &= 0xFFFF
    target: dict[str, object] = {
        "kind": "unknown",
        "region": region,
        "relative": relative,
        "size": size,
    }
    for spec in OBJECT_SLOT_TABLE_SPECS:
        if region != spec.name:
            continue
        slot_index = relative // OBJECT_SLOT_STRIDE
        record_offset = relative % OBJECT_SLOT_STRIDE
        field, field_byte_offset = object_slot_field_for_offset(record_offset)
        target.update(
            {
                "kind": "object_slot_field",
                "object_slot_table": spec.name,
                "object_slot_index": slot_index,
                "record_offset": record_offset,
                "field": field,
                "field_byte_offset": field_byte_offset,
            }
        )
        return target
    for name, offset, count in POINTER_TABLE_SPECS:
        if region != name:
            continue
        entry_index = relative // 2
        target.update(
            {
                "kind": "pointer_table_entry",
                "pointer_table": name,
                "pointer_index": entry_index,
                "pointer_table_offset": offset,
                "entry_byte_offset": relative % 2,
            }
        )
        return target
    if region.startswith("boss_group_a8ba["):
        try:
            index = int(region.split("[", 1)[1].split("]", 1)[0])
        except Exception:
            index = None
        target.update(
            {
                "kind": "boss_group_pointer",
                "pointer_table": "boss_group_a8ba",
                "pointer_index": index,
                "entry_byte_offset": relative,
            }
        )
        return target
    for name, _offset in RUNTIME_GLOBAL_WORDS:
        if region == name:
            target.update({"kind": "runtime_global", "global": name})
            return target
    return target


def resolve_pointer_value(value: int) -> dict[str, object]:
    """Return JSON-friendly recovered object-slot reference metadata."""
    ref = object_slot_ref_for_offset(value)
    return {
        "value": value & 0xFFFF,
        "object_slot_table": None if ref is None else ref[0],
        "object_slot_index": None if ref is None else ref[1],
    }


def projection_to_jsonable(projection: RuntimeWorldProjection, *, include_inactive: bool = True) -> dict[str, object]:
    objects = projection.objects if include_inactive else tuple(slot for slot in projection.objects if slot.active)
    return {
        "object_slot_tables": [asdict(spec) for spec in OBJECT_SLOT_TABLE_SPECS],
        "objects": [asdict(slot) for slot in objects],
        "pointer_entries": [asdict(entry) for entry in projection.pointer_entries],
        "logic_counts": [{"logic_id": logic_id, "count": count} for logic_id, count in projection.logic_counts],
        "active_logic_counts": [
            {"logic_id": logic_id, "count": count} for logic_id, count in projection.active_logic_counts
        ],
    }
