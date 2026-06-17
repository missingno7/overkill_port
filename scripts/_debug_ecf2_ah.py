"""Dump x86 bytes at CS:ED31..ED65 from a repro snapshot to understand AH state."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.play import load_snapshot  # type: ignore

SNAPSHOT = r"artifacts\repros\hook_verify_divergence_tandy_20260617_122607"

def main():
    runtime = load_snapshot(SNAPSHOT)
    cpu = runtime.cpu
    mem = cpu.mem
    cs = cpu.s.cs & 0xFFFF

    print(f"CS = 0x{cs:04X}")

    # Dump bytes from ED31 to ED65 inclusive
    start = 0xED31
    end = 0xED65
    print(f"\nBytes at CS:{start:04X}..{end:04X}:")
    row = []
    for off in range(start, end + 1):
        b = mem.rb(cs, off)
        row.append(f"{b:02X}")
        if (off - start) % 16 == 15 or off == end:
            print(f"  {start + ((off - start) // 16) * 16:04X}: {' '.join(row)}")
            row = []

if __name__ == "__main__":
    main()
