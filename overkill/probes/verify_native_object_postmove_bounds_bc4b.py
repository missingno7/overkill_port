"""Verify the native BC4B post-move bounds half (Y clamp + X-bounds death -> active) is byte-exact vs
the VM's 1010:BC4B across a gameplay demo -- the shared seeker/behavior post-move, partial: the y/active
slot fields (the collision-death logic_id/sprite half is a separate fresh-session producer).

BC4B (the post-move tail every seeker + several behaviors run) first clamps Y into [0, C0h]
(``clamp_postmove_y_bcb1``), then deactivates the object (-> BD17, active=0) when its post-move X
leaves the play box (``object_postmove_x_bounds_deactivates_bc4b``).  The collision path BC4B runs
afterwards sets ``logic_id`` (BFC7), NOT ``active`` -- so at BC4B's return ``active == 0`` is exactly
the X-bounds death, and ``y`` is always the clamp, regardless of collision.  This producer composes
the two recovered pure functions and checks those two slot fields.

Step-hook BC4B on the pure-VM (oracle) side: at entry capture (x, y, active, DS:A47C, logic_id) + the
return address; predict y' = clamp(y), active' = 0 if X-bounds death else active; when BC4B returns to
the caller read the slot's y (+04) and active (+00) and assert they equal the prediction.

Usage:
    python -m overkill.probes.verify_native_object_postmove_bounds_bc4b [demo_name] [max_frames]
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
from overkill.recovered.systems.collision import (  # noqa: E402
    clamp_postmove_y_bcb1,
    object_postmove_x_bounds_deactivates_bc4b,
)
from overkill.recovered.views.object_slots import (  # noqa: E402
    OFF_ACTIVE_WORD,
    OFF_LOGIC_ID,
    OFF_X,
    OFF_Y,
)

CS = 0x1010
BC4B_IP = 0xBC4B
GLOBAL_DISABLE_A47C = 0xA47C   # DS:A47C; non-zero -> wide X box


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
            if cs == CS and ip == BC4B_IP and key not in pending:
                ss = self.s.ss & 0xFFFF
                ds = self.s.ds & 0xFFFF
                bp = self.s.bp & 0xFFFF
                x = self.mem.rw(ss, (bp + OFF_X) & 0xFFFF)
                y = self.mem.rw(ss, (bp + OFF_Y) & 0xFFFF)
                active = self.mem.rw(ss, (bp + OFF_ACTIVE_WORD) & 0xFFFF)
                logic_id = self.mem.rw(ss, (bp + OFF_LOGIC_ID) & 0xFFFF)
                global_disable = self.mem.rw(ds, GLOBAL_DISABLE_A47C)
                new_y = clamp_postmove_y_bcb1(y).y_word
                new_active = 0 if object_postmove_x_bounds_deactivates_bc4b(x, global_disable, logic_id) else (active & 0xFFFF)
                ret_addr = self.mem.rw(ss, self.s.sp & 0xFFFF)
                pending[key] = (ss, bp, ret_addr, new_y, new_active)
            elif key in pending and cs == CS and ip == pending[key][2]:
                ss, bp, _ret, new_y, new_active = pending.pop(key)
                post = (
                    self.mem.rw(ss, (bp + OFF_Y) & 0xFFFF),
                    self.mem.rw(ss, (bp + OFF_ACTIVE_WORD) & 0xFFFF),
                )
                res["calls"] += 1
                if (new_y, new_active) == post:
                    res["ok"] += 1
                else:
                    res["fail"].append(((new_y, new_active), post))
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

    print(f"demo {demo_name} ({max_frames} frames): native BC4B bounds (y+active) vs VM: "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])}")
    for pred, post in res["fail"][:8]:
        print(f"  FAIL predicted={tuple(hex(v) for v in pred)} actual={tuple(hex(v) for v in post)}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native BC4B bounds (y+active) byte-exact vs the VM across the demo"
          if ok else "CHECK -- no BC4B reached, or a divergence")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
