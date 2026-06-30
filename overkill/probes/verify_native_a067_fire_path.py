"""Verify the native A067 spawn-path branch (``a067_fire_path``) vs the VM.

After the A067 entry gate arms, A067 picks one of five spawn paths.  The clean produced-vs-VM witness is
the held-action counter copy A970..976 -> A3A0..6: every FULL path performs it (a DS:A3A0 write) and the
EARLY tails do not.  So step-hook A067 on the oracle side and, between its entry and its return, watch for
the DS:A3A0 write (FULL) and for the A1C8 / A19F early-tail IPs (the two EARLY sub-paths); classify the
observed path and assert it matches ``a067_fire_path``'s prediction (FULL grouped, since the BDAC/BE06 sub
split inside FULL is downstream of the A0E8 control-flow tangle and is unit-tested instead).

Usage:
    python -m overkill.probes.verify_native_a067_fire_path [demo_name] [max_frames]
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
from overkill.recovered.systems.action_spawns import (  # noqa: E402
    A067FirePath, a067_fire_path, a067_path_copies_counters, action_fanout_gate,
)

CS = 0x1010
A067_ENTRY = 0xA067
SCROLL_2350, BDAC, FIRE_STATE_A958, BE06 = 0x2350, 0xBDAC, 0xA958, 0xBE06
INPUT_98BE, LATCH_A980, REPEAT_9790, STATE_232A = 0x98BE, 0xA980, 0x9790, 0x232A
A3A0 = 0xA3A0              # the counter-copy destination (FULL-only write)
A1C8_TAIL, A19F_TAIL = 0xA1C8, 0xA19F


def main(argv) -> int:
    demo_name = argv[0] if argv else "demo_play_tandy_L2_full_20260617_180221"
    max_frames = int(argv[1]) if len(argv) > 1 else 1200
    demo = InputDemoPlayback.load(ROOT / "artifacts" / "demos" / demo_name)
    snapshot = demo.snapshot_path()
    video = str(demo.manifest.get("metadata", {}).get("video", "tandy"))

    res = {"calls": 0, "ok": 0, "fail": []}
    st = {"in": False, "a3a0": False, "a1c8": False, "a19f": False,
          "a3a0_lin": 0, "ret": 0, "ret_sp": 0, "pred": None, "watch": False}
    orig_step = CPU8086.step

    def watcher(addr, old, new):
        if st["in"] and (addr & 0xFFFFF) == st["a3a0_lin"]:
            st["a3a0"] = True

    def step(self):
        if getattr(self, "_side", "") == "ref" and (self.s.cs & 0xFFFF) == CS:
            ip = self.s.ip & 0xFFFF
            mem = self.mem
            ds = self.s.ds & 0xFFFF
            ss = self.s.ss & 0xFFFF
            if not st["watch"]:
                self.mem.write_watchers.append(watcher)
                st["watch"] = True
            if ip == A067_ENTRY and not st["in"]:
                # The path branch only runs when the entry gate fires; not-fired A067s return at the gate
                # (no path taken), so classify only the dispatches that actually reach the path branch.
                gate = action_fanout_gate(mem.rb(ds, INPUT_98BE), mem.rw(ds, LATCH_A980),
                                          mem.rb(ds, REPEAT_9790), mem.rw(ds, STATE_232A))
                if gate.runs:
                    st.update(
                        **{"in": True}, a3a0=False, a1c8=False, a19f=False,
                        a3a0_lin=((ds << 4) + A3A0) & 0xFFFFF, pred=a067_fire_path(
                            mem.rw(ds, SCROLL_2350), mem.rw(ds, BDAC),
                            mem.rw(ds, FIRE_STATE_A958), mem.rw(ds, BE06)),
                        ret=mem.rw(ss, self.s.sp & 0xFFFF), ret_sp=(self.s.sp + 2) & 0xFFFF)
            elif st["in"]:
                if ip == A1C8_TAIL:
                    st["a1c8"] = True
                elif ip == A19F_TAIL:
                    st["a19f"] = True
                if ip == st["ret"] and (self.s.sp & 0xFFFF) == st["ret_sp"]:
                    pred = st["pred"]
                    st["in"] = False
                    if st["a3a0"]:
                        observed = "FULL"
                    elif st["a1c8"]:
                        observed = A067FirePath.EARLY_STATE2
                    elif st["a19f"]:
                        observed = A067FirePath.EARLY_DEFAULT
                    else:
                        observed = "EARLY_UNCLASSIFIED"
                    predicted = "FULL" if a067_path_copies_counters(pred) else pred
                    res["calls"] += 1
                    if observed == predicted:
                        res["ok"] += 1
                    else:
                        res["fail"].append((str(observed), str(predicted), pred.value))
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

    print(f"demo {demo_name} ({max_frames} frames): native a067_fire_path vs VM A067 path (EARLY/FULL): "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])}")
    for observed, predicted, pred_fine in res["fail"][:5]:
        print(f"  FAIL observed={observed} predicted={predicted} (native fine path={pred_fine})")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native A067 path branch (EARLY/FULL) byte-exact vs the VM across the demo"
          if ok else "CHECK -- no A067 dispatches reached, or a divergence")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
