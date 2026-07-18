"""Record WHICH code actually executes, by replaying a demo through the pure-VM oracle.

`cpuless_promote --observed` consumes this to make two evidence-driven decisions:

* a near CALL to a target that is not an IR function AND never executed is a RUNTIME-DEAD call,
  emitted as a fail-loud stub rather than blocking promotion;
* a `ret`/`retf`/`iret` that never executed is a DEAD EXIT, so it does not constrain the exit ABI --
  which is what lets a function whose only LIVE exit is a platform effect promote despite dead
  in-corpus returns.

Both are the honest kind of evidence: they do not assume the dead path is impossible, they record
that this demo never took it, and the emitted code FAILS LOUD if it ever is taken. That is the
opposite of a fallback.

MEASURED: `--observed` REGRESSES this port's promotion, and NOT because of coverage
-----------------------------------------------------------------------------------
    no --observed                      591 promotable, contains-call 20
    --observed, 1 demo  (36% covered)  571 promotable, contains-call 40
    --observed, 3 demos (59% covered)  571 promotable, contains-call 40   <- byte-identical

Doubling address coverage changed NOTHING -- the two censuses are identical. So the first
explanation ("one demo is not enough, union will fix it") was WRONG, and is recorded here as the
falsified hypothesis it was.

The real mechanism is that dead-exit marking is SUBTRACTIVE. 168 functions have EVERY `ret`
unexecuted across the union; each loses its exit ABI. For a function whose only live exit is a
platform effect that is the intended win -- but where it removes ABI a caller needed, the caller
refuses `contains-call` and the loss cascades. Net: 20 promotable functions lost, 0 gained, every
one of them refused transitively (`contains-call`), including `D007` (the attract machine) and
`CBE8` (the front end) whose OWN entries and returns both demonstrably executed.

More demos of the same kind cannot fix this: the `1F8F` sound-driver segment shows only 18 executed
addresses across all three recordings, so its functions stay all-exits-dead no matter how much
gameplay is recorded. `--observed` therefore stays OUT of the pipeline until the subtractive case is
handled (a dead exit should not be able to strip an ABI a live caller depends on).

WHY A TRAP SET, NOT A FULL TRACE
--------------------------------
`--observed`'s schema is per-address, but it only ever asks about two address classes: function
entries and return sites. Calling back on every instruction of a spine demo means tens of millions
of Python calls; trapping just those addresses is the same information for a tiny fraction of the
cost (the harness makes the check itself -- see `run_ref_step_probe`'s `trap`).

Usage:
    python scripts/capture_observed_trace.py --demo demo_play_tandy_20260718_134524 \
        --out artifacts/observed.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))

DEFAULT_IR = ROOT / "artifacts" / "recovery_ir_closed.json"
#: the spine: cold start -> intro -> menu -> level select -> gameplay
DEFAULT_DEMO = "demo_play_tandy_20260718_134524"


def trap_addresses(ir: dict) -> "tuple[frozenset, dict]":
    """The (cs, ip) pairs `--observed` can act on: every function ENTRY and every RETURN site."""
    entries, rets = set(), set()
    for key, rec in ir["functions"].items():
        cs = int(key.split(":")[0], 16)
        entries.add((cs, int(key.split(":")[1], 16)))
        for blk in rec["blocks"]:
            for i in blk["instructions"]:
                if i.get("kind") in ("ret", "retf", "iret"):
                    rets.add((cs, int(i["ip"], 16)))
    return frozenset(entries | rets), {"entries": len(entries), "rets": len(rets)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--demo", action="append", default=None,
                    help="repeatable -- evidence is UNIONED across demos. NOTE the measured result "
                         "below: more coverage did NOT help. --observed regresses promotion "
                         "(591 -> 571, contains-call 20 -> 40) IDENTICALLY at 36%% and at 59%% "
                         "address coverage, because dead-exit marking is SUBTRACTIVE, not a "
                         "coverage shortfall. See the module docstring.")
    ap.add_argument("--ir", default=str(DEFAULT_IR))
    ap.add_argument("--out", default=str(ROOT / "artifacts" / "observed.json"))
    ap.add_argument("--max-frames", type=int, default=None)
    args = ap.parse_args(argv)

    ir_path = Path(args.ir)
    if not ir_path.is_file():
        print(f"no IR at {ir_path} -- run scripts/probe_vmless_cpuless.py first")
        return 2
    ir = json.loads(ir_path.read_text(encoding="utf-8"))
    trap, counts = trap_addresses(ir)

    from overkill.probes._harness import load_demo, run_ref_step_probe, run_ref_step_probe_cold_start

    names = args.demo or [DEFAULT_DEMO]
    seen: set = set()

    def on_ref_step(cpu):
        seen.add((cpu.s.cs & 0xFFFF, cpu.s.ip & 0xFFFF))

    print(f"trapping {len(trap)} addresses "
          f"({counts['entries']} entries + {counts['rets']} returns) over {len(names)} demo(s)")
    for name in names:
        demo = load_demo(name, DEFAULT_DEMO)
        before = len(seen)
        frames = args.max_frames if args.max_frames is not None else demo.end_boundary + 5
        if demo.is_cold_start:
            run_ref_step_probe_cold_start(demo, args.max_frames, on_ref_step, trap=trap)
        else:
            run_ref_step_probe(demo, frames, on_ref_step, trap=trap)
        print(f"  {name}: +{len(seen) - before} new (total {len(seen)}/{len(trap)})")

    executed = sorted(f"{cs:04X}:{ip:04X}" for cs, ip in seen)
    out = Path(args.out)
    out.write_text(json.dumps({
        "_notice": "generated by scripts/capture_observed_trace.py -- which addresses this demo "
                   "actually executed. Consumed by cpuless_promote --observed. NOT a claim that "
                   "unlisted addresses are unreachable; only that this demo never reached them, "
                   "and the emitted code fails loud if one ever is.",
        "demos": names,
        "trapped": len(trap),
        "executed": executed,
    }, indent=1), encoding="utf-8")

    print(f"executed {len(executed)}/{len(trap)} trapped addresses "
          f"({100.0 * len(executed) / max(1, len(trap)):.0f}%)")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
