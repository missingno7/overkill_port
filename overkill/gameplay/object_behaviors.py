"""Object behaviour families + logic dispatch for the OVERKILL object runtime.

Architecture layer: **lifted**.  The per-family object behaviour bodies
(B73E/B86D/B9F0/AB77/ABA3/AE09/8D4F/AED8/B24D, the ABCA sprite-0F collision, the
AD04 logic branch, the AB10 logic body) and the AA2B/EFAE logic dispatch +
object-logic scan.  Behaviours are reached by *address* through the hook
registry, not by direct Python call, so this module depends on the movement /
postmove / contact / bounds / deactivation seams but nothing depends back on it
except the thin object_runtime dispatch spine.  Conservative names only; bodies
relocated verbatim.
"""
from __future__ import annotations

from dos_re.cpu import CF, DF
from overkill.asm import (
    _add_mem_word, _add_reg16, _and_mem_word, _cmp_byte, _cmp_word,
    _inc_mem_word_preserve_cf, _sub_mem_word,
)
from overkill.gameplay.collision import (
    run_object_slot_scan_guard_ac81,
    run_post_contact_status_helper_9e19,
    run_tile_collision_probe_ac28,
)
from overkill.gameplay.contact_overlap import (
    CONTACT_SIDE_EFFECT_RETURN_IP,
    run_overlap_contact_selector_b250,
)
from overkill.gameplay.object_bounds import _run_object_bounds_tile_tail_ad60
from overkill.gameplay.object_movement import (
    _run_aee4_step_for_direction, _run_af22_three_pixel_step_for_direction,
    _run_movement_direction_5db2, _run_object_delta_helper_5e1b,
    run_object_target_move_b729, run_runtime_patched_object_steer_5e42,
)
from overkill.gameplay.object_postmove import _run_object_postmove_bc4b
from overkill.gameplay.object_runtime_common import (
    _call_verified_child_near, _no_patch_guard, _object_ptr_from_scan_index,
    _push_loop_count_for_interpreted_tail, _raise_unverified_path,
    _run_interpreted_near_call_observed,
)
from overkill.gameplay.object_spawns import _run_formation_spawn_7476_observed
from overkill.gameplay.objects import run_object_motion_table_ab34, run_object_scroll_sprite_ab4f
from overkill.recovered.systems.objects import (
    AD04_SPRITE_COLLISION_STATE,
    B9F0_HELPER_COUNTER_LIMIT,
    B9F0_HELPER_DIFFICULTY_FAST,
    B9F0_SPAWN_COUNTER_TRIGGER,
    B9F0_SPRITE_FRAME_OFFSET,
    B9F0_X_RIGHT_EDGE,
    CAMERA_NEAR_THRESHOLD,
    RENDER_MODE_FULL,
    LEVEL_PHASE_DISABLE_THRESHOLD,
    b9f0_low_counter_runs_helper,
    b9f0_periodic_helper_mask,
    b9f0_reached_target,
    b9f0_spawn_counter_ready,
    b9f0_sprite_from_frame,
    b9f0_wrapped_target_x,
    b9f0_wrapped_x_on_overflow,
    B73E_SPAWN_WINDOW_MAX,
    B73E_SPAWN_WINDOW_MIN,
    B73E_TARGET_POSTMOVE_232E_SENTINEL,
    B73E_TARGET_RESET_A47E_MAX,
    B73E_TARGET_RESET_DIRECT_COUNTER_MAX,
    B86D_FORMATION_SPAWN_TICKS,
    advance_formation_spawn_ptr,
    b73e_idle_sprite_frame,
    b73e_reaches_b808,
    b73e_target_reached_resolution,
    b86d_formation_spawn_tick_index,
    b86d_outgoing_sprite_for_delta,
    level_disable_threshold_reached,
    object_logic_ab10,
    object_logic_aba3,
    object_logic_ae09,
    object_logic_dispatch_aa2b,
    OBJECT_LOGIC_DISPATCH_AA2B_BY_LAYER,
)
from overkill.recovered.adapters.object_slot_adapter import read_object_slot_record
from overkill.recovered.views.object_slots import (
    ObjectSlotView,
    OFF_SUBSTATE, OFF_TARGET_X, OFF_TARGET_Y, OFF_X, OFF_Y,
)



def _call_ab34(cpu, return_ip: int) -> None:
    _call_verified_child_near(cpu, 0xAB34, lambda c: run_object_motion_table_ab34(c, _no_patch_guard), return_ip)


def _call_ab4f(cpu, return_ip: int) -> None:
    _call_verified_child_near(cpu, 0xAB4F, lambda c: run_object_scroll_sprite_ab4f(c, _no_patch_guard), return_ip)


def _call_ac28(cpu, return_ip: int) -> None:
    _call_verified_child_near(cpu, 0xAC28, lambda c: run_tile_collision_probe_ac28(c, _no_patch_guard), return_ip)


def _call_ac81(cpu, return_ip: int) -> None:
    _call_verified_child_near(cpu, 0xAC81, lambda c: run_object_slot_scan_guard_ac81(c, _no_patch_guard), return_ip)


