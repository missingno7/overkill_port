#!/usr/bin/env python3
"""Diagnostic tracing for OVERKILL demo-replay divergences.

Replays a recorded demo through BOTH runtimes in lockstep -- the ASM oracle
(``reference``, all replacement hooks stripped) and the live hooked runtime
(``candidate``) -- with instrumentation attached to each, so the same probe runs
on both sides and you can see exactly where and how they part ways.  This
replaces the ad-hoc one-off watchpoint scripts that otherwise get rewritten for
every divergence (see the throwaway ``scripts/_debug_*`` files).

Subcommands
-----------
  watch    Log every write to an address (or range) on both sides and report the
           first write whose value diverges -- i.e. *who* writes it, at which
           CS:IP and frame, and what the two runtimes disagree on.  This is how
           the camera-Y bug was pinned to the extra 1010:9C55 write.

  observe  Dump chosen registers + memory each time execution reaches a CS:IP, on
           both sides, side by side.  Use it to compare a hook/routine's inputs
           and the path it takes (this found the 9C01 [a47c] gate divergence).

  globals  Diff a set of DS/CS globals between the two runtimes at every frame
           boundary and report the first frame they diverge -- a fast bisector
           for "which tracked value goes wrong first".

Address syntax: ``ds:2380``, ``cs:9C01``, or a literal ``2000:1234``.  The
``ds``/``cs``/``es``/``ss`` tokens resolve against the live segment registers.
A memory operand may carry a width suffix: ``ds:54:b`` (byte) or ``ds:2380:w``
(word, the default).

Examples
--------
  python scripts/trace.py watch   <demo> --addr ds:2380 --frames 60-70
  python scripts/trace.py observe <demo> --ip cs:9C01 --reg ax,bx --mem ds:2380,ds:a47c:w
  python scripts/trace.py globals <demo> --addr ds:a47c ds:2350 ds:2380
"""
from __future__ import annotations

import argparse
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))  # submodule repo root (no editable install under PyPy)

import overkill.frame_verify as fv  # noqa: E402
from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier  # noqa: E402
from dos_re.cpu import CPU8086  # noqa: E402
from dos_re.input_demo import InputDemoPlayback  # noqa: E402

EXE = ROOT / "assets" / "OVERKILL"
ASSETS = ROOT / "assets"
_SEG_TOKENS = ("ds", "cs", "es", "ss")


# --------------------------------------------------------------------------- #
# address parsing / resolution
# --------------------------------------------------------------------------- #
def parse_addr(spec: str) -> tuple:
    """``ds:2380`` -> ("ds", 0x2380); ``2000:1234`` -> (0x2000, 0x1234)."""
    seg_s, _, off_s = spec.partition(":")
    if not off_s:
        raise SystemExit(f"bad address {spec!r}; expected SEG:OFF (e.g. ds:2380)")
    off = int(off_s, 16)
    seg = seg_s.lower()
    return (seg if seg in _SEG_TOKENS else int(seg_s, 16), off)


def parse_mem(spec: str) -> tuple:
    """``ds:2380`` / ``ds:54:b`` -> ((seg, off), width_in_bytes)."""
    parts = spec.split(":")
    width = 2
    if len(parts) == 3:
        width = 1 if parts[2].lower() == "b" else 2
        spec = ":".join(parts[:2])
    return parse_addr(spec), width


def _seg(cpu, seg) -> int:
    return (getattr(cpu.s, seg) if isinstance(seg, str) else seg) & 0xFFFF


def resolve_linear(cpu, addr: tuple) -> int:
    seg, off = addr
    return ((_seg(cpu, seg) << 4) + (off & 0xFFFF)) & 0xFFFFF


def matches_ip(cpu, target: tuple) -> bool:
    seg, off = target
    return (cpu.s.cs & 0xFFFF) == _seg(cpu, seg) and (cpu.s.ip & 0xFFFF) == (off & 0xFFFF)


def read_mem(cpu, mem_spec: tuple) -> int:
    (seg, off), width = mem_spec
    s = _seg(cpu, seg)
    return cpu.mem.rw(s, off) if width == 2 else cpu.mem.rb(s, off)


def parse_frames(text: str | None) -> tuple | None:
    if not text:
        return None
    a, _, b = text.partition("-")
    return (int(a), int(b)) if b else (int(a), int(a))


