from overkill.recovered.adapters.world_adapter import (
    describe_world_write_target,
    resolve_pointer_value,
)
from scripts.summarize_world_writes import summarise_trace


def test_world_write_target_decodes_object_slot_field():
    target = describe_world_write_target("gameplay_object_slots_2b5c", 2 * 0x38 + 0x18, 2)

    assert target["kind"] == "object_slot_field"
    assert target["object_slot_table"] == "gameplay_object_slots_2b5c"
    assert target["object_slot_index"] == 2
    assert target["record_offset"] == 0x18
    assert target["field"] == "logic_id"
    assert target["field_byte_offset"] == 0


def test_world_write_target_decodes_pointer_and_boss_group_refs():
    target = describe_world_write_target("object_update_draw_32ca", 6, 2)
    assert target["kind"] == "pointer_table_entry"
    assert target["pointer_table"] == "object_update_draw_32ca"
    assert target["pointer_index"] == 3

    ref = resolve_pointer_value(0x2B5C + 4 * 0x38)
    assert ref["object_slot_table"] == "gameplay_object_slots_2b5c"
    assert ref["object_slot_index"] == 4

    boss = describe_world_write_target("boss_group_a8ba[2]", 0, 2)
    assert boss["kind"] == "boss_group_pointer"
    assert boss["pointer_index"] == 2


def test_summarise_world_writes_groups_by_writer_target_and_unknown_fields():
    trace = {
        "source": {"demo": "demo"},
        "status": "max_steps",
        "steps": 10,
        "events": [
            {
                "step": 1,
                "csip": "1010:AE45",
                "writer_island": "gameplay_objects",
                "writer_symbol": None,
                "target": describe_world_write_target("gameplay_object_slots_2b5c", 0x18, 2),
            },
            {
                "step": 2,
                "csip": "1010:AE45",
                "writer_island": "gameplay_objects",
                "writer_symbol": None,
                "target": describe_world_write_target("gameplay_object_slots_2b5c", 0x26, 2),
            },
        ],
    }

    summary = summarise_trace(trace)

    assert summary["event_count"] == 2
    assert summary["writer_count"] == 1
    assert summary["by_writer"][0]["csip"] == "1010:AE45"
    assert summary["by_target"][0]["target"].startswith("gameplay_object_slots_2b5c[0].")
    assert summary["unknown_object_field_writes"] == [
        {"field": "gameplay_object_slots_2b5c.unknown_0x26", "count": 1}
    ]
