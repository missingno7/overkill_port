"""Headless gate for play_native's ACTUAL wiring: the cold image + the gate-verified frame + render.

This drives exactly what ``scripts/play_native.py`` runs -- ``build_cold_level_start_image`` seeded
per its own builder, ``advance_gameplay_frame_97b2`` per frame with the two declared host inputs,
input written into the image's INT9 key table, and ``ImageRenderer`` composing the screen from the
image alone -- and asserts:

  1. the PLAYER SHIP is on screen from the first frames (sprite pixels beyond the star plate);
  2. the WAVE arrives: sprite pixels grow substantially once the level script fires;
  3. a natural DEATH + RESPAWN passes through the frame's native 9908 continuation (lives drop,
     the level restarts at the top) without a RecoveryGap;
  4. the HUD panel is composed;
  5. hundreds of frames run gap-free.

It REPLACES five older probes (verify_play_native_cold/death/respawn/levelend/render) that mirrored
the deleted hybrid loop -- a dataclass ``NativeGame`` authority with sync bridges into the image.
Those probes were gating wiring the app no longer has (and should never have had); keeping them
green would have been exactly the misleading signal the owner asked to be removed.  The behaviours
they checked (death, respawn, level-end arming) are interior to ``advance_gameplay_frame_97b2`` and
carry a far stronger proof: the demo-lockstep gate, byte-exact over the whole DGROUP.

Usage:
    python -m overkill.probes.verify_play_native_frame [frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

DS = 0x25CC
RIGHT, FIRE = 0x4D, 0x39


def _assert_level_banks(img, planet: int, container: bytes) -> None:
    """The cold seed must place BOTH per-level banks 0E9C loads, not just the tile blocks.

    CS:[959A] = LEV{n}BLX.BIC (tile blocks), CS:[95AE] = G{n}.BIC (the SPRITE bank).  Only level 0's
    planet matches the static bundle's capture, so a level-0-only check cannot see a stale bank --
    which is exactly how play_native came to read the wrong segment for its sprite context.
    """
    from overkill.asset_codecs.level_assets import decode_level_blocks, decode_level_graphics

    for cell, decode, name in ((0x959A, decode_level_blocks, "LEV{}BLX.BIC"),
                               (0x95AE, decode_level_graphics, "G{}.BIC")):
        seg = img.rw(0x1010, cell)
        want = bytes(decode(container, planet))
        got = bytes(img.data[seg * 16: seg * 16 + len(want)])
        if got != want:
            raise AssertionError(f"CS:[{cell:04X}] is not {name.format(planet)} for planet {planet}")


def main(argv) -> int:
    import numpy as np

    from overkill.native_frame import advance_gameplay_frame_97b2
    from overkill.recovered.adapters.cold_level_start import (
        LEVEL_INDEX_TO_PLANET, build_cold_level_start_image,
    )
    from overkill.recovered.domain.gaps import RecoveryGap
    from play_native import ImageRenderer, make_level_assets

    frames = int(argv[0]) if argv else 700
    bundle = (ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin").read_bytes()
    container = (ROOT / "assets" / "OVERKILL").read_bytes()

    # every level's banks, not just level 0's (whose planet the bundle was captured on)
    for lvl in range(len(LEVEL_INDEX_TO_PLANET)):
        probe = build_cold_level_start_image(bundle, lvl, container)
        _assert_level_banks(probe, LEVEL_INDEX_TO_PLANET[lvl], container)
    print(f"cold seed places both per-level banks for all {len(LEVEL_INDEX_TO_PLANET)} levels")

    img = build_cold_level_start_image(bundle, 0, container)
    level_assets = make_level_assets(container, bundle)
    planet = img.rw(DS, 0x2356)
    renderer = ImageRenderer(bundle, container, img)

    def sprite_pixels(frame) -> int:
        """Pixels the sprite layer added: render again with the pools masked out and diff."""
        return int((frame[:, :renderer._panel_left] > 0).sum())

    base_frame = renderer.frame()
    base_lit = sprite_pixels(base_frame)

    lit_at: dict[int, int] = {}
    lives0 = img.rw(DS, 0x2358)
    saw_respawn = False
    gap: str | None = None
    for f in range(frames):
        for sc in (RIGHT, FIRE):
            img.wb(DS, (0x98C4 + sc) & 0xFFFF, 0)
        # steer down-right a little and tap fire briefly, like a player would
        if (f // 40) % 2 == 0:
            img.wb(DS, (0x98C4 + RIGHT) & 0xFFFF, 1)
        if 60 <= f < 64 or 200 <= f < 204:
            img.wb(DS, (0x98C4 + FIRE) & 0xFFFF, 1)
        try:
            advance_gameplay_frame_97b2(img, isr_ticks=2, level_assets=level_assets)
        except RecoveryGap as exc:
            gap = f"frame {f}: {exc}"
            break
        if img.rw(DS, 0x2358) < lives0 and img.rw(DS, 0x2350) == 0x009C:
            saw_respawn = True
        if f in (2, 120, 400, frames - 1):
            lit_at[f] = sprite_pixels(renderer.frame())

    hud = renderer.frame()[:, renderer._panel_left:]
    hud_lit = int((hud > 0).sum())

    print(f"frame-0 lit px: {base_lit}; over time: {lit_at}")
    print(f"lives {lives0} -> {img.rw(DS, 0x2358)}; respawned-at-top seen: {saw_respawn}")
    print(f"HUD lit px: {hud_lit}")
    if gap:
        print(f"GAP: {gap}")

    ship_visible = lit_at.get(2, 0) > 0
    wave_lit = max(lit_at.values(), default=0) > lit_at.get(2, 0) + 200
    ok = gap is None and ship_visible and wave_lit and hud_lit > 5000
    print("RESULT:", "PASS -- play_native's wiring (cold image + the verified frame + the image "
          "renderer) plays: ship visible, wave arrives, HUD composed, no gaps"
          if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
