"""Verify the native object screen-di projection (project_object_to_di) is byte-exact vs the VM's
1010:30D2 across a gameplay demo -- the §1.2 produced-vs-VM gate for the render projection (a render
leaf inside the 5AC8->5A36->30D2 draw dispatch).

30D2 (the Tandy projection) computes AX = (obj_y >> 1) + DS:99C8[obj_x] for on-screen objects (cull
to 25B2 when obj_x >= 0xE0 or the column entry is FFFFh).  Step-hook 30D2 on the pure-VM (oracle)
side: at entry capture obj (X=ss:[bp+2], Y=ss:[bp+4]) + the column entry, predict via
``project_object_to_di``; at the routine's near-return (30FE/3102, the non-cull exits) assert the
VM's AX equals the prediction -- for every real on-screen object.

An all-match run means the native projection reproduces the VM byte-exact, so the native sprite
layer can place objects from NativeGameState's pool instead of reading the VM's +0C.

Usage:
    python -m overkill.probes.verify_native_projection [demo_name] [max_frames]
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
from overkill.native_video.projection import project_object_to_di  # noqa: E402

CS = 0x1010
PROJ_IP = 0x30D2
RET_IPS = (0x30FE, 0x3102)  # the two non-cull near-returns
COLUMN_TABLE = 0x99C8       # DS:99C8 per-column base table (word per X)


def main(argv) -> int:
    demo_name = argv[0] if argv else "demo_play_tandy_L2_full_20260617_180221"
    max_frames = int(argv[1]) if len(argv) > 1 else 1200
    demo = InputDemoPlayback.load(ROOT / "artifacts" / "demos" / demo_name)
    snapshot = demo.snapshot_path()
    video = str(demo.manifest.get("metadata", {}).get("video", "tandy"))

    res = {"calls": 0, "ok": 0, "fail": []}
    pending: dict[int, object] = {}
    orig_step = CPU8086.step

    def step(self):
        if getattr(self, "_side", "") == "ref":
            cs = self.s.cs & 0xFFFF
            ip = self.s.ip & 0xFFFF
            key = id(self)
            if cs == CS and ip == PROJ_IP:
                ss = self.s.ss & 0xFFFF
                ds = self.s.ds & 0xFFFF
                bp = self.s.bp & 0xFFFF
                x = self.mem.rw(ss, (bp + 2) & 0xFFFF)
                y = self.mem.rw(ss, (bp + 4) & 0xFFFF)
                col = self.mem.rw(ds, (COLUMN_TABLE + ((x * 2) & 0xFFFF)) & 0xFFFF)
                pending[key] = project_object_to_di(x, y, col)
            elif key in pending and cs == CS and ip in RET_IPS:
                predicted = pending.pop(key)
                actual = self.s.ax & 0xFFFF
                res["calls"] += 1
                if predicted == actual:
                    res["ok"] += 1
                else:
                    res["fail"].append((predicted, actual))
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

    print(f"demo {demo_name} ({max_frames} frames): native project_object_to_di vs VM 30D2: "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])}")
    for predicted, actual in res["fail"][:8]:
        print(f"  FAIL predicted={predicted} actual={actual:#06x}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native projection byte-exact vs the VM across the demo"
          if ok else "CHECK -- no projections reached, or a divergence")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
