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


def test_pure_recovered_movement_target_seek_decision_has_no_vm_dependency():
    from overkill.recovered.domain.movement import MovementTarget
    from overkill.recovered.domain.object_slots import ObjectSlotRecord
    from overkill.recovered.systems.movement import (
        choose_target_seek_direction,
        encode_target_seek_bits,
        step_delta_for_direction,
    )

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
    target = MovementTarget(y_word=0x0062, x_word=0x0052)
    table = [0xFF] * 16
    table[0x0005] = 4

    assert encode_target_seek_bits(obj, target) == 0x0005
    decision = choose_target_seek_direction(obj, target, table)
    assert decision.direction_bits == 0x0005
    assert decision.mapped_direction == 4
    assert not decision.blocked
    assert step_delta_for_direction(4, 2) == (2, 0)


def test_recovered_tile_sweep_direction_plans_are_pure_b00d_order():
    from overkill.recovered.systems.collision import tile_sweep_plan_for_direction

    assert [tile_sweep_plan_for_direction(i).components for i in range(8)] == [
        ("left",),
        ("left", "down"),
        ("down",),
        ("down", "right"),
        ("right",),
        ("right", "up"),
        ("up",),
        ("up", "left"),
    ]



def test_recovered_direction_step_operations_preserve_asm_order():
    from overkill.recovered.domain.coords import i16
    from overkill.recovered.systems.movement import step_operations_for_direction

    assert [op.axis for op in step_operations_for_direction(1, 3)] == ["x", "y"]
    assert [i16(op.delta_word) for op in step_operations_for_direction(1, 3)] == [-3, 3]
    assert [op.axis for op in step_operations_for_direction(3, 8)] == ["y", "x"]
    assert [i16(op.delta_word) for op in step_operations_for_direction(3, 8)] == [8, 8]
    assert [op.axis for op in step_operations_for_direction(7, 2)] == ["y", "x"]
    assert [i16(op.delta_word) for op in step_operations_for_direction(7, 2)] == [-2, -2]



def test_recovered_player_chase_target_projection_and_candidate_gate():
    from overkill.recovered.domain.object_slots import ObjectSlotRecord
    from overkill.recovered.systems.movement import player_center_target_from_view, align_word_to_four
    from overkill.recovered.systems.objects import is_player_chase_target_candidate

    target = player_center_target_from_view(0x0051, 0x0062)
    assert target.x_word == align_word_to_four(0x005B)
    assert target.y_word == align_word_to_four(0x006E)

    candidate = ObjectSlotRecord(
        active_word=1,
        x_word=0x00E0,
        y_word=0x0040,
        gate_or_layer=0,
        link_key=0,
        scan_flag=0,
        hazard_class=4,
        logic_id=0x0020,
    )
    assert is_player_chase_target_candidate(candidate)
    assert not is_player_chase_target_candidate(
        ObjectSlotRecord(1, 0x00E0, 0x0040, 0, 0, 0, 4, 0x0026)
    )
    assert not is_player_chase_target_candidate(
        ObjectSlotRecord(1, 0x00E1, 0x0040, 0, 0, 0, 4, 0x0020)
    )


def test_world_projection_dumps_object_slots_and_pointer_tables():
    from dos_re.cpu import CPU8086, CPUState
    from dos_re.memory import Memory
    from overkill.recovered.adapters.world_adapter import (
        object_slot_index_for_offset,
        project_runtime_world,
        read_boss_group_pointer_entries,
        read_runtime_globals,
    )
    from overkill.recovered.views.object_slots import OBJECT_SLOT_STRIDE

    mem = Memory()
    cpu = CPU8086(mem, CPUState(ds=0x2000, ss=0x3000))
    ds = 0x2000
    slot1 = 0x23B4 + OBJECT_SLOT_STRIDE
    mem.ww(ds, slot1 + 0x00, 1)
    mem.ww(ds, slot1 + 0x02, 0xFFFE)
    mem.ww(ds, slot1 + 0x04, 0x0012)
    mem.ww(ds, slot1 + 0x0A, 2)
    mem.ww(ds, slot1 + 0x0E, 0x3333)
    mem.ww(ds, slot1 + 0x14, 1)
    mem.ww(ds, slot1 + 0x16, 4)
    mem.ww(ds, slot1 + 0x18, 0x0076)
    mem.ww(ds, slot1 + 0x32, 0x0044)
    mem.ww(ds, slot1 + 0x34, 0x0055)
    mem.ww(ds, 0x32CA + 3 * 2, slot1)
    mem.ww(ds, 0xA8BA, slot1)
    mem.ww(ds, 0x95F2, 0x0100)
    mem.ww(ds, 0xA430, 1)

    projection = project_runtime_world(cpu)
    slot = projection.objects[1]

    assert slot.active
    assert slot.x_word == 0xFFFE
    assert slot.logic_id == 0x0076
    assert slot.target_y_word == 0x0044
    assert slot.target_x_word == 0x0055
    assert object_slot_index_for_offset(slot1) == 1
    assert object_slot_index_for_offset(slot1 + 2) is None
    assert any(entry.table == "object_update_draw_32ca" and entry.index == 3 and entry.object_slot_index == 1
               for entry in projection.pointer_entries)
    assert projection.active_logic_counts == ((0x0076, 1),)
    assert read_boss_group_pointer_entries(cpu)[0].object_slot_index == 1
    globals_ = read_runtime_globals(cpu)
    assert globals_["view_contact_center_x_95f2"] == 0x0100
    assert globals_["tile_sweep_blocked_a430"] == 1


def test_recovered_player_chase_acquired_target_validity_is_pure_and_adapter_checked():
    from dos_re.cpu import ZF
    from overkill.recovered.adapters.object_behavior_adapter import (
        run_player_chase_acquired_target_validity_b1b0,
    )
    from overkill.recovered.domain.object_slots import ObjectSlotRecord
    from overkill.recovered.systems.objects import is_player_chase_acquired_target_valid
    from overkill.recovered.views.object_slots import ObjectSlotView

    assert is_player_chase_acquired_target_valid(ObjectSlotRecord(1, 0x00DC, 0, 0, 0, 0, 0, 0x0020))
    assert not is_player_chase_acquired_target_valid(ObjectSlotRecord(0, 0x00DC, 0, 0, 0, 0, 0, 0x0020))
    assert not is_player_chase_acquired_target_valid(ObjectSlotRecord(1, 0x00DD, 0, 0, 0, 0, 0, 0x0020))
    assert not is_player_chase_acquired_target_valid(ObjectSlotRecord(1, 0x00DC, 0, 0, 0, 0, 0, 0x0001))

    cpu = CPU8086(Memory(), CPUState(ds=0x2000, flags=0x0202))
    slot = ObjectSlotView(cpu.mem, 0x2000, 0x0100)
    slot.set_u16(0x00, 1)
    slot.x_word = 0x00DC
    slot.set_u16(0x18, 0x0020)

    assert run_player_chase_acquired_target_validity_b1b0(cpu, slot)
    # The live flags are from the final CMP logic_id,0001h acceptance gate.
    assert not cpu.get_flag(ZF)

    rejected = CPU8086(Memory(), CPUState(ds=0x2000, flags=0x0202))
    rejected_slot = ObjectSlotView(rejected.mem, 0x2000, 0x0100)
    rejected_slot.set_u16(0x00, 1)
    rejected_slot.x_word = 0x00DD
    rejected_slot.set_u16(0x18, 0x0020)

    assert not run_player_chase_acquired_target_validity_b1b0(rejected, rejected_slot)
    # This rejection leaves flags from CMP x,00DCh.
    assert not rejected.get_flag(ZF)


