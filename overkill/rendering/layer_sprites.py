"""Shared OVERKILL layer-sprite rendering dispatch.

This module contains the lifted source-code logic for the runtime layer-sprite
setup and compositor dispatch cluster around 1010:75A6, 1010:75F5,
1010:768E, and 1010:7746.

Despite older hook names saying "tandy", these routines are shared by all three
OVERKILL video modes.  The setup code computes sprite source pointers,
destination slots, animation phase indices, and then jumps through mode-specific
compositor tables:

* CGA compositor targets live mostly in the 38xx/39xx/3xxx range.
* EGA compositor targets live mostly in the 10xx/1xxx/2xxx/40xx range.
* Tandy compositor targets live mostly in the 2Exx/2Fxx range.

The generic VM should not know these game tables or object-frame offsets.  Hook
wrappers in :mod:`overkill.hooks` keep the original ASM addresses
visible and pass the concrete compositor handlers into this module.
"""

from __future__ import annotations

from dos_re.cpu import CF
from dos_re.hooks import call_installed_hook_like_near_call, jump_installed_hook_boundary
from overkill.asm import _cmp_word

from dataclasses import dataclass
from typing import Callable, Mapping

from dos_re.cpu import ZF

Cpu = object
CompositorHandler = Callable[[Cpu], None]
SelfDisableIfPatched = Callable[[Cpu, int, bytes, str], bool]
FailUnverifiedPath = Callable[..., None]

# Object stack-frame offsets used by the layer-sprite setup routines.
OBJ_SPRITE_INDEX = 0x08
OBJ_DEST_SLOT_0C = 0x0C
OBJ_DEST_SLOT_10 = 0x10
OBJ_ANIMATION_PHASE = 0x12
OBJ_VARIANT_FLAGS = 0x24

OFFSCREEN_DESTINATION = 0xFFFF

# Runtime data tables used by OVERKILL's video-mode-specific setup.
VIDEO_MODE_SELECTOR_OFF = 0x95BC
LAYER_75A6_PRIMARY_SEGMENT_OFF = 0x95A6
LAYER_75A6_SECONDARY_SEGMENT_OFF = 0x95AE
LAYER_768E_PRIMARY_SEGMENT_OFF = 0x95AA
LAYER_768E_SECONDARY_SEGMENT_OFF = 0x95AC
COMPACT_LAYER_SEGMENT_OFF = 0x95A8
SPRITE_FRAME_TABLE_75A6 = 0x9392
SPRITE_FRAME_TABLE_768E = 0x9192
COMPACT_SPRITE_FRAME_TABLE = 0x8F92
SAVED_SPRITE_FRAME_PTR_OFF = 0x7624
SAVED_SPRITE_SEGMENT_OFF = 0x7626

# Dispatch table bases used by the shared tail dispatchers.
LAYER_TAIL_NORMAL_TABLE = 0x7628
LAYER_TAIL_VARIANT_TABLE = 0x7658
LAYER_768E_NORMAL_TABLE = 0x76E6
LAYER_768E_VARIANT_TABLE = 0x7716
COMPACT_LAYER_TABLE = 0x7782
LAYER_DRAW_TYPE_TABLE = 0x75A0

SIG_LAYER_DRAW_TYPE_DISPATCH_7596 = bytes.fromhex("8b 5e 14 d1 e3 2e ff a7 a0 75")
SIG_LAYER0_CALL_7596_A8BE = bytes.fromhex("e8 d5 cc 59 e2 d0")
SIG_LAYER0_TAIL_A8C1 = bytes.fromhex("59 e2 d0")
SIG_LAYER1_CALL_7596_A8F1 = bytes.fromhex("e8 a2 cc 59 e2 d0")
SIG_LAYER1_TAIL_A8F4 = bytes.fromhex("59 e2 d0")
SIG_SCAN_DRAW_CALL_5AC8_A858 = bytes.fromhex("e8 6d b2 59 e2 eb")
SIG_SCAN_DRAW_TAIL_A85B = bytes.fromhex("59 e2 eb")
SIG_SCAN_PRESENT_CALL_5A92_A936 = bytes.fromhex("e8 59 b1 59 e2 eb")
SIG_SCAN_PRESENT_TAIL_A939 = bytes.fromhex("59 e2 eb")


