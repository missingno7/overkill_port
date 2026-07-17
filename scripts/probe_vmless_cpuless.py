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
DEFAULT_BOUNDARY_HEADS = ART / "lift_boundary_heads.txt"


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
    ap.add_argument("--boundary-heads", default=str(DEFAULT_BOUNDARY_HEADS),
                    help="scheduler-yield head facts (the main-loop frame boundary); empty to disable")
    ap.add_argument("--roots", default="1010:97B2",
                    help="runtime-closure roots (CS:IP,...); default the gameplay frame 1010:97B2")
    ap.add_argument("--keep-going", action="store_true",
                    help="run every stage even if an earlier one reports refusals")
    args = ap.parse_args(argv)

    ir = ART / "recovery_ir_closed.json"    # the STATICALLY-CLOSED graph (stage 0 below)
    vmless = ART / "vmless_emit"
    rec = ART / "cpuless_recovered"
    adp = ART / "cpuless_adapters"
    rec.mkdir(parents=True, exist_ok=True)
    adp.mkdir(parents=True, exist_ok=True)
    # The boundary-head fact is threaded through ALL stages: irgen marks the
    # yield site, liftemit emits the boundary event + ResumePoint, and the
    # promoter carries it into the CPUless ABI analysis.
    heads = args.boundary_heads if args.boundary_heads and Path(args.boundary_heads).is_file() else None
    heads_arg = ["--boundary-heads", f"@{heads}"] if heads else []
    heads_plain = ["--boundary-heads", heads] if heads else []  # promoter takes a bare path

    # Stage 0 -- CLOSE THE CENSUS: the observed-execution entry list misses
    # statically-reachable callees, which is the dominant `contains-call` blocker.
    # close_census.py runs irgen to a fixpoint over the discovered call graph and
    # writes the closed IR that every later stage consumes (docs: dos_re_2.0.md
    # -- "discover the reachable graph, don't depend on observation coverage").
    _run([str(ROOT / "scripts" / "close_census.py"), "--snapshot", args.snapshot,
          "--seed", args.entries, "--out-ir", str(ir),
          *(["--boundary-heads", heads] if heads else [])], "close_census -> closed recovery IR")

    # Stage 2 -- VMless emit + wall check.
    emit = _run([str(DOS_RE / "tools" / "liftemit.py"), "--from-ir", str(ir),
                 *heads_arg, "--emit-dir", str(vmless), "--require-vmless-wall"],
                "liftemit -> VMless corpus")

    # Stage 3 -- CPUless promotion (the de-carrier fixpoint).
    prom = _run([str(DOS_RE / "tools" / "cpuless_promote.py"), "--ir", str(ir),
                 "--recovered-dir", str(rec), "--adapter-dir", str(adp),
                 "--import-base", "overkill.cpuless_recovered", *heads_plain,
                 "--census-out", str(ART / "cpuless_promote_census.json"), "--apply"],
                "cpuless_promote -> CPUless graph")

    # Stage 4 -- RUNTIME CLOSURE from the gameplay root: the real M3 metric
    # (docs/dos_re_2.0.md M3 -- "completion measured by the required RUNTIME
    # CLOSURE from the declared roots, not all named functions promoted").
    closure = _run([str(DOS_RE / "tools" / "cpuless_closure.py"), "--ir", str(ir),
                    "--recovered-dir", str(rec),
                    "--census", str(ART / "cpuless_promote_census.json"),
                    "--roots", args.roots, "--out", str(ART / "cpuless_closure.json")],
                   "cpuless_closure -> gameplay runtime closure")

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
    if "VMless wall: HOLDS" in emit:
        wall = "HOLDS"
    else:
        import re as _re
        m = _re.search(r"(\d+) interp_one fallback call site", emit)
        wall = f"VIOLATED ({m.group(1)} interp_one site(s))" if m else "NOT CONFIRMED"
    print(f"  VMless wall (no interp_one)    {wall}")
    print(f"  CPUless promotable (M3)        {promotable}/{total}  (whole census)")
    try:
        cl = json.loads((ART / "cpuless_closure.json").read_text())
        reached = len(cl.get("reached", []))
        pr = len(cl.get("promoted_reached", []))
        fr = cl.get("frontier", {})
        print(f"  CPUless GAMEPLAY closure       {pr}/{reached} reached from {args.roots} "
              f"({'COMPLETE' if cl.get('closure_complete') else str(len(fr)) + ' frontier'})")
    except Exception:  # noqa: BLE001
        pass
    print("\n  frontier (the automatic-recovery work-list):")
    for reason, items in sorted(refused.items(), key=lambda kv: -(len(kv[1]) if isinstance(kv[1], list) else kv[1])):
        n = len(items) if isinstance(items, list) else items
        print(f"    {reason:36s} {n}")
    print("\n  the HARD frontier (real capability/fact gaps -- everything except the")
    print("  contains-call cascade, which the fixpoint sweeps in as these close):")
    for reason, items in refused.items():
        if reason == "contains-call" or not isinstance(items, list):
            continue
        print(f"    [{reason}] {' '.join(items)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
