from dos_re.cpu import CPU8086, CPUState
from dos_re.memory import Memory
from overkill.recovered.collision_primitives import (
    mark_tile_sweep_blocked,
    run_signed_center_rect_test_8331,
)
from overkill.recovered.object_slots import (
    OBJECT_SLOT_STRIDE,
    OFF_HAZARD_CLASS,
    OFF_LOGIC_ID,
    OFF_SCAN_FLAG,
    ObjectSlotView,
)


def test_object_slot_view_is_a_live_memory_overlay():
    mem = Memory()
    slot = ObjectSlotView(mem, 0x3000, 0x0100)

    mem.ww(0x3000, 0x0102, 0xFFFE)
    mem.ww(0x3000, 0x0104, 0x0012)
    mem.ww(0x3000, 0x0118, 0x0026)

    assert slot.x_word == 0xFFFE
    assert slot.x == -2
    assert slot.y == 0x0012
    assert slot.logic_id == 0x0026

    slot.x_word = 0x0042
    slot.set_u16(OFF_SCAN_FLAG, 1)
    slot.set_u16(OFF_HAZARD_CLASS, 4)

    assert mem.rw(0x3000, 0x0102) == 0x0042
    assert mem.rw(0x3000, 0x0114) == 1
    assert mem.rw(0x3000, 0x0116) == 4
    assert slot.advanced().base == 0x0100 + OBJECT_SLOT_STRIDE


def test_object_slot_view_constructors_match_original_register_addressing():
    mem = Memory()
    cpu = CPU8086(
        mem,
        CPUState(ds=0x2000, ss=0x3000, bp=0x0100, sp=0x8000),
    )
    current = ObjectSlotView.from_ss_bp(cpu)
    table0 = ObjectSlotView.table_slot(cpu, 0)
    table1 = ObjectSlotView.table_slot(cpu, 1)

    current.set_u16(OFF_LOGIC_ID, 0x1234)
    table0.set_u16(OFF_LOGIC_ID, 0x0082)
    table1.set_u16(OFF_LOGIC_ID, 0x0094)

    assert mem.rw(0x3000, 0x0118) == 0x1234
    assert table0.base == 0x23B4
    assert table1.base == 0x23B4 + OBJECT_SLOT_STRIDE
    assert table0.logic_id == 0x0082
    assert table1.logic_id == 0x0094


def test_recovered_8331_rect_primitive_preserves_branch_flags_until_tail():
    mem = Memory()
    cpu = CPU8086(
        mem,
        CPUState(ds=0x2000, ss=0x3000, bp=0x0100, si=0x7777, flags=0x0203),
    )
    slot = ObjectSlotView.from_ss_bp(cpu)
    slot.x_word = 0x0050
    slot.y_word = 0x0060

    assert run_signed_center_rect_test_8331(cpu, slot, center_x=0x0050, center_y=0x0060)
    # Final comparison is y - (center_y - 0x10), before the caller's STC tail.
    assert cpu.s.si == 0x0050
    assert not cpu.get_flag(0x0040)  # ZF clear for 0x0060 - 0x0050.

    miss = CPU8086(
        Memory(),
        CPUState(ds=0x2000, ss=0x3000, bp=0x0100, si=0x7777, flags=0x0203),
    )
    miss_slot = ObjectSlotView.from_ss_bp(miss)
    miss_slot.x_word = 0x0071
    miss_slot.y_word = 0x0060
    assert not run_signed_center_rect_test_8331(miss, miss_slot, center_x=0x0050, center_y=0x0060)
    assert miss.s.si == 0x0060
    assert not miss.get_flag(0x0040)


def test_recovered_tile_sweep_blocked_flag_is_raw_memory_write():
    mem = Memory()
    cpu = CPU8086(mem, CPUState(ds=0x2000))

    mark_tile_sweep_blocked(cpu)

    assert mem.rw(0x2000, 0xA430) == 1


