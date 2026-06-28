"""DOS/ASM adapters for recovered collision systems."""
from __future__ import annotations

from dos_re.cpu import CF
from overkill.asm import _add_reg16, _sub_reg16
from overkill.recovered.adapters.asm_flags import (
    add_word_to_si,
    cmp_byte,
    cmp_word,
    set_carry_and_return,
    sub_word_from_si,
)
from overkill.recovered.adapters.object_slot_adapter import read_object_slot_record
from overkill.recovered.domain.collision import PostMoveContactWindow, ProbePoint, ViewContactCenter
from overkill.recovered.domain.tilemap import TileLookupInput, TileLookupResult, TileProbeInput, TileProbeResult
from overkill.recovered.domain.coords import i16
from overkill.recovered.systems.collision import (
    CONTACT_HALF_EXTENT,
    PLAYER_HAZARD_LOGIC_MAX,
    PLAYER_HAZARD_LOGIC_MIN,
    PLAYER_HAZARD_SCAN_REQUIRED_CLASS,
    PLAYER_HAZARD_SCAN_REQUIRED_FLAG,
    PLAYER_HAZARD_SCAN_REQUIRED_GATE,
    OBJECT_OVERLAP_INACTIVE_LOGIC_ID,
    OBJECT_OVERLAP_SCAN_REQUIRED_FLAG,
    POSTMOVE_CONTACT_X_BOSS_SPAN,
    POSTMOVE_CONTACT_X_BOSS_UPPER_BIAS,
    POSTMOVE_CONTACT_X_NORMAL_SPAN,
    POSTMOVE_CONTACT_X_NORMAL_UPPER_BIAS,
    POSTMOVE_CONTACT_Y_SPAN,
    POSTMOVE_CONTACT_Y_UPPER_BIAS,
    clamp_postmove_y_bcb1,
    object_overlap_scan_decision,
    player_hazard_scan_hit,
    postmove_contact_window_test_aa71,
    view_contact_center_from_offsets_aa46,
    view_contact_rect_test,
)
from overkill.recovered.systems.tilemap import (
    TILE_CONTACT_LOW_NIBBLE_MASK,
    TILE_CONTACT_ROW_DELTA,
    TILE_COLLISION_ROW_DELTA,
    TILE_CONTACT_SECOND_COLUMN_THRESHOLD,
    TILE_CONTACT_SIDE_COUNT,
    compute_tile_probe_5073,
    is_tile_contact_side_valid_4ff9,
    lookup_tile_class_505b,
    tile_contact_offset_table_byte_offset,
    tile_contact_probe_plan_4ff9,
    tile_collision_probe_plan_ac28,
)
from overkill.recovered.views.object_slots import (
    OFF_COUNTER_20,
    OFF_VARIANT,
    OFF_Y,
    ObjectSlotView,
)
from overkill.recovered.ds_globals import (
    BOSS_GROUP_LATCH,
    COLLISION_DEBUG_CODE,
    COLLISION_DEBUG_FLAG,
    CONTACT_DISPATCH_GATE,
    VIEW_TARGET_X,
    VIEW_TARGET_Y,
)

VIEW_CONTACT_CENTER_X = 0x95F2
VIEW_CONTACT_CENTER_Y = 0x95F4
POSTMOVE_CONTACT_VIEW_X = VIEW_TARGET_X
POSTMOVE_CONTACT_Y_GUARD = VIEW_TARGET_Y
VIEW_WINDOW_SIDE_SELECTOR = 0x2384
FINAL_BOSS_CONTACT_MODE = BOSS_GROUP_LATCH
TILE_SWEEP_BLOCKED_FLAG = 0xA430

# 1010:5073 coordinate-to-tile helper globals.
TILE_PROBE_ADJUSTED_X_SCRATCH = 0x215A
TILE_PROBE_ORIGIN_X = 0x234E
TILE_PROBE_ROW_BASE = 0x2350

# 1010:505B tile-class lookup globals.
TILE_PLANE_SEGMENT_PTR = 0x9592
TILE_CLASS_TABLE = 0xC3AA
TILE_CLASS_TABLE_SIZE = 0x0100

# 1010:4FF9 tile/contact probe constants.
TILE_CONTACT_OFFSET_TABLE = 0x214E
TILE_CONTACT_RECORD_X = 0x02
TILE_CONTACT_RECORD_Y = 0x04
TILE_CONTACT_RECORD_SIDE = 0x08

# 1010:AC28 tile-collision probe globals/fields.
TILE_COLLISION_GLOBAL_GATE = 0xA47C
TILE_COLLISION_DISABLE_GLOBAL = 0xBDAC
TILE_COLLISION_DEBUG_FLAG = COLLISION_DEBUG_FLAG
TILE_COLLISION_DEBUG_CODE = COLLISION_DEBUG_CODE
TILE_COLLISION_DEBUG_BLOCKED_CODE = 0x0E
TILE_COLLISION_BEDC_GATE = CONTACT_DISPATCH_GATE
TILE_COLLISION_ALT_GATE = 0x2324
TILE_COLLISION_STATE_ON_CONTACT = 0x0005
TILE_COLLISION_STATE_IDLE = 0x0000



