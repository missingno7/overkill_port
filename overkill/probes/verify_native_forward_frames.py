"""Forward-carry endurance test: how many CONSECUTIVE real game ticks can the three verified frame
stages (native_player_frame_step -> native_action_fanout_step -> native_object_pass) sustain, carrying
THEIR OWN output as the next tick's input -- with no VM underneath for those parts?

Every other probe in this package resets from a fresh VM projection on every call, so it only proves each
stage is correct in isolation.  It does NOT prove that chaining a stage's own predicted output into the
next tick (rather than a freshly re-projected VM state) stays correct -- a small threading bug could be
invisible in per-call isolation and only show up under multi-tick carry.  This is that test.

Per real game tick (the 9B2E -> A66F -> A067 -> AA0D -> AA25 sequence, confirmed in that order):
  1. At 9B2E entry: bail (stop the run) on a joystick device or scripted-input (DS:A47C != 0) tick -- the
     native controller does not model either.  Otherwise decode this tick's FrameInput and run
     native_player_frame_step over the CARRIED special_pool.
  2. At A66F entry: advance the CARRIED scroll natively (the pure A66F gate -> A6FE tick), producing the
     DS:234E/2350 the next two stages read.  Bail on a decline (rare boss/milestone branch, VM-owned).
  3. At A067 entry: run native_action_fanout_step over the (carried, just-stepped) state + FireControlState,
     feeding the CARRIED native row_base as scroll_2350 (not a VM re-read).
  4. At AA0D (gameplay-loop setup): run native_object_pass over the resulting state, with the CARRIED
     native scroll as the object scan's tile-probe origin/row.
  5. At AA25 (scan exit): compare special_pool + object_pool + fire latch/cursor + scroll origin/row against
     a FRESH VM projection.  A clean match extends the run; carry the PREDICTED state (not a VM re-read)
     into the next tick.  A mismatch stops the run and reports the first diverging tick + field.

Only special_pool/object_pool/fire are carried -- effect_pool/camera/hud are not modelled by any composed
stage yet (native_object_pass's own docstring: the effect pool is only per-slot verified, not a whole
pass), so they are re-seeded from a fresh VM read every tick (shadow mode, the same "still VM-owned"
stance FireControlState documents for the fan-out's own non-owned inputs) rather than silently carried
stale into the comparison.

Usage:
    python -m overkill.probes.verify_native_forward_frames [demo_name] [max_frames]
"""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from overkill.probes._harness import LazyBytes, load_demo, run_ref_step_probe  # noqa: E402
from overkill.recovered.adapters.native_game_state_adapter import read_native_game_state  # noqa: E402
from overkill.recovered.domain.frame_loop import FireControlState, FrameInput  # noqa: E402
from overkill.recovered.domain.object_update import ObjectUpdateGlobals  # noqa: E402
from overkill.recovered.domain.tilemap import LevelTileContext  # noqa: E402
from overkill.recovered.domain.scroll import ScrollState  # noqa: E402
from overkill.recovered.systems.frame_loop import (  # noqa: E402
    native_action_fanout_step,
    native_object_pass,
    native_player_frame_step,
)
from overkill.recovered.systems.object_update import NATIVE_OBJECT_HANDLERS  # noqa: E402
from overkill.recovered.systems.scroll import step_scroll_world_progress_gate_a66f  # noqa: E402

