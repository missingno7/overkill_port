"""Object allocation and spawn-stamping for the OVERKILL object runtime.

Architecture layer: **lifted** (see ``ARCHITECTURE.md``).  This is the slot
allocation + spawn-stamping seam carved out of ``object_runtime.py``: find a
free effect/object slot, reclaim the oldest, and stamp the new record's
fields.  These routines are self-contained — they call no other object-runtime
function and only touch the active object table through the proven slot-field
offsets — so they form a clean, independently testable module.  Conservative
names only: ``object slot``, ``spawn``, ``effect``, ``formation`` are evidenced;
no higher-level gameplay semantics are asserted.
"""
from __future__ import annotations

from overkill.asm import _add_reg16, _cmp_word, _dec_mem_word_preserve_cf
from overkill.recovered.systems.objects import (
    object_spawn_seed_7420,
    object_spawn_seed_8209,
    object_spawn_seed_a4ea,
)
from overkill.recovered.views.object_slots import ObjectSlotView, EFFECT_OBJECT_TABLE_BASE, GAMEPLAY_OBJECT_ALLOCATOR_WRAP_SENTINEL, GAMEPLAY_OBJECT_TABLE_BASE, OBJECT_SLOT_STRIDE, OFF_X, OFF_Y

# Source position the 8209 template reads from the caller's BP frame.  The slot's
# linked-counter index (offset 0x28) uses the canonical OFF_LINKED_COUNTER_INDEX.
OBJECT_SPAWN_SEED_8209_SOURCE_X_BP = 0x02
OBJECT_SPAWN_SEED_8209_SOURCE_Y_BP = 0x04


def run_object_spawn_seed_8209(cpu) -> None:
    """Lift 1010:8209, the shared object-slot spawn-stamp template.

    Reached from both sibling allocate-then-stamp paths (``81E9`` jumps here, and
    the ``81F4`` debug-gated path falls through).  ``BX`` is the freshly allocated
    DS-relative slot; the caller's source position is at ``SS:[BP+2]``/``[BP+4]``.
    The pure :func:`object_spawn_seed_8209` owns the field values; this adapter
    owns the DOS slot pointer and write order, leaves ``AX`` = source Y like the
    original's final ``MOV``, and near-returns.
    """
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF
    bx = s.bx & 0xFFFF

    source_x = mem.rw(ss, (bp + OBJECT_SPAWN_SEED_8209_SOURCE_X_BP) & 0xFFFF)
    source_y = mem.rw(ss, (bp + OBJECT_SPAWN_SEED_8209_SOURCE_Y_BP) & 0xFFFF)
    seed = object_spawn_seed_8209(source_x, source_y)

    # Stamp in the original 8209..8247 order (offsets distinct, so order is only
    # for faithfulness).
    slot = ObjectSlotView(mem, ds, bx)  # the spawned object's record (DS:BX)
    slot.linked_counter_index = seed.linked_counter_index
    slot.active_word = seed.active_word
    slot.gate_or_layer = seed.gate_or_layer
    slot.x_word = seed.x_word
    slot.target_x_word = seed.target_x_word
    slot.y_word = seed.y_word
    slot.target_y_word = seed.target_y_word
    slot.direction_or_step = seed.direction_or_step
    slot.scan_flag = seed.scan_flag
    slot.hazard_class = seed.hazard_class
    slot.logic_id = seed.logic_id
    slot.counter_20 = seed.counter_20
    slot.variant = seed.variant
    s.ax = source_y & 0xFFFF
    s.ip = cpu.pop()


