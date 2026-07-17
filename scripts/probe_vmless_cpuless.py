"""Run the DOS_RE 2.0 automatic-recovery pipeline over OVERKILL and print a stage scorecard.

This drives the same generic toolchain the Lemmings pilot used (``dos_re/docs/dos_re_2.0.md``) against
OVERKILL's binary, WITHOUT any hand-lifting: irgen (recovery IR) -> liftemit (VMless corpus, wall
check) -> cpuless_promote (the de-carrier). It reports how much of the reachable graph the pipeline
recovers automatically and enumerates the exact frontier that is NOT yet automatic -- the concrete
work-list for reaching M2 (full VMless) then M3 (CPUless).

It is a MEASUREMENT probe, not part of the shipped runtime: every artifact it writes under
``artifacts/`` is gitignored + regeneratable (Principle 6). Nothing here hand-edits generated output.

Usage:
    python scripts/probe_vmless_cpuless.py [--snapshot DIR] [--entries FILE] [--keep-going]

The snapshot only supplies CODE BYTES (the decoder's authority); any gameplay snapshot with the full
image loaded works. Default: the L1-start demo snapshot.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOS_RE = ROOT / "dos_re"
ART = ROOT / "artifacts"
PY = sys.executable

DEFAULT_SNAPSHOT = ART / "demos" / "demo_play_tandy_L1_start_20260618_143947" / "snapshot"
DEFAULT_ENTRIES = ART / "lift_census_entries.txt"


def _run(argv: "list[str]", label: str) -> str:
    print(f"\n=== {label} ===")
    proc = subprocess.run([PY, *argv], cwd=str(ROOT), capture_output=True, text=True)
    out = (proc.stdout or "") + (proc.stderr or "")
    tail = "\n".join(out.strip().splitlines()[-6:])
    print(tail)
    if proc.returncode != 0:
        print(f"[!] {label} exited {proc.returncode}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT))
    ap.add_argument("--entries", default=str(DEFAULT_ENTRIES))
    ap.add_argument("--keep-going", action="store_true",
                    help="run every stage even if an earlier one reports refusals")
    args = ap.parse_args(argv)

    ir = ART / "recovery_ir.json"
    vmless = ART / "vmless_emit"
    rec = ART / "cpuless_recovered"
    adp = ART / "cpuless_adapters"
    rec.mkdir(parents=True, exist_ok=True)
    adp.mkdir(parents=True, exist_ok=True)

    # Stage 1 -- recovery IR (docs/recovery_ir.md).
    _run([str(DOS_RE / "tools" / "irgen.py"), "--exe", str(ROOT / "assets" / "OVERKILL"),
          "--snapshot", args.snapshot, "--game-root", str(ROOT / "assets"),
          "--entries-file", args.entries, "--out", str(ir)], "irgen -> recovery IR")

    # Stage 2 -- VMless emit + wall check.
    emit = _run([str(DOS_RE / "tools" / "liftemit.py"), "--from-ir", str(ir),
                 "--emit-dir", str(vmless), "--require-vmless-wall"], "liftemit -> VMless corpus")

    # Stage 3 -- CPUless promotion (the de-carrier fixpoint).
    prom = _run([str(DOS_RE / "tools" / "cpuless_promote.py"), "--ir", str(ir),
                 "--recovered-dir", str(rec), "--adapter-dir", str(adp),
                 "--import-base", "overkill.cpuless_recovered",
                 "--census-out", str(ART / "cpuless_promote_census.json"), "--apply"],
                "cpuless_promote -> CPUless graph")

    # ---- scorecard ----
    ir_doc = json.loads(ir.read_text())
    fns = ir_doc["functions"]
    total = len(fns)
    liftable = sum(1 for f in fns.values() if f.get("liftable", True))
    census = json.loads((ART / "cpuless_promote_census.json").read_text())
    refused = census["refused"]
    promotable = census["promotable"]
    promotable = promotable if isinstance(promotable, int) else len(promotable)

    print("\n" + "=" * 64)
    print("DOS_RE 2.0 PIPELINE SCORECARD -- OVERKILL")
    print("=" * 64)
    print(f"  census entries                 {total}")
    print(f"  VMless liftable (M2 corpus)    {liftable}/{total}")
    wall = "HOLDS" if "VMless wall: HOLDS" in emit else "NOT CONFIRMED"
    print(f"  VMless wall (no interp_one)    {wall}")
    print(f"  CPUless promotable (M3)        {promotable}/{total}")
    print("\n  frontier (the automatic-recovery work-list):")
    for reason, items in refused.items():
        n = len(items) if isinstance(items, list) else items
        print(f"    {reason:32s} {n}")
    print("\n  the HARD frontier (real capability/fact gaps, not cascade):")
    hard = list(refused.get("ir-not-liftable", [])) + \
        list(refused.get("tail-dispatch-at-nonzero-depth", []))
    for a in hard:
        print(f"    {a}")
    print("\n  (contains-call refusals are a CASCADE downstream of the hard frontier;")
    print("   the fixpoint sweeps them in as the hard gaps close.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