def test_recovered_player_chase_candidate_gate_adapter_matches_pure_predicate():
    from overkill.recovered.adapters.object_behavior_adapter import run_player_chase_candidate_checks_b15a
    from overkill.recovered.views.object_slots import ObjectSlotView

    cpu = CPU8086(Memory(), CPUState(ds=0x2000, flags=0x0202))
    slot = ObjectSlotView(cpu.mem, 0x2000, 0x0100)
    slot.set_u16(0x00, 1)
    slot.x_word = 0x00E0
    slot.set_u16(0x16, 4)
    slot.set_u16(0x18, 0x0020)

    assert run_player_chase_candidate_checks_b15a(cpu, slot)

    excluded = CPU8086(Memory(), CPUState(ds=0x2000, flags=0x0202))
    excluded_slot = ObjectSlotView(excluded.mem, 0x2000, 0x0100)
    excluded_slot.set_u16(0x00, 1)
    excluded_slot.x_word = 0x00E0
    excluded_slot.set_u16(0x16, 4)
    excluded_slot.set_u16(0x18, 0x0026)

    assert not run_player_chase_candidate_checks_b15a(excluded, excluded_slot)


def test_recovered_tilemap_probe_and_lookup_are_pure_source_port_helpers():
    from overkill.recovered.domain.tilemap import TileLookupInput, TileProbeInput
    from overkill.recovered.systems.tilemap import compute_tile_probe_5073, lookup_tile_class_505b

    probe = compute_tile_probe_5073(
        TileProbeInput(
            origin_x_word=0x0040,
            row_base_word=0x0200,
            object_x_word=0x0010,
            object_y_word=0x0034,
        )
    )
    # adjusted_x=0x50 -> x_tile=5, y_tile=3, row_base - 5*13 + 3.
    assert probe.adjusted_x_word == 0x0050
    assert probe.tile_offset_word == 0x01C2
    assert not probe.negative_adjusted_x

    negative = compute_tile_probe_5073(
        TileProbeInput(0x0001, 0x0200, 0x8000, 0x0034)
    )
    assert negative.adjusted_x_word == 0x8001
    assert negative.tile_offset_word == 0xFFFF
    assert negative.negative_adjusted_x

    table = tuple((idx ^ 0x5A) & 0xFF for idx in range(256))
    lookup = lookup_tile_class_505b(TileLookupInput(raw_tile_byte=0xC3, class_table=table))
    assert lookup.raw_tile_byte == 0xC3
    assert lookup.class_byte == (0xC3 ^ 0x5A)


def test_recovered_tilemap_adapters_match_5073_505b_state_effects():
    """Covers 0x5073 overkill_tile_probe_5073 and 0x505B overkill_tile_lookup_505b."""
    from overkill.recovered.adapters.collision_adapter import (
        TILE_CLASS_TABLE,
        TILE_PLANE_SEGMENT_PTR,
        TILE_PROBE_ADJUSTED_X_SCRATCH,
        TILE_PROBE_ORIGIN_X,
        TILE_PROBE_ROW_BASE,
        run_tile_lookup_505b_body,
        run_tile_probe_5073_body,
    )
    from overkill.recovered.views.object_slots import OFF_X, OFF_Y

    mem = Memory()
    cpu = CPU8086(
        mem,
        CPUState(cs=0x1010, ds=0x2000, ss=0x3000, bp=0x0100, bx=0x0012, sp=0x8000),
    )
    ds = 0x2000
    ss = 0x3000
    mem.ww(ds, TILE_PROBE_ORIGIN_X, 0x0040)
    mem.ww(ds, TILE_PROBE_ROW_BASE, 0x0200)
    mem.ww(ss, 0x0100 + OFF_X, 0x0010)
    mem.ww(ss, 0x0100 + OFF_Y, 0x0034)

    result = run_tile_probe_5073_body(cpu, pop_return=False)

    assert result.adjusted_x_word == 0x0050
    assert result.tile_offset_word == 0x01C2
    assert mem.rw(ds, TILE_PROBE_ADJUSTED_X_SCRATCH) == 0x0050
    assert cpu.s.bx == 0x01C2

    tile_segment = 0x4000
    mem.ww(0x1010, TILE_PLANE_SEGMENT_PTR, tile_segment)
    mem.wb(tile_segment, cpu.s.bx, 0x3A)
    mem.wb(ds, TILE_CLASS_TABLE + 0x3A, 0x07)
    cpu.push(0x7777)

    lookup = run_tile_lookup_505b_body(cpu, pop_return=True)

    assert lookup.raw_tile_byte == 0x3A
    assert lookup.class_byte == 0x07
    assert cpu.get_reg8(0) == 0x07
    assert cpu.s.si == TILE_CLASS_TABLE + 0x3A
    assert cpu.s.ip == 0x7777