CS = 0x1010
IP_9B2E, IP_A66F, IP_A067, IP_AA0D, IP_AA25 = 0x9B2E, 0xA66F, 0xA067, 0xAA0D, 0xAA25
DEVICE_WORD, JOYSTICK_DEVICE, ALT_KEYBOARD_DEVICE = 0x0010, 0x0001, 0x0002
CONTROL_MAP_DEFAULT, CONTROL_MAP_ALT = 0x213E, 0x2146
KEY_STATE_BASE = 0x98C4
NO_CLAMP_GATE = 0xA47C
LATCH_A980, CURSOR_95DA = 0xA980, 0x95DA
REPEAT_9790, STATE_232A, SCROLL_2350, BDAC, FIRE_STATE_A958, BE06 = 0x9790, 0x232A, 0x2350, 0xBDAC, 0xA958, 0xBE06
SRC_INDEX_BP, SRC_X_BP, SRC_Y_BP = 0x08, 0x02, 0x04
REF_BOX_X, REF_BOX_Y, A278 = 0x237E, 0x2380, 0xA278
REF_BOX_SCAN, A47E, A7A0 = 0x2390, 0xA47E, 0xA7A0
DELTA_2342, PHASE_2328, STEP_MODE, DIR_TABLE = 0x2342, 0x2328, 0x2312, 0xA348
A482, FRAME_233C, DELTA_X_2346, BEDC, TICK_2340 = 0xA482, 0x233C, 0x2346, 0xBEDC, 0x2340
A8C2_ADDR = 0xA8C2
TILE_ORIGIN, TILE_ROW, TILE_CLASS, TILE_PLANE_PTR = 0x234E, 0x2350, 0xC3AA, 0x9592
# The A66F/A6FE scroll fields (see overkill.recovered.systems.scroll): the two gameplay-consumed
# (234E/2350, == TILE_ORIGIN/TILE_ROW above) plus its own bookkeeping (234C/A978/2354) and the
# gate globals A47C/A47E/A480 (A47C == NO_CLAMP_GATE, always 0 here since the harness bails otherwise).
SCROLL_ROW_SOURCE_234C, SCROLL_ROWS_A978, SCROLL_FWD_2354, SCROLL_A480 = 0x234C, 0xA978, 0x2354, 0xA480
OFF_ACTIVE, OFF_X, OFF_Y, OFF_DIR, OFF_SPRITE, OFF_LOGIC, OFF_SUBSTATE = 0x00, 0x02, 0x04, 0x06, 0x08, 0x18, 0x1C
# Same scope + exception as verify_native_object_pass.py -- this harness's object_pool check must match
# exactly what THAT dedicated, already-verified probe claims (no more): only NATIVE_OBJECT_HANDLERS logic
# ids are checked, and a contact-death sprite override (B86D/B9F0) is deferred to the VM either way.
SKIP_SPRITE_LOGIC_IDS = frozenset((0x001D, 0x0014))
COLLISION_DEATH_LOGIC_ID = 0x0001


def _read_scroll_from_vm(mem, ds) -> ScrollState:
    """Seed a ScrollState from the live VM (the first tick, and after any decline resync)."""
    return ScrollState(
        origin_x=mem.rw(ds, TILE_ORIGIN), row_base=mem.rw(ds, TILE_ROW),
        row_source=mem.rw(ds, SCROLL_ROW_SOURCE_234C), rows_to_milestone=mem.rw(ds, SCROLL_ROWS_A978),
        forward_last=mem.rw(ds, SCROLL_FWD_2354) == 0)


def _object_update_globals(mem, ds, cs_seg, class_cache, scroll: ScrollState) -> ObjectUpdateGlobals:
    class_table = class_cache.get(ds)
    if class_table is None:
        class_table = tuple(mem.rb(ds, (TILE_CLASS + k) & 0xFFFF) for k in range(0x100))
        class_cache[ds] = class_table
    return ObjectUpdateGlobals(
        ref_box_x=mem.rw(ds, REF_BOX_X), ref_box_y=mem.rw(ds, REF_BOX_Y),
        a278=mem.rw(ds, A278), tile_probe_suppressed=mem.rw(ds, BDAC) == 0x0001,
        tiles=LevelTileContext(
            origin_x_word=scroll.origin_x, row_base_word=scroll.row_base,
            tile_plane=LazyBytes(mem, mem.rw(cs_seg, TILE_PLANE_PTR), 0, 0x10000), class_table=class_table),
        ref_box_scan=mem.rw(ds, REF_BOX_SCAN), a47e=mem.rw(ds, A47E), a7a0=mem.rw(ds, A7A0),
        vertical_delta=mem.rw(ds, DELTA_2342), phase_2328=mem.rw(ds, PHASE_2328), step_mode=mem.rw(ds, STEP_MODE),
        direction_table=tuple(mem.rb(ds, (DIR_TABLE + k) & 0xFFFF) for k in range(16)),
        global_disable=mem.rw(ds, NO_CLAMP_GATE), a482=mem.rw(ds, A482), frame_233c=mem.rw(ds, FRAME_233C),
        horizontal_delta=mem.rw(ds, DELTA_X_2346), difficulty=mem.rw(ds, BEDC), tick=mem.rw(ds, TICK_2340),
        anim_2326=mem.rw(ds, 0x2326), level=mem.rw(ds, 0x2356),
        a8c2_boss_mode=mem.rw(ds, A8C2_ADDR) == 0x0001, bedc=mem.rw(ds, BEDC),
        waypoint_word_reader=lambda off, _m=mem, _d=ds: _m.rw(_d, off & 0xFFFF))


