"""Show ALL differing bytes between oracle and hook for call 49 of 5C74."""
from __future__ import annotations
import sys
from pathlib import Path
import copy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from overkill.runtime import load_overkill_snapshot
from overkill.hooks import overkill_tandy_postcopy_mode_sweep_5c74

SNAP = "artifacts/repros/hook_verify_divergence_tandy_20260617_125724"
CONTINUATION = 0x96C2

def main():
    exe = ROOT / "assets" / "OVERKILL"
    rt = load_overkill_snapshot(exe, SNAP, game_root=ROOT / "assets")
    cpu_orig = rt.cpu

    import copy as _copy
    orig_data_bytes = bytes(cpu_orig.mem.data)

    # --- Oracle run (raw ASM, no hooks) ---
    rt_asm = load_overkill_snapshot(exe, SNAP, game_root=ROOT / "assets")
    cpu_asm = rt_asm.cpu
    cpu_asm.replacement_hooks.clear()
    cpu_asm.hook_verifier = None

    steps = 0
    cs_val = cpu_asm.s.cs & 0xFFFF
    while steps < 5_000_000:
        if cpu_asm.s.ip == CONTINUATION and cpu_asm.s.cs == cs_val:
            break
        cpu_asm.step()
        steps += 1
    print(f"Oracle: {steps} steps, final IP={cpu_asm.s.ip:04X}")
    asm_data = bytes(cpu_asm.mem.data)

    # --- Hook run (Python hooks, no nested verification) ---
    rt_hook = load_overkill_snapshot(exe, SNAP, game_root=ROOT / "assets")
    cpu_hook = rt_hook.cpu
    cpu_hook.hook_verifier = None
    cpu_hook.step()  # triggers the 5C74 hook
    print(f"Hook: final IP={cpu_hook.s.ip:04X}")
    hook_data = bytes(cpu_hook.mem.data)

    # Compare
    diffs = [(i, asm_data[i], hook_data[i]) for i in range(min(len(asm_data), len(hook_data)))
             if asm_data[i] != hook_data[i]]
    print(f"\nTotal diffs: {len(diffs)}")
    for flat, av, hv in diffs[:50]:
        # Determine which segment this is in
        cs = 0x1010
        ss = 0x25CC
        ds_at_snap = cpu_orig.s.ds & 0xFFFF
        notes = []
        off_cs = flat - cs * 16
        if 0 <= off_cs <= 0xFFFF:
            notes.append(f"CS:0x{off_cs:04X}")
        off_ss = flat - ss * 16
        if 0 <= off_ss <= 0xFFFF:
            notes.append(f"SS:0x{off_ss:04X}")
        off_ds = flat - ds_at_snap * 16
        if 0 <= off_ds <= 0xFFFF:
            notes.append(f"DS(snap):0x{off_ds:04X}")
        note = " = ".join(notes) if notes else "?"
        # Also show initial (snapshot) value
        init = orig_data_bytes[flat]
        print(f"  flat=0x{flat:05X} {note}  init={init:02X} asm={av:02X} hook={hv:02X}")

if __name__ == "__main__":
    main()