# These exact CGA/EGA animation-phase targets are still executed by the original
# interpreter as bounded near-return compositor leaves.  This remains a narrow
# allow-list, not a general fallback: unknown table targets still fail-fast.
KNOWN_ORIGINAL_LAYER_COMPOSITE_TARGETS: frozenset[int] = frozenset({
    # CGA layer-sprite compositor table entries not lifted yet.
    0x3926, 0x39DF, 0x3AEE, 0x3C53, 0x3CBC, 0x3D52,
    0x3E12, 0x3E70, 0x3EFB, 0x3FB0, 0x3FEB, 0x403A,
    # EGA layer-sprite compositor table entries not lifted yet.  These are
    # sibling animation-phase targets of the already lifted 103C/10B7/1AEB/1D1B
    # paths and are reached by left/right movement frames.
    0x10ED, 0x11B8, 0x12B6, 0x13E7, 0x154B, 0x167C, 0x177A,
    0x1845, 0x1899, 0x18F7, 0x195F, 0x19D1, 0x1A39, 0x1A97,
    0x1B2E, 0x1B4F, 0x1BC6, 0x1C61, 0x1DF4, 0x1EAE, 0x1F49,
    0x1FC0, 0x1FFB, 0x203C, 0x2083, 0x20D0, 0x2117, 0x2158,
})

# Lifted compositor targets currently used by the shared layer dispatchers.
# The concrete functions still live beside the existing compositor hooks in
# overkill/hooks.py; wrappers pass them through LayerSpriteRuntime.
LIFTED_LAYER_COMPOSITE_TARGETS: frozenset[int] = frozenset({
    # EGA compact/spread compositor leaves.
    0x2193, 0x238D, 0x2410, 0x247E, 0x21D6, 0x2223, 0x2285, 0x22FC,
    0x409D, 0x40D7, 0x412B,
    # CGA compositor leaves.
    0x3849, 0x38B7, 0x38F9, 0x387C, 0x38D6, 0x390E,
    # EGA full-width layer compositor leaves.
    0x103C, 0x10B7, 0x1AEB, 0x1D1B,
    # Tandy compositor leaves.
    0x2F81, 0x2F40, 0x2ECB, 0x2E6E, 0x2FB6,
})


@dataclass(frozen=True)
class LayerSpriteRuntime:
    """VM-bound services needed by the game-specific layer-sprite code.

    The pure game logic in this module should not import ``overkill/hooks.py``.
    Instead, the hook wrapper supplies:

    * the runtime-patched code guard used by all replacement hooks;
    * the exact live-byte signatures for each original entry point;
    * lifted compositor handlers keyed by original target IP;
    * the fail-fast reporter from overkill/hooks.py so unknown paths keep the
      same rich object context as before.
    """

    self_disable_if_patched: SelfDisableIfPatched
    fail_unverified: FailUnverifiedPath
    signature_75a6: bytes
    signature_768e: bytes
    signature_7746: bytes
    compositor_handlers: Mapping[int, CompositorHandler]


def _cmp_word(cpu, a: int, b: int) -> None:
    left = a & 0xFFFF
    right = b & 0xFFFF
    cpu.set_sub_flags(left, right, left - right, 16)


def _test_word(cpu, value: int, mask: int) -> None:
    cpu.set_logic_flags((value & mask) & 0xFFFF, 16)


def _add_reg16(cpu, reg_idx: int, value: int) -> None:
    old = cpu.get_reg16(reg_idx)
    addend = value & 0xFFFF
    result = old + addend
    cpu.set_reg16(reg_idx, result)
    cpu.set_add_flags(old, addend, result, 16)


def _sub_reg16(cpu, reg_idx: int, value: int) -> None:
    old = cpu.get_reg16(reg_idx)
    subtrahend = value & 0xFFFF
    result = old - subtrahend
    cpu.set_reg16(reg_idx, result)
    cpu.set_sub_flags(old, subtrahend, result, 16)


def _variant_layer_table(normal_base: int, variant_base: int, variant_flags: int) -> int:
    """Select the same table as ``TEST SS:[BP+24h],FFFFh`` / conditional MOV."""
    return normal_base if (variant_flags & 0xFFFF) == 0 else variant_base



def dispatch_menu_cell_source_blit_5a6c(cpu) -> None:
    """Lift OVERKILL 1010:5A6C source-cell video-mode dispatch stub.

    5A6C is not a renderer body.  It loads the active video mode from
    ``CS:[95BC]``, performs the real ``SHL BX,1`` side effect, and jumps through
    the small mode table at ``CS:5A78``.  The selected target owns the actual
    CGA/EGA/Tandy source-cell blit.  Keeping this as a dispatch-only hook avoids
    duplicating those renderer leaves while removing the hot three-instruction
    unknown cluster (5A6C/5A71/5A73).
    """
    s = cpu.s
    cs = s.cs & 0xFFFF
    s.bx = cpu.mem.rw(cs, VIDEO_MODE_SELECTOR_OFF)
    s.bx = cpu.shift(4, s.bx, 1, 16)
    s.ip = cpu.mem.rw(cs, (0x5A78 + s.bx) & 0xFFFF)