class _TileClassTableMemoryView:
    """Lazy Sequence facade over DS:C3AA for pure 505B validation."""

    def __init__(self, mem, ds: int) -> None:
        self._mem = mem
        self._ds = ds & 0xFFFF

    def __len__(self) -> int:
        return TILE_CLASS_TABLE_SIZE

    def __getitem__(self, index: int) -> int:
        if not 0 <= index < TILE_CLASS_TABLE_SIZE:
            raise IndexError(index)
        return self._mem.rb(self._ds, (TILE_CLASS_TABLE + index) & 0xFFFF)



def run_postmove_y_clamp_bcb1_body(cpu, *, pop_return: bool) -> None:
    """Run the shared 1010:BCB1 post-move Y clamp body.

    Both the public BCB1 hook and the larger BC4B/BFC7 lifted parent need this
    exact clamp.  Keep one ASM-compatible body here while the pure recovered
    system owns the source-like decision.
    """
    s = cpu.s
    mem = cpu.mem
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF
    slot = ObjectSlotView(mem, ss, bp)
    y = slot.y_word
    pure = clamp_postmove_y_bcb1(y)

    cmp_word(cpu, y, 0x00C0)
    if i16(y) > 0x00C0:
        slot.y_word = 0x00C0
    else:
        cmp_word(cpu, y, 0x0000)
        if i16(y) < 0:
            slot.y_word = 0x0000

    if slot.y_word != pure.y_word:
        raise AssertionError("pure BCB1 Y clamp disagrees with ASM-compatible body")
    if pop_return:
        s.ip = cpu.pop()

def read_tile_probe_input_from_dos(cpu, slot: ObjectSlotView) -> TileProbeInput:
    """Project 1010:5073's DOS-memory inputs into a pure tilemap record."""
    ds = cpu.s.ds & 0xFFFF
    return TileProbeInput(
        origin_x_word=cpu.mem.rw(ds, TILE_PROBE_ORIGIN_X),
        row_base_word=cpu.mem.rw(ds, TILE_PROBE_ROW_BASE),
        object_x_word=slot.x_word,
        object_y_word=slot.y_word,
    )


def run_tile_probe_5073_body(cpu, *, slot: ObjectSlotView | None = None, pop_return: bool) -> TileProbeResult:
    """Run the shared 1010:5073 body while validating the pure tilemap system.

    ``run_tile_probe_5073`` and a few older lifted parent tails both need this
    exact helper.  Keep the implementation in one adapter so the source-like
    tile-offset formula has one canonical pure home, while the adapter still
    reproduces the original shifts/adds and live flags.
    """
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF
    slot = slot or ObjectSlotView(mem, ss, bp)
    pure = compute_tile_probe_5073(read_tile_probe_input_from_dos(cpu, slot))

    s.ax = mem.rw(ds, TILE_PROBE_ORIGIN_X)
    old_ax = s.ax
    addend = slot.x_word
    s.ax = (old_ax + addend) & 0xFFFF
    cpu.set_add_flags(old_ax, addend, old_ax + addend, 16)
    mem.ww(ds, TILE_PROBE_ADJUSTED_X_SCRATCH, s.ax)
    if s.ax & 0x8000:
        s.bx = 0xFFFF
        if pure.tile_offset_word != s.bx or not pure.negative_adjusted_x:
            raise AssertionError("pure 5073 negative-X result disagrees with ASM-compatible body")
        if pop_return:
            s.ip = cpu.pop()
        return pure

    for _ in range(4):
        s.ax = cpu.shift(5, s.ax, 1, 16)  # SHR AX,1
    s.dx = s.ax

    for _ in range(2):
        s.ax = cpu.shift(4, s.ax, 1, 16)  # SHL AX,1
    s.cx = s.ax
    s.ax = cpu.shift(4, s.ax, 1, 16)
    old_ax = s.ax
    s.ax = (old_ax + s.cx) & 0xFFFF
    cpu.set_add_flags(old_ax, s.cx, old_ax + s.cx, 16)
    old_ax = s.ax
    s.ax = (old_ax + s.dx) & 0xFFFF
    cpu.set_add_flags(old_ax, s.dx, old_ax + s.dx, 16)

    s.bx = mem.rw(ds, TILE_PROBE_ROW_BASE)
    _sub_reg16(cpu, 3, s.ax)
    s.ax = slot.y_word & 0xFFF0
    cpu.set_logic_flags(s.ax, 16)
    for _ in range(4):
        s.ax = cpu.shift(5, s.ax, 1, 16)
    _add_reg16(cpu, 3, s.ax)

    if (mem.rw(ds, TILE_PROBE_ADJUSTED_X_SCRATCH), s.bx & 0xFFFF) != (
        pure.adjusted_x_word,
        pure.tile_offset_word,
    ):
        raise AssertionError("pure 5073 tile-offset result disagrees with ASM-compatible body")
    if pop_return:
        s.ip = cpu.pop()
    return pure


def run_tile_lookup_505b_body(cpu, *, pop_return: bool) -> TileLookupResult:
    """Run the shared 1010:505B body while validating the pure tile-class map."""
    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    ds = s.ds & 0xFFFF

    s.si = TILE_CLASS_TABLE
    s.es = mem.rw(cs, TILE_PLANE_SEGMENT_PTR)
    raw_tile = mem.rb(s.es & 0xFFFF, s.bx & 0xFFFF)
    # The pure tilemap rule is the live source of the class byte (AL).
    result = lookup_tile_class_505b(TileLookupInput(raw_tile_byte=raw_tile, class_table=_TileClassTableMemoryView(mem, ds)))

    s.ax = raw_tile & 0x00FF  # MOV AL,tile / XOR AH,AH (operand for the SI advance)
    old_si = s.si
    s.si = (old_si + s.ax) & 0xFFFF  # ADD SI,AX -> class-table entry (its AF reaches RET)
    cpu.set_add_flags(old_si, s.ax, old_si + s.ax, 16)
    cpu.set_reg8(0, result.class_byte)  # AL = recovered tile class (pure rule is the source)
    cpu.set_logic_flags(result.class_byte, 8)
    if pop_return:
        s.ip = cpu.pop()
    return result



