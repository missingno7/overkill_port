"""Verify the native A067 frame stage (``native_action_fanout_step``) vs the VM -- whole-state check.

Unlike ``verify_native_a067`` (which asserts only the spawned slots' 10 stamped fields + the cursor),
this probe verifies the composed FRAME STAGE the standalone runtime will actually call: step-hook A067,
project the WHOLE :class:`NativeGameState` (special/gameplay/effect pools + camera + hud, via the same
``read_native_game_state`` the standalone loop's own verify mode uses) plus the carried
:class:`FireControlState` (DS:A980/DS:95DA), run ``native_action_fanout_step``, and at A067's return
compare the predicted state against a FRESH VM projection.

``special_pool``/``effect_pool``/``camera``/``hud`` (never touched by A067, in any path) and the DS:A980
latch are asserted on EVERY call, including declined ones -- A067's entry gate writes the latch
unconditionally before the path branch, so it is always knowable.  ``object_pool``/DS:95DA cursor are
asserted only when ``native_action_fanout_step`` actually ran a spawn: a decline (the FULL fan-out paths,
or a full pool at the first shot) is a deliberate "not modelled yet", not a claim to reproduce the VM's
spawn without running it -- comparing the pool there would just measure how much the un-composed FULL
fan-out changed the pool, not whether this stage is correct.

Usage:
    python -m overkill.probes.verify_native_action_fanout_step [demo_name] [max_frames]
"""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import overkill.frame_verify as fv  # noqa: E402
from dos_re.cpu import CPU8086  # noqa: E402
from dos_re.input_demo import InputDemoPlayback  # noqa: E402
from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier  # noqa: E402
from overkill.input_waits import pump_demo_frame  # noqa: E402
from overkill.recovered.adapters.native_game_state_adapter import read_native_game_state  # noqa: E402
from overkill.recovered.domain.frame_loop import FireControlState  # noqa: E402
from overkill.recovered.domain.native_game_state import native_game_state_mismatches  # noqa: E402
from overkill.recovered.systems.frame_loop import native_action_fanout_step  # noqa: E402

CS = 0x1010
A067_ENTRY = 0xA067
CURSOR_95DA, LATCH_A980 = 0x95DA, 0xA980
INPUT_98BE, REPEAT_9790, STATE_232A = 0x98BE, 0x9790, 0x232A
SCROLL_2350, BDAC, FIRE_STATE_A958, BE06 = 0x2350, 0xBDAC, 0xA958, 0xBE06
SRC_INDEX_BP, SRC_X_BP, SRC_Y_BP = 0x08, 0x02, 0x04