def _run_object_behavior_b73e(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Lift the first branch layer of behavior B73E until its next helper call.

    The observed gameplay object (`logic_id=20h`, `substate=FFFFh`) enters the
    no-substate path, selects an animation frame, and when it has not reached
    its target Y/X yet it prepares DS:2304/2306 and calls B729 -> 5DB2.  We stop
    at that concrete helper instead of pretending the whole behavior is known.
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    slot = ObjectSlotView(cpu.mem, ss, bp)  # this object's record (SS:BP)

    def run_b85c_move_to_target() -> None:
        target_y_local = slot.target_y_word
        target_x_local = slot.target_x_word
        cpu.mem.ww(ds, 0x2308, 0x0002)
        cpu.mem.ww(ds, 0x2304, target_y_local)
        cpu.s.ax = target_x_local
        cpu.mem.ww(ds, 0x2306, target_x_local)
        # B85C reaches the movement helper through B862 CALL B729, then
        # B735 CALL 5DB2.  The lifted helper models AF60's self-call scratch
        # relative to the current SP, so keep both real return frames live while
        # running it; otherwise AF63 is written one frame too shallow and hook
        # verification later sees stale stack garbage around SS:SP.
        saved_sp = cpu.s.sp & 0xFFFF
        cpu.push(0xB865)
        cpu.push(0xB738)
        _run_movement_direction_5db2(cpu)
        cpu.s.sp = saved_sp
        _cmp_word(cpu, cpu.mem.rw(ds, 0x230A), 0)
        slot.direction_or_step = 0x0004
        _run_object_postmove_bc4b(cpu, parent=parent, chain=f"{chain} -> B73E -> B85C -> B729 -> 5DB2", cx_value=cx_value)
        cpu.s.ip = cpu.pop()

    def run_b800_spawn_pointer_advance(*, branch: str) -> None:
        # B800: advance the DS:20A6 formation-spawn list pointer (wrapping at
        # 20C7h back to 20A8h), then gate the 7476 formation spawn on the
        # fetched entry's low bit.  Shared verbatim by the direct B7BD path and
        # the B82D waypoint loop -- confirmed identical via live ASM trace
        # (both land on the same 4D95 advance-and-fetch, then AND BX,1/JNZ).
        # The pointer advance-and-wrap (which formation slot spawns next) is the pure system;
        # the intermediate pre-wrap write is unobservable (the wrap CMP + AND BX,1 flags are dead
        # here, overwritten by the 7476 call / target-reached CMPs before any boundary), so the
        # adapter writes the final pointer once.
        new_ptr = advance_formation_spawn_ptr(cpu.mem.rw(ds, 0x20A6))
        cpu.mem.ww(ds, 0x20A6, new_ptr)
        cpu.s.bx = cpu.mem.rw(ds, new_ptr)
        cpu.s.bx &= 0x0001
        if cpu.s.bx == 0:
            _run_formation_spawn_7476_observed(
                cpu, parent=parent, chain=f"{chain} -> B73E -> {branch}", cx_value=cx_value,
            )

    def run_b7c7_reset_target(*, check_2324: bool, branch: str) -> None:
        # B7C7/B7CE: choose a new target row, align it to 8 pixels, reset the
        # behavior substate, and tail-jump into the common BC4B post-move path.
        # B7C7 performs the DS:2324 guard first; B7CE is the direct path that
        # always reloads target_y from DS:2380+8.
        if check_2324:
            value_2324 = cpu.mem.rw(ds, 0x2324)
            _cmp_word(cpu, value_2324, 0x0001)
            should_reload_y = value_2324 != 0x0001
        else:
            should_reload_y = True
        if should_reload_y:
            # target_y = DS:2380 + 8.  The ADD's flags are dead: the AND below
            # overwrites them before the BC4B boundary.
            cpu.s.ax = (cpu.mem.rw(ds, 0x2380) + 0x0008) & 0xFFFF
            slot.target_y_word = cpu.s.ax
        _and_mem_word(cpu, ss, (bp + OFF_TARGET_Y) & 0xFFFF, 0xFFF8)
        cpu.mem.ww(ds, 0x2340, 0x0028)
        slot.substate = 0x0000
        slot.sprite_or_state = 0x0078
        slot.target_x_word = 0x0020
        _run_object_postmove_bc4b(
            cpu,
            parent=parent,
            chain=f"{chain} -> B73E -> B7BD -> {branch}",
            cx_value=cx_value,
        )
        cpu.s.ip = cpu.pop()

    substate = slot.substate
    _cmp_word(cpu, substate, 0xFFFF)
    if substate != 0xFFFF:
        cpu.s.bx = substate
        cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)
        target_ip = cpu.mem.rw(cpu.s.cs & 0xFFFF, (0xB74E + cpu.s.bx) & 0xFFFF)
        if target_ip == 0xB754:
            y = slot.y_word
            target_y = slot.target_y_word
            cpu.s.ax = y
            _cmp_word(cpu, y, target_y)
            if y != target_y:
                run_b85c_move_to_target()
                return
            x = slot.x_word
            target_x = slot.target_x_word
            cpu.s.ax = x
            _cmp_word(cpu, x, target_x)
            if x != target_x:
                run_b85c_move_to_target()
                return
            _add_mem_word(cpu, ss, (bp + OFF_SUBSTATE) & 0xFFFF, 1)
            _run_object_postmove_bc4b(cpu, parent=parent, chain=f"{chain} -> B73E -> B754", cx_value=cx_value)
            cpu.s.ip = cpu.pop()
            return
        if target_ip == 0xB770:
            slot.sprite_or_state = 0x0079
            _add_mem_word(cpu, ss, (bp + OFF_SUBSTATE) & 0xFFFF, 1)
            _run_object_postmove_bc4b(cpu, parent=parent, chain=f"{chain} -> B73E -> B770", cx_value=cx_value)
            cpu.s.ip = cpu.pop()
            return
        if target_ip == 0xB77B:
            _add_mem_word(cpu, ss, (bp + OFF_X) & 0xFFFF, 0x0004)
            _cmp_word(cpu, slot.x_word, 0x00A0)
            if slot.x_word >= 0x00A0:
                slot.sprite_or_state = 0x0077
            _run_object_postmove_bc4b(cpu, parent=parent, chain=f"{chain} -> B73E -> B77B", cx_value=cx_value)
            cpu.s.ip = cpu.pop()
            return
        _raise_unverified_path(
            cpu, parent=parent, chain=f"{chain} -> B73E[substate]",
            target_ip=target_ip, bp=bp, cx_value=cx_value,
        )

    # Idle animation-frame selection from the shared DS:2338 timer — the pure
    # recovered rule is the implementation (AX is overwritten immediately below).
    y = slot.y_word
    cpu.s.ax = b73e_idle_sprite_frame(cpu.mem.rw(ds, 0x2338), y)
    slot.sprite_or_state = cpu.s.ax

    target_y = slot.target_y_word
    cpu.s.ax = y
    _cmp_word(cpu, y, target_y)
    if y != target_y:
        # B85C: move toward the target; shared by Y-mismatch and X-mismatch.
        run_b85c_move_to_target()
        return

    x = slot.x_word
    target_x = slot.target_x_word
    cpu.s.ax = x
    _cmp_word(cpu, x, target_x)
    if x != target_x:
        run_b85c_move_to_target()
        return

    # B7BD reached when this object is already at its current target.  In the
    # observed gameplay state DS:A7A0 is below 23h, so the original immediately
    # falls through to the same BC4B post-move helper.  Keep that helper as the
    # next honest frontier rather than pretending the whole behavior is closed.
    _cmp_word(cpu, cpu.mem.rw(ds, 0xA7A0), 0x0023)
    if cpu.mem.rw(ds, 0xA7A0) < 0x0023:
        _run_object_postmove_bc4b(cpu, parent=parent, chain=f"{chain} -> B73E -> B7BD", cx_value=cx_value)
        cpu.s.ip = cpu.pop()
        return

    # Spawn-window gate: inside the DS:2340 counter band the behavior runs the
    # B800 formation spawn-pointer advance, otherwise control reaches B808 and
    # skips it.  The pure rule owns the band decision; the inline compares keep
    # the original two-step flag order.
    game_counter = cpu.mem.rw(ds, 0x2340)
    pure_reaches_b808 = b73e_reaches_b808(game_counter)
    _cmp_word(cpu, game_counter, B73E_SPAWN_WINDOW_MIN)
    if game_counter < B73E_SPAWN_WINDOW_MIN:
        reaches_b808 = True
    else:
        _cmp_word(cpu, game_counter, B73E_SPAWN_WINDOW_MAX)
        reaches_b808 = game_counter > B73E_SPAWN_WINDOW_MAX
    if reaches_b808 != pure_reaches_b808:
        raise AssertionError("pure B73E spawn-window gate disagrees with ASM-compatible compares")
    if not reaches_b808:
        run_b800_spawn_pointer_advance(branch="B7BD -> B800")

    # Target-reached resolution: pick how B73E continues from three globals.
    # The pure rule owns the 4-way classification; the inline compares keep the
    # original flag order at each branch.
    a47e = cpu.mem.rw(ds, 0xA47E)
    value_232e = cpu.mem.rw(ds, 0x232E)
    resolution = b73e_target_reached_resolution(a47e, game_counter, value_232e)

    _cmp_word(cpu, a47e, B73E_TARGET_RESET_A47E_MAX)
    if a47e <= B73E_TARGET_RESET_A47E_MAX:
        if resolution.kind != "reset_target_check_2324":
            raise AssertionError("pure B73E target-reached resolution disagrees on A47E reset")
        run_b7c7_reset_target(check_2324=True, branch="B808 -> B7C7 -> BC4B")
        return
    _cmp_word(cpu, game_counter, B73E_TARGET_RESET_DIRECT_COUNTER_MAX)
    if game_counter < B73E_TARGET_RESET_DIRECT_COUNTER_MAX:
        if resolution.kind != "reset_target_direct":
            raise AssertionError("pure B73E target-reached resolution disagrees on direct reset")
        run_b7c7_reset_target(check_2324=False, branch="B815 -> B7CE -> BC4B")
        return
    _cmp_word(cpu, value_232e, B73E_TARGET_POSTMOVE_232E_SENTINEL)
    if value_232e != B73E_TARGET_POSTMOVE_232E_SENTINEL:
        if resolution.kind != "postmove":
            raise AssertionError("pure B73E target-reached resolution disagrees on postmove")
        _run_object_postmove_bc4b(
            cpu,
            parent=parent,
            chain=f"{chain} -> B73E -> B7BD -> B7F3 -> BC4B",
            cx_value=cx_value,
        )
        cpu.s.ip = cpu.pop()
        return
    if resolution.kind != "waypoint_loop":
        raise AssertionError("pure B73E target-reached resolution missed the waypoint loop")

    # B82D IS a real retry loop, confirmed by a live trace of the x/y-matched
    # case (the tandy_text_score_gameplay snapshot): B857 "jz -> B826" jumps
    # STRAIGHT BACK to the waypoint-read with NO intervening A7A0 check and NO
    # DS:20A6 touch -- i.e. the loop-back skips the spawn-check entirely.  A
    # separate whole-corpus live trace (DS:20A6 BP-tagged writes across
    # 11000+ L4 frames) confirms the converse: B73E is dispatched once per
    # frame like any other behavior, and DS:20A6 is touched at most ONCE per
    # dispatch (B7BD's reaches_b808 check above already ran the spawn, once,
    # for every resolution kind including this one) -- so this loop's own
    # body must never call run_b800_spawn_pointer_advance itself.  Doing so
    # was exactly the bug a real trace caught: it double-spawned, giving L1's
    # forward-carry sweep an extra formation member (commit 2747255).  The
    # A7A0 check that used to sit in this loop was never actually observed on
    # the loop-back path either -- removed along with the spawn-check.
    for _ in range(0x20):
        cpu.s.si = cpu.mem.rw(ds, 0xA842)
        _cmp_word(cpu, cpu.s.si, 0xA894)
        if cpu.s.si >= 0xA894:
            cpu.mem.ww(ds, 0xA842, 0xA844)
            cpu.s.si = 0xA844
        else:
            cpu.s.si = cpu.mem.rw(ds, 0xA842)
        cpu.s.ax = cpu.mem.rw(ds, cpu.s.si)
        cpu.s.si = (cpu.s.si + 2) & 0xFFFF
        # target_x = waypoint + 0x20.  The ADD's flags are dead: the CMP below
        # overwrites them before the BC4B boundary.
        cpu.s.ax = (cpu.s.ax + 0x0020) & 0xFFFF
        slot.target_x_word = cpu.s.ax
        cpu.s.ax = cpu.mem.rw(ds, cpu.s.si)
        cpu.s.si = (cpu.s.si + 2) & 0xFFFF
        slot.target_y_word = cpu.s.ax
        cpu.mem.ww(ds, 0xA842, cpu.s.si)

        x = slot.x_word
        cpu.s.ax = x
        _cmp_word(cpu, x, slot.target_x_word)
        if x != slot.target_x_word:
            _run_object_postmove_bc4b(cpu, parent=parent, chain=f"{chain} -> B73E -> B7BD -> B82D -> BC4B", cx_value=cx_value)
            cpu.s.ip = cpu.pop()
            return
        y = slot.y_word
        cpu.s.ax = y
        _cmp_word(cpu, y, slot.target_y_word)
        if y != slot.target_y_word:
            _run_object_postmove_bc4b(cpu, parent=parent, chain=f"{chain} -> B73E -> B7BD -> B82D -> BC4B", cx_value=cx_value)
            cpu.s.ip = cpu.pop()
            return
        # Both matched: real ASM jumps straight back to the waypoint-read
        # (B857 "jz -> B826"), no spawn-check, no A7A0 check.
        continue
    _raise_unverified_path(
        cpu, parent=parent, chain=f"{chain} -> B73E -> B7BD -> B82D loop (0x20 iterations exhausted)",
        target_ip=0xB826, bp=bp, cx_value=cx_value,
    )