def run_tile_contact_probe_4ff9_body(cpu) -> bool:
    """Run 1010:4FF9 while validating the recovered tile-contact plan.

    4FF9 is the mid-level tile/contact sampler built on top of the 5073
    coordinate-to-tile helper and the 505B tile-class lookup.  The pure tilemap
    layer owns only the sampling plan: three side-offset entries, one/two
    column samples from DS:215A low nibble, and optional adjacent-Y sampling.
    This adapter keeps the original stack restore, BX/CX loop, and flags.
    """
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF

    s.si = mem.rw(ss, (bp + TILE_CONTACT_RECORD_SIDE) & 0xFFFF)
    side = s.si & 0xFFFF
    cmp_word(cpu, s.si, TILE_CONTACT_SIDE_COUNT)
    if not is_tile_contact_side_valid_4ff9(side):
        cpu.set_flag(CF, True)  # 5059: STC ; RET, preserving non-CF flags.
        s.ip = cpu.pop()
        return True

    for _ in range(2):
        s.si = cpu.shift(4, s.si, 1, 16)  # SHL SI,1 twice.
    expected_offset = tile_contact_offset_table_byte_offset(side)
    if s.si != expected_offset:
        raise AssertionError("pure 4FF9 side-offset index disagrees with ASM-compatible body")

    old_si = s.si
    s.si = (old_si + TILE_CONTACT_OFFSET_TABLE) & 0xFFFF
    cpu.set_add_flags(old_si, TILE_CONTACT_OFFSET_TABLE, old_si + TILE_CONTACT_OFFSET_TABLE, 16)

    cpu.push(mem.rw(ss, (bp + TILE_CONTACT_RECORD_X) & 0xFFFF))
    cpu.push(mem.rw(ss, (bp + TILE_CONTACT_RECORD_Y) & 0xFFFF))

    s.ax = mem.rw(ds, s.si)
    s.si = (s.si + 2) & 0xFFFF
    old = mem.rw(ss, (bp + TILE_CONTACT_RECORD_X) & 0xFFFF)
    result = old + s.ax
    mem.ww(ss, (bp + TILE_CONTACT_RECORD_X) & 0xFFFF, result & 0xFFFF)
    cpu.set_add_flags(old, s.ax, result, 16)

    s.ax = mem.rw(ds, s.si)
    s.si = (s.si + 2) & 0xFFFF
    old = mem.rw(ss, (bp + TILE_CONTACT_RECORD_Y) & 0xFFFF)
    result = old + s.ax
    mem.ww(ss, (bp + TILE_CONTACT_RECORD_Y) & 0xFFFF, result & 0xFFFF)
    cpu.set_add_flags(old, s.ax, result, 16)

    cpu.push(0x501A)
    run_tile_probe_5073_body(cpu, pop_return=True)

    adjusted_x = mem.rw(ds, TILE_PROBE_ADJUSTED_X_SCRATCH)
    adjusted_y = mem.rw(ss, (bp + TILE_CONTACT_RECORD_Y) & 0xFFFF)
    plan = tile_contact_probe_plan_4ff9(
        side_index_word=side,
        adjusted_x_word=adjusted_x,
        y_word=adjusted_y,
    )
    if not plan.valid_side or plan.offset_table_index != side:
        raise AssertionError("pure 4FF9 plan disagrees with side gate")

    old_bx = s.bx & 0xFFFF
    s.bx = (old_bx + TILE_CONTACT_ROW_DELTA) & 0xFFFF
    cpu.set_add_flags(old_bx, TILE_CONTACT_ROW_DELTA, old_bx + TILE_CONTACT_ROW_DELTA, 16)

    s.ax = adjusted_x & TILE_CONTACT_LOW_NIBBLE_MASK
    cpu.set_logic_flags(s.ax, 16)
    cmp_word(cpu, s.ax, TILE_CONTACT_SECOND_COLUMN_THRESHOLD)
    s.cx = 0x0001 if s.ax <= TILE_CONTACT_SECOND_COLUMN_THRESHOLD else 0x0002
    if s.cx != plan.column_sample_count:
        raise AssertionError("pure 4FF9 column sample count disagrees with ASM-compatible body")

    while True:
        cpu.push(s.cx)
        cpu.push(s.bx)
        cpu.push(0x5033)
        run_tile_lookup_505b_body(cpu, pop_return=True)
        if not cpu.get_flag(0x0040):  # JNE 5051 after OR AL,AL in 505B.
            s.bx = cpu.pop()
            s.cx = cpu.pop()
            mem.ww(ss, (bp + TILE_CONTACT_RECORD_Y) & 0xFFFF, cpu.pop())
            mem.ww(ss, (bp + TILE_CONTACT_RECORD_X) & 0xFFFF, cpu.pop())
            cpu.set_flag(CF, True)
            s.ip = cpu.pop()
            return True

        test_value = mem.rw(ss, (bp + TILE_CONTACT_RECORD_Y) & 0xFFFF) & TILE_CONTACT_LOW_NIBBLE_MASK
        cpu.set_logic_flags(test_value, 16)
        probe_adjacent_y = not cpu.get_flag(0x0040)
        if probe_adjacent_y != plan.probe_adjacent_y:
            raise AssertionError("pure 4FF9 adjacent-Y plan disagrees with ASM-compatible body")
        if probe_adjacent_y:
            old_cf = cpu.get_flag(CF)
            old_bx = s.bx & 0xFFFF
            s.bx = (old_bx + 1) & 0xFFFF
            cpu.set_add_flags(old_bx, 1, old_bx + 1, 16)
            cpu.set_flag(CF, old_cf)  # INC preserves CF.
            cpu.push(0x5040)
            run_tile_lookup_505b_body(cpu, pop_return=True)
            if not cpu.get_flag(0x0040):
                s.bx = cpu.pop()
                s.cx = cpu.pop()
                mem.ww(ss, (bp + TILE_CONTACT_RECORD_Y) & 0xFFFF, cpu.pop())
                mem.ww(ss, (bp + TILE_CONTACT_RECORD_X) & 0xFFFF, cpu.pop())
                cpu.set_flag(CF, True)
                s.ip = cpu.pop()
                return True

        s.bx = cpu.pop()
        old_bx = s.bx & 0xFFFF
        s.bx = (old_bx - TILE_CONTACT_ROW_DELTA) & 0xFFFF
        cpu.set_sub_flags(old_bx, TILE_CONTACT_ROW_DELTA, old_bx - TILE_CONTACT_ROW_DELTA, 16)
        s.cx = cpu.pop()
        s.cx = (s.cx - 1) & 0xFFFF  # LOOP does not alter flags.
        if s.cx == 0:
            break

    mem.ww(ss, (bp + TILE_CONTACT_RECORD_Y) & 0xFFFF, cpu.pop())
    mem.ww(ss, (bp + TILE_CONTACT_RECORD_X) & 0xFFFF, cpu.pop())
    cpu.set_flag(CF, False)
    s.ip = cpu.pop()
    return False


