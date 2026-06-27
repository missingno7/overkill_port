"""Probe: dump the real render draw-list memory vs the FrameSnapshot extractor.

Loads a gameplay snapshot (memory_1mb.bin + state.json) and prints, side by side:
  - what `extract_frame_snapshot` currently produces (active object-table slots),
  - the raw presence lists the A90C present scan actually walks
    (DS:8D12 / DS:32CA) and the [CS:9598]:C7B1 stamp list,
so we can recover the *faithful* draw-list format and ground the extractor.

Usage:
    python -m overkill.probes.inspect_draw_list <snapshot_dir>
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from dos_re.memory import Memory
from overkill.recovered.adapters.frame_snapshot_adapter import extract_frame_snapshot
from overkill.recovered.views.object_slots import (
    EFFECT_OBJECT_TABLE_BASE,
    EFFECT_OBJECT_TABLE_COUNT,
    GAMEPLAY_OBJECT_TABLE_BASE,
    GAMEPLAY_OBJECT_TABLE_COUNT,
    OBJECT_SLOT_STRIDE,
    ObjectSlotView,
)

PRESENCE_LIST_8D12 = 0x8D12
PRESENCE_LIST_32CA = 0x32CA
STAMP_SEG_PTR = 0x9598   # CS:[9598] -> the presence/stamp list segment
STAMP_LIST_C7B1 = 0xC7B1


def _regs(state: dict) -> dict[str, int]:
    snap = state["cpu_snapshot"]
    return {k.lower(): int(v, 16) for k, v in re.findall(r"(\bDS|\bCS|\bES|\bSS)=([0-9A-Fa-f]{4})", snap)}


def _words(mem: Memory, seg: int, off: int, n: int) -> list[int]:
    return [mem.rw(seg, (off + 2 * i) & 0xFFFF) for i in range(n)]


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    snap = Path(argv[0])
    mem = Memory()
    mem.data[:] = (snap / "memory_1mb.bin").read_bytes()
    state = json.loads((snap / "state.json").read_text(encoding="utf-8"))
    regs = _regs(state)
    ds, cs = regs.get("ds", 0), regs.get("cs", 0x1010)
    print(f"snapshot {snap.name}  DS={ds:04X} CS={cs:04X}")

    fs = extract_frame_snapshot(mem, ds)
    print(f"\n[extractor] camera={fs.playfield.camera}  sprites={len(fs.playfield.sprites)}")
    for sd in fs.playfield.sprites[:12]:
        print(f"  sprite={sd.sprite:04X} x={sd.x:5d} y={sd.y:5d} layer={sd.layer:02X} type={sd.object_type:02X}")

    # active slot counts per table (the extractor's source)
    for name, base, count in (("effect", EFFECT_OBJECT_TABLE_BASE, EFFECT_OBJECT_TABLE_COUNT),
                              ("gameplay", GAMEPLAY_OBJECT_TABLE_BASE, GAMEPLAY_OBJECT_TABLE_COUNT)):
        active = sum(1 for i in range(count)
                     if ObjectSlotView(mem, ds, base + i * OBJECT_SLOT_STRIDE).active_word != 0)
        print(f"  table {name}: {active}/{count} active")

    print(f"\n[present list DS:{PRESENCE_LIST_8D12:04X}] (A90F scan, 34 words)")
    print("  " + " ".join(f"{w:04X}" for w in _words(mem, ds, PRESENCE_LIST_8D12, 34)))
    print(f"[present list DS:{PRESENCE_LIST_32CA:04X}] (A927 scan, 36 words)")
    print("  " + " ".join(f"{w:04X}" for w in _words(mem, ds, PRESENCE_LIST_32CA, 36)))

    stamp_seg = mem.rw(cs, STAMP_SEG_PTR)
    print(f"\n[stamp list [CS:{STAMP_SEG_PTR:04X}]={stamp_seg:04X}:{STAMP_LIST_C7B1:04X}] (40 words)")
    print("  " + " ".join(f"{w:04X}" for w in _words(mem, stamp_seg, STAMP_LIST_C7B1, 40)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
