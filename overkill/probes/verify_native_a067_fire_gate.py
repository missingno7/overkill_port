"""Verify the native A067 action/spawn fan-out entry gate (``action_fanout_gate``) vs the VM.

A067 (the fire-button action fan-out) opens with a trigger + latch decision whose ONLY state write is
DS:A980 (the latch word): not pressed -> A980 = 0 + no fan-out; pressed + repeatable -> A980 = 1 + fan-out;
pressed but held-non-repeatable -> A980 unchanged + no fan-out.  Step-hook A067's entry on the pure-VM
(oracle) side, project DS:98BE/A980/9790/232A, run ``action_fanout_gate``, and at A067's return address
assert DS:A980 equals the predicted ``new_latch_word``, for every real A067 dispatch across the demo.

Usage:
    python -m overkill.probes.verify_native_a067_fire_gate [demo_name] [max_frames]
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
from overkill.recovered.systems.action_spawns import action_fanout_gate  # noqa: E402

CS = 0x1010
A067_ENTRY = 0xA067
INPUT_98BE = 0x98BE      # action input byte (bit 4 = trigger)
LATCH_A980 = 0xA980      # the latch word (the gate's only state write)
REPEAT_9790 = 0x9790     # repeat-enable byte
STATE_232A = 0x232A      # repeatable-state word


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
        if getattr(self, "_side", "") == "ref" and (self.s.cs & 0xFFFF) == CS:
            ip = self.s.ip & 0xFFFF
            mem = self.mem
            ds = self.s.ds & 0xFFFF
            ss = self.s.ss & 0xFFFF
            key = id(self)
            if ip == A067_ENTRY and key not in pending:
                pred = action_fanout_gate(
                    mem.rb(ds, INPUT_98BE), mem.rw(ds, LATCH_A980),
                    mem.rb(ds, REPEAT_9790), mem.rw(ds, STATE_232A),
                )
                ret_addr = mem.rw(ss, self.s.sp & 0xFFFF)
                pending[key] = (ret_addr, (self.s.sp + 2) & 0xFFFF, pred)
            else:
                p = pending.get(key)
                if p is not None and ip == p[0] and (self.s.sp & 0xFFFF) == p[1]:
                    _ret, _sp, pred = pending.pop(key)
                    a980 = mem.rw(ds, LATCH_A980)
                    res["calls"] += 1
                    if a980 == pred.new_latch_word:
                        res["ok"] += 1
                    else:
                        res["fail"].append((a980, pred.new_latch_word, pred.runs))
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

    print(f"demo {demo_name} ({max_frames} frames): native action_fanout_gate vs VM A067 DS:A980: "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])}")
    for a980, pred_a980, runs in res["fail"][:5]:
        print(f"  FAIL DS:A980 vm={a980:#06x} native={pred_a980:#06x} (predicted runs={runs})")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native A067 fan-out gate (DS:A980) byte-exact vs the VM across the demo"
          if ok else "CHECK -- no A067 dispatches reached, or a divergence")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