def run_tile_collision_probe_ac28_body(cpu) -> bool:
    """Run 1010:AC28 while validating the recovered tile-collision plan.

    AC28 is the ABxx object-behaviour tile collision helper.  The pure tilemap
    layer owns only the sampling shape (row-below sample plus optional adjacent
    Y sample).  This adapter keeps the original global gates, 5073/505B calls,
    object countdown side effects, and carry/continuation semantics.
    """
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF

    cmp_word(cpu, mem.rw(ds, TILE_COLLISION_GLOBAL_GATE), 0)
    if not cpu.get_flag(0x0040):  # JZ not taken -> JMP AA44.
        s.ip = 0xAA44
        return False
    cmp_word(cpu, mem.rw(ds, TILE_COLLISION_DISABLE_GLOBAL), 1)
    if cpu.get_flag(0x0040):  # JNE not taken -> JMP AA44.
        s.ip = 0xAA44
        return False

    cpu.push(0xAC3F)
    run_tile_probe_5073_body(cpu, pop_return=True)

    y_word = mem.rw(ss, (bp + OFF_Y) & 0xFFFF)
    plan = tile_collision_probe_plan_ac28(y_word=y_word)
    if plan.row_delta != TILE_COLLISION_ROW_DELTA:
        raise AssertionError("pure AC28 row-delta plan disagrees with adapter constant")

    old_bx = s.bx & 0xFFFF
    s.bx = (old_bx + TILE_COLLISION_ROW_DELTA) & 0xFFFF
    cpu.set_add_flags(old_bx, TILE_COLLISION_ROW_DELTA, old_bx + TILE_COLLISION_ROW_DELTA, 16)
    cpu.push(0xAC45)
    run_tile_lookup_505b_body(cpu, pop_return=True)
    if not cpu.get_flag(0x0040):  # JNE AC56 after OR AL,AL in 505B.
        collided = True
    else:
        y_low = y_word & 0x000F
        cpu.set_logic_flags(y_low, 16)  # TEST [BP+4],000Fh
        probe_adjacent_y = not cpu.get_flag(0x0040)
        if probe_adjacent_y != plan.probe_adjacent_y:
            raise AssertionError("pure AC28 adjacent-Y plan disagrees with ASM-compatible body")
        if not probe_adjacent_y:
            collided = False
        else:
            old_bx = s.bx & 0xFFFF
            old_cf = cpu.get_flag(CF)
            s.bx = (old_bx + 1) & 0xFFFF
            cpu.set_add_flags(old_bx, 1, old_bx + 1, 16)
            cpu.set_flag(CF, old_cf)  # INC preserves CF.
            cpu.push(0xAC52)
            run_tile_lookup_505b_body(cpu, pop_return=True)
            collided = not cpu.get_flag(0x0040)

    if not collided:
        set_carry_and_return(cpu, False)
        return False

    cmp_byte(cpu, mem.rb(ds, TILE_COLLISION_DEBUG_FLAG), 0)
    if not cpu.get_flag(0x0040):
        mem.wb(ds, TILE_COLLISION_DEBUG_CODE, TILE_COLLISION_DEBUG_BLOCKED_CODE)
    mem.ww(ss, (bp + OFF_VARIANT) & 0xFFFF, TILE_COLLISION_STATE_ON_CONTACT)

    cmp_word(cpu, mem.rw(ds, TILE_COLLISION_BEDC_GATE), 0)
    if cpu.get_flag(0x0040):
        cmp_word(cpu, mem.rw(ds, TILE_COLLISION_ALT_GATE), 1)
        if not cpu.get_flag(0x0040):
            set_carry_and_return(cpu, False)
            return False

    counter_off = (bp + OFF_COUNTER_20) & 0xFFFF
    old = mem.rw(ss, counter_off)
    old_cf = cpu.get_flag(CF)
    result_full = old - 1
    mem.ww(ss, counter_off, result_full & 0xFFFF)
    cpu.set_sub_flags(old, 1, result_full, 16)
    cpu.set_flag(CF, old_cf)  # DEC preserves CF.
    if not cpu.get_flag(0x0040):
        set_carry_and_return(cpu, False)
        return True

    mem.ww(ss, (bp + OFF_VARIANT) & 0xFFFF, TILE_COLLISION_STATE_IDLE)
    set_carry_and_return(cpu, True)
    return True