def dispatch_draw_object_5ac8(cpu) -> None:
    """Lift OVERKILL 1010:5AC8 draw-object jump-table dispatcher."""
    s = cpu.s
    cs = s.cs & 0xFFFF
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF
    mode = cpu.mem.rw(cs, VIDEO_MODE_SELECTOR_OFF)
    bx = cpu.mem.rw(ss, (bp + 0x14) & 0xFFFF)
    bx = (bx + mode + mode + mode) & 0xFFFF
    s.bx = bx
    s.bx = cpu.shift(4, s.bx, 1, 16)
    s.ip = cpu.mem.rw(cs, (0x5AE2 + s.bx) & 0xFFFF)


def dispatch_present_object_5a92(cpu) -> None:
    """Lift OVERKILL 1010:5A92 present-object jump-table dispatcher."""
    s = cpu.s
    cs = s.cs & 0xFFFF
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF
    s.es = cpu.mem.rw(cs, 0x9598)
    s.di = cpu.mem.rw(ss, (bp + 0x0C) & 0xFFFF)
    s.si = cpu.mem.rw(ss, (bp + 0x0E) & 0xFFFF)
    mode = cpu.mem.rw(cs, VIDEO_MODE_SELECTOR_OFF)
    bx = cpu.mem.rw(ss, (bp + 0x14) & 0xFFFF)
    bx = (bx + mode + mode + mode) & 0xFFFF
    s.bx = bx
    s.bx = cpu.shift(4, s.bx, 1, 16)
    s.ip = cpu.mem.rw(cs, (0x5AB6 + s.bx) & 0xFFFF)


def _call_installed_draw_dispatch_5ac8(cpu, return_ip: int) -> None:
    """CALL 1010:5AC8 through the verifier-visible installed boundary."""
    call_installed_hook_like_near_call(cpu, (0x1010, 0x5AC8), dispatch_draw_object_5ac8, return_ip)


def _call_installed_present_dispatch_5a92(cpu, return_ip: int) -> None:
    """CALL 1010:5A92 through the verifier-visible installed boundary."""
    call_installed_hook_like_near_call(cpu, (0x1010, 0x5A92), dispatch_present_object_5a92, return_ip)


def _call_installed_layer_draw_type_7596(cpu, return_ip: int) -> None:
    """CALL 1010:7596 through the verifier-visible installed boundary."""
    call_installed_hook_like_near_call(cpu, (0x1010, 0x7596), dispatch_layer_draw_type_table_7596, return_ip)


def _jump_installed_compositor_target(cpu, target_ip: int, handler: CompositorHandler) -> None:
    """JMP/fall-through into a registered compositor target with verifier visibility."""
    jump_installed_hook_boundary(cpu, (0x1010, target_ip & 0xFFFF), handler)


def call_draw_dispatch_from_scan_a858(cpu, runtime: LayerSpriteRuntime) -> None:
    """Model ``A858: CALL 5AC8`` while preserving the real return frame."""
    if runtime.self_disable_if_patched(cpu, 0xA858, SIG_SCAN_DRAW_CALL_5AC8_A858, "overkill_scan_draw_call_5ac8_a858"):
        return
    _call_installed_draw_dispatch_5ac8(cpu, 0xA85B)


def finish_draw_scan_tail_a85b(cpu, runtime: LayerSpriteRuntime) -> None:
    """Model ``A85B: POP CX ; LOOP A849``."""
    if runtime.self_disable_if_patched(cpu, 0xA85B, SIG_SCAN_DRAW_TAIL_A85B, "overkill_scan_draw_tail_a85b"):
        return
    s = cpu.s
    s.cx = cpu.pop()
    s.cx = (s.cx - 1) & 0xFFFF
    s.ip = 0xA849 if s.cx != 0 else 0xA85E


def call_present_dispatch_from_scan_a936(cpu, runtime: LayerSpriteRuntime) -> None:
    """Model ``A936: CALL 5A92`` while preserving the real return frame."""
    if runtime.self_disable_if_patched(cpu, 0xA936, SIG_SCAN_PRESENT_CALL_5A92_A936, "overkill_scan_present_call_5a92_a936"):
        return
    _call_installed_present_dispatch_5a92(cpu, 0xA939)


