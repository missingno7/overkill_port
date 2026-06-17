"""Run verification for 5C74 call 49 with write tracing on CS:066B."""
from __future__ import annotations
import sys
import traceback as tb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from overkill.headless_verification import (
    HeadlessHookVerifyConfig, run_headless_hook_verifier,
    HookVerifyDivergence, HookVerifyLimitReached
)

SNAP = "artifacts/repros/hook_verify_divergence_tandy_20260617_132627"
TARGET_FLAT = 0x1076B  # CS:066B

def main():
    exe = ROOT / "assets" / "OVERKILL"

    config = HeadlessHookVerifyConfig(
        exe=exe,
        game_root=ROOT / "assets",
        snapshot=SNAP,
        max_verified=5,
        max_steps=5_000_000,
    )

    # Monkey-patch to trace writes after loading
    from overkill.headless_verification import load_overkill_snapshot
    rt = load_overkill_snapshot(exe, SNAP, game_root=ROOT / "assets")
    cpu = rt.cpu

    orig_wb = cpu.mem.wb
    orig_ww = cpu.mem.ww
    hits = []

    def traced_wb(seg, off, val):
        flat = ((seg & 0xFFFF) * 16 + (off & 0xFFFF)) & 0xFFFFF
        if flat == TARGET_FLAT:
            stack_lines = [f.strip() for f in tb.format_stack()[-6:-1]]
            hits.append(("wb", seg, off, val, stack_lines, cpu.s.cs, cpu.s.ip))
        orig_wb(seg, off, val)

    def traced_ww(seg, off, val):
        flat = ((seg & 0xFFFF) * 16 + (off & 0xFFFF)) & 0xFFFFF
        flat1 = (flat + 1) & 0xFFFFF
        if flat == TARGET_FLAT or flat1 == TARGET_FLAT:
            stack_lines = [f.strip() for f in tb.format_stack()[-6:-1]]
            hits.append(("ww", seg, off, val, stack_lines, cpu.s.cs, cpu.s.ip))
        orig_ww(seg, off, val)

    cpu.mem.wb = traced_wb
    cpu.mem.ww = traced_ww

    print(f"Initial CS:066B = {rt.cpu.mem.data[TARGET_FLAT]}")
    print()

    try:
        result = run_headless_hook_verifier(config)
        print(f"Result: {result}")
    except HookVerifyDivergence as e:
        print(f"DIVERGENCE: {e}")
    except HookVerifyLimitReached as e:
        print(f"Limit reached: {e}")

    print(f"\nWrites to flat 0x{TARGET_FLAT:05X} (CS:066B): {len(hits)}")
    for i, hit in enumerate(hits):
        kind, seg, off, val, stack_lines, cs, ip = hit
        print(f"\n  Hit {i+1}: {kind} seg={seg:04X} off={off:04X} val=0x{val:02X} @ CS:{cs:04X}:IP:{ip:04X}")
        for line in stack_lines:
            print(f"    {line}")

if __name__ == "__main__":
    main()