def run_postmove_contact_window_aa71_body(cpu) -> bool:
    """Run 1010:AA71 while proving the pure post-move contact decision.

    The pure system owns the gameplay predicate.  This adapter replays the
    original instruction-shaped comparisons so AX/FLAGS at the CLC/STC return
    tail remain comparable with the ASM oracle.
    """
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    slot = ObjectSlotView.from_ss_bp(cpu)
    window = PostMoveContactWindow(
        view_x_word=mem.rw(ds, POSTMOVE_CONTACT_VIEW_X),
        y_guard_word=mem.rw(ds, POSTMOVE_CONTACT_Y_GUARD),
        final_boss_narrow_x=mem.rw(ds, FINAL_BOSS_CONTACT_MODE) == 0x0001,
    )
    pure_hit = postmove_contact_window_test_aa71(read_object_slot_record(slot), window).hit

    x = slot.x_word
    s.ax = x
    cpu.set_logic_flags(x, 16)  # OR AX,AX
    if i16(x) < 0:
        if pure_hit:
            raise AssertionError("pure AA71 contact result disagrees on negative-X escape")
        set_carry_and_return(cpu, False)
        return False

    y = slot.y_word
    y_guard = window.y_guard_word
    upper_y = (y + POSTMOVE_CONTACT_Y_UPPER_BIAS) & 0xFFFF
    s.ax = upper_y
    cpu.set_add_flags(y, POSTMOVE_CONTACT_Y_UPPER_BIAS, y + POSTMOVE_CONTACT_Y_UPPER_BIAS, 16)
    cmp_word(cpu, upper_y, y_guard)
    if i16(upper_y) < i16(y_guard):
        if pure_hit:
            raise AssertionError("pure AA71 contact result disagrees on Y upper branch")
        set_carry_and_return(cpu, False)
        return False

    lower_y = (upper_y - POSTMOVE_CONTACT_Y_SPAN) & 0xFFFF
    s.ax = lower_y
    cpu.set_sub_flags(upper_y, POSTMOVE_CONTACT_Y_SPAN, upper_y - POSTMOVE_CONTACT_Y_SPAN, 16)
    cmp_word(cpu, lower_y, y_guard)
    if i16(lower_y) > i16(y_guard):
        if pure_hit:
            raise AssertionError("pure AA71 contact result disagrees on Y lower branch")
        set_carry_and_return(cpu, False)
        return False

    mode = mem.rw(ds, FINAL_BOSS_CONTACT_MODE)
    cmp_word(cpu, mode, 0x0001)
    if window.final_boss_narrow_x:
        upper_bias = POSTMOVE_CONTACT_X_BOSS_UPPER_BIAS
        span = POSTMOVE_CONTACT_X_BOSS_SPAN
    else:
        upper_bias = POSTMOVE_CONTACT_X_NORMAL_UPPER_BIAS
        span = POSTMOVE_CONTACT_X_NORMAL_SPAN

    view_x = window.view_x_word
    upper_x = (x + upper_bias) & 0xFFFF
    s.ax = upper_x
    cpu.set_add_flags(x, upper_bias, x + upper_bias, 16)
    cmp_word(cpu, upper_x, view_x)
    if upper_x < view_x:  # JB AA44, unsigned compare.
        if pure_hit:
            raise AssertionError("pure AA71 contact result disagrees on X upper branch")
        set_carry_and_return(cpu, False)
        return False

    lower_x = (upper_x - span) & 0xFFFF
    s.ax = lower_x
    cpu.set_sub_flags(upper_x, span, upper_x - span, 16)
    cmp_word(cpu, lower_x, view_x)
    if lower_x > view_x:  # JA AA44, unsigned compare.
        if pure_hit:
            raise AssertionError("pure AA71 contact result disagrees on X lower branch")
        set_carry_and_return(cpu, False)
        return False

    if not pure_hit:
        raise AssertionError("pure AA71 contact result disagrees on hit path")
    set_carry_and_return(cpu, True)
    return True