def test_recovered_ac97_overlap_scan_decision_is_pure_and_adapter_checked():
    from overkill.recovered.adapters.collision_adapter import run_object_overlap_candidate_checks_ac97
    from overkill.recovered.domain.collision import ProbePoint
    from overkill.recovered.domain.object_slots import ObjectSlotRecord
    from overkill.recovered.systems.collision import object_overlap_scan_decision
    from overkill.recovered.views.object_slots import ObjectSlotView

    current = ObjectSlotRecord(1, 0x0050, 0x0060, 0, 0x1111, 1, 4, 0x0020)
    candidate = ObjectSlotRecord(1, 0x0050, 0x0060, 0, 0x2222, 1, 4, 0x0020)
    decision = object_overlap_scan_decision(current, candidate, ProbePoint(0x0050, 0x0060))
    assert decision.overlaps
    assert decision.actionable

    linked = ObjectSlotRecord(1, 0x0050, 0x0060, 0, 0x1111, 1, 4, 0x0020)
    linked_decision = object_overlap_scan_decision(current, linked, ProbePoint(0x0050, 0x0060))
    assert not linked_decision.overlaps
    assert not linked_decision.actionable

    non_actionable = ObjectSlotRecord(1, 0x0050, 0x0060, 0, 0x2222, 1, 3, 0x0020)
    non_actionable_decision = object_overlap_scan_decision(current, non_actionable, ProbePoint(0x0050, 0x0060))
    assert non_actionable_decision.overlaps
    assert not non_actionable_decision.actionable

    cpu = CPU8086(Memory(), CPUState(ds=0x2000, ss=0x3000, bp=0x0100, flags=0x0202))
    current_view = ObjectSlotView(cpu.mem, 0x3000, 0x0100)
    current_view.set_u16(0x0E, 0x1111)
    slot = ObjectSlotView(cpu.mem, 0x2000, 0x0200)
    slot.set_u16(0x00, 1)
    slot.x_word = 0x0050
    slot.y_word = 0x0060
    slot.set_u16(0x0E, 0x2222)
    slot.set_u16(0x14, 1)
    slot.set_u16(0x16, 5)
    slot.set_u16(0x18, 0x0020)

    overlaps, actionable, acd9_flags = run_object_overlap_candidate_checks_ac97(
        cpu,
        current_record=current,
        slot=slot,
        probe_x=0x0050,
        probe_y=0x0060,
    )

    assert overlaps
    assert actionable
    assert acd9_flags != 0


def test_recovered_aa71_postmove_contact_window_is_pure_and_adapter_checked():
    from dos_re.cpu import CF, ZF
    from overkill.recovered.adapters.collision_adapter import (
        FINAL_BOSS_CONTACT_MODE,
        POSTMOVE_CONTACT_VIEW_X,
        POSTMOVE_CONTACT_Y_GUARD,
        run_postmove_contact_window_aa71_body,
    )
    from overkill.recovered.domain.collision import PostMoveContactWindow
    from overkill.recovered.domain.object_slots import ObjectSlotRecord
    from overkill.recovered.systems.collision import postmove_contact_window_test_aa71
    from overkill.recovered.views.object_slots import OFF_X, OFF_Y

    slot = ObjectSlotRecord(1, 0x0050, 0x0060, 0, 0, 0, 0, 0x0020)
    window = PostMoveContactWindow(view_x_word=0x0050, y_guard_word=0x0060, final_boss_narrow_x=False)
    assert postmove_contact_window_test_aa71(slot, window).hit
    assert not postmove_contact_window_test_aa71(
        ObjectSlotRecord(1, 0xFFF0, 0x0060, 0, 0, 0, 0, 0x0020),
        window,
    ).hit
    # Final-boss mode narrows the X span: x=0x50 covers view_x 0x50 normally,
    # but misses 0x60 in boss mode because x+8 < 0x60.
    assert postmove_contact_window_test_aa71(
        slot,
        PostMoveContactWindow(view_x_word=0x0060, y_guard_word=0x0060, final_boss_narrow_x=False),
    ).hit
    assert not postmove_contact_window_test_aa71(
        slot,
        PostMoveContactWindow(view_x_word=0x0060, y_guard_word=0x0060, final_boss_narrow_x=True),
    ).hit

    mem = Memory()
    cpu = CPU8086(
        mem,
        CPUState(ds=0x2000, ss=0x3000, bp=0x0100, sp=0x8000, flags=0x0202),
    )
    cpu.push(0x7777)
    mem.ww(0x3000, 0x0100 + OFF_X, 0x0050)
    mem.ww(0x3000, 0x0100 + OFF_Y, 0x0060)
    mem.ww(0x2000, POSTMOVE_CONTACT_VIEW_X, 0x0050)
    mem.ww(0x2000, POSTMOVE_CONTACT_Y_GUARD, 0x0060)
    mem.ww(0x2000, FINAL_BOSS_CONTACT_MODE, 0x0000)

    assert run_postmove_contact_window_aa71_body(cpu)
    assert cpu.get_flag(CF)
    assert cpu.s.ip == 0x7777
    # Hit leaves ZF from the final CMP lower_x,view_x before the STC tail.
    assert not cpu.get_flag(ZF)

    rejected = CPU8086(
        Memory(),
        CPUState(ds=0x2000, ss=0x3000, bp=0x0100, sp=0x8000, flags=0x0202),
    )
    rejected.push(0x8888)
    rejected.mem.ww(0x3000, 0x0100 + OFF_X, 0x0050)
    rejected.mem.ww(0x3000, 0x0100 + OFF_Y, 0x0060)
    rejected.mem.ww(0x2000, POSTMOVE_CONTACT_VIEW_X, 0x0060)
    rejected.mem.ww(0x2000, POSTMOVE_CONTACT_Y_GUARD, 0x0060)
    rejected.mem.ww(0x2000, FINAL_BOSS_CONTACT_MODE, 0x0001)

    assert not run_postmove_contact_window_aa71_body(rejected)
    assert not rejected.get_flag(CF)
    assert rejected.s.ip == 0x8888


def test_recovered_tile_contact_probe_plan_is_pure_4ff9_sampling_shape():
    from overkill.recovered.systems.tilemap import (
        TILE_CONTACT_ROW_DELTA,
        is_tile_contact_side_valid_4ff9,
        tile_contact_offset_table_byte_offset,
        tile_contact_probe_plan_4ff9,
    )

    assert TILE_CONTACT_ROW_DELTA == 13
    assert is_tile_contact_side_valid_4ff9(0)
    assert is_tile_contact_side_valid_4ff9(2)
    assert not is_tile_contact_side_valid_4ff9(3)
    assert tile_contact_offset_table_byte_offset(2) == 8

    aligned = tile_contact_probe_plan_4ff9(
        side_index_word=0,
        adjusted_x_word=0x001A,  # low nibble A -> one column
        y_word=0x0020,
    )
    assert aligned.valid_side
    assert aligned.offset_table_index == 0
    assert aligned.column_sample_count == 1
    assert not aligned.probe_adjacent_y

    edge = tile_contact_probe_plan_4ff9(
        side_index_word=1,
        adjusted_x_word=0x001B,  # low nibble B -> two columns
        y_word=0x0021,
    )
    assert edge.valid_side
    assert edge.offset_table_index == 1
    assert edge.column_sample_count == 2
    assert edge.probe_adjacent_y

    invalid = tile_contact_probe_plan_4ff9(
        side_index_word=3,
        adjusted_x_word=0,
        y_word=0,
    )
    assert not invalid.valid_side