def _six(words: tuple) -> tuple:
    return (words[OFF_SUBSTATE >> 1], words[OFF_DIR >> 1], words[OFF_SPRITE >> 1],
            words[OFF_X >> 1], words[OFF_Y >> 1], words[OFF_ACTIVE >> 1])


def _six_cpu(mem, ds: int, base: int) -> tuple:
    return tuple(mem.rw(ds, (base + off) & 0xFFFF) for off in (OFF_SUBSTATE, OFF_DIR, OFF_SPRITE, OFF_X, OFF_Y, OFF_ACTIVE))


def _object_pool_mismatches(entry_pool, pred_pool, mem, ds: int) -> list:
    """Same scope as verify_native_object_pass.py: only NATIVE_OBJECT_HANDLERS logic ids, gated on the
    slot's state ENTERING this tick's object-update pass (before it ran); the sprite of a B86D/B9F0 slot
    that just resolved a contact death is deferred (that collision-death half is not modelled either)."""
    out = []
    for i in range(len(entry_pool)):
        if entry_pool.active_word(i) == 0 or entry_pool.logic_id(i) not in NATIVE_OBJECT_HANDLERS:
            continue
        base = (pred_pool.base + i * pred_pool.stride) & 0xFFFF
        predicted, actual = _six(pred_pool.words(i)), _six_cpu(mem, ds, base)
        if predicted == actual:
            continue
        if (entry_pool.logic_id(i) in SKIP_SPRITE_LOGIC_IDS and mem.rw(ds, (base + OFF_LOGIC) & 0xFFFF) == COLLISION_DEATH_LOGIC_ID):
            predicted, actual = predicted[:2] + predicted[3:], actual[:2] + actual[3:]  # drop the sprite word
            if predicted == actual:
                continue
        out.append((f"object_pool[{i}]", predicted, actual))
    return out


