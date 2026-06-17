"""Show all diffs and trace writes to 0x1076B for the new 5C74 divergence."""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from overkill.runtime import load_overkill_snapshot

SNAP = "artifacts/repros/hook_verify_divergence_tandy_20260617_132627"
TARGET_FLAT = 0x1076B  # CS:066B
CONTINUATION = 0x96C2

def run_oracle(snap_path):
    exe = ROOT / "assets" / "OVERKILL"
    rt = load_overkill_snapshot(exe, snap_path, game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None

    hits = []
    orig_wb = cpu.mem.wb
    orig_ww = cpu.mem.ww
    orig_data = cpu.mem.data

    def traced_wb(seg, off, val):
        flat = ((seg & 0xFFFF) * 16 + (off & 0xFFFF)) & 0xFFFFF
        if flat == TARGET_FLAT:
            hits.append(("wb", cpu.s.cs, cpu.s.ip, val))
        orig_wb(seg, off, val)

    def traced_ww(seg, off, val):
        flat = ((seg & 0xFFFF) * 16 + (off & 0xFFFF)) & 0xFFFFF
        flat1 = (flat + 1) & 0xFFFFF
        if flat == TARGET_FLAT or flat1 == TARGET_FLAT:
            hits.append(("ww", cpu.s.cs, cpu.s.ip, val))
        orig_ww(seg, off, val)

    cpu.mem.wb = traced_wb
    cpu.mem.ww = traced_ww

    cs_val = cpu.s.cs & 0xFFFF
    steps = 0
    while steps < 5_000_000:
        if cpu.s.ip == CONTINUATION and cpu.s.cs == cs_val:
            break
        cpu.step()
        steps += 1

    final_val = orig_data[TARGET_FLAT]
    return bytes(orig_data), hits, final_val, steps

def run_hook(snap_path):
    exe = ROOT / "assets" / "OVERKILL"
    rt = load_overkill_snapshot(exe, snap_path, game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.hook_verifier = None

    hits = []
    orig_wb = cpu.mem.wb
    orig_ww = cpu.mem.ww

    def traced_wb(seg, off, val):
        flat = ((seg & 0xFFFF) * 16 + (off & 0xFFFF)) & 0xFFFFF
        if flat == TARGET_FLAT:
            import traceback as tb
            hits.append(("wb", cpu.s.cs, cpu.s.ip, val, tb.format_stack()[-4:-1]))
        orig_wb(seg, off, val)

    def traced_ww(seg, off, val):
        flat = ((seg & 0xFFFF) * 16 + (off & 0xFFFF)) & 0xFFFFF
        flat1 = (flat + 1) & 0xFFFFF
        if flat == TARGET_FLAT or flat1 == TARGET_FLAT:
            import traceback as tb
            hits.append(("ww", cpu.s.cs, cpu.s.ip, val, tb.format_stack()[-4:-1]))
        orig_ww(seg, off, val)

    cpu.mem.wb = traced_wb
    cpu.mem.ww = traced_ww

    cpu.step()  # trigger the 5C74 hook
    data = bytes(cpu.mem.data)
    return data, hits, data[TARGET_FLAT]

def main():
    exe = ROOT / "assets" / "OVERKILL"
    rt0 = load_overkill_snapshot(exe, SNAP, game_root=ROOT / "assets")
    init_val = rt0.cpu.mem.data[TARGET_FLAT]
    print(f"Initial CS:066B = 0x{init_val:02X} ({init_val})")
    print(f"Target: flat 0x{TARGET_FLAT:05X}")
    print()

    print("Running oracle...")
    asm_data, asm_hits, asm_final, steps = run_oracle(SNAP)
    print(f"Oracle: {steps} steps, CS:066B final = 0x{asm_final:02X} ({asm_final})")
    print(f"Oracle writes to target: {len(asm_hits)}")
    for h in asm_hits:
        print(f"  {h[0]} @ CS:{h[1]:04X}:IP:{h[2]:04X} val=0x{h[3]:02X}")

    print()
    print("Running hook...")
    hook_data, hook_hits, hook_final = run_hook(SNAP)
    print(f"Hook: CS:066B final = 0x{hook_final:02X} ({hook_final})")
    print(f"Hook writes to target: {len(hook_hits)}")
    for h in hook_hits:
        print(f"  {h[0]} @ CS:{h[1]:04X}:IP:{h[2]:04X} val=0x{h[3]:02X}")
        for line in h[4]:
            print(f"    {line.strip()}")

    print()
    diffs = [(i, asm_data[i], hook_data[i]) for i in range(min(len(asm_data), len(hook_data)))
             if asm_data[i] != hook_data[i]]
    print(f"Total diffs: {len(diffs)}")
    for flat, av, hv in diffs[:20]:
        cs = 0x1010
        off_cs = flat - cs * 16
        note = f"CS:0x{off_cs:04X}" if 0 <= off_cs <= 0xFFFF else "?"
        init = rt0.cpu.mem.data[flat]
        print(f"  flat=0x{flat:05X} {note}  init={init:02X} asm={av:02X} hook={hv:02X}")

if __name__ == "__main__":
    main()