def run_view_window_check_aa46_body(cpu) -> bool:
    """Run AA46's view-offset contact-center projection plus 8331 test.

    AA46 is reached from BC4B/BCCB for object-type-1 contact handling.  It is
    not a new gameplay predicate: it projects a DS:214E dx/dy pair from the live
    view globals into DS:95F2/95F4 and then reuses the same signed +/-16 object
    rectangle test as 8331.  Keep that projection and the rectangle compare in
    one adapter so BCCB no longer carries a second hand-written copy.
    """
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    slot = ObjectSlotView.from_ss_bp(cpu)

    s.ax = slot.x_word
    cpu.set_logic_flags(s.ax, 16)  # OR AX,AX
    if s.ax & 0x8000:
        cpu.set_flag(CF, False)  # 835B CLC on this observed out-of-window exit.
        return False

    s.si = mem.rw(ds, VIEW_WINDOW_SIDE_SELECTOR)
    cmp_word(cpu, s.si, TILE_CONTACT_SIDE_COUNT)
    # AA54 JAE 0xAA44: a side-selector of 3 or more falls straight through to the
    # CLC;RET no-contact exit (AA44) -- the original NEVER indexes the 3-entry
    # DS:214E offset table past its bounds.  Omitting this branch made the port
    # read garbage at DS:[214E + si*4] for si>=3 (e.g. DS:215A), write a bogus
    # DS:95F2/95F4 centre and fabricate an 8331 contact hit, which spuriously
    # killed in-window effect objects once the view side-selector reached 3.
    if (s.si & 0xFFFF) >= TILE_CONTACT_SIDE_COUNT:
        cpu.set_flag(CF, False)
        return False
    old_si = s.si
    s.si = (s.si << 1) & 0xFFFF
    cpu.set_add_flags(old_si, old_si, old_si + old_si, 16)  # SHL-by-1 flag shape approximation.
    old_si = s.si
    s.si = (s.si << 1) & 0xFFFF
    cpu.set_add_flags(old_si, old_si, old_si + old_si, 16)
    old_si = s.si
    s.si = (s.si + TILE_CONTACT_OFFSET_TABLE) & 0xFFFF
    cpu.set_add_flags(old_si, TILE_CONTACT_OFFSET_TABLE, old_si + TILE_CONTACT_OFFSET_TABLE, 16)

    offset_x = mem.rw(ds, s.si)
    s.ax = offset_x
    s.si = (s.si + 2) & 0xFFFF
    old_ax = s.ax
    view_x = mem.rw(ds, POSTMOVE_CONTACT_VIEW_X)
    s.ax = (s.ax + view_x) & 0xFFFF
    cpu.set_add_flags(old_ax, view_x, old_ax + view_x, 16)
    mem.ww(ds, VIEW_CONTACT_CENTER_X, s.ax)

    offset_y = mem.rw(ds, s.si)
    s.ax = offset_y
    s.si = (s.si + 2) & 0xFFFF
    old_ax = s.ax
    view_y = mem.rw(ds, POSTMOVE_CONTACT_Y_GUARD)
    s.ax = (s.ax + view_y) & 0xFFFF
    cpu.set_add_flags(old_ax, view_y, old_ax + view_y, 16)
    mem.ww(ds, VIEW_CONTACT_CENTER_Y, s.ax)

    pure_center = view_contact_center_from_offsets_aa46(
        view_x_word=view_x,
        view_y_word=view_y,
        offset_x_word=offset_x,
        offset_y_word=offset_y,
    )
    if (mem.rw(ds, VIEW_CONTACT_CENTER_X), mem.rw(ds, VIEW_CONTACT_CENTER_Y)) != (
        pure_center.x_word,
        pure_center.y_word,
    ):
        raise AssertionError("pure AA46 contact-center projection disagrees with ASM-compatible writes")

    hit = run_signed_center_rect_test_8331(
        cpu,
        slot,
        center_x=pure_center.x_word,
        center_y=pure_center.y_word,
    )
    cpu.set_flag(CF, hit)
    return hit

def mark_tile_sweep_blocked(cpu) -> None:
    """Recovered from 1010:B032: set the raw B00D tile-sweep blocked flag."""
    cpu.mem.ww(cpu.s.ds & 0xFFFF, TILE_SWEEP_BLOCKED_FLAG, 0x0001)


def view_contact_centers(cpu) -> tuple[int, int]:
    """Return the prepared DS:95F2/95F4 rectangle center words."""
    ds = cpu.s.ds & 0xFFFF
    return cpu.mem.rw(ds, VIEW_CONTACT_CENTER_X), cpu.mem.rw(ds, VIEW_CONTACT_CENTER_Y)


def read_view_contact_center(cpu) -> ViewContactCenter:
    """Copy the DOS contact center globals into a pure domain record."""
    x_word, y_word = view_contact_centers(cpu)
    return ViewContactCenter(x_word=x_word, y_word=y_word)


def run_signed_center_rect_test_8331(
    cpu,
    slot: ObjectSlotView,
    *,
    center_x: int,
    center_y: int,
    half_extent: int = CONTACT_HALF_EXTENT,
) -> bool:
    """Run 1010:8331 with exact SI/FLAGS while validating the pure system.

    The pure recovered system computes the portable gameplay result from copied
    domain records.  This adapter then performs the original instruction-shaped
    compare sequence so hook verification still sees the exact flags and SI at
    the return tail.
    """
    pure = view_contact_rect_test(
        read_object_slot_record(slot),
        ViewContactCenter(center_x & 0xFFFF, center_y & 0xFFFF),
        half_extent=half_extent,
    ).hit

    cpu.s.si = center_x & 0xFFFF
    add_word_to_si(cpu, half_extent)
    x = slot.x_word
    cmp_word(cpu, x, cpu.s.si)
    if i16(x) > i16(cpu.s.si):
        if pure:
            raise AssertionError("pure 8331 result disagrees with ASM-compatible X upper branch")
        return False

    sub_word_from_si(cpu, half_extent * 2)
    cmp_word(cpu, x, cpu.s.si)
    if i16(x) < i16(cpu.s.si):
        if pure:
            raise AssertionError("pure 8331 result disagrees with ASM-compatible X lower branch")
        return False

    cpu.s.si = center_y & 0xFFFF
    add_word_to_si(cpu, half_extent)
    y = slot.y_word
    cmp_word(cpu, y, cpu.s.si)
    if i16(y) > i16(cpu.s.si):
        if pure:
            raise AssertionError("pure 8331 result disagrees with ASM-compatible Y upper branch")
        return False

    sub_word_from_si(cpu, half_extent * 2)
    cmp_word(cpu, y, cpu.s.si)
    if i16(y) < i16(cpu.s.si):
        if pure:
            raise AssertionError("pure 8331 result disagrees with ASM-compatible Y lower branch")
        return False

    if not pure:
        raise AssertionError("pure 8331 result disagrees with ASM-compatible hit path")
    return True




