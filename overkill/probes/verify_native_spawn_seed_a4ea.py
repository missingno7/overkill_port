"""Verify the native A4EA spawn template (object_spawn_seed_a4ea) is byte-exact vs the VM's
1010:A4EA across a gameplay demo -- the §1.2 produced-vs-VM gate for the logic=2 spawn (a distinct
object-creation template from 8209's logic=14h effect).

A4EA allocates a slot (its leading ``call 7547``) then stamps a constant template, so the verify
needs no inputs: step-hook the routine's terminal ``RET`` at A514 on the pure-VM (oracle) side --
by then BX is the freshly allocated+stamped slot -- read its stamped fields and assert they equal
the native ``object_spawn_seed_a4ea()`` constant, for every real A4EA spawn.

(The synthetic oracle is ``test_object_spawn_seed_a4ea_free_path_matches_original``; this is the
demo-level confirmation, growing the cross-demo native-producer gate.)

Usage:
    python -m overkill.probes.verify_native_spawn_seed_a4ea [demo_name] [max_frames]
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
from overkill.recovered.systems.objects import object_spawn_seed_a4ea  # noqa: E402
from overkill.recovered.views.object_slots import ObjectSlotView  # noqa: E402

CS = 0x1010
A4EA_RET = 0xA514  # the terminal RET of A4EA: BX = the allocated+stamped slot, stamp complete

_FIELDS = (
    "active_word", "scan_enable_or_solid", "direction_or_step", "sprite_or_state",
    "scan_flag", "hazard_class", "logic_id", "substate",
)


def main(argv) -> int:
    demo_name = argv[0] if argv else "demo_play_tandy_L2_full_20260617_180221"
    max_frames = int(argv[1]) if len(argv) > 1 else 1200
    demo = InputDemoPlayback.load(ROOT / "artifacts" / "demos" / demo_name)
    snapshot = demo.snapshot_path()
    video = str(demo.manifest.get("metadata", {}).get("video", "tandy"))

    res = {"calls": 0, "ok": 0, "fail": []}
    orig_step = CPU8086.step

    def step(self):
        if getattr(self, "_side", "") == "ref" and (self.s.cs & 0xFFFF) == CS and (self.s.ip & 0xFFFF) == A4EA_RET:
            slot = ObjectSlotView(self.mem, self.s.ds & 0xFFFF, self.s.bx & 0xFFFF)
            seed = object_spawn_seed_a4ea()
            mismatches = [
                (f, getattr(slot, f), getattr(seed, f)) for f in _FIELDS
                if getattr(slot, f) != getattr(seed, f)
            ]
            res["calls"] += 1
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

    print(f"demo {demo_name} ({max_frames} frames): native object_spawn_seed_a4ea vs VM A4EA: "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])}")
    for mismatches in res["fail"][:5]:
        print(f"  FAIL {mismatches}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native A4EA spawn template byte-exact vs the VM across the demo"
          if ok else "CHECK -- no A4EA spawns reached, or a divergence")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