def _find_free_effect_slot_7524(cpu) -> int:
    """Mirror the small 1010:7524 allocator used by the BFC7 linked effect.

    It scans from DS:[95D8] through the compact 38h-byte object records before
    the main 2B5C object pool, stores the found slot back to DS:[95D8], and
    leaves BX/CX/flags as the original allocator.
    """
    ds = cpu.s.ds & 0xFFFF
    mem = cpu.mem
    cpu.s.cx = 0x0023
    cpu.s.bx = mem.rw(ds, 0x95D8)
    while True:
        bx = cpu.s.bx & 0xFFFF
        cand = ObjectSlotView(mem, ds, bx)  # candidate slot being scanned
        _cmp_word(cpu, cand.active_word, 0x0000)
        if cand.active_word == 0:
            mem.ww(ds, 0x95D8, bx)
            return bx
        _add_reg16(cpu, 3, OBJECT_SLOT_STRIDE)
        _cmp_word(cpu, cpu.s.bx, GAMEPLAY_OBJECT_TABLE_BASE)
        if cpu.s.bx == GAMEPLAY_OBJECT_TABLE_BASE:
            cpu.s.bx = EFFECT_OBJECT_TABLE_BASE
        old_cx = cpu.s.cx
        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF
        if cpu.s.cx == 0:
            cpu.s.bx = 0xFFFF
            return 0xFFFF


def _find_free_object_slot_7573(cpu) -> int:
    """Mirror the original 1010:7573 object-slot allocator.

    The loop target in the ASM is 757A, not 7583, so the sentinel/wrap check is
    repeated on every scan iteration.  A lifted version that only wrapped once
    before the loop could let DS:[95DA] advance past 32CC into Tandy draw
    scratch space; the next projectile allocation would then overlap the sprite
    buffer and vanish on the following draw pass.
    """
    ds = cpu.s.ds & 0xFFFF
    bx = cpu.mem.rw(ds, 0x95DA)
    cx = 0x0022
    while cx:
        # The wrap-sentinel CMP's flags are dead (the active_word CMP below
        # overwrites them before any boundary).
        if bx == GAMEPLAY_OBJECT_ALLOCATOR_WRAP_SENTINEL:
            bx = GAMEPLAY_OBJECT_TABLE_BASE
        cand = ObjectSlotView(cpu.mem, ds, bx)  # candidate slot being scanned
        value = cand.active_word
        _cmp_word(cpu, value, 0)
        if value == 0:
            cpu.mem.ww(ds, 0x95DA, bx)
            cpu.s.bx = bx
            cpu.s.cx = cx
            return bx
        old_bx = bx
        bx = (bx + OBJECT_SLOT_STRIDE) & 0xFFFF
        cpu.set_add_flags(old_bx, OBJECT_SLOT_STRIDE, old_bx + OBJECT_SLOT_STRIDE, 16)
        cx = (cx - 1) & 0xFFFF
    cpu.s.bx = 0xFFFF
    cpu.s.cx = 0
    return 0xFFFF


