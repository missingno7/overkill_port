"""Size the enemy-AI behavior zoo: which of the 149 EFC4 handlers share WORKERS?

The pre2 second-pass principle: most dispatch handlers are thin wrappers over a small set of shared
worker routines -- the workers are the true recovery surface, not the handler count.  This script
measures that for OVERKILL's behavior dispatch table (``CS:EFC4``, keyed on the record's ``+0x18``):

* ALIAS GROUPS -- behavior indices sharing one handler entry (table aliases);
* per-handler LINEAR span from the entry to its first unconditional flow break (``ret`` or ``jmp``),
  decoding real instructions lindis-style on a throwaway runtime;
* the CALL-target histogram (workers reached by ``call``) and the TAIL-target histogram (handlers
  ending in ``jmp X`` -- a shared tail IS a shared worker), with the common exits (``BC45``/``BC4B``)
  counted separately;
* the thin-stub count (span < 0x20 bytes).

Linear decode only (conditional branches fall through), so mid-body alternate paths are NOT walked --
this is a SIZING instrument, not a call graph; treat its numbers as lower bounds on sharing.

Usage:
    python scripts/behavior_zoo_xref.py [snapshot_dir]
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CS = 0x1010
DEFAULT_SNAP = ROOT / "artifacts/demos/demo_play_tandy_L1_start_20260618_143947/snapshot"
COMMON_EXITS = {0xBC45, 0xBC4B}
SPAN_BUDGET = 0x300      # max bytes decoded per handler before giving up
THIN_STUB_BYTES = 0x20


def _decoder(snap):
    """A lindis-style single-instruction decoder on a throwaway runtime (hooks cleared)."""
    from overkill.runtime import load_overkill_snapshot

    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None
    cpu.trace_enabled = True

    orig_fetch8, counter = cpu.fetch8, {"n": 0}

    def counting_fetch8():
        counter["n"] += 1
        return orig_fetch8()

    cpu.fetch8 = counting_fetch8
    orig_exec, last = cpu.execute_opcode, {"asm": "?"}

    def capturing_exec(op, seg_override, rep):
        res = orig_exec(op, seg_override, rep)
        last["asm"] = res
        return res

    cpu.execute_opcode = capturing_exec

    def decode_at(ip: int) -> tuple[int, str]:
        cpu.s.cs, cpu.s.ip = CS, ip & 0xFFFF
        counter["n"] = 0
        last["asm"] = "?"
        try:
            cpu.step()
            asm = last["asm"] or "?"
        except Exception as exc:  # noqa: BLE001 -- odd opcode; treat as 1 byte
            asm = f"<dec-exc {type(exc).__name__}>"
        return (counter["n"] if counter["n"] > 0 else 1), asm.strip()

    return cpu, decode_at


def _target_of(asm: str) -> int | None:
    # trace strings look like "call near -> 1010:81F4 ..." / "jmp near -> 1010:BC4B"
    if "-> " not in asm:
        return None
    tail = asm.split("-> ", 1)[1]
    seg_off = tail.split()[0]
    if ":" not in seg_off:
        return None
    seg, off = seg_off.split(":")
    try:
        return int(off, 16) if int(seg, 16) == CS else None
    except ValueError:
        return None


def main(argv) -> int:
    from overkill.recovered.adapters.behavior_dispatch_adapter import (
        BEHAVIOR_EXIT_BC45,
        load_behavior_dispatch_table,
    )

    snap = Path(argv[0]) if argv else DEFAULT_SNAP
    image = (snap / "memory_1mb.bin").read_bytes()
    table = load_behavior_dispatch_table(image)
    _cpu, decode_at = _decoder(snap)

    by_entry: dict[int, list[int]] = defaultdict(list)
    for beh, entry in enumerate(table):
        by_entry[entry].append(beh)
    real_entries = {e: b for e, b in by_entry.items() if e != BEHAVIOR_EXIT_BC45}
    print(f"{len(table)} behavior indices -> {len(real_entries)} distinct handler entries "
          f"(+ the BC45 no-op filler x{len(by_entry.get(BEHAVIOR_EXIT_BC45, []))})")
    aliases = {e: b for e, b in real_entries.items() if len(b) > 1}
    print(f"alias groups (one entry, several behavior indices): {len(aliases)}")
    for e, b in sorted(aliases.items()):
        print(f"  1010:{e:04X} <- behaviors {', '.join(f'{x:02X}' for x in b)}")

    call_targets: dict[int, list[int]] = defaultdict(list)   # worker -> [handler entries]
    tail_targets: dict[int, list[int]] = defaultdict(list)
    spans: dict[int, int] = {}
    for entry in sorted(real_entries):
        ip = entry
        while ip < entry + SPAN_BUDGET:
            n, asm = decode_at(ip)
            if asm.startswith("call near"):
                t = _target_of(asm)
                if t is not None:
                    call_targets[t].append(entry)
            if asm.startswith(("ret", "iret")):
                break
            if asm.startswith(("jmp near", "jmp short", "jmp far")):
                t = _target_of(asm)
                if t is not None:
                    tail_targets[t].append(entry)
                break
            ip += n
        spans[entry] = min(ip + 1, entry + SPAN_BUDGET) - entry

    thin = sum(1 for s in spans.values() if s < THIN_STUB_BYTES)
    print(f"\nlinear spans: thin stubs (<{THIN_STUB_BYTES:#x} bytes) = {thin}/{len(spans)}; "
          f"budget-capped = {sum(1 for s in spans.values() if s >= SPAN_BUDGET)}")

    def _histo(name, hist, skip=()):
        rows = sorted(((len(v), t) for t, v in hist.items() if t not in skip), reverse=True)
        print(f"\n{name} (target: #handlers using it):")
        for count, t in rows:
            if count < 2:
                break
            print(f"  1010:{t:04X}: {count}")
        singles = sum(1 for c, t in rows if c == 1)
        print(f"  (+ {singles} single-use targets)")

    _histo("SHARED CALL WORKERS", call_targets)
    exits = {t: v for t, v in tail_targets.items() if t in COMMON_EXITS}
    print(f"\ncommon-exit tails: " + ", ".join(f"1010:{t:04X} x{len(v)}" for t, v in sorted(exits.items())))
    _histo("SHARED TAIL WORKERS (handlers ending jmp X)", tail_targets, skip=COMMON_EXITS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
