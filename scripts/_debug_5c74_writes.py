"""Trace memory writes to flat 0x2032D during the oracle run of call 49 of 5C74."""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from overkill.runtime import load_overkill_snapshot

SNAP = "artifacts/repros/hook_verify_divergence_tandy_20260617_125724"
TARGET_FLAT = 0x2032D
CONTINUATION = 0x96C2

def main():
    exe = ROOT / "assets" / "OVERKILL"
    rt = load_overkill_snapshot(exe, SNAP, game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None

    # Patch memory write methods to trace writes to TARGET_FLAT
    orig_wb = cpu.mem.wb
    orig_ww = cpu.mem.ww

    hits = []

    def traced_wb(seg, off, val):
        flat = ((seg & 0xFFFF) * 16 + (off & 0xFFFF)) & 0xFFFFF
        if flat == TARGET_FLAT:
            hits.append(("wb", cpu.s.cs & 0xFFFF, cpu.s.ip & 0xFFFF, flat, val))
        orig_wb(seg, off, val)

    def traced_ww(seg, off, val):
        flat = ((seg & 0xFFFF) * 16 + (off & 0xFFFF)) & 0xFFFFF
        flat1 = (flat + 1) & 0xFFFFF
        if flat == TARGET_FLAT or flat1 == TARGET_FLAT:
            hits.append(("ww", cpu.s.cs & 0xFFFF, cpu.s.ip & 0xFFFF, flat, val))
        orig_ww(seg, off, val)

    # Also trace direct data[] writes via the fast-path (used by rep_movsb etc.)
    orig_data = cpu.mem.data
    # We can't easily intercept slice assignment, so use step() tracing approach

    cpu.mem.wb = traced_wb
    cpu.mem.ww = traced_ww

    print(f"Oracle run from CS:5C74, continuation=96C2")
    print(f"Tracing writes to flat 0x{TARGET_FLAT:05X}")
    print()

    steps = 0
    max_steps = 5_000_000
    cs_val = cpu.s.cs & 0xFFFF
    print(f"Start: CS:IP = {cpu.s.cs:04X}:{cpu.s.ip:04X}, CS:5901={cpu.mem.rw(cs_val, 0x5901)}")

    while steps < max_steps:
        if cpu.s.ip == CONTINUATION and cpu.s.cs == cs_val:
            print(f"Reached continuation at {steps} steps.")
            break
        try:
            cpu.step()
        except Exception as e:
            print(f"Exception at CS:IP {cpu.s.cs:04X}:{cpu.s.ip:04X}: {e}")
            break
        steps += 1
    else:
        print(f"Timeout after {max_steps} steps. Last IP: {cpu.s.cs:04X}:{cpu.s.ip:04X}")

    print(f"\nWritten to flat 0x{TARGET_FLAT:05X}: {len(hits)} hit(s)")
    for hit in hits:
        kind, cs, ip, flat, val = hit
        print(f"  {kind} @ CS:IP={cs:04X}:{ip:04X} flat=0x{flat:05X} val=0x{val:02X}")

    # Also show final byte at TARGET_FLAT
    final_val = cpu.mem.data[TARGET_FLAT]
    print(f"\nFinal byte at 0x{TARGET_FLAT:05X} = 0x{final_val:02X}")

if __name__ == "__main__":
    main()
