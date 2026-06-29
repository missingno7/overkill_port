"""Verify the native HUD text composer (``hud_text.compose_status_text_5edb``) is byte-exact
vs the VM's ``1010:5EDB`` HUD/status line across a gameplay demo -- the brief's "HUD digits
byte-exact vs B800's digit band" gate, as a §1.2 produced-vs-VM check.

Step-hook ``5EDB`` on the pure-VM (oracle/ref) side of the frame verifier.  At its entry
capture exactly the inputs the VM reads -- the label string at ``SS:2318``, the four score
bytes at ``SS:2314``, the colour/cursor globals ``DS:215C/215E/2160``, and the recovered
glyph font (``DS:1816``) -- plus a copy of the live visible B800 page (``CS:[95A4]``), and
compose the line natively into that copy.  At ``5EDB``'s return read the page the real ASM
actually wrote and assert it is byte-identical to the native composition.

An all-match run means the native HUD text rendering reproduces the VM's packed B800 output
byte-exact on real, in-game score/HUD state -- for every frame's HUD line across the demo.
(The synthetic per-routine oracle is ``tests/test_hud_text.py`` + the glyph-leaf witness
``overkill.probes.verify_hud_glyph``; this is the demo-level B800-band confirmation.)

Usage:
    python -m overkill.probes.verify_native_hud_text [demo_name] [max_frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import overkill.frame_verify as fv  # noqa: E402
from dos_re.cpu import CPU8086  # noqa: E402
from dos_re.input_demo import InputDemoPlayback  # noqa: E402
from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier  # noqa: E402
from overkill.input_waits import pump_demo_frame  # noqa: E402
from overkill.native_video.hud_text import (  # noqa: E402
    PAGE_SIZE,
    compose_status_text_5edb,
    read_glyph_font,
)

CS = 0x1010
EDB = 0x5EDB
LABEL_OFF = 0x2318
SCORE_OFF = 0x2314
COLOUR_OFF = 0x215C
COL_OFF = 0x215E
ROWB_OFF = 0x2160
PAGE_SEG_PTR = 0x95A4    # CS:[95A4] = the visible page segment 3153 draws into
MAX_LABEL = 96           # the status string is short; read a generous NUL-terminated window


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
            if cs == CS and ip == EDB and key not in pending:
                ds = self.s.ds & 0xFFFF
                ss = self.s.ss & 0xFFFF
                rb = self.mem.rb
                mem_np = np.frombuffer(self.mem.data, dtype=np.uint8)
                font = read_glyph_font(mem_np, ds)
                label = [rb(ss, (LABEL_OFF + i) & 0xFFFF) for i in range(MAX_LABEL)]
                score = [rb(ss, (SCORE_OFF + i) & 0xFFFF) for i in range(4)]
                colour = rb(ds, COLOUR_OFF)
                col = rb(ds, COL_OFF)
                row_base = self.mem.rw(ds, ROWB_OFF)
                page_seg = self.mem.rw(cs, PAGE_SEG_PTR)
                base = ((page_seg & 0xFFFF) << 4) & 0xFFFFF
                predicted = mem_np[base:base + PAGE_SIZE].copy()
                compose_status_text_5edb(predicted, font=font, label_bytes=label,
                                         score_bytes=score, colour=colour, col=col,
                                         row_base=row_base)
                ret_addr = self.mem.rw(ss, self.s.sp & 0xFFFF)
                entry_sp = (self.s.sp + 2) & 0xFFFF  # sp after 5EDB returns
                pending[key] = (ret_addr, entry_sp, base, predicted)
            elif key in pending:
                ret_addr, ret_sp, base, predicted = pending[key]
                if ip == ret_addr and (self.s.sp & 0xFFFF) == ret_sp:
                    pending.pop(key)
                    mem_np = np.frombuffer(self.mem.data, dtype=np.uint8)
                    actual = mem_np[base:base + PAGE_SIZE]
                    res["calls"] += 1
                    if np.array_equal(actual, predicted):
                        res["ok"] += 1
                    else:
                        diffs = np.flatnonzero(actual != predicted)
                        res["fail"].append((int(diffs.size), [int(d) for d in diffs[:6]]))
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

    print(f"demo {demo_name} ({max_frames} frames): native HUD text vs VM 5EDB B800: "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])}")
    for nbytes, offs in res["fail"][:10]:
        print(f"  FAIL {nbytes} diff bytes; first offsets {[f'{o:#06x}' for o in offs]}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native HUD text byte-exact vs the VM's B800 across the demo"
          if ok else "CHECK -- no HUD lines reached, or a divergence")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
