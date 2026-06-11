"""Profile OVERKILL execution and report where runtime is spent.

This is a lightweight, dependency-free profiler aimed at the asset-heavy loading
path.  It answers three questions the optimisation work keeps asking:

  1. Which CS:IP routines dominate execution?
  2. How much time goes to interpreted ASM vs replacement hooks vs the
     frame/present hooks (graphics)?
  3. Which replacement hooks are worth keeping or extending?

It works by wrapping every registered hook with a timing/counting shim and by
sampling the current CS:IP each step.  All counters are local to this script, so
the interpreter core stays clean and pays nothing when not profiling.

Usage:
    python scripts/profile_hotspots.py [steps] [--video cga|ega|tandy]
                                       [--stop-at CS:IP] [--top N]

Examples:
    python scripts/profile_hotspots.py 3000000
    python scripts/profile_hotspots.py 2000000 --video tandy --top 30
"""
from __future__ import annotations

import argparse
import time
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from overkill_port.runtime import create_runtime  # noqa: E402

# Present/frame-boundary hooks: time spent here is "graphics/present", not the
# interpreter or asset-decode work we are trying to speed up.
PRESENT_HOOKS = {
    (0x1010, 0x447B): "cga_present",
    (0x1010, 0x2750): "ega_present",
    (0x1010, 0x3354): "tandy_present",
    (0x1010, 0x50C9): "vga_retrace_wait",
    (0x1010, 0x0679): "timer_wait",
}

