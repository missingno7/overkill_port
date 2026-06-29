"""Verify the native 1010:AA2B first-level object-logic dispatch (``object_logic_dispatch_aa2b``)
is byte-exact vs the VM across a gameplay demo -- the produced-vs-VM gate for the object-update
dispatch routing (the skeleton the native object-update will route through).

Step-hook AA2B on the pure-VM (oracle/ref) side of the frame verifier.  At its entry read the
slot's draw_layer (SS:[BP+16]) and assert the recovered pure routing's handler IP (the pure
``object_logic_dispatch_aa2b`` kind mapped through the adapter's CS:AA36 IP map) equals the live
CS:[AA36 + draw_layer*2] the VM actually jumps through -- for every object dispatch across the
demo.  Also reports the observed draw_layer histogram, so any layer outside the recovered 0-7 set
is surfaced rather than silently skipped.

An all-match run means the recovered draw-layer -> handler table reproduces the VM's first-level
dispatch byte-exact.  (The per-routine oracle is the VM-free ``tests/test_object_logic_dispatch_aa2b``.)

Usage:
    python -m overkill.probes.verify_native_object_logic_dispatch_aa2b [demo_name] [max_frames]
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import overkill.frame_verify as fv  # noqa: E402
from dos_re.cpu import CPU8086  # noqa: E402
from dos_re.input_demo import InputDemoPlayback  # noqa: E402
from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier  # noqa: E402
from overkill.gameplay.object_behaviors import _AA2B_HANDLER_IP_BY_KIND  # noqa: E402
from overkill.input_waits import pump_demo_frame  # noqa: E402
from overkill.recovered.systems.objects import (  # noqa: E402
    OBJECT_LOGIC_DISPATCH_AA2B_BY_LAYER,
    object_logic_dispatch_aa2b,
)

CS = 0x1010
AA2B = 0xAA2B
AA36_TABLE = 0xAA36
DRAW_LAYER_OFF = 0x16  # SS:[BP+16] -- the slot's draw_layer / hazard_class field


def main(argv) -> int:
    demo_name = argv[0] if argv else "demo_play_tandy_L2_full_20260617_180221"
    max_frames = int(argv[1]) if len(argv) > 1 else 1200
    demo = InputDemoPlayback.load(ROOT / "artifacts" / "demos" / demo_name)
    snapshot = demo.snapshot_path()
    video = str(demo.manifest.get("metadata", {}).get("video", "tandy"))

    res = {"calls": 0, "ok": 0, "fail": [], "out_of_range": 0}
    hist: Counter = Counter()
    orig_step = CPU8086.step

    def step(self):
        if getattr(self, "_side", "") == "ref":
            cs = self.s.cs & 0xFFFF
            ip = self.s.ip & 0xFFFF
            if cs == CS and ip == AA2B:
                ss = self.s.ss & 0xFFFF
                bp = self.s.bp & 0xFFFF
                draw_layer = self.mem.rw(ss, (bp + DRAW_LAYER_OFF) & 0xFFFF)
                hist[draw_layer] += 1
                live_ip = self.mem.rw(CS, (AA36_TABLE + ((draw_layer << 1) & 0xFFFF)) & 0xFFFF)
                if draw_layer < len(OBJECT_LOGIC_DISPATCH_AA2B_BY_LAYER):
                    predicted = _AA2B_HANDLER_IP_BY_KIND[object_logic_dispatch_aa2b(draw_layer).kind]
                    res["calls"] += 1
                    if predicted == live_ip:
                        res["ok"] += 1
                    else:
                        res["fail"].append((draw_layer, predicted, live_ip))
                else:
                    res["out_of_range"] += 1
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
                           snapshot=str(snapshot), command_tail=b"", config=cfg,
                           pump_inputs=pump_inputs)
    finally:
        fv._load_runtime = orig_load
        CPU8086.step = orig_step

    print(f"demo {demo_name} ({max_frames} frames): native AA2B dispatch vs VM CS:AA36: "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])} out_of_range={res['out_of_range']}")
    print(f"  draw_layer histogram: {dict(sorted(hist.items()))}")
    for dl, predicted, live in res["fail"][:10]:
        print(f"  FAIL draw_layer={dl:#x} predicted={predicted:#06x} live={live:#06x}")
    ok = res["calls"] > 0 and not res["fail"] and res["out_of_range"] == 0
    print("RESULT:", "PASS -- native AA2B dispatch routing byte-exact vs the VM across the demo"
          if ok else "CHECK -- no dispatches reached, an out-of-range draw layer, or a divergence")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
