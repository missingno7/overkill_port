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
from overkill.recovered.systems.objects import object_spawn_seed_8209
from overkill.recovered.views.object_slots import (
    EFFECT_OBJECT_TABLE_BASE,
    GAMEPLAY_OBJECT_ALLOCATOR_WRAP_SENTINEL,
    GAMEPLAY_OBJECT_TABLE_BASE,
    OBJECT_SLOT_STRIDE,
    OFF_ACTIVE_WORD,
    OFF_COUNTER_20,
    OFF_DIRECTION_OR_STEP,
    OFF_GATE_OR_LAYER,
    OFF_HAZARD_CLASS,
    OFF_LOGIC_ID,
    OFF_SCAN_FLAG,
    OFF_TARGET_X,
    OFF_TARGET_Y,
    OFF_VARIANT,
    OFF_X,
    OFF_Y,
)

# Source position the 8209 template reads from the caller's BP frame, and the
# one slot field (offset 0x28) that has no proven name yet.
OBJECT_SPAWN_SEED_8209_SOURCE_X_BP = 0x02
OBJECT_SPAWN_SEED_8209_SOURCE_Y_BP = 0x04
OBJECT_SPAWN_SEED_8209_FIELD_28 = 0x28


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
    mem.ww(ds, (bx + OBJECT_SPAWN_SEED_8209_FIELD_28) & 0xFFFF, seed.field_28)
    mem.ww(ds, (bx + OFF_ACTIVE_WORD) & 0xFFFF, seed.active_word)
    mem.ww(ds, (bx + OFF_GATE_OR_LAYER) & 0xFFFF, seed.gate_or_layer)
    mem.ww(ds, (bx + OFF_X) & 0xFFFF, seed.x_word)
    mem.ww(ds, (bx + OFF_TARGET_X) & 0xFFFF, seed.target_x_word)
    mem.ww(ds, (bx + OFF_Y) & 0xFFFF, seed.y_word)
    mem.ww(ds, (bx + OFF_TARGET_Y) & 0xFFFF, seed.target_y_word)
    mem.ww(ds, (bx + OFF_DIRECTION_OR_STEP) & 0xFFFF, seed.direction_or_step)
    mem.ww(ds, (bx + OFF_SCAN_FLAG) & 0xFFFF, seed.scan_flag)
    mem.ww(ds, (bx + OFF_HAZARD_CLASS) & 0xFFFF, seed.hazard_class)
    mem.ww(ds, (bx + OFF_LOGIC_ID) & 0xFFFF, seed.logic_id)
    mem.ww(ds, (bx + OFF_COUNTER_20) & 0xFFFF, seed.counter_20)
    mem.ww(ds, (bx + OFF_VARIANT) & 0xFFFF, seed.variant)
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
        _cmp_word(cpu, mem.rw(ds, bx), 0x0000)
        if mem.rw(ds, bx) == 0:
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
        _cmp_word(cpu, bx, GAMEPLAY_OBJECT_ALLOCATOR_WRAP_SENTINEL)
        if bx == GAMEPLAY_OBJECT_ALLOCATOR_WRAP_SENTINEL:
            bx = GAMEPLAY_OBJECT_TABLE_BASE
        value = cpu.mem.rw(ds, bx)
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

    mem.ww(ds, 0xA482, selector_ax & 0xFFFF)
    mem.ww(ds, 0xA842, 0xA844)

    cpu.push(cpu.s.bx)
    cpu.push(cpu.s.bp)
    mem.ww(ds, 0x2376, mem.rw(ss, (bp + OFF_Y) & 0xFFFF))
    mem.ww(ds, 0x2378, mem.rw(ss, (bp + OFF_X) & 0xFFFF))
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

    cpu.s.ax = mem.rw(ss, (bp + OFF_Y) & 0xFFFF)
    old_ax = cpu.s.ax
    cpu.s.ax = (cpu.s.ax + cpu.s.cx) & 0xFFFF
    cpu.set_add_flags(old_ax, cpu.s.cx, old_ax + cpu.s.cx, 16)
    mem.ww(ds, (bx + 0x04) & 0xFFFF, cpu.s.ax)
    cpu.s.ax = mem.rw(ss, (bp + OFF_X) & 0xFFFF)
    old_ax = cpu.s.ax
    cpu.s.ax = (cpu.s.ax + cpu.s.dx) & 0xFFFF
    cpu.set_add_flags(old_ax, cpu.s.dx, old_ax + cpu.s.dx, 16)
    mem.ww(ds, (bx + 0x02) & 0xFFFF, cpu.s.ax)

    mem.ww(ds, bx, 0x0001)
    mem.ww(ds, (bx + 0x1E) & 0xFFFF, 0x0000)
    mem.ww(ds, (bx + 0x06) & 0xFFFF, 0x0000)
    mem.ww(ds, (bx + 0x08) & 0xFFFF, 0x0031)
    mem.ww(ds, (bx + 0x0A) & 0xFFFF, 0x0001)
    mem.ww(ds, (bx + 0x14) & 0xFFFF, 0x0000)
    mem.ww(ds, (bx + 0x16) & 0xFFFF, 0x0002)
    mem.ww(ds, (bx + 0x18) & 0xFFFF, 0x000B)
    mem.ww(ds, (bx + 0x1C) & 0xFFFF, 0xFFFF)

    cpu.s.ax = mem.rw(ds, (bx + 0x04) & 0xFFFF)
    cpu.s.cx = (mem.rw(ds, 0x2380) + 0x0009) & 0xFFFF
    cpu.set_add_flags(mem.rw(ds, 0x2380), 0x0009, mem.rw(ds, 0x2380) + 0x0009, 16)
    old_ax = cpu.s.ax
    cpu.s.ax = (cpu.s.ax - cpu.s.cx) & 0xFFFF
    cpu.set_sub_flags(old_ax, cpu.s.cx, old_ax - cpu.s.cx, 16)
    mem.ww(ds, (bx + 0x2C) & 0xFFFF, cpu.s.ax)
    cpu.s.ax = mem.rw(ds, (bx + 0x02) & 0xFFFF)
    cpu.s.cx = mem.rw(ds, 0x237E)
    old_ax = cpu.s.ax
    cpu.s.ax = (cpu.s.ax - cpu.s.cx) & 0xFFFF
    cpu.set_sub_flags(old_ax, cpu.s.cx, old_ax - cpu.s.cx, 16)
    mem.ww(ds, (bx + 0x2A) & 0xFFFF, cpu.s.ax)