def finish_present_scan_tail_a939(cpu, runtime: LayerSpriteRuntime) -> None:
    """Model ``A939: POP CX ; LOOP A927``."""
    if runtime.self_disable_if_patched(cpu, 0xA939, SIG_SCAN_PRESENT_TAIL_A939, "overkill_scan_present_tail_a939"):
        return
    s = cpu.s
    s.cx = cpu.pop()
    s.cx = (s.cx - 1) & 0xFFFF
    s.ip = 0xA927 if s.cx != 0 else 0xA93C




def run_clear_presence_list_parent_4d64(cpu, clear_presence_list_handler: CompositorHandler) -> None:
    """Model the tiny 1010:4D64 parent before the shared 4D6F clear loop.

    The original sequence is just::

        mov es, cs:[9598h]
        mov si, C7B1h
        mov cx, 0028h
        fall through to 4D6F

    ``4D6F`` owns the actual presence-list clear body and returns to the word
    already on the caller's stack.  This parent deliberately does not push a
    synthetic return word; jumping through the installed 4D6F boundary keeps the
    clear logic verifier-visible without changing the original fall-through stack.
    """
    s = cpu.s
    cs = s.cs & 0xFFFF
    s.es = cpu.mem.rw(cs, 0x9598)
    s.si = 0xC7B1
    s.cx = 0x0028
    jump_installed_hook_boundary(cpu, (0x1010, 0x4D6F), clear_presence_list_handler)


def call_clear_presence_list_parent_a93c(cpu, clear_presence_parent_handler: CompositorHandler) -> None:
    """Model ``A93C: CALL 4D64 ; RET`` without duplicating 4D6F."""
    call_installed_hook_like_near_call(cpu, (0x1010, 0x4D64), clear_presence_parent_handler, 0xA93F)
    if (cpu.s.ip & 0xFFFF) != 0xA93F:
        raise RuntimeError(f"4D64 returned to unexpected IP {cpu.s.ip:04X} inside A93C present-scan parent")
    cpu.s.ip = cpu.pop()


def run_presence_stamp_triplet_4ced(cpu, presence_stamp_handler: CompositorHandler) -> None:
    """Model the small ``1010:4CED`` parent around three ``4D15`` calls.

    The original routine is only orchestration glue for the already-lifted
    presence-list stamper::

        mov es, cs:[9598h]
        mov si, C6C1h
        mov di, C7B1h
        mov bp, 4D4Dh
        mov cx, 0014h
        call 4D15
        mov bp, 4D51h
        mov cx, 000Ah
        call 4D15
        mov cx, 000Ah
        call 4D15
        mov word ptr [di], FFFFh
        ret

    Compose the proven ``4D15`` hook instead of duplicating the stamping loop.
    Synthetic return words are the real call-site continuations, so full-memory
    verifier snapshots still see the same balanced call scratch under ``SP``.
    """
    s = cpu.s
    cs = s.cs & 0xFFFF
    ds = s.ds & 0xFFFF
    s.es = cpu.mem.rw(cs, 0x9598)
    s.si = 0xC6C1
    s.di = 0xC7B1

    for bp, cx, return_ip in ((0x4D4D, 0x0014, 0x4D01), (0x4D51, 0x000A, 0x4D0A), (0x4D51, 0x000A, 0x4D10)):
        s.bp = bp
        s.cx = cx
        call_installed_hook_like_near_call(cpu, (0x1010, 0x4D15), presence_stamp_handler, return_ip)
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (cs, return_ip):
            raise RuntimeError(f"4D15 returned to unexpected IP {s.cs:04X}:{s.ip:04X} inside 4CED parent")

    cpu.mem.ww(ds, s.di & 0xFFFF, 0xFFFF)
    s.ip = cpu.pop()


def run_present_object_scan_pair_a90c(
    cpu,
    scan_8d12_handler: CompositorHandler,
    scan_32ca_handler: CompositorHandler,
    clear_presence_parent_handler: CompositorHandler,
) -> None:
    """Model the A90C two-table present scan parent.

    A90C is a narrow layer-sprite orchestration parent, not a renderer leaf:
    it scans the DS:8D12 present list with the existing A90F hook, scans the
    DS:32CA list with the existing A927 hook, then clears the presence list via
    A93C/4D64/4D6F.  If either child scan finds an active entry, it preserves the
    original partial continuation at the real CALL site so the existing dispatch
    hooks own the object present body.
    """
    s = cpu.s
    s.cx = 0x0022
    jump_installed_hook_boundary(cpu, (0x1010, 0xA90F), scan_8d12_handler)
    if (s.ip & 0xFFFF) != 0xA924:
        return

    s.cx = 0x0024
    jump_installed_hook_boundary(cpu, (0x1010, 0xA927), scan_32ca_handler)
    if (s.ip & 0xFFFF) != 0xA93C:
        return

    call_clear_presence_list_parent_a93c(cpu, clear_presence_parent_handler)


