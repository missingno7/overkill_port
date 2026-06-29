"""Verify the native scroll-script interpreter step (``scroll_script_step``) is byte-exact vs
the VM's 1010:D0D4 across a gameplay demo -- the produced-vs-VM gate for the scroll-script /
level-event state transition (roadmap #2's first recovered leaf).

Step-hook D0D4 on the pure-VM (oracle/ref) side of the frame verifier.  At its entry capture the
per-command delay (DS:BE08), the script index (DS:BE06), and the next entry words at
DS:BE1A[(index+1)*6], and predict the post-step state via the native ``scroll_script_step``.  The
interpreter then either RETs at D0DA (timer still running) or reaches D107 (delay expired -> index
advanced, entry read, about to dispatch); at whichever it reaches, read the actual DS:BE08/BE06
(and DS:95FA/BE16 on the expiry path) and assert they match -- for every frame's script step.

An all-match run means the native scroll-script state transition reproduces the VM byte-exact.
(The per-routine oracle is the VM-free ``tests/test_scroll_script_step.py``.)

Usage:
    python -m overkill.probes.verify_native_scroll_script_step [demo_name] [max_frames]
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
from overkill.recovered.systems.level_script import (  # noqa: E402
    SCROLL_SCRIPT_ENTRY_STRIDE,
    scroll_script_step,
)

CS = 0x1010
D0D4 = 0xD0D4
TIMER_RET = 0xD0DA      # interpreter RET when the delay has not expired
DISPATCH = 0xD107       # interpreter reaches here after advancing + reading the entry
DELAY_BE08 = 0xBE08
INDEX_BE06 = 0xBE06
ENTRY_TABLE_BE1A = 0xBE1A
CMD_W0_95FA = 0x95FA
CMD_W1_BE16 = 0xBE16


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
            if cs == CS and ip == D0D4 and key not in pending:
                ds = self.s.ds & 0xFFFF
                rw = self.mem.rw
                delay = rw(ds, DELAY_BE08)
                index = rw(ds, INDEX_BE06)
                ne = (ENTRY_TABLE_BE1A + ((index + 1) & 0xFFFF) * SCROLL_SCRIPT_ENTRY_STRIDE) & 0xFFFF
                step_pred = scroll_script_step(delay, index, rw(ds, ne), rw(ds, (ne + 2) & 0xFFFF))
                pending[key] = (ds, step_pred)
            elif key in pending and cs == CS and ip in (TIMER_RET, DISPATCH):
                ds, pred = pending.pop(key)
                rw = self.mem.rw
                actual_delay = rw(ds, DELAY_BE08)
                actual_index = rw(ds, INDEX_BE06)
                ok = actual_delay == pred.new_delay and actual_index == pred.new_index
                if ip == DISPATCH and pred.entry_updated:
                    ok = ok and rw(ds, CMD_W0_95FA) == pred.command_w0 and rw(ds, CMD_W1_BE16) == pred.command_w1
                res["calls"] += 1
                if ok:
                    res["ok"] += 1
                else:
                    res["fail"].append((
                        f"ip={ip:04X}", (pred.new_delay, pred.new_index, pred.entry_updated),
                        (actual_delay, actual_index, rw(ds, CMD_W0_95FA), rw(ds, CMD_W1_BE16)),
                    ))
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

    print(f"demo {demo_name} ({max_frames} frames): native scroll_script_step vs VM D0D4: "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])}")
    for tag, pred, actual in res["fail"][:10]:
        print(f"  FAIL {tag} predicted={pred} actual={actual}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native scroll-script step byte-exact vs the VM across the demo"
          if ok else "CHECK -- no script steps reached, or a divergence")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