# --------------------------------------------------------------------------- #
# shared lockstep driver
# --------------------------------------------------------------------------- #
def run_demo(demo_arg: str, max_frames: int, install, pump_extra=None):
    """Replay ``demo`` through reference+candidate; ``install(rt, side, state)``
    attaches a probe to each runtime.  Returns the divergence lines (if any)."""
    demo_dir = Path(demo_arg)
    if not demo_dir.is_dir():
        demo_dir = ROOT / "artifacts" / "demos" / demo_arg
    if not demo_dir.is_dir():
        raise SystemExit(f"demo not found: {demo_arg}")
    demo = InputDemoPlayback.load(demo_dir)
    snapshot = demo.snapshot_path()
    video = str(demo.manifest.get("metadata", {}).get("video", "tandy"))

    state = {"frame": 0}
    orig_load = fv._load_runtime
    sides = iter(("ref", "cand"))

    def patched_load(exe, assets, snap, tail):
        rt = orig_load(exe, assets, snap, tail)
        side = next(sides)
        rt.cpu._side = side
        install(rt, side, state)
        return rt

    fv._load_runtime = patched_load
    boundary = {"n": 0}

    def pump(ref_rt, cand_rt):
        state["frame"] = boundary["n"]
        if pump_extra is not None:
            pump_extra(ref_rt, cand_rt, boundary["n"])
        demo.apply_to_runtimes(boundary["n"], (ref_rt, cand_rt))
        boundary["n"] += 1

    cfg = FrameVerifyConfig(video=video, source="both", max_frames=max_frames,
                            semantic_state_check=True, stop_on_diff=True, log_every=0)
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            run_frame_verifier(exe=EXE, assets=ASSETS, snapshot=str(snapshot),
                               command_tail=b"", config=cfg, pump_inputs=pump)
    except Exception as exc:  # noqa: BLE001 - surface the harness stop reason
        buf.write(f"\n[harness stop] {exc}\n")
    finally:
        fv._load_runtime = orig_load
    return [ln for ln in buf.getvalue().splitlines()
            if "DIVERGENCE" in ln or "TIMEOUT" in ln or "harness stop" in ln]


def _print_divergence(lines):
    if lines:
        print("\n-- frame verifier --")
        for ln in lines:
            print("  " + ln.strip())


# --------------------------------------------------------------------------- #
# watch
# --------------------------------------------------------------------------- #
def cmd_watch(args):
    addr = parse_addr(args.addr)
    window = parse_frames(args.frames)
    logs = {"ref": [], "cand": []}

    def install(rt, side, state):
        cpu, mem = rt.cpu, rt.program.memory
        lo = resolve_linear(cpu, addr)
        hi = lo + args.range

        def watcher(a, old, new, _c=cpu, _s=side, _lo=lo, _hi=hi):
            if _lo <= a < _hi:
                fr = state["frame"]
                if window and not (window[0] <= fr <= window[1]):
                    return
                logs[_s].append((fr, _c.s.cs & 0xFFFF, _c.s.ip & 0xFFFF,
                                 a - _lo, int.from_bytes(old, "little"),
                                 int.from_bytes(new, "little")))

        mem.write_watchers.append(watcher)

    div = run_demo(args.demo, args.max_frames, install)
    r, c = logs["ref"], logs["cand"]
    print(f"writes to {args.addr}+{args.range}: reference={len(r)} candidate={len(c)}")

    def fmt(e):
        fr, cs, ip, off, old, new = e
        return f"f{fr} {cs:04X}:{ip:04X} [+{off:02X}] {old:04X}->{new:04X}"

    # Compare the *observable* effect -- (offset, written value) -- not the
    # CS:IP, which legitimately differs between raw-ASM (reference) and the
    # lifted hook (candidate) for the same write.  The IP is still shown so you
    # can see who writes; it just doesn't count as a divergence on its own.
    first = None
    for i, (a, b) in enumerate(zip(r, c)):
        if (a[3], a[5]) != (b[3], b[5]):
            first = i
            break
    if first is None and len(r) != len(c):
        first = min(len(r), len(c))
    if first is None:
        print("no write divergence in the matched prefix.")
    else:
        print(f"\nFIRST DIVERGING WRITE at index {first}:")
        for s, lg in (("ref ", r), ("cand", c)):
            lo, hi = max(0, first - 2), first + 3
            for j in range(lo, min(hi, len(lg))):
                mark = "  <<<" if j == first else ""
                print(f"  {s} #{j}: {fmt(lg[j])}{mark}")
    if args.show:
        print("\nall writes (reference | candidate):")
        for i in range(max(len(r), len(c))):
            rs = fmt(r[i]) if i < len(r) else "-"
            cs = fmt(c[i]) if i < len(c) else "-"
            print(f"  #{i}: {rs:38} | {cs}")
    _print_divergence(div)