def dispatch_layer_draw_type_table_7596(cpu) -> None:
    """Run the tiny SS:[BP+14h] -> CS:75A0 draw-type table dispatch."""
    s = cpu.s
    cs = s.cs & 0xFFFF
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF
    s.bx = cpu.mem.rw(ss, (bp + 0x14) & 0xFFFF)
    s.bx = cpu.shift(4, s.bx, 1, 16)
    s.ip = cpu.mem.rw(cs, (LAYER_DRAW_TYPE_TABLE + s.bx) & 0xFFFF)


def call_layer0_draw_type_from_scan_a8be(cpu, runtime: LayerSpriteRuntime) -> None:
    """Model ``A8BE: CALL 7596`` in the layer-0 scan."""
    if runtime.self_disable_if_patched(cpu, 0xA8BE, SIG_LAYER0_CALL_7596_A8BE, "overkill_layer0_call_7596_a8be"):
        return
    _call_installed_layer_draw_type_7596(cpu, 0xA8C1)


def finish_layer0_scan_tail_a8c1(cpu, runtime: LayerSpriteRuntime) -> None:
    """Model ``A8C1: POP CX ; LOOP A894``."""
    if runtime.self_disable_if_patched(cpu, 0xA8C1, SIG_LAYER0_TAIL_A8C1, "overkill_layer0_scan_tail_a8c1"):
        return
    s = cpu.s
    s.cx = cpu.pop()
    s.cx = (s.cx - 1) & 0xFFFF
    s.ip = 0xA894 if s.cx != 0 else 0xA8C4


def call_layer1_draw_type_from_scan_a8f1(cpu, runtime: LayerSpriteRuntime) -> None:
    """Model ``A8F1: CALL 7596`` in the layer-1 scan."""
    if runtime.self_disable_if_patched(cpu, 0xA8F1, SIG_LAYER1_CALL_7596_A8F1, "overkill_layer1_call_7596_a8f1"):
        return
    _call_installed_layer_draw_type_7596(cpu, 0xA8F4)


def finish_layer1_scan_tail_a8f4(cpu, runtime: LayerSpriteRuntime) -> None:
    """Model ``A8F4: POP CX ; LOOP A8C7``."""
    if runtime.self_disable_if_patched(cpu, 0xA8F4, SIG_LAYER1_TAIL_A8F4, "overkill_layer1_scan_tail_a8f4"):
        return
    s = cpu.s
    s.cx = cpu.pop()
    s.cx = (s.cx - 1) & 0xFFFF
    s.ip = 0xA8C7 if s.cx != 0 else 0xA8F7


def dispatch_layer_draw_type_7596(cpu, runtime: LayerSpriteRuntime) -> None:
    """Lift OVERKILL 1010:7596 object-type layer draw dispatcher.

    The original body is a tiny jump-table stub reached from the layer-0/layer-1
    scan loops after they have selected the current object in ``BP``::

        mov bx, ss:[bp+14h]
        shl bx, 1
        jmp word ptr cs:[bx+75A0h]

    Keeping this as a real hook removes a very hot interpreted glue cluster while
    still preserving the original boundary: the selected draw helper runs as its
    own hook/interpreted routine exactly as the jump table chose it.
    """
    if runtime.self_disable_if_patched(cpu, 0x7596, SIG_LAYER_DRAW_TYPE_DISPATCH_7596, "overkill_layer_draw_type_dispatch_7596"):
        return

    dispatch_layer_draw_type_table_7596(cpu)


def _run_original_layer_composite_near_target(cpu, target_ip: int, runtime: LayerSpriteRuntime, *, max_steps: int = 20000) -> None:
    """Execute an unlifted but known layer compositor target until near RET.

    These targets are leaves reached from OVERKILL's layer-sprite dispatch tables.
    They are kept as a strict allow-list to avoid widening the hook into a silent
    fallback.  The original routine must return to the word already on SS:SP.
    """
    s = cpu.s
    entry_cs = s.cs & 0xFFFF
    entry_sp = s.sp & 0xFFFF
    return_ip = cpu.mem.rw(s.ss & 0xFFFF, entry_sp)
    s.ip = target_ip & 0xFFFF
    for _ in range(max_steps):
        cpu.step()
        if (
            (s.cs & 0xFFFF) == entry_cs
            and (s.ip & 0xFFFF) == return_ip
            and (s.sp & 0xFFFF) == ((entry_sp + 2) & 0xFFFF)
        ):
            return
    runtime.fail_unverified(
        cpu,
        parent="1010:75F5",
        chain="bounded original layer compositor did not return",
        target_ip=target_ip,
    )


