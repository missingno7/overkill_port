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
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "artifacts"
sys.path.insert(0, str(ROOT / "dos_re"))

from dos_re.lift.cpuless import register_effects  # noqa: E402
from dos_re.lift.ir import scan_from_ir_record  # noqa: E402

#: registers we report as ABI channels (word file + segments); AL/AH etc. are
#: normalised to the word register by ``register_effects`` already.
_REGS = ("ax", "bx", "cx", "dx", "si", "di", "bp", "sp", "ds", "es", "ss", "cs")
#: moffs opcodes (mov AL/AX <-> [disp]) -- a direct global cell with no ModRM.
_MOFFS = (0xA0, 0xA1, 0xA2, 0xA3)


def _direct_cell(inst) -> "tuple[str, int] | None":
    """The (segment, offset) of a DIRECT global-memory operand, or None.

    A ``mod==0, rm==6`` ModRM or a moffs opcode names a compile-time-fixed cell
    -- the global-state dependency the memoryless stage must bind.  Base/index
    forms ([bx+si], [bp+k], ...) are computed and excluded here (they are the
    array/struct accesses, not fixed globals)."""
    seg = getattr(inst, "seg_override", None)
    if inst.op in _MOFFS and inst.imm is not None:   # mov AL/AX <-> [addr]: addr is the immediate
        return (seg or "ds", inst.imm & 0xFFFF)
    if inst.mod == 0 and inst.rm == 6 and inst.disp is not None:
        return (seg or "ds", inst.disp & 0xFFFF)
    return None


def abi_metadata(scan, dyn: dict, cs: str) -> dict:
    """Aggregate per-function ABI/side-effect metadata from ``register_effects``.

    This is the machine-readable seed the memoryless (DOS-layout-less) stage
    consumes: which register channels the function may read/write, whether it
    touches memory/ports, which fixed global cells it depends on, its interrupt
    side effects, and its indirect-dispatch callees (from observed evidence).
    ``reads``/``writes`` are MAY sets (union over all paths), not strict
    live-in -- the promoter computes the strict contract for auto-cpuless fns;
    this covers every discovered function uniformly, promotable or not."""
    reads: set = set()
    writes: set = set()
    g_read: set = set()
    g_write: set = set()
    mem_r = mem_w = port = uses_frame = False
    ind_targets: set = set()
    for ip, inst in scan.insts.items():
        e = register_effects(inst)
        reads |= {r for r in e.reads if r in _REGS}
        writes |= {w for w in e.writes if w in _REGS}
        mem_r = mem_r or e.mem_read
        mem_w = mem_w or e.mem_write
        port = port or e.port_io
        uses_frame = uses_frame or e.frame_establish
        cell = _direct_cell(inst)
        if cell is not None:
            (g_write if e.mem_write else g_read).add(cell)
        ind_targets |= set(dyn.get(f"{cs}:{ip:04X}", ()))
    fmt = lambda cells: sorted(f"{s}:{o:04X}" for s, o in cells)  # noqa: E731
    return {
        "regs_read": sorted(reads),
        "regs_written": sorted(writes),
        "reads_mem": mem_r,
        "writes_mem": mem_w,
        "port_io": port,
        "uses_bp_frame": uses_frame,
        "global_reads": fmt(g_read),
        "global_writes": fmt(g_write),
        "callees_indirect": sorted(ind_targets),
    }

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


def classify(ir: dict, census: dict, reached: "set[str]", manual: "set[str]", dyn: dict) -> dict:
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
        rec = {
            "class": cat, "detail": detail,
            "observed_reachable": a in reached,
            "exits": f.get("exits", []),
            "callees_near": [f"{cs}:{t}" for t in f.get("calls_near", [])],
            "callees_far": [f"{s}:{o}" for s, o in f.get("calls_far", [])],
            "ints": f.get("ints", []),
            "ir_refusals": ir_ref,
        }
        try:
            rec["abi"] = abi_metadata(scan_from_ir_record(f), dyn, cs)
        except Exception as exc:  # a decode-garbage record -- record the gap, don't crash the census
            rec["abi"] = {"error": f"{type(exc).__name__}: {exc}"}
        out[a] = rec
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

    view = classify(ir, census, reached, manual, dyn)
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
    # ABI-metadata coverage (the memoryless-bridge seed): how many carry a clean record.
    abi_ok = sum(1 for v in view.values() if "error" not in v.get("abi", {"error": 1}))
    g_dep = sum(1 for v in view.values()
                if v.get("abi", {}).get("global_reads") or v.get("abi", {}).get("global_writes"))
    print(f"\n  ABI metadata: {abi_ok}/{len(view)} functions carry a clean per-fn record "
          f"(regs r/w, mem, ports, global cells, indirect callees); {g_dep} touch fixed global cells")
    print(f"  wrote per-function metadata -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