def main(argv) -> int:
    demo_name = argv[0] if argv else "demo_play_tandy_L2_full_20260617_180221"
    max_frames = int(argv[1]) if len(argv) > 1 else 1200
    demo = InputDemoPlayback.load(ROOT / "artifacts" / "demos" / demo_name)
    snapshot = demo.snapshot_path()
    video = str(demo.manifest.get("metadata", {}).get("video", "tandy"))

    res = {"calls": 0, "ok": 0, "fail": [], "spawned": 0, "no_spawn": 0}
    pending: dict[int, tuple] = {}
    orig_step = CPU8086.step

    def step(self):
        if getattr(self, "_side", "") == "ref" and (self.s.cs & 0xFFFF) == CS:
            ip = self.s.ip & 0xFFFF
            mem = self.mem
            ds = self.s.ds & 0xFFFF
            ss = self.s.ss & 0xFFFF
            bp = self.s.bp & 0xFFFF
            key = id(self)
            if ip == A067_ENTRY and key not in pending:
                state_before = read_native_game_state(mem, ds)
                fire_before = FireControlState(latch_a980=mem.rw(ds, LATCH_A980), cursor_95da=mem.rw(ds, CURSOR_95DA))
                inputs = dict(
                    input_flags=mem.rb(ds, INPUT_98BE), repeat_9790=mem.rb(ds, REPEAT_9790),
                    state_232a=mem.rw(ds, STATE_232A), scroll_2350=mem.rw(ds, SCROLL_2350),
                    bdac=mem.rw(ds, BDAC), a958=mem.rw(ds, FIRE_STATE_A958), be06=mem.rw(ds, BE06),
                    source_index=mem.rw(ss, (bp + SRC_INDEX_BP) & 0xFFFF),
                    source_x=mem.rw(ss, (bp + SRC_X_BP) & 0xFFFF),
                    source_y=mem.rw(ss, (bp + SRC_Y_BP) & 0xFFFF),
                    read_ds_word=lambda off, _m=mem, _d=ds: _m.rw(_d, off & 0xFFFF))
                state_pred, fire_pred = native_action_fanout_step(state_before, fire_before, **inputs)
                # pool_touched is the reliable "did this call actually fold a spawn" signal (dataclasses.
                # replace always returns a NEW FireControlState, even when its value is unchanged, so
                # identity on fire_pred is not a usable "declined" test -- object_pool identity is, since
                # it is only ever replaced in the one branch that actually applied a spawn).
                pool_touched = state_pred.object_pool is not state_before.object_pool
                ret_addr = mem.rw(ss, self.s.sp & 0xFFFF)
                pending[key] = (ret_addr, (self.s.sp + 2) & 0xFFFF, state_pred, fire_pred, pool_touched)
            else:
                p = pending.get(key)
                if p is not None and ip == p[0] and (self.s.sp & 0xFFFF) == p[1]:
                    _ret, _sp, state_pred, fire_pred, pool_touched = pending.pop(key)
                    state_actual = read_native_game_state(mem, ds)
                    # On a decline, object_pool is deliberately not modelled this frame -- exclude it from
                    # the comparison (substitute the VM's actual pool) so only the ALWAYS-true parts
                    # (special/effect/camera/hud, never touched by A067) are checked.
                    check_pred = state_pred if pool_touched else dataclasses.replace(
                        state_pred, object_pool=state_actual.object_pool)
                    mismatches = list(native_game_state_mismatches(check_pred, state_actual))
                    if mem.rw(ds, LATCH_A980) != fire_pred.latch_a980:
                        mismatches.append(("fire", "latch_a980", fire_pred.latch_a980, mem.rw(ds, LATCH_A980)))
                    if pool_touched and mem.rw(ds, CURSOR_95DA) != fire_pred.cursor_95da:
                        mismatches.append(("fire", "cursor_95da", fire_pred.cursor_95da, mem.rw(ds, CURSOR_95DA)))
                    res["calls"] += 1
                    res["spawned" if pool_touched else "no_spawn"] += 1
                    if not mismatches:
                        res["ok"] += 1
                    else:
                        res["fail"].append(mismatches)
        return orig_step(self)

    CPU8086.step = step
    orig_load = fv._load_runtime
    sides = iter(("ref", "cand"))

    def patched_load(exe, assets, snap, tail):
        rt = orig_load(exe, assets, snap, tail)
        rt.cpu._side = next(sides)
        return rt

    fv._load_runtime = patched_load
    boundary = {"n": 0}

    def pump_inputs(ref_rt, cand_rt):
        boundary["n"], _ = pump_demo_frame(demo, boundary["n"], (ref_rt, cand_rt), ref_rt.cpu)
        boundary["n"] += 1

    cfg = FrameVerifyConfig(video=video, source="candidate", max_frames=max_frames,
                            semantic_state_check=False, stop_on_diff=False, log_every=0)
    try:
        run_frame_verifier(exe=ROOT / "assets" / "OVERKILL", assets=ROOT / "assets",
                           snapshot=str(snapshot), command_tail=b"", config=cfg, pump_inputs=pump_inputs)
    finally:
        fv._load_runtime = orig_load
        CPU8086.step = orig_step

    print(f"demo {demo_name} ({max_frames} frames): native_action_fanout_step (whole NativeGameState) vs VM: "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])} "
          f"(spawned={res['spawned']} no_spawn={res['no_spawn']})")
    for mism in res["fail"][:5]:
        print(f"  FAIL {mism[:8]}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native_action_fanout_step's whole folded state matches the VM across the demo"
          if ok else "CHECK -- no A067 entries reached, or a divergence")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