def test_recovered_ac28_tile_collision_plan_and_adapter_are_canonical():
    from dos_re.cpu import CF
    from overkill.recovered.adapters.collision_adapter import (
        TILE_CLASS_TABLE,
        TILE_COLLISION_BEDC_GATE,
        TILE_COLLISION_DISABLE_GLOBAL,
        TILE_COLLISION_GLOBAL_GATE,
        TILE_COLLISION_ROW_DELTA,
        TILE_PLANE_SEGMENT_PTR,
        TILE_PROBE_ORIGIN_X,
        TILE_PROBE_ROW_BASE,
        run_tile_collision_probe_ac28_body,
    )
    from overkill.recovered.systems.tilemap import tile_collision_probe_plan_ac28
    from overkill.recovered.views.object_slots import OFF_COUNTER_20, OFF_VARIANT, OFF_X, OFF_Y

    assert tile_collision_probe_plan_ac28(y_word=0x0020).row_delta == TILE_COLLISION_ROW_DELTA
    assert not tile_collision_probe_plan_ac28(y_word=0x0020).probe_adjacent_y
    assert tile_collision_probe_plan_ac28(y_word=0x0021).probe_adjacent_y

    def make_cpu(*, y: int, first_class: int, second_class: int = 0, counter: int = 1):
        mem = Memory()
        cpu = CPU8086(
            mem,
            CPUState(cs=0x1010, ds=0x2000, ss=0x3000, bp=0x0100, sp=0x8000, flags=0x0202),
        )
        cpu.push(0x7777)
        ds = 0x2000
        ss = 0x3000
        tile_seg = 0x4000
        mem.ww(0x1010, TILE_PLANE_SEGMENT_PTR, tile_seg)
        mem.ww(ds, TILE_COLLISION_GLOBAL_GATE, 0)
        mem.ww(ds, TILE_COLLISION_DISABLE_GLOBAL, 0)
        mem.ww(ds, TILE_COLLISION_BEDC_GATE, 1)
        mem.ww(ds, TILE_PROBE_ORIGIN_X, 0)
        mem.ww(ds, TILE_PROBE_ROW_BASE, 0x0200)
        mem.ww(ss, 0x0100 + OFF_X, 0x0010)
        mem.ww(ss, 0x0100 + OFF_Y, y)
        mem.ww(ss, 0x0100 + OFF_COUNTER_20, counter)
        # 5073 maps x=0010,y~=0 to BX=01F3; AC28 samples BX+0D -> 0200.
        mem.wb(tile_seg, 0x0200, 5)
        mem.wb(tile_seg, 0x0201, 7)
        mem.wb(ds, TILE_CLASS_TABLE + 5, first_class)
        mem.wb(ds, TILE_CLASS_TABLE + 7, second_class)
        return cpu

    clear = make_cpu(y=0x0000, first_class=0)
    assert not run_tile_collision_probe_ac28_body(clear)
    assert not clear.get_flag(CF)
    assert clear.s.ip == 0x7777

    blocked = make_cpu(y=0x0000, first_class=1, counter=1)
    assert run_tile_collision_probe_ac28_body(blocked)
    assert blocked.get_flag(CF)
    assert blocked.mem.rw(0x3000, 0x0100 + OFF_VARIANT) == 0
    assert blocked.s.ip == 0x7777

    adjacent = make_cpu(y=0x0001, first_class=0, second_class=1, counter=2)
    assert run_tile_collision_probe_ac28_body(adjacent)
    assert not adjacent.get_flag(CF)
    assert adjacent.mem.rw(0x3000, 0x0100 + OFF_VARIANT) == 5
    assert adjacent.mem.rw(0x3000, 0x0100 + OFF_COUNTER_20) == 1
    assert adjacent.s.ip == 0x7777


def test_recovered_bcb1_y_clamp_system_and_shared_adapter_are_canonical():
    from overkill.recovered.adapters.collision_adapter import run_postmove_y_clamp_bcb1_body
    from overkill.recovered.systems.collision import clamp_postmove_y_bcb1
    from overkill.recovered.views.object_slots import OFF_Y

    assert clamp_postmove_y_bcb1(0x00C1).y_word == 0x00C0
    assert clamp_postmove_y_bcb1(0xFFFF).y_word == 0x0000
    assert clamp_postmove_y_bcb1(0x0060).y_word == 0x0060

    def make_cpu(y_word: int, *, push_return: bool = True):
        mem = Memory()
        cpu = CPU8086(
            mem,
            CPUState(cs=0x1010, ds=0x2000, ss=0x3000, bp=0x0100, sp=0x8000, flags=0x0202),
        )
        mem.ww(0x3000, 0x0100 + OFF_Y, y_word)
        if push_return:
            cpu.push(0x7777)
        return cpu

    high = make_cpu(0x00C1)
    run_postmove_y_clamp_bcb1_body(high, pop_return=True)
    assert high.mem.rw(0x3000, 0x0100 + OFF_Y) == 0x00C0
    assert high.s.ip == 0x7777

    negative = make_cpu(0xFFFF)
    run_postmove_y_clamp_bcb1_body(negative, pop_return=True)
    assert negative.mem.rw(0x3000, 0x0100 + OFF_Y) == 0x0000
    assert negative.s.ip == 0x7777

    inline = make_cpu(0x0060, push_return=False)
    start_sp = inline.s.sp
    run_postmove_y_clamp_bcb1_body(inline, pop_return=False)
    assert inline.mem.rw(0x3000, 0x0100 + OFF_Y) == 0x0060
    assert inline.s.sp == start_sp



def test_recovered_boss_group_transition_targets_and_slot_state_are_pure():
    from overkill.recovered.systems.objects import (
        BOSS_GROUP_DEACTIVATED_LOGIC_ID,
        BOSS_GROUP_SPRITE_OR_STATE_DEATH,
        BOSS_GROUP_TRANSITION_LATCH_CLEAR,
        boss_group_slot_transition_c194,
        boss_group_transition_targets,
    )

    assert boss_group_transition_targets(0x268C, (0x2654, 0x268C, 0x26C4, 0x2734)) == (
        0x2654,
        0x26C4,
        0x2734,
    )

    transition = boss_group_slot_transition_c194(0x0077)
    assert transition.previous_logic_id == 0x0077
    assert transition.logic_id == BOSS_GROUP_DEACTIVATED_LOGIC_ID
    assert transition.transition_latch == BOSS_GROUP_TRANSITION_LATCH_CLEAR
    assert transition.sprite_or_state == BOSS_GROUP_SPRITE_OR_STATE_DEATH