def run_layer_sprite_compositor_target(cpu, target_ip: int, runtime: LayerSpriteRuntime) -> bool:
    """Run a known CGA/EGA/Tandy layer compositor target.

    Lifted targets are dispatched through explicit hook functions supplied by the
    wrapper.  Rare known CGA/EGA animation-phase leaves are interpreted through a
    bounded near-return runner.  Unknown targets return False so the caller can
    fail-fast with its original context.
    """
    target = target_ip & 0xFFFF
    if target in KNOWN_ORIGINAL_LAYER_COMPOSITE_TARGETS:
        _run_original_layer_composite_near_target(cpu, target, runtime)
        return True
    handler = runtime.compositor_handlers.get(target)
    if handler is None:
        return False
    _jump_installed_compositor_target(cpu, target, handler)
    return True


def dispatch_layer_sprite_tail_75f5(cpu, obj_bp: int, chain: str, runtime: LayerSpriteRuntime) -> None:
    """Run shared OVERKILL 1010:75F5 layer-sprite compositor tail.

    The original code sets ES to the sprite-work buffer, computes a dispatch
    table index from video mode, animation phase, and variant flag, then jumps to
    a mode-specific compositor target.  The target consumes DS:SI source pixels,
    ES:DI destination, BP/CX row count, and returns near to the caller's stack
    continuation.
    """
    s = cpu.s
    cs = s.cs & 0xFFFF
    ss = s.ss & 0xFFFF
    mem = cpu.mem

    s.es = mem.rw(cs, 0x9598)
    bx = (mem.rw(cs, VIDEO_MODE_SELECTOR_OFF) << 3) & 0xFFFF
    bx = (bx + mem.rw(ss, (obj_bp + OBJ_ANIMATION_PHASE) & 0xFFFF)) & 0xFFFF
    base = _variant_layer_table(
        LAYER_TAIL_NORMAL_TABLE,
        LAYER_TAIL_VARIANT_TABLE,
        mem.rw(ss, (obj_bp + OBJ_VARIANT_FLAGS) & 0xFFFF),
    )
    s.dx = base  # MOV DX,base; lifted compositors preserve DX the same way.
    bx = ((bx << 1) & 0xFFFF)
    bx = (bx + base) & 0xFFFF
    s.bx = bx
    target = mem.rw(cs, bx)
    s.ds = s.cx & 0xFFFF
    s.bp = 0x0010
    s.cx = 0x0010

    if not run_layer_sprite_compositor_target(cpu, target, runtime):
        runtime.fail_unverified(cpu, parent="1010:75F5", chain=chain, target_ip=target, bp=obj_bp)


def draw_layer_sprite_768e(cpu, runtime: LayerSpriteRuntime) -> None:
    """Hook body for OVERKILL 1010:768E shared layer-sprite draw helper.

    This is the sibling of 75A6.  It draws a single destination slot using sprite
    indices from the large frame table at 9192h and a mode/phase/variant dispatch
    table rooted at 76E6h/7716h.  It is shared by CGA, EGA, and Tandy despite the
    legacy hook name.
    """
    if runtime.self_disable_if_patched(cpu, 0x768E, runtime.signature_768e, "overkill_layer_sprite_draw_768e"):
        return

    s = cpu.s
    cs = s.cs & 0xFFFF
    ss = s.ss & 0xFFFF
    obj_bp = s.bp & 0xFFFF
    mem = cpu.mem

    s.di = mem.rw(ss, (obj_bp + OBJ_DEST_SLOT_0C) & 0xFFFF)
    _cmp_word(cpu, s.di, OFFSCREEN_DESTINATION)
    if s.di == OFFSCREEN_DESTINATION:
        s.ip = cpu.pop()
        return

    s.es = mem.rw(cs, 0x9598)
    s.bx = mem.rw(ss, (obj_bp + OBJ_SPRITE_INDEX) & 0xFFFF)
    s.cx = mem.rw(cs, LAYER_768E_PRIMARY_SEGMENT_OFF)
    _cmp_word(cpu, s.bx, 0x00FA)
    if s.bx >= 0x00FA:
        _sub_reg16(cpu, 3, 0x00FA)
        s.cx = mem.rw(cs, LAYER_768E_SECONDARY_SEGMENT_OFF)

    s.bx = cpu.shift(4, s.bx, 1, 16)
    _add_reg16(cpu, 3, SPRITE_FRAME_TABLE_768E)
    s.si = mem.rw(cs, s.bx)

    dispatch = (mem.rw(cs, VIDEO_MODE_SELECTOR_OFF) << 3) & 0xFFFF
    dispatch = (dispatch + mem.rw(ss, (obj_bp + OBJ_ANIMATION_PHASE) & 0xFFFF)) & 0xFFFF
    table = _variant_layer_table(
        LAYER_768E_NORMAL_TABLE,
        LAYER_768E_VARIANT_TABLE,
        mem.rw(ss, (obj_bp + OBJ_VARIANT_FLAGS) & 0xFFFF),
    )
    s.dx = table
    s.bx = ((dispatch << 1) & 0xFFFF)
    _add_reg16(cpu, 3, table)
    target_ip = mem.rw(cs, s.bx)
    s.ds = s.cx & 0xFFFF
    s.bp = 0x0010
    s.cx = s.bp

    if not run_layer_sprite_compositor_target(cpu, target_ip, runtime):
        runtime.fail_unverified(
            cpu,
            parent="1010:768E",
            chain="768E Tandy sprite compositor dispatch (shared CGA/EGA/Tandy layer path)",
            target_ip=target_ip,
            bp=obj_bp,
        )