def test_pure_recovered_collision_system_has_no_vm_dependency():
    from overkill.recovered.domain.collision import ViewContactCenter
    from overkill.recovered.domain.object_slots import ObjectSlotRecord
    from overkill.recovered.systems.collision import view_contact_rect_test

    obj = ObjectSlotRecord(
        active_word=1,
        x_word=0x0050,
        y_word=0x0060,
        gate_or_layer=0,
        link_key=0,
        scan_flag=0,
        hazard_class=0,
        logic_id=0x26,
    )
    center = ViewContactCenter(x_word=0x0050, y_word=0x0060)

    assert view_contact_rect_test(obj, center).hit

    outside = ObjectSlotRecord(
        active_word=1,
        x_word=0x0071,
        y_word=0x0060,
        gate_or_layer=0,
        link_key=0,
        scan_flag=0,
        hazard_class=0,
        logic_id=0x26,
    )
    assert not view_contact_rect_test(outside, center).hit


def test_object_slot_adapter_projects_memory_view_to_pure_record():
    from dos_re.memory import Memory
    from overkill.recovered.adapters.object_slot_adapter import read_object_slot_record
    from overkill.recovered.views.object_slots import ObjectSlotView

    mem = Memory()
    view = ObjectSlotView(mem, 0x2000, 0x0100)
    view.set_u16(0x00, 1)
    view.x_word = 0xFFFE
    view.y_word = 0x0012
    view.set_u16(0x0A, 2)
    view.set_u16(0x0E, 0x3333)
    view.set_u16(0x14, 1)
    view.set_u16(0x16, 4)
    view.set_u16(0x18, 0x0082)

    record = read_object_slot_record(view)

    assert record.x == -2
    assert record.y == 0x0012
    assert record.logic_id == 0x0082
    assert record.hazard_class == 4



def test_pure_recovered_player_hazard_scan_hit_is_source_port_safe():
    from overkill.recovered.domain.collision import ProbePoint
    from overkill.recovered.domain.object_slots import ObjectSlotRecord
    from overkill.recovered.systems.collision import (
        is_player_hazard_scan_candidate,
        player_hazard_scan_hit,
        slot_contains_probe_point,
        word_inside_signed_center_window,
    )

    current = ObjectSlotRecord(
        active_word=1,
        x_word=0,
        y_word=0,
        gate_or_layer=0,
        link_key=0x1111,
        scan_flag=0,
        hazard_class=0,
        logic_id=0x0026,
    )
    hazard = ObjectSlotRecord(
        active_word=1,
        x_word=0x0050,
        y_word=0x0060,
        gate_or_layer=2,
        link_key=0x2222,
        scan_flag=1,
        hazard_class=4,
        logic_id=0x0082,
    )

    assert is_player_hazard_scan_candidate(hazard)
    assert word_inside_signed_center_window(0x0050, 0x0050, include_edges=True)
    assert word_inside_signed_center_window(0x0040, 0x0050, include_edges=True)
    assert not word_inside_signed_center_window(0x0040, 0x0050, include_edges=False)
    assert slot_contains_probe_point(
        hazard,
        ProbePoint(x_word=0x0050, y_word=0x0060),
        include_edges=False,
    )
    assert player_hazard_scan_hit(current, hazard, ProbePoint(x_word=0x0050, y_word=0x0060))

    linked = ObjectSlotRecord(
        active_word=hazard.active_word,
        x_word=hazard.x_word,
        y_word=hazard.y_word,
        gate_or_layer=hazard.gate_or_layer,
        link_key=current.link_key,
        scan_flag=hazard.scan_flag,
        hazard_class=hazard.hazard_class,
        logic_id=hazard.logic_id,
    )
    assert not player_hazard_scan_hit(current, linked, ProbePoint(x_word=0x0050, y_word=0x0060))

    inert = ObjectSlotRecord(
        active_word=hazard.active_word,
        x_word=hazard.x_word,
        y_word=hazard.y_word,
        gate_or_layer=hazard.gate_or_layer,
        link_key=hazard.link_key,
        scan_flag=hazard.scan_flag,
        hazard_class=hazard.hazard_class,
        logic_id=0x0081,
    )
    assert not is_player_hazard_scan_candidate(inert)
    assert not player_hazard_scan_hit(current, inert, ProbePoint(x_word=0x0050, y_word=0x0060))
