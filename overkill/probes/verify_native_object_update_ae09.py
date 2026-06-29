"""Verify the native AE09 movement transform (object_movement_step_ae09) is byte-exact vs the VM's
1010:AE09 behavior across a gameplay demo -- the first §1.2 produced-vs-VM gate for the OBJECT-UPDATE
(the per-slot movement half).

AE09 (the EFAE logic_id=0Ch behavior) decrements the slot's substate timer, steps it 3px in its
direction (AF22), and tails into the AD60 bounds/tile + BD17 deactivation tail.  The AD60/BD17 tail
only sets the slot's ``active`` word + global counters -- it does NOT touch the five movement fields
(substate +1C, direction +06, sprite +08, x +02, y +04).  So those five are a pure composition of
recovered systems (``object_logic_ae09`` + the AF22 ``step_operations_for_direction``), which
``object_movement_step_ae09`` computes.

Step-hook AE09 on the pure-VM (oracle) side: at entry capture the slot pointer + (substate, direction,
x, y) and the routine's return address; predict via ``object_movement_step_ae09``; when control
returns (the AD60 tail RETs to AE09's caller) read the slot's five post-frame movement fields and
assert they equal the prediction -- for every real AE09 object.  (``active``/deactivation + global
side-effects are out of scope here; they are the death-tail island, separate producers.)

Usage:
    python -m overkill.probes.verify_native_object_update_ae09 [demo_name] [max_frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import overkill.frame_verify as fv  # noqa: E402
from dos_re.cpu import CPU8086  # noqa: E402
from dos_re.input_demo import InputDemoPlayback  # noqa: E402
from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier  # noqa: E402
from overkill.input_waits import pump_demo_frame  # noqa: E402
from overkill.recovered.systems.objects import object_movement_step_ae09  # noqa: E402
from overkill.recovered.views.object_slots import (  # noqa: E402
    OFF_DIRECTION_OR_STEP,
    OFF_SPRITE_OR_STATE,
    OFF_SUBSTATE,
    OFF_X,
    OFF_Y,
)

CS = 0x1010
AE09_IP = 0xAE09


def main(argv) -> int:
    demo_name = argv[0] if argv else "demo_play_tandy_L2_full_20260617_180221"
    max_frames = int(argv[1]) if len(argv) > 1 else 1200
    demo = InputDemoPlayback.load(ROOT / "artifacts" / "demos" / demo_name)
    snapshot = demo.snapshot_path()
    video = str(demo.manifest.get("metadata", {}).get("video", "tandy"))

    res = {"calls": 0, "ok": 0, "fail": []}
    pending: dict[int, tuple] = {}
    orig_step = CPU8086.step

    def step(self):
        if getattr(self, "_side", "") == "ref":
            cs = self.s.cs & 0xFFFF
            ip = self.s.ip & 0xFFFF
            key = id(self)
            if cs == CS and ip == AE09_IP and key not in pending:
                ss = self.s.ss & 0xFFFF
                bp = self.s.bp & 0xFFFF
                substate = self.mem.rw(ss, (bp + OFF_SUBSTATE) & 0xFFFF)
                direction = self.mem.rw(ss, (bp + OFF_DIRECTION_OR_STEP) & 0xFFFF)
                x = self.mem.rw(ss, (bp + OFF_X) & 0xFFFF)
                y = self.mem.rw(ss, (bp + OFF_Y) & 0xFFFF)
                ret_addr = self.mem.rw(ss, self.s.sp & 0xFFFF)  # AD60 tail RETs here
                predicted = object_movement_step_ae09(substate, direction, x, y)
                pending[key] = (ss, bp, ret_addr, predicted)
            elif key in pending and cs == CS and ip == pending[key][2]:
                ss, bp, _ret, predicted = pending.pop(key)
                post = (
                    self.mem.rw(ss, (bp + OFF_SUBSTATE) & 0xFFFF),
                    self.mem.rw(ss, (bp + OFF_DIRECTION_OR_STEP) & 0xFFFF),
                    self.mem.rw(ss, (bp + OFF_SPRITE_OR_STATE) & 0xFFFF),
                    self.mem.rw(ss, (bp + OFF_X) & 0xFFFF),
                    self.mem.rw(ss, (bp + OFF_Y) & 0xFFFF),
                )
                pred = (predicted.substate, predicted.direction_or_step,
                        predicted.sprite_or_state, predicted.x_word, predicted.y_word)
                res["calls"] += 1
                if pred == post:
                    res["ok"] += 1
                else:
                    res["fail"].append((pred, post))
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

    print(f"demo {demo_name} ({max_frames} frames): native object_movement_step_ae09 vs VM AE09: "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])}")
    for pred, post in res["fail"][:8]:
        print(f"  FAIL predicted={tuple(hex(v) for v in pred)} actual={tuple(hex(v) for v in post)}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native AE09 movement byte-exact vs the VM across the demo"
          if ok else "CHECK -- no AE09 reached, or a divergence")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
