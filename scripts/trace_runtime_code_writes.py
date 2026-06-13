#!/usr/bin/env python
"""Trace writes that overlap known runtime-code variant regions.

This is an evidence tool for polyvariant/self-modified code.  It does not try to
interpret the write as a hook.  It records who wrote bytes into addresses that
are already known to be runtime-code frontiers so we can later name the installer
and discover additional variants from cold start.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from overkill_port.games.overkill.runtime_code import (
    RUNTIME_CODE_SLOTS,
    RuntimeCodeWriteTracer,
    describe_live_runtime_code_state,
)
from overkill_port.runtime import create_runtime
from overkill_port.snapshot import load_snapshot


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--exe", default="assets/OVERKILL")
    p.add_argument("--game-root", default="assets")
    p.add_argument("--snapshot", help="Optional snapshot directory to start from")
    p.add_argument("--steps", type=int, default=250_000)
    p.add_argument("--out", type=Path, help="Optional log file")
    p.add_argument("--no-hooks", action="store_true", help="Clear replacement hooks and trace original interpreted execution only")
    p.add_argument("--all-code", action="store_true", help="Watch the whole loaded 1010:0000-FFFF code segment, not only registered runtime-code frontiers")
    p.add_argument("--dump-final-variants", action="store_true", help="After stepping, print the live byte variant/digest for each registered runtime-code slot")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    exe = Path(args.exe)
    game_root = Path(args.game_root)
    if args.snapshot:
        rt = load_snapshot(exe, Path(args.snapshot), game_root=game_root)
    else:
        rt = create_runtime(exe, game_root=game_root)
    rt.cpu.trace_enabled = False
    if args.no_hooks:
        rt.cpu.replacement_hooks.clear()
        rt.cpu.hook_names.clear()
    if args.out:
        args.out.write_text("", encoding="utf-8")
    regions = (((0x1010, 0x0000), 0x10000),) if args.all_code else None
    tracer = RuntimeCodeWriteTracer(rt.cpu, regions=regions, sink=args.out).install()
    error = None
    try:
        for _ in range(args.steps):
            rt.cpu.step()
    except Exception as exc:  # keep the evidence collected before an unrelated stop
        error = exc
    finally:
        tracer.uninstall()
    print(f"runtime-code write events: {len(tracer.events)}")
    for event in tracer.events[-20:]:
        print(event.line())
    if args.dump_final_variants:
        print("final registered runtime-code slots:")
        for addr in sorted(RUNTIME_CODE_SLOTS):
            state = describe_live_runtime_code_state(rt.cpu, addr)
            print(
                f"  {state['addr']} {state['slot']} "
                f"variant={state['variant']} status={state['status']} sha1={state['sha1']}"
            )
    if error is not None:
        print(f"stopped by {type(error).__name__}: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