def main(argv) -> int:
    demo_name = argv[0] if argv else "demo_play_tandy_L2_full_20260617_180221"
    max_frames = int(argv[1]) if len(argv) > 1 else 400
    demo = load_demo(demo_name, "demo_play_tandy_L2_full_20260617_180221")

    run = {"state": None, "fire": None, "scroll": None, "ticks": 0, "stopped": False,
           "stop_reason": "", "fail": None}
    stage: dict[int, dict] = {}
    class_cache: dict[int, tuple] = {}

    def stop(reason: str) -> None:
        run["stopped"] = True
        run["stop_reason"] = reason

    def on_ref_step(cpu):
        if run["stopped"]:
            return
        cs = cpu.s.cs & 0xFFFF
        ip = cpu.s.ip & 0xFFFF
        if cs != CS:
            return
        mem = cpu.mem
        ds = cpu.s.ds & 0xFFFF
        key = id(cpu)

        if ip == IP_9B2E:
            device = mem.rw(ds, DEVICE_WORD)
            if device == JOYSTICK_DEVICE:
                stop(f"joystick device at tick {run['ticks']}")
                return
            no_clamp = mem.rw(ds, NO_CLAMP_GATE) != 0
            if no_clamp:
                stop(f"scripted-input tick (DS:A47C != 0) at tick {run['ticks']}")
                return
            fresh = read_native_game_state(mem, ds)
            if run["state"] is None:
                run["state"] = fresh
                run["fire"] = FireControlState(latch_a980=mem.rw(ds, LATCH_A980), cursor_95da=mem.rw(ds, CURSOR_95DA))
            else:
                # Carry special_pool/object_pool forward (our own prior prediction); re-seed everything
                # this composition does not model yet (shadow mode -- still VM-owned every tick).
                run["state"] = dataclasses.replace(
                    run["state"], effect_pool=fresh.effect_pool, camera=fresh.camera, hud=fresh.hud)
            table = CONTROL_MAP_ALT if device == ALT_KEYBOARD_DEVICE else CONTROL_MAP_DEFAULT
            frame_input = FrameInput(
                control_map=tuple(mem.rb(ds, (table + k) & 0xFFFF) for k in range(8)),
                key_state=LazyBytes(mem, ds, KEY_STATE_BASE, 0x100))
            player_step = native_player_frame_step(run["state"].special_pool, frame_input, no_clamp=no_clamp)
            new_state = dataclasses.replace(run["state"], special_pool=player_step.special_pool)
            stage[key] = {"phase": "player_done", "state": new_state, "fire": run["fire"],
                          "input_flags": player_step.input_flags}

        elif ip == IP_A66F:
            # A66F runs here, between 9B2E and A067, and produces the DS:234E/2350 the fan-out +
            # object stages then read.  Carry OUR own scroll prediction forward (seed from the VM only
            # on the first tick), advancing it natively via the pure gate.  A decline (rare boss/
            # milestone branch) is left VM-owned for that one tick -- shadow mode, the same stance the
            # harness already takes for effect_pool/camera/hud: s["scroll"]=None marks the tick, the
            # downstream stages read VM scroll (post-A66F, since A067 runs after A66F returns), and the
            # carried scroll is re-seeded from the VM at AA25 so the next native tick starts aligned.
            s = stage.get(key)
            if s is None or s["phase"] != "player_done":
                return  # A66F seen outside a normal gameplay tick; the 9B2E/A067 guards handle ordering
            if run["scroll"] is None:
                run["scroll"] = _read_scroll_from_vm(mem, ds)
            outcome = step_scroll_world_progress_gate_a66f(
                run["scroll"], a47c=mem.rw(ds, NO_CLAMP_GATE), a47e=mem.rw(ds, A47E), a480=mem.rw(ds, SCROLL_A480))
            if outcome is None:
                run["scroll"] = None  # decline: this tick is VM-owned; re-seed at AA25 for the next tick
                s["scroll"] = None
            else:
                run["scroll"] = outcome.state
                s["scroll"] = outcome.state

        elif ip == IP_A067:
            s = stage.get(key)
            if s is None or s["phase"] != "player_done":
                stop(f"A067 reached without a preceding 9B2E player step at tick {run['ticks']}")
                return
            if "scroll" not in s:
                stop(f"A067 reached without a preceding A66F scroll step at tick {run['ticks']}")
                return
            # On a declined (VM-owned) tick s["scroll"] is None -> read VM DS:2350 (post-A66F, since
            # A067 runs after A66F returns); otherwise feed the carried native row_base.
            scroll_2350 = mem.rw(ds, SCROLL_2350) if s["scroll"] is None else s["scroll"].row_base
            ss, bp = cpu.s.ss & 0xFFFF, cpu.s.bp & 0xFFFF
            pre_fanout_pool = s["state"].object_pool
            new_state, new_fire = native_action_fanout_step(
                s["state"], s["fire"], input_flags=s["input_flags"],
                repeat_9790=mem.rb(ds, REPEAT_9790), state_232a=mem.rw(ds, STATE_232A),
                scroll_2350=scroll_2350, bdac=mem.rw(ds, BDAC),
                a958=mem.rw(ds, FIRE_STATE_A958), be06=mem.rw(ds, BE06),
                source_index=mem.rw(ss, (bp + SRC_INDEX_BP) & 0xFFFF),
                source_x=mem.rw(ss, (bp + SRC_X_BP) & 0xFFFF), source_y=mem.rw(ss, (bp + SRC_Y_BP) & 0xFFFF),
                read_ds_word=lambda off, _m=mem, _d=ds: _m.rw(_d, off & 0xFFFF))
            # Same signal as verify_native_action_fanout_step.py: pool identity, not fire identity
            # (dataclasses.replace always returns a new FireControlState even when the value is
            # unchanged).  A decline (FULL path / a full pool) leaves the cursor VM-owned, so only
            # check it on a tick that actually spawned -- else this false-fires on every decline.
            spawned = new_state.object_pool is not pre_fanout_pool
            stage[key] = {"phase": "fanout_done", "state": new_state, "fire": new_fire,
                          "spawned": spawned, "scroll": s["scroll"]}

        elif ip == IP_AA0D:
            s = stage.get(key)
            if s is None or s["phase"] != "fanout_done":
                stop(f"AA0D reached without a preceding A067 fan-out step at tick {run['ticks']}")
                return
            entry_object_pool = s["state"].object_pool  # pre-object-update snapshot: the compare's gate
            obj_scroll = _read_scroll_from_vm(mem, ds) if s["scroll"] is None else s["scroll"]
            g = _object_update_globals(mem, ds, cs, class_cache, obj_scroll)
            new_state = native_object_pass(s["state"], g)
            stage[key] = {"phase": "objects_done", "state": new_state, "fire": s["fire"],
                          "entry_pool": entry_object_pool, "spawned": s["spawned"], "scroll": s["scroll"]}

        elif ip == IP_AA25:
            s = stage.get(key)
            if s is None or s["phase"] != "objects_done":
                stop(f"AA25 reached without a preceding AA0D object-scan step at tick {run['ticks']}")
                return
            stage.pop(key)
            pred_state, pred_fire = s["state"], s["fire"]
            actual_state = read_native_game_state(mem, ds)
            # Scope the check to exactly what the three composed stages claim to model (matching each
            # dedicated probe's own scope): special_pool's X/Y only (native_player_frame_step never touches
            # anything else -- the rest, e.g. the +0C render-projection scratch, is a SEPARATE, already-
            # verified subsystem's job, recomputed by the present stage every tick); object_pool only for
            # NATIVE_OBJECT_HANDLERS logic ids (verify_native_object_pass's own gate).  effect_pool/camera/
            # hud are not modelled by anything here, so not checked at all.
            mismatches = []
            pred_xy = (pred_state.special_pool.x_word(0), pred_state.special_pool.y_word(0))
            actual_xy = (actual_state.special_pool.x_word(0), actual_state.special_pool.y_word(0))
            if pred_xy != actual_xy:
                mismatches.append(("special_pool[0]", "xy", pred_xy, actual_xy))
            mismatches.extend(_object_pool_mismatches(s["entry_pool"], pred_state.object_pool, mem, ds))
            if mem.rw(ds, LATCH_A980) != pred_fire.latch_a980:
                mismatches.append(("fire", "latch_a980", pred_fire.latch_a980, mem.rw(ds, LATCH_A980)))
            if s["spawned"] and mem.rw(ds, CURSOR_95DA) != pred_fire.cursor_95da:
                mismatches.append(("fire", "cursor_95da", pred_fire.cursor_95da, mem.rw(ds, CURSOR_95DA)))
            # Scroll is carried natively (A66F -> A6FE), so check the two gameplay-consumed fields
            # (DS:234E/2350) against the VM directly -- a first-class carried quantity, like the pools.
            # A declined tick (s["scroll"] is None) was VM-owned: don't check it, and re-seed the carried
            # scroll from the VM (now post-A66F) so the next native tick starts aligned.
            if s["scroll"] is None:
                run["scroll"] = _read_scroll_from_vm(mem, ds)
            else:
                pred_scroll = (s["scroll"].origin_x, s["scroll"].row_base)
                actual_scroll = (mem.rw(ds, TILE_ORIGIN), mem.rw(ds, TILE_ROW))
                if pred_scroll != actual_scroll:
                    mismatches.append(("scroll", "origin/row", pred_scroll, actual_scroll))
            if mismatches:
                run["fail"] = (run["ticks"], mismatches[:8])
                stop(f"state mismatch at tick {run['ticks']}")
                return
            run["ticks"] += 1
            run["state"], run["fire"] = pred_state, pred_fire  # carry OUR prediction, not a VM re-read

    run_ref_step_probe(demo, max_frames, on_ref_step)

    print(f"demo {demo_name} ({max_frames} frames): forward-carry endurance "
          f"(native_player_frame_step -> native_action_fanout_step -> native_object_pass, carried): "
          f"ticks_sustained={run['ticks']} stop_reason={run['stop_reason'] or '(ran out of frames)'}")
    if run["fail"] is not None:
        tick, mismatches = run["fail"]
        print(f"  first divergence at tick {tick}:")
        for m in mismatches:
            print(f"    {m}")
    ok = run["fail"] is None
    print("RESULT:", f"SUSTAINED {run['ticks']} consecutive VM-less ticks with no state divergence"
          if ok else f"DIVERGED after {run['ticks']} consecutive VM-less ticks (see above)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
