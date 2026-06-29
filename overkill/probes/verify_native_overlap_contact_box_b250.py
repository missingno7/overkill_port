"""Verify the native B250 overlap predicate (``overlap_contact_box_contains`` + the substate-1
skip) selects the same tail as the VM's 1010:B250 selector across a gameplay demo -- the
produced-vs-VM gate for the shared overlap/contact decision that several object behaviors
(b24d/aed8/...) reach.

Step-hook B250 on the pure-VM (oracle/ref) side of the frame verifier.  At its entry read the
slot's X/Y (SS:[BP+2]/[+4]), the skip-overlap substate (SS:[BP+1E]), and the reference box
(DS:237E/2380), and predict the tail the selector will route to: the no-contact tail (AD5A)
when the substate skips or the slot is outside the box, else the contact tail (ADC9).  Then
watch for the first AD5A/ADC9 the real ASM reaches and assert it matches -- for every B250 call.

An all-match run means the recovered pure overlap predicate reproduces the VM's B250 contact
decision byte-exact.  (The per-routine oracle is ``tests/test_overlap_contact_box_contains``.)

Usage:
    python -m overkill.probes.verify_native_overlap_contact_box_b250 [demo_name] [max_frames]
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
from overkill.gameplay.contact_overlap import (  # noqa: E402
    OVERLAP_REF_BOX_X,
    OVERLAP_REF_BOX_Y,
    SUBSTATE_SKIP_OVERLAP,
    TAIL_CONTACT,
    TAIL_NO_CONTACT,
)
from overkill.input_waits import pump_demo_frame  # noqa: E402
from overkill.recovered.systems.collision import overlap_contact_box_contains  # noqa: E402
from overkill.recovered.views.object_slots import (  # noqa: E402
    OFF_SCAN_ENABLE_OR_SOLID,
    OFF_X,
    OFF_Y,
)

CS = 0x1010
B250 = 0xB250
TAILS = (TAIL_NO_CONTACT, TAIL_CONTACT)


def main(argv) -> int:
    demo_name = argv[0] if argv else "demo_play_tandy_L2_full_20260617_180221"
    max_frames = int(argv[1]) if len(argv) > 1 else 1200
    demo = InputDemoPlayback.load(ROOT / "artifacts" / "demos" / demo_name)
    snapshot = demo.snapshot_path()
    video = str(demo.manifest.get("metadata", {}).get("video", "tandy"))

    res = {"calls": 0, "ok": 0, "fail": []}
    pending: dict[int, int] = {}
    orig_step = CPU8086.step

    def step(self):
        if getattr(self, "_side", "") == "ref":
            cs = self.s.cs & 0xFFFF
            ip = self.s.ip & 0xFFFF
            key = id(self)
            if cs == CS and ip == B250 and key not in pending:
                ss = self.s.ss & 0xFFFF
                ds = self.s.ds & 0xFFFF
                bp = self.s.bp & 0xFFFF
                rw = self.mem.rw
                substate = rw(ss, (bp + OFF_SCAN_ENABLE_OR_SOLID) & 0xFFFF)
                obj_x = rw(ss, (bp + OFF_X) & 0xFFFF)
                obj_y = rw(ss, (bp + OFF_Y) & 0xFFFF)
                ref_x = rw(ds, OVERLAP_REF_BOX_X)
                ref_y = rw(ds, OVERLAP_REF_BOX_Y)
                contact = (substate != SUBSTATE_SKIP_OVERLAP) and overlap_contact_box_contains(
                    obj_x, obj_y, ref_x, ref_y
                )
                pending[key] = TAIL_CONTACT if contact else TAIL_NO_CONTACT
            elif key in pending and cs == CS and ip in TAILS:
                predicted = pending.pop(key)
                res["calls"] += 1
                if ip == predicted:
                    res["ok"] += 1
                else:
                    res["fail"].append((predicted, ip))
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

    print(f"demo {demo_name} ({max_frames} frames): native B250 overlap predicate vs VM tail: "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])}")
    for predicted, actual in res["fail"][:10]:
        print(f"  FAIL predicted={predicted:#06x} actual={actual:#06x}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native B250 overlap predicate byte-exact vs the VM across the demo"
          if ok else "CHECK -- no B250 calls reached, or a divergence")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
