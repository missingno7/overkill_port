"""Verify the native score producer (advance_hud_score) is byte-exact vs the VM's 1010:5F0D
across a gameplay demo -- the §1.2 produced-vs-VM gate for the score (ScoreState).

Step-hook 5F0D on the pure-VM (oracle) side; at entry capture the score (SS:2314..2317) packed
into ``HudLayer.score_bcd`` (the representation ``NativeGameState`` carries) plus the BCD delta in
BX, and predict the next score via the native :func:`advance_hud_score`; at the routine's return
read the actual score and assert they match -- for every real in-game score event.

An all-match run means the native score producer reproduces the VM byte-exact on real inputs.
(The synthetic per-routine oracle is ``test_bcd_add_score_5f0d_matches_interpreted_asm``; this is
the demo-level confirmation against the actual score deltas the game generates.)

Usage:
    python -m overkill.probes.verify_native_score [demo_name] [max_frames]
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
from overkill.recovered.domain.frame_snapshot import HudLayer  # noqa: E402
from overkill.recovered.systems.score import advance_hud_score  # noqa: E402

CS = 0x1010
SCORE_OFF = 0x2314


def _read_score_bcd(cpu) -> tuple[int, int]:
    ss = cpu.s.ss & 0xFFFF
    b = [cpu.mem.rb(ss, (SCORE_OFF + i) & 0xFFFF) for i in range(4)]
    return (b[0] | (b[1] << 8), b[2] | (b[3] << 8))


def main(argv) -> int:
    demo_name = argv[0] if argv else "demo_play_tandy_L2_full_20260617_180221"
    max_frames = int(argv[1]) if len(argv) > 1 else 1200
    demo = InputDemoPlayback.load(ROOT / "artifacts" / "demos" / demo_name)
    snapshot = demo.snapshot_path()
    video = str(demo.manifest.get("metadata", {}).get("video", "tandy"))

    res = {"calls": 0, "ok": 0, "fail": []}
    pending: dict[int, tuple[int, int]] = {}
    orig_step = CPU8086.step

    def step(self):
        if getattr(self, "_side", "") == "ref":
            cs = self.s.cs & 0xFFFF
            ip = self.s.ip & 0xFFFF
            key = id(self)
            if cs == CS and ip == 0x5F0D and key not in pending:
                hud = HudLayer(counters=(), score_bcd=_read_score_bcd(self))
                pending[key] = advance_hud_score(hud, self.s.bx & 0xFFFF).score_bcd
            elif key in pending and not (cs == CS and 0x5F0D <= ip <= 0x5F42):
                predicted = pending.pop(key)
                actual = _read_score_bcd(self)
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

    print(f"demo {demo_name} ({max_frames} frames): native advance_hud_score vs VM 5F0D: "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])}")
    for predicted, actual in res["fail"][:10]:
        print(f"  FAIL predicted={predicted} actual={actual}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native score producer byte-exact vs the VM across the demo"
          if ok else "CHECK -- no score events reached, or a divergence")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
