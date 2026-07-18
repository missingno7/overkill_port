"""VERIFICATION COVERAGE: how much of the promoted corpus has actually been PROVEN, not just emitted.

The pipeline scorecard reports "CPUless promotable 591/626, walls HOLD". That is easy to read as "591
functions verified" -- and it is not. Promotion is a STRUCTURAL property (the function emits as a pure
`(mem, plat, *regs)` module touching no carrier). Whether it COMPUTES what the CPU does is a separate,
per-function question answered only by a differential, and a demo-driven differential can only reach the
functions that demo actually executes.

That gap is not academic: it is how "the menu functions are promoted" got reported as though they were
verified, when no demo reaches them at all. This report makes the distinction explicit and countable:

    promoted            -- structurally CPUless (from the promotion census)
    verified PASS       -- byte-exact against the interpreter at real states (from --ledger runs)
    DIVERGED            -- proven wrong (must be zero)
    INCONCLUSIVE        -- reached but not decidable (e.g. an interpreter spin that never returns)
    NEVER EXERCISED     -- promoted, but no demo has ever run it: the honest unproven surface

Usage:
    python scripts/verify_cpuless.py --demo D --ledger artifacts/verify_ledger_D.json   # produce
    python scripts/cpuless_verification_coverage.py                                      # report
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "artifacts"


def load_ledgers(paths) -> "tuple[dict, list[str]]":
    """Union per-function verdicts across ledgers. A function PASSES if any demo proved it; a DIVERGED
    anywhere sticks (a single proven-wrong result is not cancelled by a pass elsewhere)."""
    merged: dict[str, str] = {}
    demos: list[str] = []
    rank = {"DIVERGED": 3, "PASS": 2, "INCONCLUSIVE": 1, "SKIP": 0}
    for p in paths:
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        demos.append(d.get("demo", Path(p).stem))
        for key, verdict in d.get("verdicts", {}).items():
            cur = merged.get(key)
            if cur is None or rank.get(verdict, 0) > rank.get(cur, 0):
                merged[key] = verdict
    return merged, demos


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--census", default=str(ART / "cpuless_promote_census.json"))
    ap.add_argument("--ledgers", default=str(ART), help="dir (or comma-list) of verify ledgers")
    args = ap.parse_args(argv)

    census_path = Path(args.census)
    if not census_path.is_file():
        print(f"no census at {census_path} -- run scripts/probe_vmless_cpuless.py first")
        return 2
    promoted = {a.upper() for a in json.loads(census_path.read_text(encoding="utf-8"))
                .get("promotable", [])}

    src = Path(args.ledgers)
    paths = (sorted(src.glob("verify_ledger_*.json")) if src.is_dir()
             else [Path(p) for p in args.ledgers.split(",") if p])
    verdicts, demos = load_ledgers(paths) if paths else ({}, [])

    by = {"PASS": set(), "DIVERGED": set(), "INCONCLUSIVE": set(), "SKIP": set()}
    for key, v in verdicts.items():
        by.setdefault(v, set()).add(key.upper())
    never = promoted - set(verdicts.keys()) - {k.upper() for k in verdicts}

    print("=" * 72)
    print("CPULESS VERIFICATION COVERAGE -- promoted (structural) vs PROVEN (differential)")
    print("=" * 72)
    print(f"  ledgers            {len(paths)}  {demos}")
    print(f"  promoted           {len(promoted)}")
    print(f"  verified PASS      {len(by['PASS'] & promoted)}")
    print(f"  DIVERGED           {len(by['DIVERGED'])}   <-- must be 0")
    print(f"  INCONCLUSIVE       {len(by['INCONCLUSIVE'])}")
    print(f"  NEVER EXERCISED    {len(never)}   <-- promoted but no demo ever ran it")
    if promoted:
        pct = 100.0 * len(by["PASS"] & promoted) / len(promoted)
        print(f"\n  proven fraction    {pct:.1f}% of the promoted corpus")
    if by["DIVERGED"]:
        print("\n  DIVERGED:", " ".join(sorted(by["DIVERGED"])))
    if not paths:
        print("\n  (no ledgers found -- run verify_cpuless.py --demo ... --ledger ... to populate)")
    print("\n  NOTE: 'NEVER EXERCISED' is the honest unproven surface. It is NOT a failure -- it is the"
          "\n  measure of how far demo coverage is from the corpus, and the number to quote instead of"
          "\n  the promotion count when claiming correctness.")
    return 1 if by["DIVERGED"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
