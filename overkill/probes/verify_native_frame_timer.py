"""Verify the native frame-timer step (step_first_active_timer) is byte-exact vs the VM's 1010:61C7
across a gameplay demo -- the §1.2 produced-vs-VM gate for the frame-timer countdown table (a
distinct per-frame state, decremented ~23x/frame via the 61F7 loop).

61C7 scans the 6-word countdown table at DS:2368, decrements the first non-zero counter, and
returns (at 61D1 found / 61DB all-zero).  Step-hook 61C7 on the pure-VM (oracle) side: at entry
snapshot the table and predict the next table via ``step_first_active_timer(counters, 0)``; at the
return read the table and assert it matches -- for every real frame-timer tick.

An all-match run means the native frame-timer step reproduces the VM byte-exact on the real tick
sequence.  Grows the cross-demo native-producer gate to a distinct state beyond the object lifecycle.

Usage:
    python -m overkill.probes.verify_native_frame_timer [demo_name] [max_frames]
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
from overkill.recovered.systems.frame_timers import step_first_active_timer  # noqa: E402
from overkill.recovered.views.object_slots import FRAME_TIMER_COUNT, FRAME_TIMER_TABLE_BASE  # noqa: E402

CS = 0x1010
SCAN_IP = 0x61C7        # mov di,2368 -> scan; always starts at table base (start_index 0)
RET_IPS = (0x61D1, 0x61DB)  # found+decremented / all-zero


def _read_timers(cpu) -> tuple[int, ...]:
    ds = cpu.s.ds & 0xFFFF
    return tuple(cpu.mem.rw(ds, (FRAME_TIMER_TABLE_BASE + 2 * i) & 0xFFFF) for i in range(FRAME_TIMER_COUNT))


def main(argv) -> int:
    demo_name = argv[0] if argv else "demo_play_tandy_L2_full_20260617_180221"
    max_frames = int(argv[1]) if len(argv) > 1 else 1200
    demo = InputDemoPlayback.load(ROOT / "artifacts" / "demos" / demo_name)
    snapshot = demo.snapshot_path()
    video = str(demo.manifest.get("metadata", {}).get("video", "tandy"))

    res = {"calls": 0, "ok": 0, "fail": []}
    pending: dict[int, tuple[int, ...]] = {}
    orig_step = CPU8086.step

    def step(self):
        if getattr(self, "_side", "") == "ref":
            cs = self.s.cs & 0xFFFF
            ip = self.s.ip & 0xFFFF
            key = id(self)
            if cs == CS and ip == SCAN_IP and key not in pending:
                pending[key] = step_first_active_timer(_read_timers(self), 0).counters
            elif key in pending and cs == CS and ip in RET_IPS:
                predicted = pending.pop(key)
                actual = _read_timers(self)
                res["calls"] += 1
                if actual == predicted:
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

    print(f"demo {demo_name} ({max_frames} frames): native step_first_active_timer vs VM 61C7: "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])}")
    for predicted, actual in res["fail"][:5]:
        print(f"  FAIL predicted={predicted} actual={actual}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native frame-timer step byte-exact vs the VM across the demo"
          if ok else "CHECK -- no timer ticks reached, or a divergence")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
