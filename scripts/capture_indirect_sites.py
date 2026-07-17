"""Capture per-site DYNAMIC-DISPATCH evidence (indirect_sites.json) for the CPUless promoter.

The near indirect jmp/call sites (video-mode jump tables, dispatch stubs) can't be resolved statically,
but every target they actually take appears for free when a demo runs (dos_re_2.0.md §6a: promotion is
EVIDENCE-GATED -- a dynamic-transfer function promotes only when every observed target is dispatchable).
This runs the recorded demo(s) through the reference VM, traps every near-indirect site in the recovery
IR, computes the resolved target the same way the interpreter does (16-bit EA -> the target word), and
writes ``{ "CS:IP": ["CS:IP", ...] }`` -- the ``--dyn-evidence`` input the promoter + the standalone
runtime's DISPATCH registry both consume.

It is a MEASUREMENT probe; output is gitignored + regeneratable. Nothing here is hand-authored.

Usage:
    python scripts/capture_indirect_sites.py [--ir IR] [--demos d1,d2,...] [--out indirect_sites.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))

from overkill.probes._harness import load_demo, run_ref_step_probe, run_ref_step_probe_cold_start  # noqa: E402
from dos_re.lift.decode import decode_one  # noqa: E402

# 16-bit ModRM base/index register combos by rm (mod != 3).
_EA_REGS = (("bx", "si"), ("bx", "di"), ("bp", "si"), ("bp", "di"),
            ("si",), ("di",), ("bp",), ("bx",))
_SEG_OVERRIDE = {0x26: "es", 0x2E: "cs", 0x36: "ss", 0x3E: "ds"}
_W16 = ("ax", "cx", "dx", "bx", "sp", "bp", "si", "di")


def _near_indirect_target(cpu, inst) -> "str | None":
    """The near jmp/call target the interpreter would take, as 'CS:IP'.  Handles
    both memory-indirect (`call [bx+d]`) and REGISTER-indirect (`call ax`) -- the
    latter is a computed function pointer whose target IS the register value, and
    is just as much a dispatch that the CPUless registry must resolve."""
    if inst.modrm is None:
        return None
    s = cpu.s
    mod, rm = inst.modrm >> 6, inst.modrm & 7
    if mod == 3:                                       # register-indirect: target = the reg
        return f"{s.cs & 0xFFFF:04X}:{getattr(s, _W16[rm]) & 0xFFFF:04X}"
    seg = next((_SEG_OVERRIDE[p] for p in inst.prefixes if p in _SEG_OVERRIDE), None)
    if mod == 0 and rm == 6:                           # direct [disp16]
        ea = (inst.disp or 0) & 0xFFFF
    else:
        regs = _EA_REGS[rm]
        ea = (sum(getattr(s, r) for r in regs) + (inst.disp or 0)) & 0xFFFF
        if seg is None and "bp" in regs:
            seg = "ss"                                 # bp-based EA defaults to SS
    segval = getattr(s, seg or "ds") & 0xFFFF
    return f"{s.cs & 0xFFFF:04X}:{cpu.mem.rw(segval, ea):04X}"


def capture(ir_path: Path, demos: "list[str]") -> dict:
    ir = json.loads(ir_path.read_text())
    trap = set()
    for a, f in ir["functions"].items():
        cs = int(a.split(":")[0], 16)
        for blk in f.get("blocks", ()):
            for i in blk["instructions"]:
                if i.get("kind") in ("call_ind", "jmp_ind"):
                    trap.add((cs, int(i["ip"], 16)))

    sites: dict[str, set] = {}

    def on_ref(cpu):
        cs, ip = cpu.s.cs & 0xFFFF, cpu.s.ip & 0xFFFF
        if (cs, ip) not in trap:
            return
        inst = decode_one(lambda o: cpu.mem.rb(cs, o & 0xFFFF), ip)
        tgt = _near_indirect_target(cpu, inst)
        if tgt is not None:
            sites.setdefault(f"{cs:04X}:{ip:04X}", set()).add(tgt)

    frozen = frozenset(trap)
    for name in demos:
        demo = load_demo(name, name)
        if demo.is_cold_start:
            run_ref_step_probe_cold_start(demo, None, on_ref, trap=frozen)
        else:
            run_ref_step_probe(demo, demo.end_boundary + 5, on_ref, trap=frozen)
        print(f"  {name}: {sum(len(v) for v in sites.values())} (site,target) pairs so far")
    return {k: sorted(v) for k, v in sorted(sites.items())}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ir", default=str(ROOT / "artifacts" / "recovery_ir_closed.json"))
    ap.add_argument("--demos", default="demo_play_tandy_L1_start_20260618_143947,"
                                        "demo_cold_start_intro_20260711_203259")
    ap.add_argument("--out", default=str(ROOT / "artifacts" / "indirect_sites.json"))
    args = ap.parse_args(argv)
    ev = capture(Path(args.ir), [d for d in args.demos.split(",") if d])
    Path(args.out).write_text(json.dumps(ev, indent=1))
    resolved = sum(len(v) for v in ev.values())
    print(f"captured {len(ev)} indirect sites, {resolved} distinct targets -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