def _run_c054_c12d_effect_spawn_tail(cpu, *, object_bp: int, selector_ax: int) -> None:
    """Mirror the C054:C12D linked-effect tail used by BD17 and BFC7.

    The 7Eh/7Dh/1Fh/1Ch/15h/13h selector family does more than choose AX:
    C12D publishes the selected script, pushes BX/BP below the live C054 return
    frame, CALLs 7420, then decrements DS:A47E.  Full-memory hook verification
    observes the freed stack scratch, so this helper deliberately models the
    nested CALL frames instead of treating the effect spawn as a pure function.
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    mem = cpu.mem
    bp = object_bp & 0xFFFF
    slot = ObjectSlotView(mem, ss, bp)  # the linked object's record (SS:BP)

    mem.ww(ds, 0xA482, selector_ax & 0xFFFF)
    mem.ww(ds, 0xA842, 0xA844)

    cpu.push(cpu.s.bx)
    cpu.push(cpu.s.bp)
    mem.ww(ds, 0x2376, slot.y_word)
    mem.ww(ds, 0x2378, slot.x_word)
    cpu.s.ax = 0x0002
    mem.ww(ds, 0x237A, cpu.s.ax)

    call_7420_sp = cpu.s.sp & 0xFFFF
    cpu.push(0xC14D)
    cpu.push(0x7423)
    _run_linked_effect_spawn_7420_observed(cpu)

    # Simulate the RETs from 7420/C12D while preserving the scratch words below
    # final SP for the full-memory verifier.
    cpu.s.sp = call_7420_sp
    cpu.s.bp = cpu.pop()
    cpu.s.bx = cpu.pop()
    _dec_mem_word_preserve_cf(cpu, ds, 0xA47E)


def _run_formation_spawn_7476_observed(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Run observed B800 -> 7476 helper that spawns a formation child object."""
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    slot = ObjectSlotView(cpu.mem, ss, bp)  # this object's record (SS:BP)
    mem = cpu.mem

    bx = _find_free_object_slot_7573(cpu)
    _cmp_word(cpu, cpu.s.bx, 0xFFFF)
    if bx == 0xFFFF:
        return
    if mem.rb(ds, 0x98C0) != 0:
        mem.wb(ds, 0xBEFF, 0x1A)

    cpu.s.cx = 0x000C
    cpu.s.dx = 0x000C
    _cmp_word(cpu, mem.rw(ds, 0xA8C2), 0x0001)
    if mem.rw(ds, 0xA8C2) == 0x0001:
        cpu.s.cx = 0x001C
        cpu.s.dx = 0x0008

    cpu.s.ax = slot.y_word
    old_ax = cpu.s.ax
    cpu.s.ax = (cpu.s.ax + cpu.s.cx) & 0xFFFF
    cpu.set_add_flags(old_ax, cpu.s.cx, old_ax + cpu.s.cx, 16)
    dst = ObjectSlotView(mem, ds, bx)  # the spawned/target object's record (DS:BX)
    dst.y_word = cpu.s.ax
    cpu.s.ax = slot.x_word
    old_ax = cpu.s.ax
    cpu.s.ax = (cpu.s.ax + cpu.s.dx) & 0xFFFF
    cpu.set_add_flags(old_ax, cpu.s.dx, old_ax + cpu.s.dx, 16)
    dst.x_word = cpu.s.ax

    dst.active_word = 0x0001
    dst.scan_enable_or_solid = 0x0000
    dst.direction_or_step = 0x0000
    dst.sprite_or_state = 0x0031
    dst.gate_or_layer = 0x0001
    dst.scan_flag = 0x0000
    dst.hazard_class = 0x0002
    dst.logic_id = 0x000B
    dst.substate = 0xFFFF

    cpu.s.ax = dst.y_word
    cpu.s.cx = (mem.rw(ds, 0x2380) + 0x0009) & 0xFFFF
    cpu.set_add_flags(mem.rw(ds, 0x2380), 0x0009, mem.rw(ds, 0x2380) + 0x0009, 16)
    old_ax = cpu.s.ax
    cpu.s.ax = (cpu.s.ax - cpu.s.cx) & 0xFFFF
    cpu.set_sub_flags(old_ax, cpu.s.cx, old_ax - cpu.s.cx, 16)
    dst.move_delta_y = cpu.s.ax
    cpu.s.ax = dst.x_word
    cpu.s.cx = mem.rw(ds, 0x237E)
    old_ax = cpu.s.ax
    cpu.s.ax = (cpu.s.ax - cpu.s.cx) & 0xFFFF
    cpu.set_sub_flags(old_ax, cpu.s.cx, old_ax - cpu.s.cx, 16)
    dst.move_delta_x = cpu.s.ax


