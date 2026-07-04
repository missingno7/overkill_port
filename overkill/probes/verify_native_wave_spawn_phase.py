"""Driven-oracle: the enemy-wave phase dispatch vs the ORIGINAL 1010:B48B.

Drives ``B48B`` with a synthetic ``DS:A7A0`` and observes which spawn-path entry it reaches -- B615
(per-planet), B5D8->B5E6 (formation) or BC4B (skip) -- comparing to
``systems.frame_loop.wave_spawn_phase_b48b``.

Usage:
    python -m overkill.probes.verify_native_wave_spawn_phase [snapshot_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CS = 0x1010
ENTRY = 0xB48B
TARGETS = {0xB615: "per_planet", 0xB5D8: "formation", 0xBC4B: "none"}
DEFAULT_SNAP = "artifacts/demos/demo_play_tandy_L1_start_20260618_143947/snapshot"


def main(argv) -> int:
    from overkill.runtime import load_overkill_snapshot
    from overkill.recovered.systems.frame_loop import wave_spawn_phase_b48b

    snap = Path(argv[0]) if argv else ROOT / DEFAULT_SNAP
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None
    s = cpu.s
    ds = s.ds & 0xFFFF
    m = cpu.mem

    def drive(a7a0):
        m.ww(ds, 0xA7A0, a7a0 & 0xFFFF)
        s.cs, s.ip = CS, ENTRY
        for _ in range(300):
            ip = s.ip & 0xFFFF
            if (s.cs & 0xFFFF) == CS and ip in TARGETS:
                return TARGETS[ip]
            cpu.step()
        return "?"

    fails = 0
    for a in (0x00, 0x20, 0x31, 0x32, 0x40, 0x59, 0x5A, 0x60, 0x80, 0xFF):
        vm = drive(a)
        mine = wave_spawn_phase_b48b(a)
        ok = vm == mine
        fails += not ok
        print(f"  A7A0={a:#04x}: vm={vm} mine={mine} {'ok' if ok else 'FAIL'}")

    print(f"wave-spawn phase dispatch: fails={fails}")
    print("RESULT:", "PASS -- wave_spawn_phase_b48b matches the original B48B dispatch"
          if not fails else "CHECK")
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
