"""Locate the cold-boot blueprint char-writer's SOURCE draw call by watching the actual pixel-copy
primitives that fire every frame in the reveal window (`witness_all_hooks_window.py` narrowed the
candidates to 306F "tandy_rect_copy" and 30BA "tandy_patched_row_copy" -- the only per-frame routines
besides the already-understood dirty-cell PRESENTER, which only flushes what's already dirty and can't
itself be the source of new content).  Also traps the D2B8/1F8F:0980 far-renderer at the instruction
level in the same pass (zero hits in an isolated run -- confirming here rules it out for good).

Logs each 306F/30BA hit's registers (si=likely source, di=likely dest, cx=likely count) per boundary,
with RELIABLE boundary numbers (the same `pump_demo_frame` boundary counter the whole harness uses),
so a growing si/cx across frames would directly show the reveal advancing.

Usage:
    pypy -m overkill.probes.witness_charwriter_source [demo_name] [--frames N] [--from F]
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
from dos_re.step_probe import install_step_observer  # noqa: E402

DEFAULT_DEMO = "demo_cold_start_intro_20260711_203259"
FAR_TARGETS = {(0x1F8F, 0x0980): "farRenderer:1F8F:0980", (0x1010, 0xD2B8): "D2B8:renderSetup"}


def witness(demo_name: str, max_frames: int, from_frame: int):
    import overkill.hooks  # noqa: F401
    from dos_re.hooks import registry

    demo = load_demo(demo_name, demo_name)
    meta = demo.manifest.get("metadata", {})
    video = str(meta.get("video", "tandy"))
    tail = str(meta.get("command_tail", "")) if demo.is_cold_start else b""

    state = {"f": 0, "ref": None}
    events: list[dict] = []
    far_events: list[dict] = []

    wrapped_keys = {(0x1010, 0x306F): "306F:rectCopy", (0x1010, 0x30BA): "30BA:patchedRowCopy"}
    originals = {}
    for key, name in wrapped_keys.items():
        rep = registry.replacements[key]
        originals[key] = rep.handler

        def make_wrapped(rep=rep, name=name, orig=rep.handler):
            def wrapped(cpu):
                f = state["f"]
                if from_frame <= f < from_frame + max_frames:
                    ds = cpu.s.ds & 0xFFFF
                    si = cpu.s.si & 0xFFFF
                    src_bytes = bytes(cpu.mem.rb(ds, (si + i) & 0xFFFF) for i in range(40))
                    events.append({
                        "f": f, "name": name,
                        "ax": cpu.s.ax & 0xFFFF, "bx": cpu.s.bx & 0xFFFF, "cx": cpu.s.cx & 0xFFFF,
                        "dx": cpu.s.dx & 0xFFFF, "si": si, "di": cpu.s.di & 0xFFFF,
                        "es": cpu.s.es & 0xFFFF, "ds": ds, "src": src_bytes,
                    })
                orig(cpu)
            return wrapped

        object.__setattr__(rep, "handler", make_wrapped())

    def on_far(cpu):
        f = state["f"]
        if from_frame <= f < from_frame + max_frames:
            cs, ip = cpu.s.cs & 0xFFFF, cpu.s.ip & 0xFFFF
            far_events.append({"f": f, "name": FAR_TARGETS[(cs, ip)],
                               "ax": cpu.s.ax & 0xFFFF, "si": cpu.s.si & 0xFFFF, "di": cpu.s.di & 0xFFFF})

    orig_load = fv._load_runtime
    sides = iter(("ref", "cand"))

    def patched(exe, assets, snap, t):
        rt = orig_load(exe, assets, snap, t)
        if next(sides) == "ref":
            state["ref"] = rt
            install_step_observer(rt.cpu, on_far, trap=frozenset(FAR_TARGETS))
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
        for key, rep in registry.replacements.items():
            if key in originals:
                object.__setattr__(rep, "handler", originals[key])
    return events, far_events


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("demo", nargs="?", default=DEFAULT_DEMO)
    ap.add_argument("--frames", type=int, default=40)
    ap.add_argument("--from-frame", type=int, default=447, dest="from_frame")
    args = ap.parse_args(argv)
    events, far_events = witness(args.demo, args.frames, args.from_frame)
    print(f"far-renderer hits: {len(far_events)}  (should confirm zero if D2B8/0980 is ruled out)")
    for e in far_events[:20]:
        print(f"  f={e['f']:4d}  {e['name']}  ax={e['ax']:04X} si={e['si']:04X} di={e['di']:04X}")
    print(f"\n306F/30BA hits: {len(events)} in boundaries [{args.from_frame}, {args.from_frame + args.frames})")
    for e in events:
        print(f"  f={e['f']:4d}  {e['name']:20s}  ax={e['ax']:04X} bx={e['bx']:04X} cx={e['cx']:04X} "
              f"dx={e['dx']:04X} si={e['si']:04X} di={e['di']:04X} es={e['es']:04X} ds={e['ds']:04X} "
              f"src={e['src'].hex()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