def _run_linked_effect_spawn_7420_observed(cpu) -> None:
    """Run the 1010:7420 linked-effect spawn used by BFC7/BFEE.

    When a linked-counter group's last member dies, 7420 allocates a compact effect
    slot via 7524 and seeds a short-lived visual object at the staged source position
    (DS:2376 Y / 2378 X / 237A type) plus the scroll offset DS:A278.  The pure
    :func:`object_spawn_seed_7420` owns the field values (X = 2378 + A278, Y = 2376
    clamped to 00C0h, sprite = 237A + 46h, the raw type also at +26h); this adapter
    owns the 7524 allocation, the DOS write order, and the register/flag
    choreography -- the y-clamp ``CMP`` and the ``si += 46h`` ``ADD`` (the x-add flags
    are dead, overwritten by the clamp), leaving AX = Y and SI = sprite as 7420 does.
    """
    ds = cpu.s.ds & 0xFFFF
    mem = cpu.mem

    bx = _find_free_effect_slot_7524(cpu)
    _cmp_word(cpu, cpu.s.bx, 0xFFFF)
    if bx == 0xFFFF:
        return

    seed = object_spawn_seed_7420(
        source_x=mem.rw(ds, 0x2378),
        source_y=mem.rw(ds, 0x2376),
        source_type=mem.rw(ds, 0x237A),
        x_offset=mem.rw(ds, 0xA278),
    )

    dst = ObjectSlotView(mem, ds, bx)  # the spawned effect's record (DS:BX)
    dst.active_word = seed.active_word
    cpu.s.ax = seed.x_word
    dst.x_word = cpu.s.ax

    # Re-run the y-clamp CMP for its (live-shaped) flags; the result is seed.y_word.
    cpu.s.ax = mem.rw(ds, 0x2376)
    _cmp_word(cpu, cpu.s.ax, 0x00C0)
    cpu.s.ax = seed.y_word
    dst.y_word = cpu.s.ax

    dst.transition_latch = seed.transition_latch
    dst.scan_flag = seed.scan_flag
    dst.hazard_class = seed.hazard_class
    dst.logic_id = seed.logic_id
    dst.linked_counter_index = seed.linked_counter_index
    dst.variant = seed.variant

    cpu.s.si = mem.rw(ds, 0x237A)
    mem.ww(ds, (bx + 0x26) & 0xFFFF, seed.slot_field_26)
    _add_reg16(cpu, 6, 0x0046)  # SI += 46h -> SI = seed.sprite_or_state (register-faithful)
    dst.sprite_or_state = seed.sprite_or_state
    dst.gate_or_layer = seed.gate_or_layer


def run_object_slot_allocate_or_reclaim_7547(cpu) -> None:
    """Lift the hot 1010:7547 object-slot allocation gate.

    The common path is a thin wrapper around 7573: allocate a free 38h-byte
    gameplay object slot, compare BX against FFFFh, and return if a slot exists.
    If the pool is exhausted, the original falls through to 7550 and eventually
    jumps through BD0D to reclaim/deactivate a candidate object.  Keep that rare
    fallback as original code for now, but make it an explicit continuation
    instead of burning the hot allocation path as unknown ASM.
    """
    bx = _find_free_object_slot_7573(cpu)
    _cmp_word(cpu, bx, 0xFFFF)
    if bx != 0xFFFF:
        cpu.s.ip = cpu.pop()
        return
    cpu.s.ip = 0x7550