def test_recovered_c054_deactivate_dispatch_classification_is_pure_and_named():
    from overkill.recovered.systems.objects import (
        OBJECT_DEACTIVATE_DEBUG_BYTE_LOGIC_ID,
        object_deactivate_dispatch_decision_c054,
    )

    assert object_deactivate_dispatch_decision_c054(0x0076).kind == "boss_group_transition"
    assert object_deactivate_dispatch_decision_c054(OBJECT_DEACTIVATE_DEBUG_BYTE_LOGIC_ID).kind == "counter_drop"
    script = object_deactivate_dispatch_decision_c054(0x001F)
    assert script.kind == "script_select"
    assert script.ax_script == 0xA83E
    assert object_deactivate_dispatch_decision_c054(0x1234).kind == "none"


def test_recovered_ad60_bounds_tile_decision_is_pure_and_named():
    from overkill.recovered.systems.objects import (
        OBJECT_BOUNDS_MAX_X,
        OBJECT_BOUNDS_MAX_Y,
        OBJECT_BOUNDS_MIN_X,
        OBJECT_BOUNDS_TILE_PROBE_DRAW_LAYER,
        OBJECT_BOUNDS_TILE_PROBE_LOGIC_IDS,
        object_bounds_tile_decision_ad60,
    )

    in_bounds_x = (OBJECT_BOUNDS_MIN_X + OBJECT_BOUNDS_MAX_X) // 2
    in_bounds_y = OBJECT_BOUNDS_MAX_Y - 1
    probe_layer = OBJECT_BOUNDS_TILE_PROBE_DRAW_LAYER
    probe_logic = OBJECT_BOUNDS_TILE_PROBE_LOGIC_IDS[0]

    # Out-of-bounds families route to the deactivate tail on any failing edge.
    assert object_bounds_tile_decision_ad60(
        OBJECT_BOUNDS_MIN_X - 1, in_bounds_y, probe_layer, probe_logic, False
    ).kind == "deactivate"
    assert object_bounds_tile_decision_ad60(
        OBJECT_BOUNDS_MAX_X + 1, in_bounds_y, probe_layer, probe_logic, False
    ).kind == "deactivate"
    assert object_bounds_tile_decision_ad60(
        in_bounds_x, OBJECT_BOUNDS_MAX_Y + 1, probe_layer, probe_logic, False
    ).kind == "deactivate"

    # In-bounds but non-probing: wrong draw layer, non-probing logic id, or the
    # BDAC probe-suppress flag all return without a tile probe.
    assert object_bounds_tile_decision_ad60(
        in_bounds_x, in_bounds_y, probe_layer + 1, probe_logic, False
    ).kind == "skip"
    assert object_bounds_tile_decision_ad60(
        in_bounds_x, in_bounds_y, probe_layer, 0x9999, False
    ).kind == "skip"
    assert object_bounds_tile_decision_ad60(
        in_bounds_x, in_bounds_y, probe_layer, probe_logic, True
    ).kind == "skip"

    # In-bounds probing family with BDAC clear runs the tile probe.
    for logic_id in OBJECT_BOUNDS_TILE_PROBE_LOGIC_IDS:
        assert object_bounds_tile_decision_ad60(
            in_bounds_x, in_bounds_y, probe_layer, logic_id, False
        ).kind == "tile_probe"

    # Edges are inclusive on the in-bounds side (MIN_X and MAX_X stay in play).
    assert object_bounds_tile_decision_ad60(
        OBJECT_BOUNDS_MIN_X, in_bounds_y, probe_layer, probe_logic, False
    ).kind == "tile_probe"
    assert object_bounds_tile_decision_ad60(
        OBJECT_BOUNDS_MAX_X, in_bounds_y, probe_layer, probe_logic, False
    ).kind == "tile_probe"


def test_recovered_ab10_object_logic_is_pure_and_named():
    from overkill.recovered.systems.objects import (
        AB10_PHASE_DISABLE_THRESHOLD,
        AB10_SPRITE_BASE_OFFSET,
        object_logic_ab10,
    )

    # Deactivates once either the frame phase or the global disable reaches 0003h.
    assert object_logic_ab10(AB10_PHASE_DISABLE_THRESHOLD, 0, 0, 0, 0, 0, 0).deactivate is True
    assert object_logic_ab10(0, AB10_PHASE_DISABLE_THRESHOLD, 0, 0, 0, 0, 0).deactivate is True
    assert object_logic_ab10(0xFFFF, 0, 0, 0, 0, 0, 0).deactivate is True

    # Below the threshold: sprite = table byte + 9, position = anim pair + view box.
    up = object_logic_ab10(
        frame_phase=2, global_disable=2, sprite_table_value=0x0030,
        anim_x=0x0100, anim_y=0x0050, ref_x=0x0008, ref_y=0x0004,
    )
    assert up.deactivate is False
    assert up.sprite == (0x0030 + AB10_SPRITE_BASE_OFFSET)
    assert up.x == 0x0108
    assert up.y == 0x0054

    # 16-bit wrap is preserved in every field.
    w = object_logic_ab10(0, 0, 0xFFFB, 0xFFFF, 0xFFFE, 0x0003, 0x0005)
    assert w.sprite == 0x0004 and w.x == 0x0002 and w.y == 0x0003


def test_recovered_ae09_object_logic_is_pure_and_named():
    from overkill.recovered.systems.objects import AE09_SPRITE_OFFSET, object_logic_ae09

    # Timer already zero: no decrement, step left, sprite = direction + 28h.
    up = object_logic_ae09(substate=0, direction_or_step=0x0006)
    assert up.substate == 0 and up.direction_or_step == 0x0006
    assert up.decrement_x is True
    assert up.sprite == (0x0006 + AE09_SPRITE_OFFSET)

    # Timer counts down but does not reach zero: decrement only, keep dir, no step.
    up = object_logic_ae09(substate=3, direction_or_step=0x0006)
    assert up.substate == 2 and up.direction_or_step == 0x0006
    assert up.decrement_x is False
    assert up.sprite == (0x0006 + AE09_SPRITE_OFFSET)

    # Timer expires this frame: clear direction, step left, sprite = 28h.
    up = object_logic_ae09(substate=1, direction_or_step=0x0006)
    assert up.substate == 0 and up.direction_or_step == 0x0000
    assert up.decrement_x is True
    assert up.sprite == AE09_SPRITE_OFFSET

    # 16-bit wrap on the sprite add.
    assert object_logic_ae09(0, 0xFFFF).sprite == (0xFFFF + AE09_SPRITE_OFFSET) & 0xFFFF