def _run_b250_overlap_contact_selector(cpu, *, caller: str) -> int:
    """Run the shared B250 overlap/contact selector.

    The selector itself now lives in :mod:`overkill.gameplay.contact_overlap`.
    This thin shim injects the *native* lifted ``9E19`` post-contact helper as the
    per-iteration side effect (a Phase-2 chain collapse: the hot ``B297`` loop no
    longer ping-pongs into interpreted ``9E19`` ASM), and returns the selected
    original tail IP (AD5A/ADC9) to the caller.
    """
    def post_contact_side_effect(c) -> None:
        # 9E19 is a near-ret helper: push its return IP (B29C) so its final RET
        # lands back in the B297 loop exactly like the original CALL 9E19 did.
        c.push(CONTACT_SIDE_EFFECT_RETURN_IP)
        # 9E19 is static code (not runtime-patched), so the no-op patch guard is
        # correct here, matching the other lifted object-runtime children.
        run_post_contact_status_helper_9e19(
            c, _no_patch_guard, _run_interpreted_near_call_observed
        )

    return run_overlap_contact_selector_b250(
        cpu, caller=caller, post_contact_side_effect=post_contact_side_effect
    )


def _run_object_behavior_b24d(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Lift the observed ``1010:B24D`` object-family behavior prelude.

    B24D is selected by the second-level EFAE object-family dispatcher in the
    active gameplay snapshot.  The hot path calls the runtime-patched 5E42
    steering helper, then runs the shared B250 overlap/contact selector.  This
    hook stops at the selected AD5A/ADC9 frontier; larger parents may compose
    those tails when their own verifier boundary requires a near return.
    """
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    slot = ObjectSlotView(cpu.mem, ss, bp)  # this object's record (SS:BP)

    # B24D: CALL 5E42.  The live 5E42 body is the runtime-patched gameplay
    # steering helper, not the cold executable bytes at the same address.
    cpu.push(0xB250)
    run_runtime_patched_object_steer_5e42(cpu)
    if (cpu.s.ip & 0xFFFF) != 0xB250:
        raise RuntimeError(f"5E42 returned to unexpected IP {cpu.s.ip:04X} inside B24D")

    # B250 -> the selected AD5A/ADC9 tail, now COMPOSED natively (the AED8 pattern) instead of
    # bouncing to the interpreted tail: both route to the recovered AD60 bounds/tile tail -- AD5A
    # first adds DS:A278 to X, ADC9 forces X = FFFFh.  Now that the B250 overlap predicate is pure,
    # B24D is a full native composition (5E42 steer + B250 overlap + AD60 bounds/tile).
    selected_tail = _run_b250_overlap_contact_selector(cpu, caller="B24D")
    if selected_tail == 0xAD5A:
        _run_object_bounds_tile_tail_ad60(
            cpu, parent=parent, chain=f"{chain} -> B24D -> B250 -> AD5A",
            cx_value=cx_value, add_a278_to_x=True,
        )
        return
    if selected_tail == 0xADC9:
        slot.x_word = 0xFFFF
        _run_object_bounds_tile_tail_ad60(
            cpu, parent=parent, chain=f"{chain} -> B24D -> B250 -> ADC9",
            cx_value=cx_value, add_a278_to_x=False,
        )
        return
    cpu.s.ip = selected_tail  # defensive: any unexpected tail keeps the original frontier bounce


def _run_object_behavior_b86d(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Lift observed 1010:B86D object-slot behavior branches.

    This is still low-level object-runtime logic: it updates slot coordinates,
    sprite words, movement-target globals, and then joins the shared BC4B
    post-move/collision tail.  The B8F8 edge-steering tail is now covered too;
    less frequent later B90x/B93x/B96x continuations remain separate frontiers.
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    slot = ObjectSlotView(cpu.mem, ss, bp)  # this object's record (SS:BP)
    mem = cpu.mem

    def call_7476(return_ip: int) -> None:
        # B86D's 7476 is the recovered formation spawn (used directly by B73E); call it
        # natively instead of bouncing to the interpreter, then resume at the return IP.
        _run_formation_spawn_7476_observed(cpu, parent=parent, chain=chain, cx_value=cx_value)
        cpu.s.ip = return_ip & 0xFFFF

    def run_b729_target_move(return_ip: int, *, mode: int) -> bool:
        mem.ww(ds, 0x2308, mode & 0xFFFF)
        _call_verified_child_near(
            cpu,
            0xB729,
            lambda c: run_object_target_move_b729(c, _no_patch_guard),
            return_ip & 0xFFFF,
        )
        if (cpu.s.ip & 0xFFFF) != (return_ip & 0xFFFF):
            raise RuntimeError(f"B729 returned to unexpected IP {cpu.s.ip:04X} inside B86D")
        _cmp_word(cpu, mem.rw(ds, 0x230A), 0)
        return mem.rw(ds, 0x230A) == 0

    def run_b8f8_edge_steer() -> None:
        # B8F8: object has crossed the B86D entry guard (early global phase or
        # X > 00C0h).  Steer it back toward the DS:237C reference box, force the
        # outgoing sprite, then join the shared post-move/collision boundary.
        cpu.s.bx = 0x237C
        _run_object_delta_helper_5e1b(cpu)
        cpu.push(0xB901)
        run_runtime_patched_object_steer_5e42(cpu)
        if (cpu.s.ip & 0xFFFF) != 0xB901:
            raise RuntimeError(f"5E42 returned to unexpected IP {cpu.s.ip:04X} inside B86D/B8F8")
        slot.sprite_or_state = 0x0076
        cpu.s.ip = 0xBC4B

    # All three guard CMPs below have dead flags: each branch overwrites them
    # before its boundary (the B8F8 edge-steer runs 5E42, the A7A0 block runs an
    # AND-into-memory, and the fall-through reaches the NEG/ADD).
    if mem.rw(ds, 0xA47E) <= 0x0002:
        run_b8f8_edge_steer()
        return

    x = slot.x_word
    if x > 0x00C0:
        run_b8f8_edge_steer()
        return

    if mem.rw(ds, 0xA7A0) < 0x0028:
        mem.ww(ds, 0x2308, 0x0001)
        slot.sprite_or_state = 0x0075
        _and_mem_word(cpu, ss, (bp + OFF_TARGET_Y) & 0xFFFF, 0xFFFE)
        _and_mem_word(cpu, ss, (bp + OFF_Y) & 0xFFFF, 0xFFFE)
        _and_mem_word(cpu, ss, (bp + OFF_TARGET_X) & 0xFFFF, 0xFFFE)
        _and_mem_word(cpu, ss, (bp + OFF_X) & 0xFFFF, 0xFFFE)
        if not run_b729_target_move(0xB8A3, mode=1):
            slot.direction_or_step = 0x0004
        cpu.s.ip = 0xBC4B
        return

    # Formation-spawn schedule: a CALL 7476 fires only on the exact DS:2340
    # ticks owned by the pure rule.  The tick-match CMP flags are dead -- the
    # NEG/ADD below always runs after this block and overwrites them before the
    # BC4B boundary; the 7476 continuation addresses are adapter glue.
    formation_spawn_return_ips = (0xB8BB, 0xB8C6, 0xB8D0)
    game_counter = mem.rw(ds, 0x2340)
    spawn_index = b86d_formation_spawn_tick_index(game_counter)
    if game_counter == B86D_FORMATION_SPAWN_TICKS[0]:
        if spawn_index != 0:
            raise AssertionError("pure B86D formation-spawn schedule disagrees on tick 0")
        call_7476(formation_spawn_return_ips[0])
    else:
        if game_counter == B86D_FORMATION_SPAWN_TICKS[1]:
            if spawn_index != 1:
                raise AssertionError("pure B86D formation-spawn schedule disagrees on tick 1")
            call_7476(formation_spawn_return_ips[1])
        else:
            if game_counter == B86D_FORMATION_SPAWN_TICKS[2]:
                if spawn_index != 2:
                    raise AssertionError("pure B86D formation-spawn schedule disagrees on tick 2")
                call_7476(formation_spawn_return_ips[2])
            elif spawn_index is not None:
                raise AssertionError("pure B86D formation-spawn schedule fired on a non-tick counter")

    # X += -delta (live), then the pure rule selects the outgoing sprite from the
    # sign of the global vertical delta.  AX holds the sprite at the BC4B boundary.
    delta = mem.rw(ds, 0x2342)
    cpu.s.ax = (-delta) & 0xFFFF
    _add_mem_word(cpu, ss, (bp + OFF_X) & 0xFFFF, cpu.s.ax)
    cpu.s.ax = b86d_outgoing_sprite_for_delta(delta)
    slot.sprite_or_state = cpu.s.ax
    _cmp_word(cpu, mem.rw(ds, 0x2328), 0x0007)
    if mem.rw(ds, 0x2328) == 0x0007:
        _inc_mem_word_preserve_cf(cpu, ss, (bp + OFF_X) & 0xFFFF)
    cpu.s.ip = 0xBC4B


def _run_object_behavior_b9f0(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Lift observed object-family behavior at ``1010:B9F0`` up to ``BC4B``.

    B9F0 is the hot behavior selected by ``EFAE`` for the current gameplay
    snapshot.  The routine updates the object's target-position fields from the
    global motion deltas and then either:

    * refreshes its sprite/animation word and jumps directly to ``BC4B``; or
    * prepares ``DS:2304/2306/2308``, calls the already verified ``5DB2``
      movement helper, and jumps to ``BC4B``.

    Less frequent helper calls are kept explicit and bounded.  They either use
    already-lifted helpers (7476 formation spawn, 5DB2 movement) or narrowly run
    the original helper until its real near-return continuation.
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    slot = ObjectSlotView(cpu.mem, ss, bp)  # this object's record (SS:BP)
    mem = cpu.mem

    def call_7476(return_ip: int, why: str) -> None:
        # 7476/5E1B/5E42 are recovered hooks (used natively by B73E/B86D and proven
        # full-memory-faithful), so call them directly instead of bouncing to the
        # interpreter, then resume at the near-call return IP.
        _run_formation_spawn_7476_observed(cpu, parent=parent, chain=chain, cx_value=cx_value)
        cpu.s.ip = return_ip & 0xFFFF

    def call_5e1b(return_ip: int) -> None:
        _run_object_delta_helper_5e1b(cpu)
        cpu.s.ip = return_ip & 0xFFFF

    def call_5e42(return_ip: int) -> None:
        cpu.push(return_ip & 0xFFFF)
        run_runtime_patched_object_steer_5e42(cpu)
        if (cpu.s.ip & 0xFFFF) != (return_ip & 0xFFFF):
            raise RuntimeError(f"5E42 returned to unexpected IP {cpu.s.ip:04X} inside B9F0")

    def run_ba5a_helper_branch() -> None:
        # BA56 is reached only from the counter-wrap tests; BA5A itself is also
        # used directly when A47E < 6.  The caller performs the optional INC.
        # After BA63 the original falls through to BA67, so this helper only
        # performs the motion work and leaves AX/flags live for the BA67 block.
        cpu.s.bx = 0x237C
        call_5e1b(0xBA60)
        call_5e42(0xBA63)
        _add_mem_word(cpu, ss, (bp + OFF_X) & 0xFFFF, 0x0002)

    # B9F0: CMP DS:A482,A4E4 / JNE BA67.
    _cmp_word(cpu, mem.rw(ds, 0xA482), 0xA4E4)
    if mem.rw(ds, 0xA482) == 0xA4E4:
        # B9F8..BA03: one exact tick calls 7476 before continuing.
        _cmp_word(cpu, mem.rw(ds, 0x2340), 0x02EF)
        if mem.rw(ds, 0x2340) == 0x02EF:
            call_7476(0xBA03, "BA00 CALL 7476")
            _inc_mem_word_preserve_cf(cpu, ds, 0x2340)

        # BA07..BA10: apply global target deltas into +32/+34.
        cpu.s.ax = mem.rw(ds, 0x2342)
        _add_mem_word(cpu, ss, (bp + OFF_TARGET_Y) & 0xFFFF, cpu.s.ax)
        cpu.s.ax = mem.rw(ds, 0x2346)
        _add_mem_word(cpu, ss, (bp + OFF_TARGET_X) & 0xFFFF, cpu.s.ax)

        # BA13..BA1A: wrap target X back to the left edge once it passes the right
        # edge.  The CMP flag is replayed for fidelity but is dead by the next boundary.
        target_x = slot.target_x_word
        _cmp_word(cpu, target_x, B9F0_X_RIGHT_EDGE)
        wrapped_x = b9f0_wrapped_target_x(target_x)
        if wrapped_x != target_x:
            slot.target_x_word = wrapped_x

        # BA1F..BA31: if current position plus vertical delta reached target, use the
        # direct sprite-refresh/helper branch; otherwise branch to BA99.  The decision is
        # the recovered rule, now taking the native slot record (Phase 2); the AX writes
        # and CMP flags are replayed from its fields for boundary fidelity (the Y+delta
        # ADD's flags are dead -- the CMP below overwrites them).
        delta_y = mem.rw(ds, 0x2342)
        record = read_object_slot_record(slot)
        reached_target = b9f0_reached_target(record, delta_y)
        cpu.s.ax = record.y_word
        cpu.s.ax = (cpu.s.ax + delta_y) & 0xFFFF
        target_y = record.target_y_word
        _cmp_word(cpu, cpu.s.ax, target_y)
        if cpu.s.ax == target_y:
            cpu.s.ax = record.x_word
            target_x = record.target_x_word
            _cmp_word(cpu, cpu.s.ax, target_x)

        if reached_target:
            # BA33..BA5A: low level/tick branches call two helper leaves, then
            # advance X by two pixels before BC4B.  The common path falls through
            # to BA67 after failing the counter mask test.
            _cmp_word(cpu, mem.rw(ds, 0xA47E), B9F0_HELPER_COUNTER_LIMIT)
            ran_helper = False
            if b9f0_low_counter_runs_helper(mem.rw(ds, 0xA47E)):
                run_ba5a_helper_branch()
                ran_helper = True

            if not ran_helper:
                # BA3D..BA5A: the BA5A helper also fires on a periodic tick of DS:2340 --
                # every 128th tick on the fast difficulty (DS:BEDC == 2, mask 7Fh), else
                # every 256th (mask FFh).  The recovered rule owns the difficulty->mask
                # choice; the AND's flags are dead (the CMP below overwrites them).
                cpu.s.ax = mem.rw(ds, 0x2340)
                bedc = mem.rw(ds, 0xBEDC)
                _cmp_word(cpu, bedc, B9F0_HELPER_DIFFICULTY_FAST)
                tick_mask = b9f0_periodic_helper_mask(bedc)
                cpu.s.ax &= tick_mask
                _cmp_word(cpu, cpu.s.ax, tick_mask)
                if cpu.s.ax == tick_mask:
                    _inc_mem_word_preserve_cf(cpu, ds, 0x2340)
                    run_ba5a_helper_branch()
                    ran_helper = True
            # BA67 path below.
        else:
            # BA99: decide whether to move toward the target through 5DB2 or use
            # the overshoot helper branch.
            cpu.s.ax = slot.x_word
            target_x = slot.target_x_word
            _cmp_word(cpu, cpu.s.ax, target_x)
            if cpu.s.ax > target_x:
                # BAA1..BABA: helper call, optional spawn, then either continue
                # to BC4B or wrap Y to 10h on unsigned overflow.
                call_5e42(0xBAA4)
                _cmp_word(cpu, mem.rw(ds, 0xA47E), B9F0_HELPER_COUNTER_LIMIT)
                if b9f0_low_counter_runs_helper(mem.rw(ds, 0xA47E)):
                    _cmp_word(cpu, mem.rw(ds, 0x232E), B9F0_SPAWN_COUNTER_TRIGGER)
                    if b9f0_spawn_counter_ready(mem.rw(ds, 0x232E)):
                        call_7476(0xBAB5, "BAB2 CALL 7476")
                x_now = slot.x_word
                _cmp_word(cpu, x_now, B9F0_X_RIGHT_EDGE)
                wrapped_now = b9f0_wrapped_x_on_overflow(x_now)
                if wrapped_now != x_now:
                    slot.x_word = wrapped_now
                cpu.s.ip = 0xBC4B
                return

            # BA73..BA8D: align target/current coordinates and publish movement
            # target globals.
            cpu.s.ax = slot.target_y_word
            cpu.s.ax &= 0xFFFE
            _and_mem_word(cpu, ss, (bp + OFF_Y) & 0xFFFF, 0xFFFE)
            mem.ww(ds, 0x2304, cpu.s.ax)
            cpu.s.ax = slot.target_x_word
            cpu.s.ax &= 0xFFFE
            _and_mem_word(cpu, ss, (bp + OFF_X) & 0xFFFF, 0xFFFE)
            mem.ww(ds, 0x2306, cpu.s.ax)
            mem.ww(ds, 0x2308, 0x0001)

            # BA93: CALL 5DB2.  Push/pop the real return word so full-memory
            # verifier snapshots see the same balanced call scratch below SP.
            cpu.push(0xBA96)
            _run_movement_direction_5db2(cpu)
            cpu.s.ip = cpu.pop()
            if (cpu.s.ip & 0xFFFF) != 0xBA96:
                raise RuntimeError(f"5DB2 returned to unexpected IP {cpu.s.ip:04X} inside B9F0")
            cpu.s.ip = 0xBC4B
            return

    # BA67..BA70: update sprite/animation word from current global frame and
    # jump into the shared post-move helper.
    frame = mem.rw(ds, 0x233C)
    cpu.s.ax = frame
    _add_reg16(cpu, 0, B9F0_SPRITE_FRAME_OFFSET)  # AX = frame + 1Ch
    slot.sprite_or_state = b9f0_sprite_from_frame(frame)
    cpu.s.ip = 0xBC4B


def _run_object_family_dispatch_efae(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Run EFAE's prologue and leave IP at the concrete second-level target.

    EFAE is a dispatcher, not a behavior body.  It publishes the object's current
    Y/X into DS:D1FE/D200 and then jumps through a second table indexed by
    SS:[BP+18].  Keep this boundary conservative: do not run the selected
    gameplay routine inline here.
    """
    ss = cpu.s.ss & 0xFFFF
    ds = cpu.s.ds & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    slot = ObjectSlotView(cpu.mem, ss, bp)  # this object's record (SS:BP)

    cpu.s.ax = slot.y_word
    cpu.mem.ww(ds, 0xD1FE, cpu.s.ax)
    cpu.s.ax = slot.x_word
    cpu.mem.ww(ds, 0xD200, cpu.s.ax)

    cpu.s.bx = slot.logic_id
    cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)  # SHL BX,1
    target_ip = cpu.mem.rw(cpu.s.cs & 0xFFFF, (0xEFC4 + cpu.s.bx) & 0xFFFF)
    cpu.s.ip = target_ip