def run_object_spawn_anchor_offset_a571(cpu) -> None:
    """Lift 1010:A571, copying a source slot center+offset into a spawned slot.

    BP points at the source object/anchor slot and BX points at the destination
    object slot.  The routine writes destination Y/X from source Y/X plus ten
    pixels.  This is still raw slot seeding, not a semantic enemy/projectile
    constructor.
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    mem = cpu.mem
    bp = cpu.s.bp & 0xFFFF
    slot = ObjectSlotView(cpu.mem, ss, bp)  # this object's record (SS:BP)
    bx = cpu.s.bx & 0xFFFF

    # Dest Y = source Y + 0x0A.  The ADD's flags are dead (the X ADD below
    # overwrites them; only that one's flags reach the RET).
    cpu.s.ax = (slot.y_word + 0x000A) & 0xFFFF
    dst = ObjectSlotView(mem, ds, bx)  # the spawned/target object's record (DS:BX)
    dst.y_word = cpu.s.ax

    ax = slot.x_word
    result = ax + 0x000A
    ax = result & 0xFFFF
    cpu.s.ax = ax
    cpu.set_add_flags((result - 0x000A) & 0xFFFF, 0x000A, result, 16)
    dst.x_word = ax
    cpu.s.ip = cpu.pop()


def _stamp_object_spawn_seed_a4ea(dst: ObjectSlotView) -> None:
    """Stamp the pure A4EA spawn template (:func:`object_spawn_seed_a4ea`) into an
    already-allocated slot view.  Shared by the A4EA and A4D7 lifts, which stamp
    the identical constant field block before any per-call customisation."""
    seed = object_spawn_seed_a4ea()
    dst.active_word = seed.active_word
    dst.scan_enable_or_solid = seed.scan_enable_or_solid
    dst.direction_or_step = seed.direction_or_step
    dst.sprite_or_state = seed.sprite_or_state
    dst.scan_flag = seed.scan_flag
    dst.hazard_class = seed.hazard_class
    dst.logic_id = seed.logic_id
    dst.substate = seed.substate


def run_object_spawn_seed_a4ea(cpu) -> None:
    """Lift the common 1010:A4EA object-spawn seed template.

    This routine allocates/reclaims a gameplay object slot through 7547 and then
    seeds the common active/runtime fields.  It is still a raw object-slot seed,
    not a semantic enemy/projectile constructor.
    """
    bx = _find_free_object_slot_7573(cpu)
    _cmp_word(cpu, bx, 0xFFFF)
    if bx == 0xFFFF:
        # Original A4EA reached 7550 via CALL 7547, which pushes the live A4ED
        # return word (the inner CALL 7573's 754A return was dead scratch below
        # SP, no longer modelled).
        cpu.push(0xA4ED)
        cpu.s.ip = 0x7550
        return

    ds = cpu.s.ds & 0xFFFF
    mem = cpu.mem
    dst = ObjectSlotView(mem, ds, bx)  # the spawned/target object's record (DS:BX)
    _stamp_object_spawn_seed_a4ea(dst)
    cpu.s.ip = cpu.pop()


def run_object_spawn_seed_from_source_a4d7(cpu) -> None:
    """Lift 1010:A4D7: A4EA seed plus source-coordinate copy.

    SI points at a two-word source coordinate pair.  The spawned object receives
    X from [SI+2] and Y from [SI+4]+4 after the common A4EA seed.
    """
    bx = _find_free_object_slot_7573(cpu)
    _cmp_word(cpu, bx, 0xFFFF)
    if bx == 0xFFFF:
        # Original A4D7 reached 7550 via CALL A4EA (pushes A4DA) → CALL 7547
        # (pushes A4ED); both are live return words.  The inner CALL 7573's 754A
        # return was dead scratch below SP, no longer modelled.
        cpu.push(0xA4DA)
        cpu.push(0xA4ED)
        cpu.s.ip = 0x7550
        return

    ds = cpu.s.ds & 0xFFFF
    mem = cpu.mem
    dst = ObjectSlotView(mem, ds, bx)  # the spawned/target object's record (DS:BX)
    _stamp_object_spawn_seed_a4ea(dst)

    si = cpu.s.si & 0xFFFF
    cpu.s.ax = mem.rw(ds, (si + OFF_X) & 0xFFFF)
    dst.x_word = cpu.s.ax
    cpu.s.ax = mem.rw(ds, (si + OFF_Y) & 0xFFFF)
    old_ax = cpu.s.ax
    cpu.s.ax = (old_ax + 0x0004) & 0xFFFF
    cpu.set_add_flags(old_ax, 0x0004, old_ax + 0x0004, 16)
    dst.y_word = cpu.s.ax
    cpu.s.ip = cpu.pop()
