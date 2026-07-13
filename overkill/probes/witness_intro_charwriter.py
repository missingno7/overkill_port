"""Witness the COLD-BOOT INTRO char-writer: which routine drives the blueprint typewriter, and what
glyph stream does it draw.

The text/glyph path (1010:518C string loop -> 519A dispatch -> 3153 Tandy glyph draw) is ALREADY
fully recovered (`overkill/rendering/text.py`, wired as VM hooks in `overkill/hook_wrappers/text.py`).
`docs/overkill/run_status.md` (2026-07-13) established the cold-boot blueprint is CHAR-WRITTEN from
present-frame f447 (~1 glyph/present-frame) rather than the attract's 3-beat cell reveal, but the
CALLER driving that per-frame reveal was unidentified -- the free-running snapshot never takes that
code path (it falls into the steady attract cycle instead).

This probe wraps the 3153 glyph-draw hook over a COLD-START demo replay (real timing, real command
tail) and records, per glyph draw: the present-frame boundary it happened in, the caller's return
address (read off the stack at entry -- 3153 is a hook REPLACEMENT, so the real call site's return IP
is exactly what's on SS:SP), the character, cursor (x,y), and colour.  That directly answers both open
questions: the exact per-frame trigger routine (the caller address) and the literal briefing text.

Usage:
    pypy -m overkill.probes.witness_intro_charwriter [demo_name] [--frames N] [--from F]
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
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
    import overkill.hooks  # noqa: F401 -- registers the hooks (incl. hook_wrappers.text)
    from dos_re.hooks import registry

    demo = load_demo(demo_name, demo_name)
    meta = demo.manifest.get("metadata", {})
    video = str(meta.get("video", "tandy"))
    tail = str(meta.get("command_tail", "")) if demo.is_cold_start else b""

    # Hook 519A (the DISPATCHER), not 3153 -- 519A has THREE branches (Tandy-3153 glyph draw,
    # an "unlifted non-Tandy backend" ASM run, and a raw text_backend==0 ES:DI word-write path) and
    # only the first is witnessed by hooking 3153.  Hooking the dispatcher catches all three so the
    # cold-boot path (which may not be the 3153 branch at all) is not missed.
    dispatch_rep = registry.replacements[(0x1010, 0x519A)]
    original = dispatch_rep.handler

    events: list[dict] = []
    state = {"f": 0, "ref": None}

    def witnessed_dispatch(cpu):
        f = state["f"]
        if from_frame <= f < from_frame + max_frames:
            al = cpu.s.ax & 0xFF
            ds = cpu.s.ds & 0xFFFF
            cs = cpu.s.cs & 0xFFFF
            ss = cpu.s.ss & 0xFFFF
            ret = cpu.mem.rw(ss, cpu.s.sp & 0xFFFF)
            text_backend = cpu.mem.rw(ds, 0x21A2)
            mode = cpu.mem.rw(cs, 0x95BC)
            target = cpu.mem.rw(cs, (0x51B2 + (mode << 4)) & 0xFFFF) if text_backend != 0 else None
            events.append({
                "f": f, "char": al, "ret": f"{cs:04X}:{ret:04X}",
                "x": cpu.mem.rb(ds, 0x215E), "y": cpu.mem.rw(ds, 0x2160),
                "colour": cpu.mem.rb(ds, 0x215C),
                "backend": text_backend, "mode": mode, "target": target,
            })
        original(cpu)

    object.__setattr__(dispatch_rep, "handler", witnessed_dispatch)

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
        object.__setattr__(dispatch_rep, "handler", original)
    return events


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("demo", nargs="?", default=DEFAULT_DEMO)
    ap.add_argument("--frames", type=int, default=150)
    ap.add_argument("--from-frame", type=int, default=440, dest="from_frame")
    args = ap.parse_args(argv)
    events = witness(args.demo, args.frames, args.from_frame)
    print(f"{len(events)} dispatch calls in boundaries [{args.from_frame}, {args.from_frame + args.frames})")
    callers = Counter(e["ret"] for e in events)
    print(f"caller return addresses: {callers.most_common(10)}")
    backends = Counter((e["backend"], e["mode"], e["target"]) for e in events)
    print(f"(backend,mode,target) combos: {backends.most_common(10)}")
    for e in events[:60]:
        ch = chr(e["char"]) if 0x20 <= e["char"] < 0x7F else "."
        tgt = "-" if e["target"] is None else f"{e['target']:04X}"
        print(f"  f={e['f']:4d}  '{ch}' ({e['char']:#04x})  @ x={e['x']:#04x} y={e['y']:#06x} "
              f"colour={e['colour']:#03x}  backend={e['backend']} mode={e['mode']} target={tgt} "
              f"caller={e['ret']}")
    text = "".join(chr(e["char"]) if 0x20 <= e["char"] < 0x7F else "\n" if e["char"] in (0x0D, 0x0A) else "."
                   for e in events if e["char"] >= 0x12)
    print(f"\nfull text drawn: {text!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
