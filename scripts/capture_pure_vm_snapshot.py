#!/usr/bin/env python
"""Capture a PURE-VM (hooks-stripped) snapshot at a frame boundary where a target behaviour is LIVE.

The lifter-assisted actor recovery (docs/overkill/actor_model.md §7) needs a snapshot from which
``liftverify`` can forward-run INTO an enemy behaviour handler.  ``scripts/capture_demo_snapshot.py``
cannot serve that: it replays through the HOOKED runtime, so a behaviour that already has a native
replacement hook (or is far-called from one) is intercepted and its interpreted ASM never executes --
liftverify then reports ``NOT_REACHED``.

This tool replays a demo through the frame verifier's PURE reference VM (the same one the walk shadow
trusts), and the first time it reaches a 1010:9B2E frame boundary (at/after ``--min-boundary``) with an
ACTIVE object record whose behaviour id (``+0x18``) is in ``--behavior``, it writes a standard
``memory_1mb.bin`` + minimal ``state.json`` snapshot.  Feed that to liftverify:

    python scripts/capture_pure_vm_snapshot.py --demo artifacts/demos/demo_play_tandy_L4_full_... \
        --behavior 0x7D --behavior 0x7E --min-boundary 100 --out artifacts/tmp_snap_wp
    python dos_re/tools/liftverify.py --exe assets/OVERKILL --snapshot artifacts/tmp_snap_wp \
        --entry 1010:8D4F --entry 1F8F:027A --emit-dir lifted

Validated 2026-07-10: the 8D4F / 1F8F:027A waypoint family lifted 2 ORACLE_PASSING, 0 DIVERGED from a
snapshot this tool produced (record 23EC live at L4 boundary 120).  To exercise a deeper branch (e.g. a
waypoint ARRIVAL), raise ``--min-boundary`` so the captured actor is nearer that state, or pass
``--stop-at`` to capture the first boundary at/after a specific record reaching a chosen state.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))

from overkill.probes._harness import load_demo, run_ref_step_probe  # noqa: E402

CS = 0x1010
DS = 0x25CC
FRAME_TOP = 0x9B2E
STRIDE = 0x38
POOLS = ((0x23B4, 0x23), (0x2B5C, 0x22))   # effect pool, gameplay pool
OFF_ACTIVE, OFF_BEHAVIOR = 0x00, 0x18


def _live_record(mem, behaviors: set[int]) -> int | None:
    for base, count in POOLS:
        for i in range(count):
            rec = (base + i * STRIDE) & 0xFFFF
            if mem.rw(DS, rec) != 0 and mem.rw(DS, (rec + OFF_BEHAVIOR) & 0xFFFF) in behaviors:
                return rec
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--demo", required=True, help="demo dir name or path under artifacts/demos")
    ap.add_argument("--behavior", action="append", required=True,
                    help="target behaviour id(s) (record +0x18), e.g. --behavior 0x7D (repeatable)")
    ap.add_argument("--min-boundary", type=int, default=100)
    ap.add_argument("--max-boundary", type=int, default=4000)
    ap.add_argument("--out", required=True, help="snapshot output directory")
    args = ap.parse_args(argv)

    behaviors = {int(b, 0) for b in args.behavior}
    demo = load_demo(args.demo if "/" not in args.demo and "\\" not in args.demo else None, args.demo)
    out = Path(args.out)
    st = {"n": 0, "done": False}

    def on_step(cpu):
        if st["done"]:
            return
        s = cpu.s
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) != (CS, FRAME_TOP):
            return
        st["n"] += 1
        if st["n"] < args.min_boundary:
            return
        if st["n"] > args.max_boundary:
            raise StopIteration
        rec = _live_record(cpu.mem, behaviors)
        if rec is None:
            return
        out.mkdir(parents=True, exist_ok=True)
        (out / "memory_1mb.bin").write_bytes(bytes(cpu.mem.data))
        beh = cpu.mem.rw(DS, (rec + OFF_BEHAVIOR) & 0xFFFF)
        (out / "state.json").write_text(json.dumps({
            "status": f"pure-VM {demo_name(demo)} boundary {st['n']}, behaviour {beh:#04x} live @ {rec:04X}",
            "steps": 0,
            "cpu": dataclasses.asdict(s),
        }, indent=2), encoding="utf-8")
        print(f"snapshot written: boundary {st['n']}, behaviour {beh:#04x} live at record {rec:04X} -> {out}")
        st["done"] = True
        raise StopIteration

    try:
        run_ref_step_probe(demo, args.max_boundary + 5, on_step, trap=frozenset({(CS, FRAME_TOP)}))
    except StopIteration:
        pass
    if not st["done"]:
        print(f"FAIL: no active record with behaviour in {sorted(behaviors)} at a boundary "
              f"[{args.min_boundary}, {args.max_boundary}]")
        return 1
    return 0


def demo_name(demo):
    try:
        return Path(demo.snapshot_path()).parents[0].name
    except Exception:  # noqa: BLE001
        return "demo"


if __name__ == "__main__":
    raise SystemExit(main())
