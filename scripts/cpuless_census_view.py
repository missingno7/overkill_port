"""VIEW B -- the BINARY-WIDE CPUless census: classify EVERY discovered function.

The observed demo closure (view A, verify_cpuless --demo + cpuless_closure) proves one exercised product
path is fully CPUless.  It does NOT prove the rest of the binary is irrelevant.  This classifies every
function discovered by the static+dynamic closure into the architecture's categories, so the next
capability is chosen by BOTH criteria (observed-closure unblock AND whole-binary unblock + reusability),
and so we have a complete map for the later ABI-recovery / memoryless transition.

"Discovered" = the closed recovery-IR (static call graph from the recovery-fact seeds + every observed
dynamic-dispatch target).  Functions reachable ONLY through not-yet-observed dispatch are still missing;
that residue is itself a reported work item (broaden the demos / capture), never silently "dead".

Categories (per the architecture):
  auto-cpuless          generated CPUless + composable now (the default implementation)
  manual-override       a manual body registered at this address (generated kept for differential)
  platform-replacement  a platform/runtime INT/port effect bound to a native adapter (fail-loud until bound)
  blocked-shape         emitted-nothing yet: an unsupported COMPILER SHAPE (sp-as-data, tail-dispatch, ...)
  blocked-dispatch      blocked by an indirect/unresolved dispatch target
  blocked-cascade       would compose but a (transitive) callee is still unpromoted
  likely-data           decode garbage / SMC / foreign-segment stub -- likely data or a false entry
  boundary-loop         no-exit loop needing a boundary-head fact
  unclassified          none of the above (investigate)

Each function also carries machine-readable metadata (exits, direct/indirect callees, refusal, observed-
reachability) -- the seed of the ABI metadata the memoryless stage consumes.

Usage:
    python scripts/cpuless_census_view.py [--ir IR] [--census C] [--closure CL] [--out JSON]
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "artifacts"

_SHAPE = {"sp-as-data", "tail-dispatch-at-nonzero-depth", "tail-dispatch-with-unbalanced-stack",
          "boundary-head-on-transfer", "mixed-return-kinds", "cs-or-ss-mutation",
          "frame-pointer-clobbered", "unresolved-stack-effect"}
_DISPATCH = {"boundary-or-dispatch-address", "indirect-control-flow", "indirect-or-far-transfer",
             "tail-dispatch-with-unbalanced-stack"}
_PLATFORM = {"vectored-int-call", "contains-interrupt", "port-io"}
_DATA_IR = {"decoder-mismatch", "unsupported-opcode", "region-budget", "code-patched-at-runtime",
            "self-modifying"}


def reachable_from(ir: dict, roots: "list[str]", dyn: dict) -> "set[str]":
    """Static+observed-dispatch reachability from ``roots`` over the recovery-IR call graph:
    follow every near/far call target and every OBSERVED indirect-dispatch target."""
    fns = ir["functions"]
    seen: set = set()
    work = list(roots)
    while work:
        a = work.pop()
        if a in seen or a not in fns:
            continue
        seen.add(a)
        cs = a.split(":")[0]
        f = fns[a]
        for t in f.get("calls_near", ()):
            work.append(f"{cs}:{t}")
        for s, o in f.get("calls_far", ()):
            work.append(f"{s}:{o}")
        for blk in f.get("blocks", ()):
            for i in blk["instructions"]:
                if i.get("kind") in ("call_ind", "jmp_ind"):
                    work.extend(dyn.get(f"{cs}:{i['ip']}", ()))
    return seen


def classify(ir: dict, census: dict, reached: "set[str]", manual: "set[str]") -> dict:
    fns = ir["functions"]
    prom = set(census.get("promotable", [])) if isinstance(census.get("promotable"), list) else set()
    refused = census.get("refused", {})
    reason_of = {a: r for r, items in refused.items() if isinstance(items, list) for a in items}

    out = {}
    for a, f in fns.items():
        cs = a.split(":")[0]
        ir_ref = [r.get("reason") for r in f.get("refusals", [])]
        cat = "unclassified"
        detail = ""
        if a in manual:
            cat = "manual-override"
        elif a in prom:
            cat = "auto-cpuless"
        elif not f.get("liftable"):
            if any(r in _DATA_IR for r in ir_ref):
                cat, detail = "likely-data", ",".join(ir_ref)
            elif "no-exit" in ir_ref:
                cat, detail = "boundary-loop", "no ret; needs a boundary-head fact"
            else:
                cat, detail = "blocked-shape", ",".join(ir_ref)
        else:
            r = reason_of.get(a, "")
            if r in _PLATFORM:
                cat, detail = "platform-replacement", r
            elif r in _SHAPE:
                cat, detail = "blocked-shape", r
            elif r in _DISPATCH:
                cat, detail = "blocked-dispatch", r
            elif r == "contains-call":
                cat, detail = "blocked-cascade", r
            elif r:
                cat, detail = "blocked-shape", r
        out[a] = {
            "class": cat, "detail": detail,
            "observed_reachable": a in reached,
            "exits": f.get("exits", []),
            "callees_near": [f"{cs}:{t}" for t in f.get("calls_near", [])],
            "callees_far": [f"{s}:{o}" for s, o in f.get("calls_far", [])],
            "ints": f.get("ints", []),
            "ir_refusals": ir_ref,
        }
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ir", default=str(ART / "recovery_ir_closed.json"))
    ap.add_argument("--census", default=str(ART / "cpuless_promote_census.json"))
    ap.add_argument("--dyn-evidence", default=str(ART / "indirect_sites.json"))
    ap.add_argument("--roots", default="1010:97B2,1010:0D42,254A:04D7,1010:CC04",
                    help="reachability roots (gameplay frame, shared-asset init, boot, front-end loop)")
    ap.add_argument("--manual", default=str(ART / "cpuless_manual_overrides.txt"),
                    help="one CS:IP per line: addresses with a manual CPUless override")
    ap.add_argument("--out", default=str(ART / "cpuless_census_view.json"))
    args = ap.parse_args(argv)

    ir = json.loads(Path(args.ir).read_text())
    census = json.loads(Path(args.census).read_text())
    dyn = json.loads(Path(args.dyn_evidence).read_text()) if Path(args.dyn_evidence).is_file() else {}
    reached = reachable_from(ir, args.roots.split(","), dyn)
    manual = set()
    mp = Path(args.manual)
    if mp.is_file():
        manual = {ln.strip() for ln in mp.read_text().splitlines() if ln.strip() and not ln.startswith("#")}

    view = classify(ir, census, reached, manual)
    Path(args.out).write_text(json.dumps(view, indent=1))

    by_cat = Counter(v["class"] for v in view.values())
    print("=" * 64)
    print(f"BINARY-WIDE CPUless CENSUS -- {len(view)} discovered functions")
    print("=" * 64)
    order = ["auto-cpuless", "manual-override", "platform-replacement", "blocked-cascade",
             "blocked-shape", "blocked-dispatch", "boundary-loop", "likely-data", "unclassified"]
    for cat in order:
        n = by_cat.get(cat, 0)
        if n:
            print(f"  {cat:22s} {n:4d}")
    # per-shape breakdown of the blocked work items (the capability work-list)
    shapes = Counter(v["detail"] for v in view.values() if v["class"] in ("blocked-shape", "boundary-loop"))
    if shapes:
        print("\n  blocked-shape / boundary work items (the generic-capability queue):")
        for d, n in shapes.most_common():
            print(f"    {d:40s} {n}")
    # observed-reachability split: NOT-reached is NOT dead -- it is unobserved work.
    reached_n = sum(1 for v in view.values() if v["observed_reachable"])
    print(f"\n  reachable from roots: {reached_n}/{len(view)}  "
          f"(the {len(view) - reached_n} unreached are UNOBSERVED, not proven dead)")
    print("  next-capability leverage (blocked fns, whole-binary vs reached-only):")
    for cat in ("blocked-shape", "boundary-loop", "blocked-dispatch"):
        tot = sum(1 for v in view.values() if v["class"] == cat)
        rch = sum(1 for v in view.values() if v["class"] == cat and v["observed_reachable"])
        if tot:
            print(f"    {cat:18s} {tot:3d} total  {rch:3d} reached")
    print(f"\n  wrote per-function metadata -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
