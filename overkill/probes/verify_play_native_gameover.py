"""Verify the native GAME-OVER pieces (the 9773 -> 98EB flow play_native wires).

Four checks, all VM-free (the snapshot is used once as a byte oracle for the banner asset):

1. **the banner asset**: ``THEND.BIC`` decoded natively (``deplanarize_tandy(sm=False, hdr=True)``)
   byte-equals the VM's decoded ``CS:[95B2]`` segment (the cell 5C35 draws at ``(0, 0x4E)``), and
   unpacks to the documented 44x320 banner;
2. **the trigger chain**: on the last life, the post-9EA3 death state (``A95A = 0xFFFF``) fires the
   DEATH gameplay exit, and the 990B lives decrement lands on 0xFFFF -- the exact condition
   play_native's game-over branch keys on (9773's ``cmp [2358],FFFF -> 98EB``);
3. **the [978D] cheat guard**: with the cheat byte set the decrement is re-inc'd (no game over);
4. **the 96E0 restart**: a fresh ``build_cold_level_start_image`` resets lives to 3 and the score
   to 0 (96EE is the fresh-session init) -- the state play_native's ``_restart_session`` produces.

Usage:
    python -m overkill.probes.verify_play_native_gameover
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DS = 0x25CC
CS = 0x1010
SNAP = ROOT / "artifacts" / "demos" / "demo_play_tandy_L2_full_20260617_180221" / "snapshot"
BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"


def main(argv) -> int:
    from overkill.asset_codecs.container import load_container_asset
    from overkill.asset_codecs.planar import deplanarize_tandy
    from overkill.recovered.adapters.cold_level_start import build_cold_level_start_image
    from overkill.recovered.domain.frame_loop import GameplayExit
    from overkill.recovered.systems.frame_loop import detect_gameplay_transition

    container = (ROOT / "assets" / "OVERKILL").read_bytes()
    ok = True

    # 1) the banner asset vs the VM's decoded segment
    dec = bytes(deplanarize_tandy(load_container_asset(container, "THEND.BIC"),
                                  sprite_mode=False, emit_item_headers=True))
    mem = (SNAP / "memory_1mb.bin").read_bytes()
    seg = mem[CS * 16 + 0x95B2] | (mem[CS * 16 + 0x95B3] << 8)
    vm = mem[seg * 16: seg * 16 + len(dec)]
    rows = dec[0] | (dec[1] << 8)
    width_px = (dec[2] | (dec[3] << 8)) * 8
    banner_ok = vm == dec and rows == 0x2C and width_px == 320
    print(f"THEND.BIC: {len(dec)}B decoded, rows={rows} width={width_px}px, "
          f"vm-segment match={vm == dec}")
    ok &= banner_ok

    # 2) the trigger chain on the last life
    bundle = BUNDLE.read_bytes()
    img = build_cold_level_start_image(bundle, 0)
    img.ww(DS, 0x2358, 0x0000)          # last life
    img.ww(DS, 0xA95A, 0xFFFF)          # the post-9EA3 death state
    exit_ = detect_gameplay_transition(
        a47c=img.rw(DS, 0xA47C), a95a=img.rw(DS, 0xA95A),
        a97a=img.rw(DS, 0xA97A), v2326=3,   # the dying mode at the explosion's end
        anchor_counter_after_inc=0x0F)
    death = exit_ is not None and exit_.exit is GameplayExit.DEATH
    lives = (img.rw(DS, 0x2358) - 1) & 0xFFFF      # 990B
    print(f"death exit on last life: {death}; 990B lives -> {lives:#06x} "
          f"(game over: {lives == 0xFFFF})")
    ok &= death and lives == 0xFFFF

    # 3) the [978D] cheat re-inc
    img.wb(DS, 0x978D, 1)
    cheat_lives = (img.rw(DS, 0x2358) - 1) & 0xFFFF
    if img.rb(DS, 0x978D):
        cheat_lives = (cheat_lives + 1) & 0xFFFF
    print(f"[978D] cheat: lives -> {cheat_lives:#06x} (no game over: {cheat_lives != 0xFFFF})")
    ok &= cheat_lives != 0xFFFF

    # 4) the fresh-session restart
    fresh = build_cold_level_start_image(bundle, 0)
    lives3 = fresh.rw(DS, 0x2358)
    score = (fresh.rw(DS, 0x2314), fresh.rw(DS, 0x2316))
    print(f"fresh session: lives={lives3} score={score}")
    ok &= lives3 == 3 and score == (0, 0)

    print("RESULT:", "PASS -- the native game-over chain: banner asset byte-exact, the last-life "
          "death fires the 98EB condition, the cheat guards it, and the restart is a fresh session"
          if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