# --------------------------------------------------------------------------- #
# observe
# --------------------------------------------------------------------------- #
def cmd_observe(args):
    target = parse_addr(args.ip)
    window = parse_frames(args.frames)
    regs = [r.strip().lower() for r in args.reg.split(",")] if args.reg else []
    mems = [parse_mem(m.strip()) for m in args.mem.split(",")] if args.mem else []
    hits = []

    _orig_step = CPU8086.step

    def step(self):
        if matches_ip(self, target):
            fr = getattr(self, "_trace_state", {"frame": 0})["frame"]
            if not window or (window[0] <= fr <= window[1]):
                fields = [f"{r}={getattr(self.s, r) & 0xFFFF:04X}" for r in regs]
                fields += [f"{m[0][0] if isinstance(m[0][0], str) else format(m[0][0],'04X')}:"
                           f"{m[0][1]:04X}={read_mem(self, m):0{m[1]*2}X}" for m in mems]
                fields.append(f"flags={self.s.flags & 0xFFFF:04X}")
                hits.append((fr, getattr(self, "_side", "?"), " ".join(fields)))
        return _orig_step(self)

    CPU8086.step = step

    def install(rt, side, state):
        rt.cpu._trace_state = state

    try:
        div = run_demo(args.demo, args.max_frames, install)
    finally:
        CPU8086.step = _orig_step

    print(f"observe {args.ip}  ({len(hits)} executions)")
    for fr, side, fields in hits:
        print(f"  [{side:4} f{fr}] {fields}")
    _print_divergence(div)


# --------------------------------------------------------------------------- #
# globals
# --------------------------------------------------------------------------- #
def cmd_globals(args):
    window = parse_frames(args.frames)
    specs = [(a, parse_mem(a)) for a in args.addr]

    def install(rt, side, state):
        pass

    first = {"frame": None}

    def pump_extra(ref_rt, cand_rt, n):
        if window and not (window[0] <= n <= window[1]):
            return
        rv = {name: read_mem(ref_rt.cpu, spec) for name, spec in specs}
        cv = {name: read_mem(cand_rt.cpu, spec) for name, spec in specs}
        diffs = [k for k in rv if rv[k] != cv[k]]
        tag = "" if not diffs else "   <<< DIVERGE " + ",".join(diffs)
        if args.show or diffs:
            print(f"f{n}: ref={ {k: hex(v) for k, v in rv.items()} }{tag}")
            if diffs:
                print(f"     cand={ {k: hex(v) for k, v in cv.items()} }")
        if diffs and first["frame"] is None:
            first["frame"] = n

    div = run_demo(args.demo, args.max_frames, install, pump_extra=pump_extra)
    if first["frame"] is None:
        print(f"\nno divergence in {', '.join(args.addr)} over the replayed frames.")
    else:
        print(f"\nfirst divergence at frame {first['frame']}.")
    _print_divergence(div)


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("demo", help="demo directory or name under artifacts/demos/")
    common.add_argument("--frames", help="limit to frame window A-B (or single A)")
    common.add_argument("--max-frames", type=int, default=400)

    w = sub.add_parser("watch", parents=[common], help="watch writes to an address")
    w.add_argument("--addr", required=True, help="SEG:OFF, e.g. ds:2380")
    w.add_argument("--range", type=int, default=2, help="bytes to watch from addr")
    w.add_argument("--show", action="store_true", help="print every write")
    w.set_defaults(func=cmd_watch)

    o = sub.add_parser("observe", parents=[common], help="dump state at a CS:IP")
    o.add_argument("--ip", required=True, help="CS:IP, e.g. cs:9C01")
    o.add_argument("--reg", help="comma list, e.g. ax,bx,si")
    o.add_argument("--mem", help="comma list of SEG:OFF[:b|:w], e.g. ds:2380,ds:54:b")
    o.set_defaults(func=cmd_observe)

    g = sub.add_parser("globals", parents=[common], help="diff globals each frame")
    g.add_argument("--addr", nargs="+", required=True, help="SEG:OFF[:b|:w] list")
    g.add_argument("--show", action="store_true", help="print every frame, not just diffs")
    g.set_defaults(func=cmd_globals)

    args = ap.parse_args()
    args.frames = args.frames  # keep raw; parsed per-command
    args.func(args)


if __name__ == "__main__":
    main()