def _run_object_behavior_ab77(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Lift the observed AB77 object-behaviour driver without duplicating leaves.

    AB77 is the shared tail reached from AD04's tracked-object branches
    (AB71/AB69/AB61).  The hot observed path is: choose the scroll-relative
    sprite through AB4F, probe tile collision through AC28, scan object overlaps
    through AC81/AC97, then return if nothing was hit.  The unobserved collision
    continuations remain as exact original IP continuations instead of being
    guessed here.
    """
    ds = cpu.s.ds & 0xFFFF
    mem = cpu.mem

    v2384 = mem.rw(ds, 0x2384)
    _cmp_word(cpu, v2384, LEVEL_PHASE_DISABLE_THRESHOLD)  # replay the gate CMP flags
    if level_disable_threshold_reached(v2384):
        cpu.s.ip = 0xAB8F
        return

    _call_ab4f(cpu, 0xAB81)
    if cpu.s.ip != 0xAB81:
        _raise_unverified_path(cpu, parent=parent, chain=f"{chain} -> AB4F", target_ip=cpu.s.ip, bp=cpu.s.bp, cx_value=cx_value)

    _call_ac28(cpu, 0xAB84)
    if cpu.s.ip == 0xAA44:
        cpu.set_flag(CF, False)
        cpu.s.ip = cpu.pop()
    if cpu.s.ip != 0xAB84:
        _raise_unverified_path(cpu, parent=parent, chain=f"{chain} -> AC28", target_ip=cpu.s.ip, bp=cpu.s.bp, cx_value=cx_value)
    if cpu.get_flag(CF):
        cpu.s.ip = 0xAB8F
        return

    _call_ac81(cpu, 0xAB89)
    if cpu.s.ip == 0xAA44:
        cpu.set_flag(CF, False)
        cpu.s.ip = cpu.pop()
    if cpu.s.ip == 0xACD9:
        return
    if cpu.s.ip != 0xAB89:
        _raise_unverified_path(cpu, parent=parent, chain=f"{chain} -> AC81", target_ip=cpu.s.ip, bp=cpu.s.bp, cx_value=cx_value)
    if cpu.get_flag(CF):
        cpu.s.ip = 0xAB8C
        return

    # AB8B RET
    cpu.s.ip = cpu.pop()


def _run_tracked_object_selector_to_ab77(cpu, *, selector_addr: int) -> None:
    """Mirror the tiny AB59/AB61/AB69/AB71 selector stubs before AB77.

    These are not independent object behaviours.  Each writes the address of one
    tracked-object global into DS:A42C, then jumps into the shared AB77 tail.
    Keeping them as one helper makes the AD04 frontier explicit without
    duplicating AB77 itself.
    """
    cpu.mem.ww(cpu.s.ds & 0xFFFF, 0xA42C, selector_addr & 0xFFFF)
    cpu.s.ip = 0xAB77


def _run_object_sprite0f_collision_abca(
    cpu,
    *,
    parent: str,
    chain: str,
    cx_value: int,
    run_original_near_call,
) -> None:
    """Lift the observed ABCA sprite-0F/tracked collision behaviour.

    ABCA is reached from AD04 when the slot sprite field is 000Fh.  The hot
    cold-start/attract path derives a motion-table position through AB34,
    probes tiles through AC28, then scans nearby object slots through AC81.
    Collision/deactivation continuations are preserved either through existing
    lifted helpers or through bounded original calls for the still-separate
    animation/reinitialization leaves.
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    mem = cpu.mem

    def finish_deactivate_tail(*, call_ab99: bool) -> None:
        mem.ww(ds, 0xA96E, 0xFFFF)
        if call_ab99:
            run_original_near_call(cpu, 0xAB99, 0xABF3)
            if cpu.s.ip != 0xABF3:
                _raise_unverified_path(
                    cpu, parent=parent, chain=f"{chain} -> AB99",
                    target_ip=cpu.s.ip, bp=cpu.s.bp, cx_value=cx_value,
                )

        bp = cpu.s.bp & 0xFFFF
        slot = ObjectSlotView(mem, ss, bp)  # this object's record (SS:BP)
        _cmp_word(cpu, bp, 0xFFFF)
        if bp == 0xFFFF:
            cpu.s.ip = cpu.pop()
            return

        _cmp_byte(cpu, mem.rb(ds, 0x98C0), 0x00)
        if mem.rb(ds, 0x98C0) != 0:
            mem.wb(ds, 0xBEFF, 0x19)

        slot.logic_id = 0x0001
        slot.hazard_class = 0x0004  # OFF_DRAW_LAYER aliases hazard_class
        slot.transition_latch = 0x0000
        slot.sprite_or_state = 0x0000

        cpu.push(bp)
        run_original_near_call(cpu, 0x837A, 0xAC1D)
        if cpu.s.ip != 0xAC1D:
            _raise_unverified_path(
                cpu, parent=parent, chain=f"{chain} -> 837A",
                target_ip=cpu.s.ip, bp=cpu.s.bp, cx_value=cx_value,
            )
        run_original_near_call(cpu, 0x859E, 0xAC20)
        if cpu.s.ip != 0xAC20:
            _raise_unverified_path(
                cpu, parent=parent, chain=f"{chain} -> 859E",
                target_ip=cpu.s.ip, bp=cpu.s.bp, cx_value=cx_value,
            )
        cpu.s.bp = cpu.pop()
        cpu.s.ip = cpu.pop()

    v2384 = mem.rw(ds, 0x2384)
    # Frame-phase gate DS:2384, shared with AB10/ABA3/AB77: below the disable
    # threshold the collision body runs its motion/tile-probe path; at/after it the
    # object deactivates.  The CMP flags are dead (overwritten by AB34/AC28 when the
    # branch is taken, and by finish_deactivate_tail's own CMP otherwise).
    _cmp_word(cpu, v2384, LEVEL_PHASE_DISABLE_THRESHOLD)
    if not level_disable_threshold_reached(v2384):
        cpu.s.dx = 0xA420
        _call_ab34(cpu, 0xABD7)
        if cpu.s.ip != 0xABD7:
            _raise_unverified_path(
                cpu, parent=parent, chain=f"{chain} -> AB34",
                target_ip=cpu.s.ip, bp=cpu.s.bp, cx_value=cx_value,
            )

        _call_ac28(cpu, 0xABDA)
        if cpu.s.ip == 0xAA44:
            cpu.set_flag(CF, False)
            cpu.s.ip = cpu.pop()
        if cpu.s.ip != 0xABDA:
            _raise_unverified_path(
                cpu, parent=parent, chain=f"{chain} -> AC28",
                target_ip=cpu.s.ip, bp=cpu.s.bp, cx_value=cx_value,
            )
        # ABDA: JAE ABE4.  If CF is set, fall through to ABDC/ABF3.
        if not cpu.get_flag(CF):
            _call_ac81(cpu, 0xABE7)
            if cpu.s.ip == 0xAA44:
                cpu.set_flag(CF, False)
                cpu.s.ip = cpu.pop()
            if cpu.s.ip == 0xACD9:
                return
            if cpu.s.ip != 0xABE7:
                _raise_unverified_path(
                    cpu, parent=parent, chain=f"{chain} -> AC81",
                    target_ip=cpu.s.ip, bp=cpu.s.bp, cx_value=cx_value,
                )
            if not cpu.get_flag(CF):
                cpu.s.ip = cpu.pop()
                return
            finish_deactivate_tail(call_ab99=True)
            return

    finish_deactivate_tail(call_ab99=False)


def _run_object_logic_branch_ad04(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Mirror the 1010:AD04 small object-logic branch selector.

    AD04 is a hot first-level object logic target, not a full behavior body.  It
    decides whether to return immediately or jump into one of the nearby ABxx
    behavior tails according to global state and a handful of tracked object
    pointer globals.  Keeping it as a branch selector avoids duplicating those
    ABxx bodies while removing the tiny interpreted hotspot cluster.
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    slot = ObjectSlotView(cpu.mem, ss, bp)  # this object's record (SS:BP)
    mem = cpu.mem

    bdac = mem.rw(ds, 0xBDAC)
    # The BDAC==1 test's flags are dead: every path overwrites them (the 2350 CMP
    # when taken, the sprite CMP when not) before reaching a boundary.  The
    # render-mode / near-camera gate is shared with the A8C7 layer-1 scan.
    if bdac != RENDER_MODE_FULL:
        v2350 = mem.rw(ds, 0x2350)
        _cmp_word(cpu, v2350, CAMERA_NEAR_THRESHOLD)
        if v2350 <= CAMERA_NEAR_THRESHOLD:
            cpu.s.ip = cpu.pop()
            return

    sprite = slot.sprite_or_state
    _cmp_word(cpu, sprite, AD04_SPRITE_COLLISION_STATE)
    if sprite == AD04_SPRITE_COLLISION_STATE:
        cpu.s.ip = 0xABCA
        return

    for global_off, target_ip in (
        (0xA966, 0xAB71),
        (0xA968, 0xAB69),
        (0xA96A, 0xAB61),
        (0xA96C, 0xAB59),
    ):
        tracked = mem.rw(ds, global_off)
        _cmp_word(cpu, bp, tracked)
        if bp == tracked:
            cpu.s.ip = target_ip
            return

    cpu.s.bx = 0xA962
    tracked = mem.rw(ds, 0xA962)
    _cmp_word(cpu, bp, tracked)
    if bp == tracked:
        cpu.s.ip = 0xABA3
        return

    cpu.s.bx = 0xA964
    tracked = mem.rw(ds, 0xA964)
    _cmp_word(cpu, bp, tracked)
    if bp == tracked:
        cpu.s.ip = 0xABA3
        return

    cpu.s.ip = cpu.pop()


def _run_object_behavior_aba3(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Lift the observed ABA3 tracked-object follower probe.

    ABA3 is reached from AD04 when the current slot matches one of the global
    tracked object pointers at A962/A964.  The observed hot path stores the
    selected tracker pointer in DS:A42E, derives a scroll-relative sprite index
    from DS:233C+14h, and reuses the already lifted AC81/AC97 object-slot scan
    guard.  Collision continuations after the CF-set branch are preserved as
    original IP continuations until they are separately understood.
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    slot = ObjectSlotView(cpu.mem, ss, bp)  # this object's record (SS:BP)
    mem = cpu.mem

    mem.ww(ds, 0xA42E, cpu.s.bx)
    v2384 = mem.rw(ds, 0x2384)
    update = object_logic_aba3(v2384, mem.rw(ds, 0x233C))
    _cmp_word(cpu, v2384, LEVEL_PHASE_DISABLE_THRESHOLD)  # replay the gate CMP flags
    if update.branch_abc0:
        cpu.s.ip = 0xABC0
        return

    # Sprite = scroll frame (DS:233C) + 0x14.  The ADD's flags are dead: the
    # AC81 call below overwrites them (its CF is what the branches below read).
    cpu.s.ax = update.sprite
    slot.sprite_or_state = update.sprite

    _call_ac81(cpu, 0xABBA)
    if cpu.s.ip == 0xAA44:
        cpu.set_flag(CF, False)
        cpu.s.ip = cpu.pop()
    if cpu.s.ip == 0xACD9:
        return
    if cpu.s.ip != 0xABBA:
        _raise_unverified_path(cpu, parent=parent, chain=f"{chain} -> AC81", target_ip=cpu.s.ip, bp=cpu.s.bp, cx_value=cx_value)
    if cpu.get_flag(CF):
        cpu.s.ip = 0xABBD
        return
    cpu.s.ip = cpu.pop()


def _run_object_behavior_ae09(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Observed EFAE logic-id 0Ch behavior: timer, 3-pixel step, then AD60 tail."""
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    slot = ObjectSlotView(cpu.mem, ss, bp)  # this object's record (SS:BP)

    update = object_logic_ae09(slot.substate, slot.direction_or_step)
    slot.substate = update.substate
    slot.direction_or_step = update.direction_or_step
    if update.decrement_x:
        slot.x_word = (slot.x_word - 2) & 0xFFFF

    # Outgoing sprite = direction/step + 0x28.  Every CMP/DEC/SUB/ADD flag of the
    # AE09 body is dead at the AF22 tail boundary (AF22's first ops overwrite them),
    # so no flag replay is needed; the rule owns the timer/step/sprite decision.
    cpu.s.ax = update.sprite
    slot.sprite_or_state = update.sprite

    _run_af22_three_pixel_step_for_direction(cpu, parent="1010:AF22")
    _run_object_bounds_tile_tail_ad60(
        cpu,
        parent=parent,
        chain=f"{chain} -> AE09",
        cx_value=cx_value,
        add_a278_to_x=False,
    )


def _run_object_behavior_8d4f(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Lift the observed logic_id=1Fh target-patrol behavior at 1010:8D4F.

    The body is mostly an overlay far-call (`1F8F:027A`) that reads the next
    waypoint pair from DS:A482, publishes target X/Y to DS:2306/2304, sets
    movement mode 3, calls the generic 5DB2 direction helper through the far
    trampoline at 1010:8D8B, then returns to 8D54 and joins BC4B.
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    cpu.s.si = mem.rw(ds, 0xA482)
    cpu.s.ax = mem.rw(ds, cpu.s.si)
    cpu.s.si = (cpu.s.si + 2) & 0xFFFF
    old_ax = cpu.s.ax
    cpu.s.ax = (cpu.s.ax + 0x0020) & 0xFFFF
    cpu.set_add_flags(old_ax, 0x0020, old_ax + 0x0020, 16)
    mem.ww(ds, 0x2306, cpu.s.ax)
    cpu.s.ax = mem.rw(ds, cpu.s.si)
    cpu.s.si = (cpu.s.si + 2) & 0xFFFF
    mem.ww(ds, 0x2304, cpu.s.ax)
    mem.ww(ds, 0x2308, 0x0003)
    cpu.s.ax = 0x5DB2
    # Faithfully reproduce the call frame the original leaves below SP -- OVERKILL
    # reads this scratch through its self-call tricks, so an approximation diverges:
    #   8D4F      CALL FAR 1F8F:027A   pushes CS=1010, IP=8D54
    #   1F8F:0292 CALL FAR 1010:8D8B   pushes CS=1F8F, IP=0297
    #   1010:8D8B CALL AX (=5DB2)      pushes IP=8D8D
    # 5DB2 then runs and three RET/RETF pops unwind the frame back to 8D54.
    cpu.push(0x1010)
    cpu.push(0x8D54)
    cpu.push(0x1F8F)
    cpu.push(0x0297)
    cpu.push(0x8D8D)
    _run_movement_direction_5db2(cpu)
    cpu.s.sp = (cpu.s.sp + 0x000A) & 0xFFFF  # RET 5DB2 + RETF 8D8D + RETF 1F8F:0451
    _run_object_postmove_bc4b(cpu, parent=parent, chain=f"{chain} -> 8D4F -> 1F8F:027A -> 5DB2", cx_value=cx_value)
    cpu.s.ip = cpu.pop()


def _run_object_behavior_aed8(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Lift the observed EFAE logic_id=2 movement/tile-probe branch at AED8."""
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    slot = ObjectSlotView(cpu.mem, ss, bp)  # this object's record (SS:BP)
    mem = cpu.mem

    _sub_mem_word(cpu, ss, (bp + OFF_SUBSTATE) & 0xFFFF, 1)
    if slot.substate == 0:
        _raise_unverified_path(cpu, parent=parent, chain=f"{chain} -> AED8 timer expired", target_ip=0xADC9, bp=bp, cx_value=cx_value)

    cpu.s.ax = 0xB250
    _run_aee4_step_for_direction(cpu)

    selected_tail = _run_b250_overlap_contact_selector(cpu, caller="AED8")
    if selected_tail == 0xAD5A:
        _run_object_bounds_tile_tail_ad60(
            cpu,
            parent=parent,
            chain=f"{chain} -> AED8 -> B250 -> AD5A",
            cx_value=cx_value,
            add_a278_to_x=True,
        )
        return
    if selected_tail == 0xADC9:
        # ADC9: MOV SS:[BP+02],FFFFh; JMP AD60.  Unlike AD5A, this tail does
        # not first add DS:A278 to X.
        slot.x_word = 0xFFFF
        _run_object_bounds_tile_tail_ad60(
            cpu,
            parent=parent,
            chain=f"{chain} -> AED8 -> B250 -> ADC9",
            cx_value=cx_value,
            add_a278_to_x=False,
        )
        return
    raise RuntimeError(f"unexpected B250 selector target 1010:{selected_tail:04X} inside AED8")


def _run_object_logic_ab10(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Lift the observed AA2B target AB10 position/sprite update helper.

    AB10 is a first-level object logic target for SS:[BP+16] == 6 in the current
    island.  The gameplay decision -- deactivate once the level frame phase
    (DS:2384) or the global disable counter (DS:A47C) reaches 0003h, else the
    DS:A40C animation-frame sprite and the DS:A414 animation-pair position offset by
    the DS:237C view reference box -- now lives in the recovered pure rule
    ``object_logic_ab10``.  This adapter owns the DOS reads, the XLAT/animation-pair
    addressing, and the original CMP/ADD flags + register state at the RET boundary.
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    slot = ObjectSlotView(cpu.mem, ss, bp)  # this object's record (SS:BP)
    mem = cpu.mem

    v2384 = mem.rw(ds, 0x2384)
    _cmp_word(cpu, v2384, LEVEL_PHASE_DISABLE_THRESHOLD)
    if level_disable_threshold_reached(v2384):
        mem.ww(ss, bp, 0x0000)
        cpu.s.ip = cpu.pop()
        return

    global_disable = mem.rw(ds, 0xA47C)
    _cmp_word(cpu, global_disable, LEVEL_PHASE_DISABLE_THRESHOLD)
    if level_disable_threshold_reached(global_disable):
        mem.ww(ss, bp, 0x0000)
        cpu.s.ip = cpu.pop()
        return

    # Sprite source byte: XLAT(DS:A40C, DS:2336), AH preserved (the rule adds 9).
    anim_counter = mem.rw(ds, 0x2336)
    sprite_table_value = (anim_counter & 0xFF00) | mem.rb(ds, (0xA40C + (anim_counter & 0x00FF)) & 0xFFFF)

    # Animation pair at DS:A414 indexed by the frame phase, walked DF-controlled.
    si = (((v2384 << 2) & 0xFFFF) + 0xA414) & 0xFFFF
    step = -2 if cpu.get_flag(DF) else 2
    anim_x = mem.rw(ds, si)
    si = (si + step) & 0xFFFF
    anim_y = mem.rw(ds, si)
    si = (si + step) & 0xFFFF
    ref_x = mem.rw(ds, 0x237E)  # DS:237C + 2
    ref_y = mem.rw(ds, 0x2380)  # DS:237C + 4

    update = object_logic_ab10(v2384, global_disable, sprite_table_value, anim_x, anim_y, ref_x, ref_y)
    slot.sprite_or_state = update.sprite
    slot.x_word = update.x
    slot.y_word = update.y

    # Register + flag boundary the original leaves at RET (AX=y, BX=237C, DX=A414,
    # SI past the pair; only the final y-ADD flags are live).
    cpu.s.bx = 0x237C
    cpu.s.dx = 0xA414
    cpu.s.si = si
    cpu.s.ax = update.y
    cpu.set_add_flags(anim_y & 0xFFFF, ref_y & 0xFFFF, (anim_y & 0xFFFF) + (ref_y & 0xFFFF), 16)
    cpu.s.ip = cpu.pop()


# CS:AA36 dispatch target IP for each recovered AA2B handler kind.  This adapter-side
# map + the pure object_logic_dispatch_aa2b routing together reconstruct the CS:AA36
# table; the hook cross-checks them against the live read (the C054 adapter pattern).
_AA2B_HANDLER_IP_BY_KIND = {
    "postmove_prelude_bc45": 0xBC45,
    "tracked_logic_ad04": 0xAD04,
    "family_dispatch_efae": 0xEFAE,
    "action_44af": 0x44AF,
    "collision_tail_aac2": 0xAAC2,
    "logic_ab10": 0xAB10,
    "handler_c3f8": 0xC3F8,
}


def _run_object_logic_dispatch_aa2b(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Run AA2B's first-level dispatch and leave IP at the selected target.

    AA2B dispatches through CS:AA36 using the slot's draw_layer (SS:[BP+16]).  It is a
    jump-table stub, not a stable gameplay body, so keep the hook at this exact
    boundary instead of executing the selected behavior inline.  The recovered pure
    ``object_logic_dispatch_aa2b`` owns the draw-layer -> handler routing; this adapter
    keeps the live CS:AA36 read authoritative and cross-checks the pure decision against
    it (so it stays robust for any future draw layer outside the recovered 0-7 set).
    """
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    slot = ObjectSlotView(cpu.mem, ss, bp)  # this object's record (SS:BP)
    draw_layer = slot.draw_layer & 0xFFFF
    cpu.s.bx = slot.draw_layer
    cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)  # SHL BX,1
    target_ip = cpu.mem.rw(cpu.s.cs & 0xFFFF, (0xAA36 + cpu.s.bx) & 0xFFFF)
    if draw_layer < len(OBJECT_LOGIC_DISPATCH_AA2B_BY_LAYER):
        expected_ip = _AA2B_HANDLER_IP_BY_KIND[object_logic_dispatch_aa2b(draw_layer).kind]
        if expected_ip != target_ip:
            raise AssertionError(
                f"pure AA2B dispatch disagrees with CS:AA36 (draw layer {draw_layer:#x}): "
                f"{expected_ip:#06x} != live {target_ip:#06x}"
            )
    cpu.s.ip = target_ip


def _scan_object_logic_via_aa2b(
    cpu,
    *,
    table_base: int,
    done_ip: int,
    call_ip: int,
    advance_global_counter: bool,
) -> None:
    """Collapse the AA2B object scan only up to the next real CALL.

    The loop bodies at A9E0/AA10 are scan wrappers, not the object logic itself.
    They PUSH CX, select BP from an object table, and only then call AA2B for
    active objects.  A previous replacement crossed that CALL boundary and ran
    the whole AA2B dispatch inline.  That is too large a hook boundary: the
    verifier quite reasonably stops the original ASM at AA01/AA1F before the
    CALL, while the hook had already consumed the call and sometimes the whole
    remaining scan.

    Keep this hook as a narrow scan accelerator: consume inactive entries, but
    when the first active object is found, leave CPU state exactly as the ASM has
    it immediately before CALL AA2B.  The interpreter then executes the CALL,
    and the separate AA2B hook owns the object-logic dispatch boundary.
    """
    iterations = cpu.s.cx & 0xFFFF
    if iterations == 0:
        iterations = 0x10000

    while iterations:
        cx_value = cpu.s.cx & 0xFFFF

        # PUSH CX / MOV BX,CX / SHL BX,1 / MOV BP,[table+BX]
        _object_ptr_from_scan_index(cpu, table_base, cx_value)

        if advance_global_counter:
            ds = cpu.s.ds & 0xFFFF
            old_counter = cpu.mem.rw(ds, 0x2340)
            counter = (old_counter + 1) & 0xFFFF
            cpu.mem.ww(ds, 0x2340, counter)
            _cmp_word(cpu, counter, 0x05DC)
            if counter >= 0x05DC:
                cpu.mem.ww(ds, 0x2340, 0)

        active = cpu.mem.rw(cpu.s.ss & 0xFFFF, cpu.s.bp & 0xFFFF)
        _cmp_word(cpu, active, 0)
        if active != 0:
            _push_loop_count_for_interpreted_tail(cpu, cx_value)
            cpu.s.ip = call_ip & 0xFFFF
            return

        cpu.s.cx = (cx_value - 1) & 0xFFFF
        iterations -= 1
        if cpu.s.cx == 0:
            cpu.s.ip = done_ip & 0xFFFF
            return

    cpu.s.ip = done_ip & 0xFFFF