def run_slot_probe_window_compare_sequence(
    cpu,
    *,
    slot: ObjectSlotView,
    probe_x: int,
    probe_y: int,
    half_extent: int,
    include_edges: bool,
    pure_hit: bool,
    label: str,
    miss_return,
):
    """Replay the shared object-centered +/- window compare sequence.

    BDE3 and AC97 both test a probe point against the current candidate
    slot's centered X/Y window using the same SI choreography:

    ``SI = slot.x + half; CMP probe_x, SI; SI -= half*2; CMP ...``

    The only semantic difference is edge handling.  BDE3 is strict
    (``lower < probe < upper``), while AC97 is inclusive
    (``lower <= probe <= upper``).  Keep this one adapter helper so the
    exact flag/SI-producing sequence has a single source, and let the pure
    systems own the portable hit decision.
    """

    def reject_upper(value: int, upper: int) -> bool:
        if include_edges:
            return i16(value) > i16(upper)
        return i16(value) >= i16(upper)

    def reject_lower(value: int, lower: int) -> bool:
        if include_edges:
            return i16(value) < i16(lower)
        return i16(value) <= i16(lower)

    def fail(branch: str):
        if pure_hit:
            raise AssertionError(f"pure {label} result disagrees on {branch}")
        return miss_return()

    si0 = slot.x_word
    si = (si0 + half_extent) & 0xFFFF
    cpu.s.si = si
    cpu.set_add_flags(si0, half_extent, si0 + half_extent, 16)
    cmp_word(cpu, probe_x, si)
    if reject_upper(probe_x, si):
        return False, fail("X upper bound")

    si_before = si
    si = (si - half_extent * 2) & 0xFFFF
    cpu.s.si = si
    cpu.set_sub_flags(si_before, half_extent * 2, si_before - half_extent * 2, 16)
    cmp_word(cpu, probe_x, si)
    if reject_lower(probe_x, si):
        return False, fail("X lower bound")

    si0 = slot.y_word
    si = (si0 + half_extent) & 0xFFFF
    cpu.s.si = si
    cpu.set_add_flags(si0, half_extent, si0 + half_extent, 16)
    cmp_word(cpu, probe_y, si)
    if reject_upper(probe_y, si):
        return False, fail("Y upper bound")

    si_before = si
    si = (si - half_extent * 2) & 0xFFFF
    cpu.s.si = si
    cpu.set_sub_flags(si_before, half_extent * 2, si_before - half_extent * 2, 16)
    cmp_word(cpu, probe_y, si)
    if reject_lower(probe_y, si):
        return False, fail("Y lower bound")

    return True, None

def run_player_hazard_candidate_checks_bde3(
    cpu,
    *,
    current_record,
    slot,
    probe_x: int,
    probe_y: int,
    half_extent: int = CONTACT_HALF_EXTENT,
) -> bool:
    """Run one BDE3 object candidate check with exact ASM flags.

    The portable decision is computed by
    ``systems.collision.player_hazard_scan_hit``.  This adapter then performs
    the original compare sequence so hook verification still observes the same
    flags/SI at every skip or hit boundary.  The caller owns BX/CX advancement
    and the final jump/RET continuation.
    """
    slot_record = read_object_slot_record(slot)
    pure_hit = player_hazard_scan_hit(
        current_record,
        slot_record,
        ProbePoint(x_word=probe_x & 0xFFFF, y_word=probe_y & 0xFFFF),
        half_extent=half_extent,
    )

    value = slot.active_word
    cmp_word(cpu, value, 0)
    if value == 0:
        if pure_hit:
            raise AssertionError("pure BDE3 hazard result disagrees on active-word gate")
        return False

    value = slot.gate_or_layer
    cmp_word(cpu, value, PLAYER_HAZARD_SCAN_REQUIRED_GATE)
    if value == PLAYER_HAZARD_SCAN_REQUIRED_GATE:
        if pure_hit:
            raise AssertionError("pure BDE3 hazard result disagrees on gate/layer rejection")
        return False

    value = slot.scan_flag
    cmp_word(cpu, value, PLAYER_HAZARD_SCAN_REQUIRED_FLAG)
    if value != PLAYER_HAZARD_SCAN_REQUIRED_FLAG:
        if pure_hit:
            raise AssertionError("pure BDE3 hazard result disagrees on scan-flag gate")
        return False

    value = slot.hazard_class
    cmp_word(cpu, value, PLAYER_HAZARD_SCAN_REQUIRED_CLASS)
    if value != PLAYER_HAZARD_SCAN_REQUIRED_CLASS:
        if pure_hit:
            raise AssertionError("pure BDE3 hazard result disagrees on hazard-class gate")
        return False

    obj_id = slot.logic_id
    cmp_word(cpu, obj_id, PLAYER_HAZARD_LOGIC_MIN)
    if obj_id < PLAYER_HAZARD_LOGIC_MIN:
        if pure_hit:
            raise AssertionError("pure BDE3 hazard result disagrees on logic-id lower gate")
        return False

    cmp_word(cpu, obj_id, PLAYER_HAZARD_LOGIC_MAX)
    if obj_id > PLAYER_HAZARD_LOGIC_MAX:
        if pure_hit:
            raise AssertionError("pure BDE3 hazard result disagrees on logic-id upper gate")
        return False

    inside_window, miss_value = run_slot_probe_window_compare_sequence(
        cpu,
        slot=slot,
        probe_x=probe_x,
        probe_y=probe_y,
        half_extent=half_extent,
        include_edges=False,
        pure_hit=pure_hit,
        label="BDE3 hazard",
        miss_return=lambda: False,
    )
    if not inside_window:
        return miss_value

    si = current_record.link_key
    cpu.s.si = si
    other = slot.link_key
    cmp_word(cpu, si, other)
    hit = si != other
    if pure_hit != hit:
        raise AssertionError("pure BDE3 hazard result disagrees on link-key gate")
    return hit



