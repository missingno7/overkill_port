"""Driven-oracle: the 99F6 scripted-input dispatch prologue vs the ORIGINAL 1010:99F6.

Drives the original bytes with a synthetic ``(A47C, 2380)``, runs the prologue until it jumps to the
per-mode handler, and confirms ``systems.frame_loop.scripted_input_prologue_99f6`` predicts the same
handler IP (via the ``CS:9A0C`` table), the same cleared ``DS:2380`` bit and ``DS:98BE == 0``.

Usage:
    python -m overkill.probes.verify_native_scripted_input_dispatch [snapshot_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CS = 0x1010
ENTRY = 0x99F6
PROLOGUE_IPS = {0x99F6, 0x99FB, 0x9A00, 0x9A04, 0x9A06}   # up to and incl. the JMP
DEFAULT_SNAP = "artifacts/demos/demo_play_tandy_player_death_20260618_233821/snapshot"
COMBOS = [(0, 0xFFFF), (1, 0x0001), (2, 0x1235), (3, 0x0000), (4, 0xABCD)]


def main(argv) -> int:
    from overkill.runtime import load_overkill_snapshot
    from overkill.recovered.systems.frame_loop import (
        SCRIPTED_INPUT_TABLE_9A0C, scripted_input_prologue_99f6)

    snap = Path(argv[0]) if argv else ROOT / DEFAULT_SNAP
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None
    ds = cpu.s.ds & 0xFFFF
    m = cpu.mem

    def drive(a47c, v2380):
        m.ww(ds, 0xA47C, a47c & 0xFFFF)
        m.ww(ds, 0x2380, v2380 & 0xFFFF)
        s = cpu.s
        s.cs, s.ip = CS, ENTRY
        handler_ip = None
        for _ in range(500):
            ip = s.ip & 0xFFFF
            if (s.cs & 0xFFFF) == CS and ip not in PROLOGUE_IPS:
                handler_ip = ip     # first instruction past the JMP = the handler
                break
            cpu.step()
        return handler_ip, m.rw(ds, 0x2380) & 0xFFFF, m.rw(ds, 0x98BE) & 0xFFFF

    fails = []
    for a47c, v2380 in COMBOS:
        vm_ip, vm_2380, vm_98be = drive(a47c, v2380)
        new_2380, new_98be, off = scripted_input_prologue_99f6(a47c, v2380)
        mine_ip = m.rw(CS, (SCRIPTED_INPUT_TABLE_9A0C + off) & 0xFFFF) & 0xFFFF
        if (mine_ip, new_2380, new_98be) != (vm_ip, vm_2380, vm_98be & 0xFF):
            fails.append(((a47c, hex(v2380)),
                          (hex(mine_ip), hex(new_2380), hex(new_98be)),
                          (hex(vm_ip) if vm_ip else None, hex(vm_2380), hex(vm_98be))))

    print(f"99F6 scripted-input dispatch driven-oracle: combos={len(COMBOS)} fails={len(fails)}")
    for f in fails:
        print("  FAIL in=", f[0], "mine=", f[1], "vm=", f[2])
    ok = not fails
    print("RESULT:", "PASS -- scripted_input_prologue_99f6 matches the original 99F6 dispatch"
          if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
