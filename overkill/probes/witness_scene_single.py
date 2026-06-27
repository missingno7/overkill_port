"""Probe: witness the scene timeline over a long demo on a SINGLE hooked runtime.

The both-runtime frame verifier can't replay the long start-to-end demos: the
pure-ASM reference busy-waits in the menu (no idle-yield hook) and trips the
per-frame instruction budget. This probe instead replays the demo through one
hooked runtime on the recorded boundary clock (exactly like
`scripts/capture_demo_snapshot.py`), where the hybrid menu-idle hook yields, so it
runs the whole demo: boot/menu -> game -> game-over -> menu.

It records, per boundary, the scene/HUD text glyph draws (1010:3153), the present
scroll cursor (DS:[234C] at 3354), and which key render hooks fire — yielding the
scene text producers, the scroll (camera) direction, and the scene segmentation.

Caveat: the boundary counter (loop-top IP test on the present/timer/retrace IPs)
under-counts presents that are reached via a direct installed-hook call rather
than by stepping to the IP, so on long demos the boundary clock can drift from the
recording and the input clock can desync. The hook *fire counts* (which is what
the key finding rests on — does 3153/61DC ever fire?) are exact regardless.

Finding (start_to_end demo): over a replay that exercised both menu (`menu_idle`)
and gameplay (`obj`/`present`), 3153 and 61DC fired ZERO times — all text/HUD is
page-baked at scene-entry, captured by the present+palette page decode (see
docs/overkill/render_completeness.md). No per-frame glyph model is needed.

Usage:
    python -m overkill.probes.witness_scene_single <demo_dir> [max_boundary]
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PRESENT_IP = 0x3354
TIMER_WAIT_IP = 0x0679
RETRACE_WAIT_IP = 0x50C9
GLYPH_IP = 0x3153
BOUNDARY_IPS = {PRESENT_IP, TIMER_WAIT_IP, RETRACE_WAIT_IP}

PHASE_IPS = {0x5AC8: "obj", 0x3354: "present", 0x61DC: "hud", 0x558B: "menu_idle", 0x3153: "glyph"}
CURSOR_OFF = 0x234C


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    demo_dir = Path(argv[0])
    max_boundary = int(argv[1]) if len(argv) > 1 else 6000

    import overkill.hooks  # noqa: F401 - registers hooks
    from dos_re.input_demo import InputDemoPlayback
    from overkill.runtime import load_overkill_snapshot

    demo = InputDemoPlayback.load(demo_dir)
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", demo.snapshot_path(),
                                game_root=ROOT / "assets")
    rt.cpu.trace_enabled = False
    rt.cpu.coverage_telemetry = None

    state = {"boundary": 0}
    glyphs: list[tuple[int, int, int, int, int]] = []  # (boundary, char, x, y, colour)
    cursors: list[tuple[int, int]] = []                 # (boundary, cursor)
    phase_hits: dict[int, Counter] = {}
    seen = {"glyph": False, "present": False}

    hooks = rt.cpu.replacement_hooks

    def wrap_glyph(orig):
        def h(cpu):
            al = cpu.s.ax & 0xFF
            ds = cpu.s.ds & 0xFFFF
            if al >= 0x12:
                glyphs.append((state["boundary"], al, cpu.mem.rb(ds, 0x215E),
                               cpu.mem.rw(ds, 0x2160), cpu.mem.rb(ds, 0x215C)))
                if not seen["glyph"]:
                    seen["glyph"] = True
                    print(f"  [event] first GLYPH at boundary {state['boundary']}", flush=True)
            phase_hits.setdefault(state["boundary"], Counter())["glyph"] += 1
            orig(cpu)
        return h

    def wrap_present(orig):
        def h(cpu):
            cursors.append((state["boundary"], cpu.mem.rw(cpu.s.ds & 0xFFFF, CURSOR_OFF)))
            if not seen["present"]:
                seen["present"] = True
                print(f"  [event] first PRESENT (gameplay) at boundary {state['boundary']}", flush=True)
            phase_hits.setdefault(state["boundary"], Counter())["present"] += 1
            orig(cpu)
        return h

    def wrap_phase(orig, name):
        def h(cpu):
            phase_hits.setdefault(state["boundary"], Counter())[name] += 1
            orig(cpu)
        return h

    for ip, name in PHASE_IPS.items():
        key = (0x1010, ip)
        orig = hooks.get(key)
        if orig is None:
            continue
        if ip == GLYPH_IP:
            hooks[key] = wrap_glyph(orig)
        elif ip == PRESENT_IP:
            hooks[key] = wrap_present(orig)
        else:
            hooks[key] = wrap_phase(orig, name)

    demo.apply_to_runtime(0, rt)
    s = rt.cpu.s
    step_fn = rt.cpu.step
    demo_boundary = 0
    MAX_STEPS = 200_000_000

    for step in range(1, MAX_STEPS + 1):
        if s.cs == 0x1010 and s.ip in BOUNDARY_IPS:
            state["boundary"] += 1
            if state["boundary"] > demo_boundary:
                demo_boundary = state["boundary"]
                if demo.finished(demo_boundary) or demo_boundary >= max_boundary:
                    print(f"  [done] demo finished/cap at boundary {demo_boundary}, step {step}", flush=True)
                    break
                demo.apply_to_runtime(demo_boundary, rt)
                if demo_boundary % 400 == 0:
                    print(f"  [progress] boundary {demo_boundary}: glyphs={len(glyphs)} present={len(cursors)}", flush=True)
        step_fn()

    print(f"\ndemo {demo_dir.name}: boundaries={state['boundary']} glyphs={len(glyphs)} present_calls={len(cursors)}")

    if glyphs:
        runs: list[tuple[int, int, list[int]]] = []
        for bnd, ch, x, y, col in glyphs:
            if runs and bnd - runs[-1][1] <= 4:
                runs[-1] = (runs[-1][0], bnd, runs[-1][2] + [ch])
            else:
                runs.append((bnd, bnd, [ch]))
        print(f"\n-- text runs ({len(runs)}) --")
        for b0, b1, chars in runs[:60]:
            t = "".join(chr(c) if 0x20 <= c < 0x7F else "." for c in chars)
            print(f"  boundary {b0}-{b1}: {t[:90]}")

    if cursors:
        per = {}
        for bnd, cur in cursors:
            per.setdefault(bnd, cur)
        seq = [per[b] for b in sorted(per)]
        deltas = [seq[i + 1] - seq[i] for i in range(len(seq) - 1)]
        signed = [d - 0x10000 if d > 0x8000 else (d + 0x10000 if d < -0x8000 else d) for d in deltas]
        neg = sum(1 for d in signed if d < 0)
        pos = sum(1 for d in signed if d > 0)
        zero = sum(1 for d in signed if d == 0)
        print(f"\n-- scroll cursor [234C]: forward(neg)={neg} backward(pos)={pos} static(zero)={zero} --")
        print(f"  distinct nonzero deltas: {sorted(set(d for d in signed if d))[:24]}")

    if phase_hits:
        print("\n-- phase bands (every 200 boundaries) --")
        maxb = max(phase_hits)
        for b0 in range(0, maxb + 1, 200):
            agg = Counter()
            for b in range(b0, min(b0 + 200, maxb + 1)):
                agg.update(phase_hits.get(b, {}))
            if agg:
                print(f"  boundary {b0:4d}-{b0+199:4d}: " + " ".join(f"{k}={v}" for k, v in agg.most_common()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