def draw_layer_sprite_75a6(cpu, runtime: LayerSpriteRuntime) -> None:
    """Hook body for OVERKILL 1010:75A6 double-slot layer-sprite draw helper.

    75A6 looks up a sprite frame in the 9392h table, saves the frame pointer and
    source segment in CS:7624/7626, draws slot SS:[BP+0Ch] through a real CALL
    to 75F5, then optionally advances to the next frame and falls through into
    the same compositor tail for slot SS:[BP+10h].
    """
    if runtime.self_disable_if_patched(cpu, 0x75A6, runtime.signature_75a6, "overkill_layer_sprite_draw_75a6"):
        return

    s = cpu.s
    cs = s.cs & 0xFFFF
    ss = s.ss & 0xFFFF
    mem = cpu.mem
    obj_bp = s.bp & 0xFFFF

    s.bx = mem.rw(ss, (obj_bp + OBJ_SPRITE_INDEX) & 0xFFFF)
    s.cx = mem.rw(cs, LAYER_75A6_PRIMARY_SEGMENT_OFF)
    _cmp_word(cpu, s.bx, 0x001C)
    if (s.bx & 0xFFFF) >= 0x001C:
        _sub_reg16(cpu, 3, 0x001C)
        s.cx = mem.rw(cs, LAYER_75A6_SECONDARY_SEGMENT_OFF)
    s.bx = cpu.shift(4, s.bx, 1, 16)
    _add_reg16(cpu, 3, SPRITE_FRAME_TABLE_75A6)
    s.si = mem.rw(cs, s.bx & 0xFFFF)
    mem.ww(cs, SAVED_SPRITE_FRAME_PTR_OFF, s.si & 0xFFFF)
    mem.ww(cs, SAVED_SPRITE_SEGMENT_OFF, s.cx & 0xFFFF)

    s.di = mem.rw(ss, (obj_bp + OBJ_DEST_SLOT_0C) & 0xFFFF)
    _cmp_word(cpu, s.di, OFFSCREEN_DESTINATION)
    if (s.di & 0xFFFF) != OFFSCREEN_DESTINATION:
        cpu.push(obj_bp)
        cpu.push(0x75DA)
        dispatch_layer_sprite_tail_75f5(cpu, obj_bp, "A8C7 -> 7596 -> 75A6 -> 75F5 (slot 0Ch)", runtime)
        if (s.ip & 0xFFFF) != 0x75DA:
            raise RuntimeError(f"75A6 slot-0Ch composite returned to {s.ip:04X}, expected 75DA")
        s.bp = cpu.pop()
        obj_bp = s.bp & 0xFFFF

    s.di = mem.rw(ss, (obj_bp + OBJ_DEST_SLOT_10) & 0xFFFF)
    _cmp_word(cpu, s.di, OFFSCREEN_DESTINATION)
    if (s.di & 0xFFFF) == OFFSCREEN_DESTINATION:
        s.ip = cpu.pop()
        return

    s.si = mem.rw(cs, SAVED_SPRITE_FRAME_PTR_OFF)
    s.cx = mem.rw(cs, SAVED_SPRITE_SEGMENT_OFF)
    s.ax = mem.rw(s.ds & 0xFFFF, 0x1028)
    s.ax = cpu.shift(5, s.ax, 1, 16)
    old_si = s.si & 0xFFFF
    s.si = (old_si + (s.ax & 0xFFFF)) & 0xFFFF
    cpu.set_add_flags(old_si, s.ax & 0xFFFF, old_si + (s.ax & 0xFFFF), 16)
    dispatch_layer_sprite_tail_75f5(cpu, obj_bp, "A8C7 -> 7596 -> 75A6 -> 75F5 (slot 10h)", runtime)