def run_object_overlap_candidate_checks_ac97(
    cpu,
    *,
    current_record,
    slot,
    probe_x: int,
    probe_y: int,
    half_extent: int = CONTACT_HALF_EXTENT,
):
    """Run one AC97 object-overlap candidate check with exact ASM flags.

    Returns ``(overlaps, actionable, acd9_entry_flags)``.  ``overlaps`` means
    the ASM-compatible path reached the ACD9 decision after the link-key CMP.
    ``actionable`` means the recovered type-4/type-5 family should stop at the
    ACD9 continuation.  The caller owns BX/CX advancement, near-return handling,
    and whether non-actionable overlaps are absorbed by the lifted ACD9->ACD2
    continue tail.
    """
    slot_record = read_object_slot_record(slot)
    pure = object_overlap_scan_decision(
        current_record,
        slot_record,
        ProbePoint(x_word=probe_x & 0xFFFF, y_word=probe_y & 0xFFFF),
        half_extent=half_extent,
    )

    value = slot.active_word
    cmp_word(cpu, value, 0)
    if value == 0:
        if pure.overlaps:
            raise AssertionError("pure AC97 overlap result disagrees on active-word gate")
        return False, False, cpu.s.flags

    value = slot.logic_id
    cmp_word(cpu, value, OBJECT_OVERLAP_INACTIVE_LOGIC_ID)
    if value == OBJECT_OVERLAP_INACTIVE_LOGIC_ID:
        if pure.overlaps:
            raise AssertionError("pure AC97 overlap result disagrees on logic-id gate")
        return False, False, cpu.s.flags

    value = slot.scan_flag
    cmp_word(cpu, value, OBJECT_OVERLAP_SCAN_REQUIRED_FLAG)
    if value != OBJECT_OVERLAP_SCAN_REQUIRED_FLAG:
        if pure.overlaps:
            raise AssertionError("pure AC97 overlap result disagrees on scan-flag gate")
        return False, False, cpu.s.flags

    inside_window, miss_value = run_slot_probe_window_compare_sequence(
        cpu,
        slot=slot,
        probe_x=probe_x,
        probe_y=probe_y,
        half_extent=half_extent,
        include_edges=True,
        pure_hit=pure.overlaps,
        label="AC97 overlap",
        miss_return=lambda: (False, False, cpu.s.flags),
    )
    if not inside_window:
        return miss_value

    si = current_record.link_key
    cpu.s.si = si
    other = slot.link_key
    cmp_word(cpu, si, other)
    acd9_entry_flags = cpu.s.flags
    overlaps = si != other
    if pure.overlaps != overlaps:
        raise AssertionError("pure AC97 overlap result disagrees on link-key gate")
    if not overlaps:
        return False, False, acd9_entry_flags

    kind_16 = slot.hazard_class
    cmp_word(cpu, kind_16, 0x0005)
    if kind_16 == 0x0005:
        if not pure.actionable:
            raise AssertionError("pure AC97 overlap result disagrees on class-5 action")
        return True, True, acd9_entry_flags

    value = slot.scan_flag
    cmp_word(cpu, value, OBJECT_OVERLAP_SCAN_REQUIRED_FLAG)
    if value != OBJECT_OVERLAP_SCAN_REQUIRED_FLAG:
        # This branch is not expected after the earlier gate for a stable slot,
        # but the original ACD9 tail can still return immediately here.  Keep
        # the ASM-visible comparison for fidelity and report it as a
        # non-actionable overlap to the caller.
        if pure.actionable:
            raise AssertionError("pure AC97 overlap result disagrees on ACD9 scan-flag recheck")
        return True, False, acd9_entry_flags

    cmp_word(cpu, kind_16, 0x0004)
    if kind_16 == 0x0004:
        if not pure.actionable:
            raise AssertionError("pure AC97 overlap result disagrees on class-4 action")
        return True, True, acd9_entry_flags

    if pure.actionable:
        raise AssertionError("pure AC97 overlap result disagrees on non-actionable class")
    return True, False, acd9_entry_flags
