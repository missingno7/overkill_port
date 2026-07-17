"""Converge the DISPATCH graph: iterate capture <-> close to a fixpoint.

`close_census.py` closes the STATIC call graph and folds in whatever dynamic-dispatch targets the current
`indirect_sites.json` holds -- but each close ADDS functions, and those new functions have their OWN
indirect sites that the previous capture never trapped (it only traps sites in the IR it was given).  So
a single capture+close leaves the last generation of dispatch targets missing -- the demo-driven
differential surfaces them one at a time as `UnknownDispatchTarget`.

This alternates the two to a fixpoint: capture (over the current IR) -> close (fold the new targets in)
-> repeat until the closed entry set stops growing.  The result is a dispatch graph with no missing
targets on the exercised demos.  Output: the converged `indirect_sites.json` + `recovery_ir_closed.json`.

Usage:
    python scripts/close_dispatch_fixpoint.py [--demos d1,d2] [--max-rounds N]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "artifacts"
PY = sys.executable


def _run(argv, label):
    print(f"  [{label}] ...", flush=True)
    p = subprocess.run([PY, *argv], cwd=str(ROOT), capture_output=True, text=True)
    if p.returncode != 0:
        sys.stderr.write(p.stdout + p.stderr)
        raise SystemExit(f"{label} failed ({p.returncode})")
    return p.stdout


def _entries() -> int:
    ir = ART / "recovery_ir_closed.json"
    return len(json.loads(ir.read_text())["functions"]) if ir.is_file() else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--demos", default="demo_play_tandy_L1_start_20260618_143947,"
                                        "demo_cold_start_intro_20260711_203259")
    ap.add_argument("--max-rounds", type=int, default=6)
    args = ap.parse_args(argv)

    prev = -1
    for rnd in range(1, args.max_rounds + 1):
        print(f"== dispatch-fixpoint round {rnd} ==", flush=True)
        _run([str(ROOT / "scripts" / "capture_indirect_sites.py"),
              "--demos", args.demos, "--out", str(ART / "indirect_sites.json")], "capture")
        _run([str(ROOT / "scripts" / "close_census.py")], "close")
        n = _entries()
        print(f"   entries = {n}", flush=True)
        if n == prev:
            print(f"CONVERGED at {n} entries (round {rnd}).")
            return 0
        prev = n
    print(f"[!] not converged in {args.max_rounds} rounds ({prev} entries)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