VIDEO_TAIL = {
    "cga": b"",
    "ega": bytes((0x0D, 0x01)),
    "tandy": bytes((0x0D, 0x02)),
}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("steps", nargs="?", type=int, default=3_000_000,
                   help="max interpreted steps to profile (default 3,000,000)")
    p.add_argument("--video", choices=("cga", "ega", "tandy"), default="cga")
    p.add_argument("--stop-at", default=None, help="stop early at CS:IP, e.g. 1010:475A")
    p.add_argument("--top", type=int, default=25, help="how many rows to print")
    args = p.parse_args(argv)

    stop_at = None
    if args.stop_at:
        cs, ip = args.stop_at.split(":")
        stop_at = (int(cs, 16) & 0xFFFF, int(ip, 16) & 0xFFFF)

    rt = create_runtime(
        ROOT / "assets" / "OVERKILL.UNLZEXE.EXE",
        game_root=ROOT / "assets",
        command_tail=VIDEO_TAIL[args.video],
    )
    cpu = rt.cpu
    cpu.trace_enabled = False

    # Wrap every registered hook with a counting/timing shim.
    hook_calls: Counter[tuple[int, int]] = Counter()
    hook_time: dict[tuple[int, int], float] = {}
    perf = time.perf_counter

    def wrap(addr, fn):
        def shim(c):
            t0 = perf()
            fn(c)
            hook_time[addr] = hook_time.get(addr, 0.0) + (perf() - t0)
            hook_calls[addr] += 1
        return shim

    for addr, fn in list(cpu.replacement_hooks.items()):
        cpu.replacement_hooks[addr] = wrap(addr, fn)

    addr_counts: Counter[tuple[int, int]] = Counter()
    hook_predecessors: dict[tuple[int, int], Counter[tuple[int, int]]] = {}
    hook_stack_words: dict[tuple[int, int], Counter[int]] = {}
    backward_edges: Counter[tuple[tuple[int, int], tuple[int, int]]] = Counter()
    step = cpu.step
    cur = cpu.addr
    hook_set = set(cpu.replacement_hooks)
    previous_addr: tuple[int, int] | None = None

    t_start = perf()
    executed = 0
    try:
        for _ in range(args.steps):
            a = cur()
            addr_counts[a] += 1
            if a in hook_set:
                if previous_addr is not None:
                    hook_predecessors.setdefault(a, Counter())[previous_addr] += 1
                if cpu.s.sp <= 0xFFFE:
                    hook_stack_words.setdefault(a, Counter())[cpu.mem.rw(cpu.s.ss, cpu.s.sp)] += 1
            if stop_at is not None and a == stop_at:
                break
            step()
            b = cur()
            if b[0] == a[0] and b[1] <= a[1]:
                backward_edges[(a, b)] += 1
            previous_addr = a
            executed += 1
    except Exception as exc:  # keep partial results useful during bring-up
        cs, ip = cpu.addr()
        print(f"\n[stopped on exception @ {cs:04X}:{ip:04X}] {type(exc).__name__}: {exc}\n")
    wall = perf() - t_start
    if wall <= 0:
        wall = 1e-9

    total_hook_time = sum(hook_time.values())
    total_hook_calls = sum(hook_calls.values())
    present_time = sum(t for a, t in hook_time.items() if a in PRESENT_HOOKS)
    decode_hook_time = total_hook_time - present_time
    interp_time = max(0.0, wall - total_hook_time)

    print("=" * 64)
    print(f"OVERKILL profile  video={args.video}  steps={executed:,}")
    print(f"wall={wall:.2f}s   {executed / wall:,.0f} interpreted-steps/sec")
    cs, ip = cpu.addr()
    print(f"final CS:IP = {cs:04X}:{ip:04X}")
    print("-" * 64)
    print("Time breakdown (wall-clock):")
    print(f"  interpreter (interpreted ASM) : {interp_time:7.2f}s  {100*interp_time/wall:5.1f}%")
    print(f"  replacement hooks (decode/io) : {decode_hook_time:7.2f}s  {100*decode_hook_time/wall:5.1f}%")
    print(f"  present/frame/graphics hooks  : {present_time:7.2f}s  {100*present_time/wall:5.1f}%")
    print(f"  hook invocations total        : {total_hook_calls:,}")
    print("-" * 64)

    print(f"Top {args.top} executed CS:IP (interpreted-instruction frequency):")
    for (hcs, hip), count in addr_counts.most_common(args.top):
        name = cpu.hook_names.get((hcs, hip), "")
        tag = f"  <hook {name}>" if (hcs, hip) in hook_set else ""
        print(f"  {hcs:04X}:{hip:04X}  {count:9,}{tag}")
    print("-" * 64)

    print("Replacement hooks by cumulative time:")
    ranked = sorted(hook_time.items(), key=lambda kv: kv[1], reverse=True)
    for addr, t in ranked[: args.top]:
        name = cpu.hook_names.get(addr, "")
        calls = hook_calls[addr]
        per = (t / calls * 1e6) if calls else 0.0
        kind = "present" if addr in PRESENT_HOOKS else "decode "
        print(f"  {addr[0]:04X}:{addr[1]:04X} {kind} {t:7.3f}s  calls={calls:>8,}  {per:8.1f}us/call  {name}")
    print("-" * 64)

    print("Top interpreted backward edges / tight loops:")
    for (src, dst), count in backward_edges.most_common(args.top):
        print(f"  {src[0]:04X}:{src[1]:04X} -> {dst[0]:04X}:{dst[1]:04X}  {count:9,}")
    print("-" * 64)

    print("Top hook boundary crossings by predecessor address:")
    crossing_rows = []
    for hook_addr, preds in hook_predecessors.items():
        for pred, count in preds.items():
            crossing_rows.append((count, pred, hook_addr))
    for count, pred, hook_addr in sorted(crossing_rows, reverse=True)[: args.top]:
        name = cpu.hook_names.get(hook_addr, "")
        print(f"  {pred[0]:04X}:{pred[1]:04X} -> {hook_addr[0]:04X}:{hook_addr[1]:04X}  {count:9,}  {name}")
    print("-" * 64)

    print("Top hook stack return words / likely call sites:")
    hook_call_rows = []
    for hook_addr, words in hook_stack_words.items():
        for word, count in words.items():
            hook_call_rows.append((count, hook_addr, word))
    for count, hook_addr, word in sorted(hook_call_rows, reverse=True)[: args.top]:
        name = cpu.hook_names.get(hook_addr, "")
        print(f"  {hook_addr[0]:04X}:{hook_addr[1]:04X}  stack={word:04X}  {count:9,}  {name}")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