def draw_compact_layer_sprite_7746(cpu, runtime: LayerSpriteRuntime) -> None:
    """Hook body for OVERKILL 1010:7746 compact layer-sprite helper.

    This path draws compact eight-row layer sprites.  It uses the 8F92h frame
    table and 7782h dispatch table, but otherwise follows the same shared
    mode-specific compositor pattern as 75A6/768E.
    """
    if runtime.self_disable_if_patched(cpu, 0x7746, runtime.signature_7746, "overkill_compact_layer_sprite_draw_7746"):
        return

    s = cpu.s
    cs = s.cs & 0xFFFF
    ss = s.ss & 0xFFFF
    obj_bp = s.bp & 0xFFFF
    mem = cpu.mem

    s.di = mem.rw(ss, (obj_bp + OBJ_DEST_SLOT_0C) & 0xFFFF)
    _cmp_word(cpu, s.di, OFFSCREEN_DESTINATION)
    if s.di == OFFSCREEN_DESTINATION:
        s.ip = cpu.pop()
        return

    s.es = mem.rw(cs, 0x9598)
    s.bx = mem.rw(ss, (obj_bp + OBJ_SPRITE_INDEX) & 0xFFFF)
    s.cx = mem.rw(cs, COMPACT_LAYER_SEGMENT_OFF)
    s.bx = cpu.shift(4, s.bx, 1, 16)
    _add_reg16(cpu, 3, COMPACT_SPRITE_FRAME_TABLE)
    s.si = mem.rw(cs, s.bx)

    dispatch = (mem.rw(cs, VIDEO_MODE_SELECTOR_OFF) << 3) & 0xFFFF
    dispatch = (dispatch + mem.rw(ss, (obj_bp + OBJ_ANIMATION_PHASE) & 0xFFFF)) & 0xFFFF
    s.ds = s.cx & 0xFFFF
    s.bp = 0x0008
    s.cx = s.bp
    s.bx = ((dispatch << 1) & 0xFFFF)
    target_ip = mem.rw(cs, (COMPACT_LAYER_TABLE + s.bx) & 0xFFFF)

    if not run_layer_sprite_compositor_target(cpu, target_ip, runtime):
        runtime.fail_unverified(
            cpu,
            parent="1010:7746",
            chain="7746 compact layer compositor dispatch",
            target_ip=target_ip,
            bp=obj_bp,
        )


SIG_VIDEO_PAGE_TOGGLE_511F = bytes.fromhex(
    "2e 83 3e bc 95 01 74 01 c3 2e ff 06 5e 51 2e 83 26 5e 51 01 "
    "2e c7 06 a4 95 00 a0 75 01 c3 2e c7 06 a4 95 00 a2 c3"
)


def _inc_cs_word_preserve_cf(cpu, off: int) -> int:
    old = cpu.mem.rw(cpu.s.cs & 0xFFFF, off & 0xFFFF)
    old_cf = cpu.get_flag(CF)
    result = (old + 1) & 0xFFFF
    cpu.mem.ww(cpu.s.cs & 0xFFFF, off & 0xFFFF, result)
    cpu.set_add_flags(old, 1, old + 1, 16)
    cpu.set_flag(CF, old_cf)
    return result


def run_video_page_toggle_511f(cpu, self_disable_if_patched) -> None:
    """Lift shared 1010:511F video-page toggle stub.

    All video modes call this from the main frame loop, but only mode 1 uses the
    page flip: non-mode-1 paths are just CMP/JNE/RET and preserve that compare's
    flags.  Keeping it neutral avoids mislabelling Tandy execution as CGA/EGA
    rendering while still removing the tiny interpreted per-frame stub.
    """
    if self_disable_if_patched(cpu, 0x511F, SIG_VIDEO_PAGE_TOGGLE_511F, "overkill_video_page_toggle_511f"):
        return
    cs = cpu.s.cs & 0xFFFF
    mode = cpu.mem.rw(cs, 0x95BC)
    _cmp_word(cpu, mode, 1)
    if mode != 1:
        cpu.s.ip = cpu.pop()
        return

    _inc_cs_word_preserve_cf(cpu, 0x515E)
    value = cpu.mem.rw(cs, 0x515E) & 0x0001
    cpu.mem.ww(cs, 0x515E, value)
    cpu.set_logic_flags(value, 16)
    cpu.mem.ww(cs, 0x95A4, 0xA000)
    if value != 0:
        cpu.mem.ww(cs, 0x95A4, 0xA200)
    cpu.s.ip = cpu.pop()
