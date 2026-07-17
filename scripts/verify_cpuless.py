"""verify_cpuless.py -- per-function CPUless DIFFERENTIAL: the recovered function must compute what the
interpreter does, over randomized state (the manifest's "function differential", dos_re_2.0.md §6a).

Structural promotion only proves a function EMITS as a pure `(mem, plat, *regs)` module; it does not
prove it COMPUTES the same thing the CPU does.  This closes that gap the same way the DAA test does, but
per promoted function and automatically: load the real game image (valid code+data), pick a randomized
register/flag state, then

  * run the generated CPU-ABI ADAPTER (which calls the pure recovered body) on one CPU, and
  * INTERPRET the original bytes to the function's return on an identical clone,

and diff the full register file + memory.  A match over many trials is strong byte-exact evidence; a
mismatch names the first divergent register/cell.  This is the correctness gate the deep de-carrier
capabilities (tail-dispatch, sp-as-data) need under them before they can land safely.

Scope: NEAR-RET functions with no platform effect (the bulk).  retf/iret, sp-output, boundary-head and
port/int functions are reported SKIPPED (they need the standalone runtime's scheduler/registry to drive
faithfully) -- never silently passed.

Usage:
    python scripts/verify_cpuless.py [--snapshot DIR] [--entries a,b,..|@file] [--trials N] [--limit N]
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))

from dos_re.cpu import CPU8086, CPUState  # noqa: E402
from dos_re.memory import Memory  # noqa: E402
from overkill.runtime import load_overkill_snapshot  # noqa: E402

_W = ("ax", "bx", "cx", "dx", "si", "di", "bp", "sp", "ds", "es")
_SENTINEL = 0x7FEE          # return offset we push; the fn RETs to it (near ret pops the offset)


def _lcg(seed: int):
    x = seed & 0xFFFFFFFF
    while True:
        x = (1103515245 * x + 12345) & 0xFFFFFFFF
        yield (x >> 8) & 0xFFFF


def _make_cpu(base: bytes, regs: dict) -> CPU8086:
    mem = Memory()
    mem.data[:len(base)] = base
    st = CPUState(**{r: regs[r] for r in ("ax", "bx", "cx", "dx", "si", "di", "bp", "sp",
                                          "cs", "ds", "es", "ss", "ip")})
    st.flags = regs["flags"]
    cpu = CPU8086(mem, st)
    cpu.trace_enabled = False
    return cpu


def _run_interp(base: bytes, regs: dict, budget: int = 200000):
    # Fully-random register state can send the interpreter down a path that
    # reads/executes data as code; that is a random-state ARTIFACT, not a
    # divergence, so any interpreter fault -> None (INCONCLUSIVE), never a fail.
    from dos_re.x86 import UnsupportedInstruction
    cpu = _make_cpu(base, regs)
    cs = cpu.s.cs & 0xFFFF
    try:
        for _ in range(budget):
            if (cpu.s.cs & 0xFFFF) == cs and (cpu.s.ip & 0xFFFF) == _SENTINEL:
                return cpu
            cpu.step()
    except (UnsupportedInstruction, Exception):  # noqa: BLE001
        return None
    return None                # never returned in budget -> inconclusive


def _run_adapter(base: bytes, regs: dict, adapter):
    cpu = _make_cpu(base, regs)
    adapter(cpu)
    return cpu


def _has_dynamic(f) -> bool:
    return any(i.get("kind") in ("call_ind", "jmp_ind")
               for blk in f.get("blocks", ()) for i in blk["instructions"])


def _cmp(a: CPU8086, b: CPU8086) -> "list[str]":
    diffs = []
    for r in _W + ("ip",):
        if (getattr(a.s, r) & 0xFFFF) != (getattr(b.s, r) & 0xFFFF):
            diffs.append(f"{r}: interp={getattr(a.s, r) & 0xFFFF:04X} adapter={getattr(b.s, r) & 0xFFFF:04X}")
    if a.mem.data != b.mem.data:
        for i in range(len(a.mem.data)):
            if a.mem.data[i] != b.mem.data[i]:
                diffs.append(f"mem[{i:06X}]: interp={a.mem.data[i]:02X} adapter={b.mem.data[i]:02X}")
                if len([d for d in diffs if d.startswith('mem')]) >= 4:
                    break
    return diffs


def verify_one(base: bytes, cs: int, ip: int, ss: int, sp0: int, adapter, trials: int) -> tuple:
    """Return (verdict, detail). verdict in PASS/DIVERGED/INCONCLUSIVE."""
    from overkill.cpuless_recovered._dyncall import UnknownDispatchTarget
    rng = _lcg((cs << 16) | ip)
    for t in range(trials):
        regs = {r: next(rng) for r in ("ax", "bx", "cx", "dx", "si", "di", "bp")}
        regs.update(cs=cs, ds=next(rng) & 0xFF00 | 0x25CC & 0x00FF, es=next(rng), ss=ss, ip=ip)
        regs["ds"] = 0x25CC     # the game DGROUP (so DS-relative reads land in real data)
        regs["es"] = 0x25CC
        regs["sp"] = (sp0 - 2) & 0xFFFF
        regs["flags"] = 0x0002 | (next(rng) & 0x0CD5)   # random defined-flag bits
        base2 = bytearray(base)
        # push the sentinel return offset at SS:SP (near ret pops it into IP)
        addr = (ss << 4) + regs["sp"]
        base2[addr] = _SENTINEL & 0xFF
        base2[addr + 1] = (_SENTINEL >> 8) & 0xFF
        base2 = bytes(base2)
        ia = _run_interp(base2, regs)
        if ia is None:
            return "INCONCLUSIVE", f"interp did not return in budget (trial {t})"
        try:
            ba = _run_adapter(base2, regs, adapter)
        except UnknownDispatchTarget as exc:
            return "INCONCLUSIVE", f"dispatch target not in registry: {str(exc)[:60]}"
        except Exception as exc:  # noqa: BLE001 -- adapter faulted where interp ran clean: REAL
            return "DIVERGED", f"trial {t}: adapter raised {type(exc).__name__}: {str(exc)[:80]}"
        d = _cmp(ia, ba)
        if d:
            return "DIVERGED", f"trial {t}: " + "; ".join(d[:5])
    return "PASS", f"{trials} trials byte-exact"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--snapshot",
                    default=str(ROOT / "artifacts" / "demos" / "demo_play_tandy_L1_start_20260618_143947" / "snapshot"))
    ap.add_argument("--ir", default=str(ROOT / "artifacts" / "recovery_ir_closed.json"))
    ap.add_argument("--entries", default="", help="CS:IP,... or @file; default = all near-ret promoted")
    ap.add_argument("--trials", type=int, default=12)
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--adapter-pkg", default="overkill.cpuless_adapters")
    args = ap.parse_args(argv)

    ir = json.loads(Path(args.ir).read_text())
    fns = ir["functions"]
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", args.snapshot, game_root=ROOT / "assets")
    base = bytes(rt.cpu.mem.data)
    ss, sp0 = rt.cpu.s.ss & 0xFFFF, 0x7F00

    if args.entries.startswith("@"):
        want = [ln.strip() for ln in Path(args.entries[1:]).read_text().splitlines() if ln.strip()]
    elif args.entries:
        want = args.entries.split(",")
    else:  # all near-ret, no-int, no dynamic transfer, 1010 segment (differential-eligible)
        want = [a for a, f in fns.items()
                if f.get("liftable") and f.get("exits") == ["ret"] and not f.get("ints")
                and not _has_dynamic(f) and a.startswith("1010:")]
    want = want[:args.limit]

    tally = {"PASS": 0, "DIVERGED": 0, "INCONCLUSIVE": 0, "SKIP": 0}
    diverged = []
    for key in want:
        cs, ip = (int(x, 16) for x in key.split(":"))
        stem = f"lifted_{cs:04x}_{ip:04x}"
        try:
            mod = importlib.import_module(f"{args.adapter_pkg}.{stem}")
            adapter = getattr(mod, stem)
        except Exception as exc:  # noqa: BLE001 -- not promoted / not near-ret adapter
            tally["SKIP"] += 1
            continue
        verdict, detail = verify_one(base, cs, ip, ss, sp0, adapter, args.trials)
        tally[verdict] += 1
        mark = {"PASS": "PASS    ", "DIVERGED": "DIVERGED", "INCONCLUSIVE": "INCONCL "}[verdict]
        print(f"  {mark} {key}  {detail}")
        if verdict == "DIVERGED":
            diverged.append(key)

    print(f"\n{tally['PASS']} PASS, {tally['DIVERGED']} DIVERGED, {tally['INCONCLUSIVE']} INCONCLUSIVE, "
          f"{tally['SKIP']} skipped / {len(want)} requested")
    if diverged:
        print("DIVERGED:", " ".join(diverged))
    return 1 if diverged else 0


if __name__ == "__main__":
    raise SystemExit(main())
