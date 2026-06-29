"""Verify the native target-seek movement (object_target_seek_step_5db2) is byte-exact vs the VM's
1010:5DB2 across a gameplay demo -- the SHARED object-update movement producer (used by B729/D281/
B1B0 and the b73e/b9f0/8d4f behaviors).

5DB2 picks a direction toward the target globals (DS:2304 Y / DS:2306 X) via the DS:A348 table, writes
it to the slot's direction_or_step (+06), and steps the slot's x (+02) / y (+04) by that direction --
the step distance dispatched by the mode DS:2308 through the CS:5E0C table (mode 1 -> AF63 one 2px
step, mode 2 -> AF60 two 2px steps, mode 3 -> AEE4 one 8px step).  On the blocked branch (table -> FFh)
it touches nothing.  ``object_target_seek_step_5db2`` composes the verified seek direction +
step-by-mode; the AD60/BD17 tail (run by the callers, not 5DB2) is out of scope, as are the DS:A954/
230A globals.

Step-hook 5DB2 on the pure-VM (oracle) side: at entry capture the slot (x, y, direction), the target,
the mode, and the DS:A348 table + the routine's return address; predict; when 5DB2's step tail RETs to
the caller, read the slot's three post fields (direction +06, x +02, y +04) and assert they equal the
prediction -- for every real 5DB2 call.  (Unverified modes -- mode 0/AFA2, absent from the green
demos -- are skipped, matching the lift's fail-loud.)

Usage:
    python -m overkill.probes.verify_native_object_seek_step_5db2 [demo_name] [max_frames]
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
from overkill.recovered.domain.movement import MovementTarget  # noqa: E402
from overkill.recovered.systems.movement import object_target_seek_step_5db2  # noqa: E402
from overkill.recovered.views.object_slots import (  # noqa: E402
    OFF_DIRECTION_OR_STEP,
    OFF_X,
    OFF_Y,
)

CS = 0x1010
SEEK_IP = 0x5DB2
TARGET_Y = 0x2304
TARGET_X = 0x2306
MOVEMENT_MODE = 0x2308
DIRECTION_TABLE = 0xA348  # 16-byte direction map


def main(argv) -> int:
    demo_name = argv[0] if argv else "demo_play_tandy_L2_full_20260617_180221"
    max_frames = int(argv[1]) if len(argv) > 1 else 1200
    demo = InputDemoPlayback.load(ROOT / "artifacts" / "demos" / demo_name)
    snapshot = demo.snapshot_path()
    video = str(demo.manifest.get("metadata", {}).get("video", "tandy"))

    res = {"calls": 0, "ok": 0, "fail": [], "skipped": 0}
    pending: dict[int, tuple] = {}
    orig_step = CPU8086.step

    def step(self):
        if getattr(self, "_side", "") == "ref":
            cs = self.s.cs & 0xFFFF
            ip = self.s.ip & 0xFFFF
            key = id(self)
            if cs == CS and ip == SEEK_IP and key not in pending:
                ss = self.s.ss & 0xFFFF
                ds = self.s.ds & 0xFFFF
                bp = self.s.bp & 0xFFFF
                x = self.mem.rw(ss, (bp + OFF_X) & 0xFFFF)
                y = self.mem.rw(ss, (bp + OFF_Y) & 0xFFFF)
                direction = self.mem.rw(ss, (bp + OFF_DIRECTION_OR_STEP) & 0xFFFF)
                target = MovementTarget(y_word=self.mem.rw(ds, TARGET_Y), x_word=self.mem.rw(ds, TARGET_X))
                mode = self.mem.rw(ds, MOVEMENT_MODE)
                table = tuple(self.mem.rb(ds, (DIRECTION_TABLE + i) & 0xFFFF) for i in range(16))
                ret_addr = self.mem.rw(ss, self.s.sp & 0xFFFF)
                try:
                    predicted = object_target_seek_step_5db2(x, y, direction, target, mode, table)
                except ValueError:
                    res["skipped"] += 1  # unverified mode (0/AFA2); lift fails loud too
                    return orig_step(self)
                pending[key] = (ss, bp, ret_addr, predicted)
            elif key in pending and cs == CS and ip == pending[key][2]:
                ss, bp, _ret, predicted = pending.pop(key)
                post = (
                    self.mem.rw(ss, (bp + OFF_DIRECTION_OR_STEP) & 0xFFFF),
                    self.mem.rw(ss, (bp + OFF_X) & 0xFFFF),
                    self.mem.rw(ss, (bp + OFF_Y) & 0xFFFF),
                )
                pred = (predicted.direction_or_step, predicted.x_word, predicted.y_word)
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

    print(f"demo {demo_name} ({max_frames} frames): native object_target_seek_step_5db2 vs VM 5DB2: "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])} skipped={res['skipped']}")
    for pred, post in res["fail"][:8]:
        print(f"  FAIL predicted={tuple(hex(v) for v in pred)} actual={tuple(hex(v) for v in post)}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native 5DB2 target-seek movement byte-exact vs the VM across the demo"
          if ok else "CHECK -- no 5DB2 reached, or a divergence")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