def _run_linked_effect_spawn_7420_observed(cpu) -> None:
    """Run the observed 1010:7420 spawn helper used by BFC7/BFEE.

    The helper publishes source Y/X/type in DS:2376/2378/237A, allocates a
    compact effect slot via 7524, and seeds a short-lived visual object.
    """
    ds = cpu.s.ds & 0xFFFF
    mem = cpu.mem

    bx = _find_free_effect_slot_7524(cpu)
    _cmp_word(cpu, cpu.s.bx, 0xFFFF)
    if bx == 0xFFFF:
        return

    mem.ww(ds, bx, 0x0001)
    cpu.s.ax = mem.rw(ds, 0x2378)
    old_ax = cpu.s.ax
    addend = mem.rw(ds, 0xA278)
    cpu.s.ax = (cpu.s.ax + addend) & 0xFFFF
    cpu.set_add_flags(old_ax, addend, old_ax + addend, 16)
    mem.ww(ds, (bx + 0x02) & 0xFFFF, cpu.s.ax)

    cpu.s.ax = mem.rw(ds, 0x2376)
    _cmp_word(cpu, cpu.s.ax, 0x00C0)
    if cpu.s.ax > 0x00C0:
        cpu.s.ax = 0x00C0
    mem.ww(ds, (bx + 0x04) & 0xFFFF, cpu.s.ax)

    mem.ww(ds, (bx + 0x22) & 0xFFFF, 0x0000)
    mem.ww(ds, (bx + 0x14) & 0xFFFF, 0x0001)
    mem.ww(ds, (bx + 0x16) & 0xFFFF, 0x0005)
    mem.ww(ds, (bx + 0x18) & 0xFFFF, 0x0000)
    mem.ww(ds, (bx + 0x28) & 0xFFFF, 0xFFFF)
    mem.ww(ds, (bx + 0x24) & 0xFFFF, 0x0000)

    cpu.s.si = mem.rw(ds, 0x237A)
    mem.ww(ds, (bx + 0x26) & 0xFFFF, cpu.s.si)
    _add_reg16(cpu, 6, 0x0046)
    mem.ww(ds, (bx + 0x08) & 0xFFFF, cpu.s.si)
    mem.ww(ds, (bx + 0x0A) & 0xFFFF, 0x0000)


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
    ss = cpu.s.ss & 0xFFFF
    sp = cpu.s.sp & 0xFFFF
    cpu.mem.ww(ss, (sp - 2) & 0xFFFF, 0x754A)
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
    bx = cpu.s.bx & 0xFFFF

    ax = mem.rw(ss, (bp + OFF_Y) & 0xFFFF)
    result = ax + 0x000A
    ax = result & 0xFFFF
    cpu.s.ax = ax
    cpu.set_add_flags((result - 0x000A) & 0xFFFF, 0x000A, result, 16)
    mem.ww(ds, (bx + 0x04) & 0xFFFF, ax)

    ax = mem.rw(ss, (bp + OFF_X) & 0xFFFF)
    result = ax + 0x000A
    ax = result & 0xFFFF
    cpu.s.ax = ax
    cpu.set_add_flags((result - 0x000A) & 0xFFFF, 0x000A, result, 16)
    mem.ww(ds, (bx + 0x02) & 0xFFFF, ax)
    cpu.s.ip = cpu.pop()


