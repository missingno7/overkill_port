"""Driven-oracle: the per-planet video/palette dispatch vs the ORIGINAL 1010:C565.

Drives ``C565`` (``jmp cs:[DS:2356*2 + 0xC570]``) for each of the six planets (2356=0..5), captures where
the jump lands, and asserts it matches ``native_app.PLANET_VIDEO_DISPATCH``.  Also confirms scenes 6/7
dispatch to DISTINCT handlers (the special-scene GAP) -- i.e. the table does NOT stop at the six planets.

Usage:
    python -m overkill.probes.verify_native_planet_video_dispatch [snapshot_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CS = 0x1010
ENTRY = 0xC565
DISPATCH_IPS = {0xC565, 0xC569, 0xC56B}   # the mov/shl/jmp of the dispatch itself
DEFAULT_SNAP = "artifacts/demos/demo_play_tandy_player_death_20260618_233821/snapshot"


def main(argv) -> int:
    from overkill.runtime import load_overkill_snapshot
    from overkill.native_app import PLANET_VIDEO_DISPATCH

    snap = Path(argv[0]) if argv else ROOT / DEFAULT_SNAP
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None
    s = cpu.s
    ds = s.ds & 0xFFFF
    m = cpu.mem

    def dispatch_target(scene: int) -> int:
        m.ww(ds, 0x2356, scene & 0xFFFF)
        s.cs, s.ip = CS, ENTRY
        for _ in range(64):
            ip = s.ip & 0xFFFF
            if (s.cs & 0xFFFF) == CS and ip not in DISPATCH_IPS:
                return ip
            cpu.step()
        return -1

    fails = 0
    for scene, expect in PLANET_VIDEO_DISPATCH.items():
        got = dispatch_target(scene)
        ok = got == expect
        fails += not ok
        print(f"  planet {scene}: dispatch -> {got:04X}  expect {expect:04X}  {'ok' if ok else 'FAIL'}")

    # scenes 6/7 must be distinct special handlers (the table continues past the six planets)
    s6, s7 = dispatch_target(6), dispatch_target(7)
    special_ok = s6 not in PLANET_VIDEO_DISPATCH.values() and s7 not in PLANET_VIDEO_DISPATCH.values() and s6 != s7
    print(f"  scene 6 -> {s6:04X}, scene 7 -> {s7:04X}  (distinct special-scene handlers: {special_ok})")

    ok = not fails and special_ok
    print("RESULT:", "PASS -- PLANET_VIDEO_DISPATCH matches the original C565 dispatch"
          if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
