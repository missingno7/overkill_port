"""Trace the CDAA dirty-cell PRESENTER (`changed_dword_present_8rows_cdaa`, already recovered) over the
cold-boot char-writer window: it copies an already-drawn WORK-BUFFER cell to visible B800h.  Visual
proof (`artifacts/intro_frame_dump/f0500.png` etc, 2026-07-13) confirms REAL varying glyph shapes
appear over time, but the steady-state 306F calls in this window always carry a FIXED solid-FF 8x1
payload (a moving cursor stamp, not the glyphs) -- so the actual glyph pixels must already be present
in CDAA's SOURCE (DS:SI) by the time it fires.  This dumps CDAA's (ds,si,di,cx) and the source bytes it
is about to flush, to find where that source buffer is and whether it visibly varies per character.

Usage:
    pypy -m overkill.probes.witness_cdaa_presenter [demo_name] [--frames N] [--from F]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))

import overkill.frame_verify as fv  # noqa: E402
from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier  # noqa: E402
from overkill.probes._harness import load_demo  # noqa: E402
from overkill.input_waits import pump_demo_frame  # noqa: E402

DEFAULT_DEMO = "demo_cold_start_intro_20260711_203259"


def witness(demo_name: str, max_frames: int, from_frame: int):
    import overkill.hooks  # noqa: F401
    from dos_re.hooks import registry

    demo = load_demo(demo_name, demo_name)
    meta = demo.manifest.get("metadata", {})
    video = str(meta.get("video", "tandy"))
    tail = str(meta.get("command_tail", "")) if demo.is_cold_start else b""

    state = {"f": 0, "ref": None}
    events: list[dict] = []

    key = (0x1010, 0xCDAA)
    rep = registry.replacements[key]
    original = rep.handler

    def wrapped(cpu):
        f = state["f"]
        if from_frame <= f < from_frame + max_frames:
            ds = cpu.s.ds & 0xFFFF
            es = cpu.s.es & 0xFFFF
            si = cpu.s.si & 0xFFFF
            di = cpu.s.di & 0xFFFF
            cx = cpu.s.cx & 0xFFFF
            rows = cx if cx else 0x10000
            # sample up to 4 rows of the 4-byte cell (stride 0x00A0) it is about to flush
            sample = []
            for r in range(min(rows, 4)):
                off = (si + r * 0x00A0) & 0xFFFF
                sample.append(bytes(cpu.mem.rb(ds, (off + i) & 0xFFFF) for i in range(4)))
            events.append({"f": f, "ds": ds, "es": es, "si": si, "di": di, "cx": cx, "sample": sample})
        original(cpu)

    object.__setattr__(rep, "handler", wrapped)

    orig_load = fv._load_runtime
    sides = iter(("ref", "cand"))

    def patched(exe, assets, snap, t):
        rt = orig_load(exe, assets, snap, t)
        if next(sides) == "ref":
            state["ref"] = rt
        return rt

    fv._load_runtime = patched

    def pump(ref, cand):
        pump_demo_frame(demo, state["f"], (ref, cand), ref.cpu)
        state["f"] += 1

    cfg = FrameVerifyConfig(video=video, source="candidate", max_frames=from_frame + max_frames,
                            semantic_state_check=False, stop_on_diff=False, log_every=0,
                            frame_budget=120_000_000)
    try:
        run_frame_verifier(exe=ROOT / "assets" / "OVERKILL", assets=ROOT / "assets",
                           snapshot=None, command_tail=tail, config=cfg, pump_inputs=pump)
    finally:
        fv._load_runtime = orig_load
        object.__setattr__(rep, "handler", original)
    return events


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("demo", nargs="?", default=DEFAULT_DEMO)
    ap.add_argument("--frames", type=int, default=30)
    ap.add_argument("--from-frame", type=int, default=490, dest="from_frame")
    args = ap.parse_args(argv)
    events = witness(args.demo, args.frames, args.from_frame)
    print(f"{len(events)} CDAA hits in boundaries [{args.from_frame}, {args.from_frame + args.frames})")
    for e in events:
        rows_hex = " ".join(row.hex() for row in e["sample"])
        print(f"  f={e['f']:4d}  ds={e['ds']:04X} es={e['es']:04X} si={e['si']:04X} di={e['di']:04X} "
              f"cx={e['cx']:04X}  rows={rows_hex}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