def run_object_spawn_seed_a4ea(cpu) -> None:
    """Lift the common 1010:A4EA object-spawn seed template.

    This routine allocates/reclaims a gameplay object slot through 7547 and then
    seeds the common active/runtime fields.  It is still a raw object-slot seed,
    not a semantic enemy/projectile constructor.
    """
    bx = _find_free_object_slot_7573(cpu)
    _cmp_word(cpu, bx, 0xFFFF)
    if bx == 0xFFFF:
        # Original A4EA reached this by CALL 7547 (pushes A4ED) → CALL 7573
        # (pushes 754A) → 7573 returns → JZ 7550.  Simulate both stack writes so
        # the stale 754A left by CALL 7573 is present, matching the ASM state.
        cpu.push(0xA4ED)
        ss = cpu.s.ss & 0xFFFF
        sp = cpu.s.sp & 0xFFFF
        cpu.mem.ww(ss, (sp - 2) & 0xFFFF, 0x754A)
        cpu.s.ip = 0x7550
        return

    ss = cpu.s.ss & 0xFFFF
    sp = cpu.s.sp & 0xFFFF
    cpu.mem.ww(ss, (sp - 2) & 0xFFFF, 0xA4ED)
    cpu.mem.ww(ss, (sp - 4) & 0xFFFF, 0x754A)

    ds = cpu.s.ds & 0xFFFF
    mem = cpu.mem
    mem.ww(ds, bx, 0x0001)
    mem.ww(ds, (bx + 0x1E) & 0xFFFF, 0x0001)
    mem.ww(ds, (bx + 0x06) & 0xFFFF, 0x0000)
    mem.ww(ds, (bx + 0x08) & 0xFFFF, 0x0032)
    mem.ww(ds, (bx + 0x14) & 0xFFFF, 0x0000)
    mem.ww(ds, (bx + 0x16) & 0xFFFF, 0x0002)
    mem.ww(ds, (bx + 0x18) & 0xFFFF, 0x0002)
    mem.ww(ds, (bx + 0x1C) & 0xFFFF, 0xFFFF)
    cpu.s.ip = cpu.pop()


def run_object_spawn_seed_from_source_a4d7(cpu) -> None:
    """Lift 1010:A4D7: A4EA seed plus source-coordinate copy.

    SI points at a two-word source coordinate pair.  The spawned object receives
    X from [SI+2] and Y from [SI+4]+4 after the common A4EA seed.
    """
    bx = _find_free_object_slot_7573(cpu)
    _cmp_word(cpu, bx, 0xFFFF)
    if bx == 0xFFFF:
        # Original A4D7 CALL A4EA (→ A4DA), A4EA CALL 7547 (→ A4ED),
        # 7547 CALL 7573 (→ 754A stale).  Mirror all three stack writes.
        cpu.push(0xA4DA)
        cpu.push(0xA4ED)
        ss = cpu.s.ss & 0xFFFF
        sp = cpu.s.sp & 0xFFFF
        cpu.mem.ww(ss, (sp - 2) & 0xFFFF, 0x754A)
        cpu.s.ip = 0x7550
        return

    ss = cpu.s.ss & 0xFFFF
    sp = cpu.s.sp & 0xFFFF
    cpu.mem.ww(ss, (sp - 2) & 0xFFFF, 0xA4DA)
    cpu.mem.ww(ss, (sp - 4) & 0xFFFF, 0xA4ED)
    cpu.mem.ww(ss, (sp - 6) & 0xFFFF, 0x754A)

    ds = cpu.s.ds & 0xFFFF
    mem = cpu.mem
    mem.ww(ds, bx, 0x0001)
    mem.ww(ds, (bx + 0x1E) & 0xFFFF, 0x0001)
    mem.ww(ds, (bx + 0x06) & 0xFFFF, 0x0000)
    mem.ww(ds, (bx + 0x08) & 0xFFFF, 0x0032)
    mem.ww(ds, (bx + 0x14) & 0xFFFF, 0x0000)
    mem.ww(ds, (bx + 0x16) & 0xFFFF, 0x0002)
    mem.ww(ds, (bx + 0x18) & 0xFFFF, 0x0002)
    mem.ww(ds, (bx + 0x1C) & 0xFFFF, 0xFFFF)

    si = cpu.s.si & 0xFFFF
    cpu.s.ax = mem.rw(ds, (si + 0x02) & 0xFFFF)
    mem.ww(ds, (bx + 0x02) & 0xFFFF, cpu.s.ax)
    cpu.s.ax = mem.rw(ds, (si + 0x04) & 0xFFFF)
    old_ax = cpu.s.ax
    cpu.s.ax = (old_ax + 0x0004) & 0xFFFF
    cpu.set_add_flags(old_ax, 0x0004, old_ax + 0x0004, 16)
    mem.ww(ds, (bx + 0x04) & 0xFFFF, cpu.s.ax)
    cpu.s.ip = cpu.pop()
