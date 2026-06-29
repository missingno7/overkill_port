"""Verify the native delta-steer (object_delta_steer_5e42) is byte-exact vs the VM's runtime-patched
1010:5E42 across a gameplay demo -- the 3rd object-update movement primitive (the delta-based steer
used by the b24d/b86d behaviors), after AE09 (fixed step) and 5DB2 (target-seek).

5E42 converts the slot's signed Y/X movement deltas (+2C/+2A) into a direction via a Bresenham axis
selection against the move_step_error accumulator (+2E) and the DS:A348 table, then steps the slot's
x (+02) / y (+04) by that direction (AF22 3px when DS:2312==3, else AF63 2px); on the blocked branch
(table -> FFh) direction + x/y are untouched but the accumulator still advances.
``object_delta_steer_5e42`` composes that whole transform.

Step-hook 5E42 on the pure-VM (oracle) side: at entry capture the slot (x, y, direction, the two
deltas, the accumulator) + DS:2312 + the DS:A348 table + the return address; predict; when 5E42's step
tail RETs to the caller, read the slot's four post fields (direction +06, move_step_error +2E, x +02,
y +04) and assert they equal the prediction -- for every real 5E42 call.

Usage:
    python -m overkill.probes.verify_native_object_steer_5e42 [demo_name] [max_frames]
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
from overkill.recovered.systems.movement import object_delta_steer_5e42  # noqa: E402
from overkill.recovered.views.object_slots import (  # noqa: E402
    OFF_DIRECTION_OR_STEP,
    OFF_MOVE_DELTA_X,
    OFF_MOVE_DELTA_Y,
    OFF_MOVE_STEP_ERROR,
    OFF_X,
    OFF_Y,
)

CS = 0x1010
STEER_IP = 0x5E42
STEP_MODE_2312 = 0x2312      # DS:2312; == 3 -> AF22 3px, else AF63 2px
DIRECTION_TABLE = 0xA348     # 16-byte direction-bits -> direction map


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
            if cs == CS and ip == STEER_IP and key not in pending:
                ss = self.s.ss & 0xFFFF
                ds = self.s.ds & 0xFFFF
                bp = self.s.bp & 0xFFFF
                x = self.mem.rw(ss, (bp + OFF_X) & 0xFFFF)
                y = self.mem.rw(ss, (bp + OFF_Y) & 0xFFFF)
                direction = self.mem.rw(ss, (bp + OFF_DIRECTION_OR_STEP) & 0xFFFF)
                delta_y = self.mem.rw(ss, (bp + OFF_MOVE_DELTA_Y) & 0xFFFF)
                delta_x = self.mem.rw(ss, (bp + OFF_MOVE_DELTA_X) & 0xFFFF)
                err = self.mem.rw(ss, (bp + OFF_MOVE_STEP_ERROR) & 0xFFFF)
                step_mode = self.mem.rw(ds, STEP_MODE_2312)
                table = tuple(self.mem.rb(ds, (DIRECTION_TABLE + i) & 0xFFFF) for i in range(16))
                predicted = object_delta_steer_5e42(x, y, direction, delta_y, delta_x, err, step_mode, table)
                ret_addr = self.mem.rw(ss, self.s.sp & 0xFFFF)
                pending[key] = (ss, bp, ret_addr, predicted)
            elif key in pending and cs == CS and ip == pending[key][2]:
                ss, bp, _ret, predicted = pending.pop(key)
                post = (
                    self.mem.rw(ss, (bp + OFF_DIRECTION_OR_STEP) & 0xFFFF),
                    self.mem.rw(ss, (bp + OFF_MOVE_STEP_ERROR) & 0xFFFF),
                    self.mem.rw(ss, (bp + OFF_X) & 0xFFFF),
                    self.mem.rw(ss, (bp + OFF_Y) & 0xFFFF),
                )
                pred = (predicted.direction_or_step, predicted.move_step_error,
                        predicted.x_word, predicted.y_word)
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

    print(f"demo {demo_name} ({max_frames} frames): native object_delta_steer_5e42 vs VM 5E42: "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])}")
    for pred, post in res["fail"][:8]:
        print(f"  FAIL predicted={tuple(hex(v) for v in pred)} actual={tuple(hex(v) for v in post)}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native 5E42 delta-steer byte-exact vs the VM across the demo"
          if ok else "CHECK -- no 5E42 reached, or a divergence")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
