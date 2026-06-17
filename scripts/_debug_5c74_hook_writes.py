"""Trace memory writes to flat 0x2032D during the HOOK run of call 49 of 5C74."""
from __future__ import annotations
import sys
import traceback as tb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from overkill.runtime import load_overkill_snapshot

SNAP = "artifacts/repros/hook_verify_divergence_tandy_20260617_125724"
TARGET_FLAT = 0x2032D

def main():
    exe = ROOT / "assets" / "OVERKILL"
    rt = load_overkill_snapshot(exe, SNAP, game_root=ROOT / "assets")
    cpu = rt.cpu

    # Don't clear hooks — run the hook path
    cpu.hook_verifier = None  # disable nested verification

    orig_wb = cpu.mem.wb
    orig_ww = cpu.mem.ww
    # Also patch raw data[] writes (used by _rep_movsb fast path)
    orig_data_class = type(cpu.mem.data)

    hits = []

    def traced_wb(seg, off, val):
        flat = ((seg & 0xFFFF) * 16 + (off & 0xFFFF)) & 0xFFFFF
        if flat == TARGET_FLAT:
            hits.append(("wb", flat, val, tb.extract_stack()))
        orig_wb(seg, off, val)

    def traced_ww(seg, off, val):
        flat = ((seg & 0xFFFF) * 16 + (off & 0xFFFF)) & 0xFFFFF
        flat1 = (flat + 1) & 0xFFFFF
        if flat == TARGET_FLAT or flat1 == TARGET_FLAT:
            hits.append(("ww", flat, val, tb.extract_stack()))
        orig_ww(seg, off, val)

    cpu.mem.wb = traced_wb
    cpu.mem.ww = traced_ww

    # Intercept raw data[] slice assignment by wrapping the bytearray
    class TracedData:
        def __init__(self, data):
            self._data = data
        def __getattr__(self, name):
            return getattr(self._data, name)
        def __setitem__(self, key, val):
            if isinstance(key, slice):
                start = key.start or 0
                stop = key.stop if key.stop is not None else len(self._data)
                if start <= TARGET_FLAT < stop:
                    hits.append(("slice", TARGET_FLAT, val[TARGET_FLAT - start] if hasattr(val, '__getitem__') else val, tb.extract_stack()))
            elif key == TARGET_FLAT:
                hits.append(("direct", key, val, tb.extract_stack()))
            self._data[key] = val
        def __getitem__(self, key):
            return self._data[key]
        def __len__(self):
            return len(self._data)

    cpu.mem.data = TracedData(cpu.mem.data._data if hasattr(cpu.mem.data, '_data') else cpu.mem.data)

    cs_val = cpu.s.cs & 0xFFFF
    print(f"Hook run: CS:IP={cpu.s.cs:04X}:{cpu.s.ip:04X}, CS:5901={cpu.mem.rw(cs_val, 0x5901)}")
    print(f"Tracing writes to flat 0x{TARGET_FLAT:05X}")
    print()

    # Trigger the hook by stepping
    try:
        cpu.step()
    except Exception as e:
        print(f"Exception: {e}")
        tb.print_exc()

    print(f"After hook: CS:IP={cpu.s.cs:04X}:{cpu.s.ip:04X}")
    print(f"Written to flat 0x{TARGET_FLAT:05X}: {len(hits)} hit(s)")
    for i, hit in enumerate(hits[:10]):
        kind = hit[0]
        flat = hit[1]
        val = hit[2]
        stack = hit[3]
        print(f"\nHit {i+1}: {kind} flat=0x{flat:05X} val=0x{val:02X}")
        # Show last few frames
        for frame in stack[-6:]:
            print(f"  File '{frame.filename}', line {frame.lineno}, in {frame.name}")
            if frame.line:
                print(f"    {frame.line}")

if __name__ == "__main__":
    main()