def test_recovered_ad60_bounds_tile_tail_adapter_matches_pure_decision():
    from overkill.gameplay import object_bounds
    from overkill.recovered.systems.objects import (
        OBJECT_BOUNDS_MAX_X,
        OBJECT_BOUNDS_MAX_Y,
        OBJECT_BOUNDS_MIN_X,
        OBJECT_BOUNDS_TILE_PROBE_DRAW_LAYER,
        OBJECT_BOUNDS_TILE_PROBE_LOGIC_IDS,
    )
    from overkill.recovered.views.object_slots import OFF_DRAW_LAYER, OFF_LOGIC_ID, OFF_X, OFF_Y

    def make_cpu(x, y, draw_layer, logic_id, bdac):
        mem = Memory()
        cpu = CPU8086(
            mem,
            CPUState(cs=0x1010, ds=0x2000, ss=0x3000, bp=0x0100, sp=0x8000, flags=0x0202),
        )
        mem.ww(0x3000, (0x0100 + OFF_X) & 0xFFFF, x)
        mem.ww(0x3000, (0x0100 + OFF_Y) & 0xFFFF, y)
        mem.ww(0x3000, (0x0100 + OFF_DRAW_LAYER) & 0xFFFF, draw_layer)
        mem.ww(0x3000, (0x0100 + OFF_LOGIC_ID) & 0xFFFF, logic_id)
        mem.ww(0x2000, 0xBDAC, bdac)
        cpu.push(0x7777)
        return cpu

    in_x = (OBJECT_BOUNDS_MIN_X + OBJECT_BOUNDS_MAX_X) // 2
    in_y = OBJECT_BOUNDS_MAX_Y - 1
    layer = OBJECT_BOUNDS_TILE_PROBE_DRAW_LAYER
    logic = OBJECT_BOUNDS_TILE_PROBE_LOGIC_IDS[0]

    # The skip branches (in-bounds, non-probing) just return to the pushed IP and
    # must agree with the pure decision without raising.
    skip = make_cpu(in_x, in_y, layer + 1, logic, 0)
    object_bounds._run_object_bounds_tile_tail_ad60(
        skip, parent="test", chain="test", cx_value=0, add_a278_to_x=False
    )
    assert skip.s.ip == 0x7777

    suppressed = make_cpu(in_x, in_y, layer, logic, 1)
    object_bounds._run_object_bounds_tile_tail_ad60(
        suppressed, parent="test", chain="test", cx_value=0, add_a278_to_x=False
    )
    assert suppressed.s.ip == 0x7777


