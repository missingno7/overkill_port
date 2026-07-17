"""Transitively complete the lift census by STATIC call-target discovery.

The observed-execution census (`lift_census_entries.txt`, from dos_re's codemap) only lists functions
some recording actually executed -- so statically-reachable callees on unobserved paths are missing,
and every caller of a missing function refuses `contains-call` in the CPUless promoter. That is the
dominant CPUless blocker on OVERKILL (measured: 96 first-order missing targets gate ~110 of the 114
cascade).

This closes it the 2.0 way -- discover the reachable graph, don't depend on observation coverage:
seed from the observed entries, run irgen, add every near/far call TARGET the IR records as a new
entry, and repeat until the entry set stops growing. Indirect-dispatch targets are NOT invented here
(they need dyn-evidence, per dos_re); this closes the STATIC call graph, which is what `contains-call`
is about. Unreachable/garbage targets simply refuse in irgen (fail-loud) and are pruned by re-seeding
only from targets that themselves decoded.

Output: a completed entries file (default `artifacts/lift_census_entries_closed.txt`) + the final IR.
Idempotent and regeneratable; nothing here is hand-authored game logic.

Usage:
    python scripts/close_census.py [--snapshot DIR] [--seed FILE] [--out-entries FILE] [--out-ir FILE]
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


def _targets(ir: dict, dyn: "dict | None" = None) -> "set[str]":
    present = set(ir["functions"])
    out: set[str] = set(present)
    for a, f in ir["functions"].items():
        cs = a.split(":")[0]
        for t in f.get("calls_near", ()):
            out.add(f"{cs}:{t}")
        for s, o in f.get("calls_far", ()):
            out.add(f"{s}:{o}")
    # DYNAMIC-DISPATCH targets (jmp/call cs:[table]) are unreachable by the
    # static call graph -- but the demo OBSERVES every one they take
    # (capture_indirect_sites.py). Following them closes the graph over the
    # video-mode dispatchers + their mode-specific render/handler targets
    # (e.g. 5A00 -> 3103); without this the standalone hits UnknownDispatchTarget.
    if dyn:
        for _site, tgts in dyn.items():
            out.update(tgts)
    return out


def _run_irgen(snapshot: str, entries: Path, heads: "str | None",
               keep: "str | None", out_ir: Path) -> dict:
    argv = [PY, str(DOS_RE / "tools" / "irgen.py"),
            "--exe", str(ROOT / "assets" / "OVERKILL"), "--snapshot", snapshot,
            "--game-root", str(ROOT / "assets"), "--entries-file", str(entries),
            "--out", str(out_ir)]
    if heads:
        argv += ["--boundary-heads", f"@{heads}"]
    if keep:
        argv += ["--keep-interpreted", f"@{keep}"]
    proc = subprocess.run(argv, cwd=str(ROOT), capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout + proc.stderr)
        raise SystemExit(f"irgen failed (exit {proc.returncode})")
    return json.loads(out_ir.read_text())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--snapshot",
                    default=str(ART / "demos" / "demo_play_tandy_L1_start_20260618_143947" / "snapshot"))
    ap.add_argument("--seed", default=str(ART / "lift_census_entries.txt"))
    ap.add_argument("--boundary-heads", default=str(ART / "lift_boundary_heads.txt"))
    ap.add_argument("--keep-interpreted", default=str(ART / "lift_keep_interpreted.txt"))
    ap.add_argument("--out-entries", default=str(ART / "lift_census_entries_closed.txt"))
    ap.add_argument("--out-ir", default=str(ART / "recovery_ir_closed.json"))
    ap.add_argument("--dyn-evidence", default=str(ART / "indirect_sites.json"),
                    help="captured indirect-dispatch targets to also close over (capture_indirect_sites.py)")
    ap.add_argument("--max-rounds", type=int, default=12)
    args = ap.parse_args(argv)

    heads = args.boundary_heads if Path(args.boundary_heads).is_file() else None
    keep = args.keep_interpreted if Path(args.keep_interpreted).is_file() else None
    dyn = json.loads(Path(args.dyn_evidence).read_text()) if Path(args.dyn_evidence).is_file() else None
    entries = {ln.strip() for ln in Path(args.seed).read_text().splitlines()
               if ln.strip() and not ln.startswith("#")}
    out_entries = Path(args.out_entries)

    for rnd in range(1, args.max_rounds + 1):
        out_entries.write_text("".join(f"{e}\n" for e in sorted(entries)))
        ir = _run_irgen(args.snapshot, out_entries, heads, keep, Path(args.out_ir))
        discovered = _targets(ir, dyn)
        new = discovered - entries
        liftable = sum(1 for f in ir["functions"].values() if f.get("liftable", True))
        print(f"round {rnd}: entries={len(entries)} liftable={liftable}/{len(ir['functions'])} "
              f"new_targets={len(new)}")
        if not new:
            print(f"CLOSED: {len(entries)} entries (fixpoint). IR -> {args.out_ir}")
            return 0
        entries |= new
    print(f"[!] did not reach fixpoint in {args.max_rounds} rounds ({len(entries)} entries)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