def test_recovered_b73e_idle_phase_rules_are_pure_and_named():
    from overkill.recovered.systems.objects import (
        B73E_IDLE_HIGH_Y_FRAME_BASE,
        B73E_IDLE_LOW_Y_FRAME_BASE,
        B73E_IDLE_LOW_Y_THRESHOLD,
        B73E_SPAWN_WINDOW_MAX,
        B73E_SPAWN_WINDOW_MIN,
        b73e_idle_sprite_frame,
        b73e_reaches_b808,
    )

    # High objects (above the Y line) count down from 007Fh.
    assert b73e_idle_sprite_frame(0x0001, B73E_IDLE_LOW_Y_THRESHOLD - 1) == B73E_IDLE_LOW_Y_FRAME_BASE - 1
    assert b73e_idle_sprite_frame(0x0000, 0x0000) == B73E_IDLE_LOW_Y_FRAME_BASE
    # NEG/ADD wraps to 16 bits when the timer exceeds the base.
    assert b73e_idle_sprite_frame(0x0080, 0x0000) == ((B73E_IDLE_LOW_Y_FRAME_BASE - 0x0080) & 0xFFFF)
    # Low objects (at/below the Y line) count up from 007Ah.
    assert b73e_idle_sprite_frame(0x0005, B73E_IDLE_LOW_Y_THRESHOLD) == B73E_IDLE_HIGH_Y_FRAME_BASE + 0x0005
    assert b73e_idle_sprite_frame(0x0001, 0x00FF) == B73E_IDLE_HIGH_Y_FRAME_BASE + 0x0001

    # Spawn window: inside [02BCh, 02D0h] the spawn block runs (does not reach
    # B808); outside the band control reaches B808 and skips it.
    assert b73e_reaches_b808(B73E_SPAWN_WINDOW_MIN - 1) is True
    assert b73e_reaches_b808(B73E_SPAWN_WINDOW_MAX + 1) is True
    assert b73e_reaches_b808(B73E_SPAWN_WINDOW_MIN) is False
    assert b73e_reaches_b808(B73E_SPAWN_WINDOW_MAX) is False
    assert b73e_reaches_b808((B73E_SPAWN_WINDOW_MIN + B73E_SPAWN_WINDOW_MAX) // 2) is False


def test_recovered_b73e_target_reached_resolution_is_pure_and_named():
    from overkill.recovered.systems.objects import (
        B73E_TARGET_POSTMOVE_232E_SENTINEL,
        B73E_TARGET_RESET_A47E_MAX,
        B73E_TARGET_RESET_DIRECT_COUNTER_MAX,
        b73e_target_reached_resolution,
    )

    high_a47e = B73E_TARGET_RESET_A47E_MAX + 1
    high_counter = B73E_TARGET_RESET_DIRECT_COUNTER_MAX + 10

    # Low A47E wins first regardless of the other globals.
    assert b73e_target_reached_resolution(
        B73E_TARGET_RESET_A47E_MAX, high_counter, 0x0000
    ).kind == "reset_target_check_2324"
    # Then a low DS:2340 counter.
    assert b73e_target_reached_resolution(
        high_a47e, B73E_TARGET_RESET_DIRECT_COUNTER_MAX - 1, 0x0000
    ).kind == "reset_target_direct"
    # Then DS:232E not at the sentinel -> shared post-move tail.
    assert b73e_target_reached_resolution(
        high_a47e, high_counter, B73E_TARGET_POSTMOVE_232E_SENTINEL + 1
    ).kind == "postmove"
    # Otherwise the waypoint-table loop.
    assert b73e_target_reached_resolution(
        high_a47e, high_counter, B73E_TARGET_POSTMOVE_232E_SENTINEL
    ).kind == "waypoint_loop"


def test_recovered_b86d_common_path_rules_are_pure_and_named():
    from overkill.recovered.systems.objects import (
        B86D_FORMATION_SPAWN_TICKS,
        B86D_OUTGOING_SPRITE_FALLING,
        B86D_OUTGOING_SPRITE_RISING,
        B86D_VERTICAL_DELTA_RISING,
        b86d_formation_spawn_tick_index,
        b86d_outgoing_sprite_for_delta,
    )

    # Formation spawn fires only on the three exact counter ticks.
    assert b86d_formation_spawn_tick_index(B86D_FORMATION_SPAWN_TICKS[0]) == 0
    assert b86d_formation_spawn_tick_index(B86D_FORMATION_SPAWN_TICKS[1]) == 1
    assert b86d_formation_spawn_tick_index(B86D_FORMATION_SPAWN_TICKS[2]) == 2
    assert b86d_formation_spawn_tick_index(0x00CB) is None
    assert b86d_formation_spawn_tick_index(B86D_FORMATION_SPAWN_TICKS[0] - 1) is None
    assert b86d_formation_spawn_tick_index(B86D_FORMATION_SPAWN_TICKS[0] + 1) is None

    # Outgoing sprite: only the FFFFh (one-pixel-up) delta keeps the rising sprite.
    assert b86d_outgoing_sprite_for_delta(B86D_VERTICAL_DELTA_RISING) == B86D_OUTGOING_SPRITE_RISING
    assert b86d_outgoing_sprite_for_delta(0x0000) == B86D_OUTGOING_SPRITE_FALLING
    assert b86d_outgoing_sprite_for_delta(0x0001) == B86D_OUTGOING_SPRITE_FALLING
    assert b86d_outgoing_sprite_for_delta(0xFFFE) == B86D_OUTGOING_SPRITE_FALLING


def test_recovered_aa46_view_window_projection_reuses_8331_adapter():
    from dos_re.cpu import CF
    from overkill.recovered.adapters.collision_adapter import (
        POSTMOVE_CONTACT_VIEW_X,
        POSTMOVE_CONTACT_Y_GUARD,
        TILE_CONTACT_OFFSET_TABLE,
        VIEW_CONTACT_CENTER_X,
        VIEW_CONTACT_CENTER_Y,
        VIEW_WINDOW_SIDE_SELECTOR,
        run_view_window_check_aa46_body,
    )
    from overkill.recovered.systems.collision import view_contact_center_from_offsets_aa46
    from overkill.recovered.views.object_slots import OFF_X, OFF_Y

    pure = view_contact_center_from_offsets_aa46(
        view_x_word=0x0100,
        view_y_word=0x0200,
        offset_x_word=0xFFF0,
        offset_y_word=0x0010,
    )
    assert (pure.x_word, pure.y_word) == (0x00F0, 0x0210)

    mem = Memory()
    cpu = CPU8086(
        mem,
        CPUState(cs=0x1010, ds=0x2000, ss=0x3000, bp=0x0100, sp=0x8000, flags=0x0202),
    )
    ds = 0x2000
    ss = 0x3000
    mem.ww(ds, POSTMOVE_CONTACT_VIEW_X, 0x0100)
    mem.ww(ds, POSTMOVE_CONTACT_Y_GUARD, 0x0200)
    mem.ww(ds, VIEW_WINDOW_SIDE_SELECTOR, 0x0001)
    mem.ww(ds, TILE_CONTACT_OFFSET_TABLE + 4, 0xFFF0)
    mem.ww(ds, TILE_CONTACT_OFFSET_TABLE + 6, 0x0010)
    mem.ww(ss, 0x0100 + OFF_X, 0x00F0)
    mem.ww(ss, 0x0100 + OFF_Y, 0x0210)

    assert run_view_window_check_aa46_body(cpu)
    assert cpu.get_flag(CF)
    assert mem.rw(ds, VIEW_CONTACT_CENTER_X) == 0x00F0
    assert mem.rw(ds, VIEW_CONTACT_CENTER_Y) == 0x0210

    negative = CPU8086(
        Memory(),
        CPUState(cs=0x1010, ds=0x2000, ss=0x3000, bp=0x0100, sp=0x8000, flags=0x0203),
    )
    negative.mem.ww(0x3000, 0x0100 + OFF_X, 0xFFFF)
    assert not run_view_window_check_aa46_body(negative)
    assert not negative.get_flag(CF)


def test_recovered_axis_clamp_and_vertical_scroll_bias_are_pure_source_port_helpers():
    from overkill.recovered.domain.movement import VerticalScrollEdgeInput
    from overkill.recovered.systems.movement import (
        bottom_scroll_edge_response_a63c,
        decay_bottom_scroll_bias_a63c,
        one_pixel_axis_step,
        recover_top_scroll_bias_a662,
        top_scroll_edge_response_a648,
        two_pass_axis_clamp_step,
        vertical_scroll_edge_response_a616,
    )

    assert one_pixel_axis_step(0x0020, increment=False).final_word == 0x001F
    assert two_pass_axis_clamp_step(0x0020, limit_word=0x0020, increment=False).step_count == 0
    assert two_pass_axis_clamp_step(0x0021, limit_word=0x0020, increment=False).final_word == 0x0020
    assert two_pass_axis_clamp_step(0x0030, limit_word=0x0020, increment=False).final_word == 0x002E
    assert two_pass_axis_clamp_step(
        0x00AF,
        limit_word=0x00B0,
        increment=True,
        below_condition=True,
    ).final_word == 0x00B0

    assert recover_top_scroll_bias_a662(0xFFFE) == 0xFFFF
    assert recover_top_scroll_bias_a662(0x0000) == 0x0000
    assert decay_bottom_scroll_bias_a63c(0x0003) == 0x0002
    assert decay_bottom_scroll_bias_a63c(0x0000) == 0x0000
    assert top_scroll_edge_response_a648(
        object_y_word=0x0000,
        input_bits=0x02,
        top_bias_word=0x0000,
    ) == 0xFFFF
    assert top_scroll_edge_response_a648(
        object_y_word=0x0000,
        input_bits=0x02,
        top_bias_word=0xFFF8,
    ) == 0xFFF8
    assert bottom_scroll_edge_response_a63c(
        object_y_word=0x00B0,
        input_bits=0x01,
        bottom_bias_word=0x0007,
    ) == 0x0008

    gated = vertical_scroll_edge_response_a616(
        VerticalScrollEdgeInput(
            view_y_word=0x00B6,
            object_y_word=0x0000,
            input_bits=0x03,
            top_bias_word=0x0001,
            bottom_bias_word=0x0002,
        )
    )
    assert not gated.view_gate_open
    assert gated.top_bias_word == 0x0001
    assert gated.bottom_bias_word == 0x0002

    active = vertical_scroll_edge_response_a616(
        VerticalScrollEdgeInput(
            view_y_word=0x00B7,
            object_y_word=0x00B0,
            input_bits=0x01,
            top_bias_word=0xFFFE,
            bottom_bias_word=0x0007,
        )
    )
    assert active.view_gate_open
    assert active.top_bias_word == 0xFFFF
    assert active.bottom_bias_word == 0x0008


def test_frame_timer_step_decrements_first_active_from_start():
    from overkill.recovered.systems.frame_timers import step_first_active_timer

    # First non-zero from the start is decremented; nothing else changes.
    step = step_first_active_timer((0, 0, 5, 3, 0, 0))
    assert step.counters == (0, 0, 4, 3, 0, 0)
    assert step.decremented_index == 2

    # All zero -> no change, no index.
    step = step_first_active_timer((0, 0, 0, 0, 0, 0))
    assert step.counters == (0, 0, 0, 0, 0, 0)
    assert step.decremented_index is None

    # start_index models the 61CA entry where the caller pre-positions DI past
    # earlier slots.
    step = step_first_active_timer((9, 9, 0, 4, 0, 0), start_index=2)
    assert step.counters == (9, 9, 0, 3, 0, 0)
    assert step.decremented_index == 3

    # 16-bit wrap.
    assert step_first_active_timer((0x0000, 0x0001)).counters == (0x0000, 0x0000)
    assert step_first_active_timer((0x8000,)).counters == (0x7FFF,)


def test_game_snapshot_diff_localises_object_field_divergence():
    from overkill.recovered.domain.game_snapshot import (
        GameSnapshot,
        ObjectSlotSnapshot,
        diff_game_snapshot,
    )

    def slot(idx, x):
        return ObjectSlotSnapshot(
            table="gameplay", index=idx, active_word=1, x_word=x, y_word=0,
            direction_or_step=0, sprite_or_state=0, object_type=0, draw_layer=0,
            logic_id=0, previous_logic_id=0, substate=0, target_x_word=0,
            target_y_word=0, raw=bytes(0x38),
        )

    a = GameSnapshot((1, 2, 3, 4, 5, 6), b"\x00" * 5, (slot(0, 100), slot(1, 200)))
    assert diff_game_snapshot(a, a) == []

    # an object x position differs -> one localised field divergence
    b = GameSnapshot((1, 2, 3, 4, 5, 6), b"\x00" * 5, (slot(0, 100), slot(1, 201)))
    diffs = diff_game_snapshot(a, b)
    assert any(d.path == "objects[gameplay:1].x_word" for d in diffs)

    # a frame timer differs -> reported at the top level
    c = GameSnapshot((1, 2, 0, 4, 5, 6), b"\x00" * 5, (slot(0, 100), slot(1, 200)))
    assert any(d.path == "frame_timers" for d in diff_game_snapshot(a, c))

    # a global counter differs -> localised named global divergence.  This is the
    # state class the ringlas bug hid in (DS:A972) before it was in the snapshot.
    g1 = GameSnapshot((1,), b"", (), state_globals=(("action_spawn_counter_a972", 0x14),))
    g2 = GameSnapshot((1,), b"", (), state_globals=(("action_spawn_counter_a972", 0x13),))
    assert diff_game_snapshot(g1, g1) == []
    gdiffs = diff_game_snapshot(g1, g2)
    assert any(d.path == "globals.action_spawn_counter_a972" for d in gdiffs)


def test_decoded_snapshot_includes_state_globals():
    from overkill.recovered.adapters.game_snapshot_adapter import SNAPSHOT_GLOBAL_WORDS

    # The verifier now compares these global counters/gates each frame; the
    # action-spawn/weapon-list counters must be among them (the ringlas guard).
    names = {name for name, _off in SNAPSHOT_GLOBAL_WORDS}
    for required in ("action_spawn_counter_a972", "formation_game_counter_2340", "game_mode_2356"):
        assert required in names


def test_status_cursor_stride_rule_per_video_mode():
    import pytest

    from overkill.recovered.systems.status_display import (
        STATUS_CURSOR_STRIDE_BY_MODE,
        status_cursor_stride,
    )

    # The single rule the 613E/615A hooks now share: cursor stride per mode.
    assert STATUS_CURSOR_STRIDE_BY_MODE == {0: 2, 1: 1, 2: 4}
    assert status_cursor_stride(0) == 2
    assert status_cursor_stride(1) == 1
    assert status_cursor_stride(2) == 4
    # Unknown mode must fail loudly (the original jump tables have no entry).
    with pytest.raises(ValueError):
        status_cursor_stride(3)


def test_object_record_memory_map_covers_every_word_exactly_once():
    from overkill.recovered.views.object_slots import (
        FIELD_UNKNOWN,
        OBJECT_RECORD_FIELDS,
        OBJECT_SLOT_STRIDE,
        object_record_field_status,
    )

    offsets = [off for off, _name, _status in OBJECT_RECORD_FIELDS]
    # Every 16-bit word of the 0x38-byte record, each exactly once, in order:
    # the map can never silently drift from the record stride.
    assert offsets == list(range(0, OBJECT_SLOT_STRIDE, 2))

    for off, name, status in OBJECT_RECORD_FIELDS:
        if status == FIELD_UNKNOWN:
            assert name == "", f"unknown word 0x{off:02X} must stay unnamed"
        else:
            assert name, f"mapped word 0x{off:02X} must carry a name"

    counts = object_record_field_status()
    assert sum(counts.values()) == OBJECT_SLOT_STRIDE // 2 == len(OBJECT_RECORD_FIELDS)


def test_object_record_memory_map_agrees_with_off_constants():
    from overkill.recovered.views import object_slots as m

    by_off = {off: (name, status) for off, name, status in m.OBJECT_RECORD_FIELDS}
    # Rock-solid fields are marked known and sit at their OFF_* offset.
    assert by_off[m.OFF_X] == ("x", m.FIELD_KNOWN)
    assert by_off[m.OFF_LOGIC_ID][1] == m.FIELD_KNOWN
    # Inferred fields stay honest as "guessed" until evidence firms up.
    assert by_off[m.OFF_SCAN_ENABLE_OR_SOLID][1] == m.FIELD_GUESSED
    # The 5E1B delta helper and 5E42 steer routine pinned 0x2A/0x2C/0x2E as the
    # signed X/Y movement deltas and the Bresenham step-error accumulator;
    # promoted unknown -> known.
    assert by_off[m.OFF_MOVE_DELTA_X] == ("move_delta_x", m.FIELD_KNOWN)
    assert by_off[m.OFF_MOVE_DELTA_Y] == ("move_delta_y", m.FIELD_KNOWN)
    assert by_off[m.OFF_MOVE_STEP_ERROR] == ("move_step_error", m.FIELD_KNOWN)
    # 0x28 indexes the DS:2078 linked-counter table; the mechanism is proven but
    # the exact grouping is inferred, so it stays "guessed", not "known".
    assert by_off[m.OFF_LINKED_COUNTER_INDEX] == ("linked_counter_index", m.FIELD_GUESSED)
    # The remaining documented gaps are explicit unknowns, not silent holes.
    for gap in (0x10, 0x26, 0x36):
        assert by_off[gap] == ("", m.FIELD_UNKNOWN)
