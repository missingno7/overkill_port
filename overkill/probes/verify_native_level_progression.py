"""Integration gate: cold-start plays EVERY level and advances through all six planets, VM-free.

The per-routine gates prove individual pieces byte-exact; this proves they compose into a whole
playable progression.  It cold-seeds level 0, plays 40 frames on each planet, checks the level's own
sprite bank (G{n}.BIC at CS:[95AE]) is loaded, then runs the 9734 level advance -- for all six
planets in the play order (1, 2, 3, 4, 5, 0).

It exists because a bug can hide in the SEAM between verified routines: the sprite-bank load, the
planet-5 A940 attract middle, and the level advance each pass their own gate, but only running the
progression end to end proves the cold seed + the frame + the loader actually carry a game through
all six levels.  (This test is what surfaced both the planet-5 A940 gap and confirmed its fix.)

The final planet (0, the mothership) stops at the ``9844`` story intro -- a declared front-end gap,
not a gameplay one -- so the gate asserts the five real levels advance cleanly and planet 0 reaches
exactly that gap.

Usage:
    python -m overkill.probes.verify_native_level_progression
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

DS = 0x25CC
CS = 0x1010
FRAMES_PER_LEVEL = 40


def main(argv) -> int:
    from overkill.asset_codecs.level_assets import decode_level_graphics
    from overkill.native_frame import _level_advance_9734, advance_gameplay_frame_97b2
    from overkill.recovered.adapters.cold_level_start import (
        LEVEL_INDEX_TO_PLANET, build_cold_level_start_image,
    )
    from overkill.recovered.domain.gaps import RecoveryGap
    from play_native import make_level_assets

    bundle = (ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin").read_bytes()
    container = (ROOT / "assets" / "OVERKILL").read_bytes()
    img = build_cold_level_start_image(bundle, 0, container)
    loader = make_level_assets(container, bundle)

    advanced: list[int] = []
    story_intro_planet: int | None = None
    for _ in range(len(LEVEL_INDEX_TO_PLANET)):
        planet = img.rw(DS, 0x2356)
        for f in range(FRAMES_PER_LEVEL):
            try:
                advance_gameplay_frame_97b2(img, isr_ticks=2, level_assets=loader, menu_pick=0)
            except RecoveryGap as exc:
                print(f"RESULT: FAIL -- planet {planet} play GAP at frame {f}: {exc}")
                return 1
        seg = img.rw(CS, 0x95AE)
        want = bytes(decode_level_graphics(container, planet))
        if bytes(img.data[seg * 16: seg * 16 + len(want)]) != want:
            print(f"RESULT: FAIL -- planet {planet} sprite bank is not G{planet}.BIC")
            return 1
        try:
            _level_advance_9734(img, loader)
        except RecoveryGap as exc:
            if "9844" in str(exc):
                story_intro_planet = planet
                print(f"  planet {planet}: 40 frames OK, sprite bank OK -> the 9844 story intro "
                      "(a declared front-end gap)")
                break
            print(f"RESULT: FAIL -- planet {planet} advance GAP: {exc}")
            return 1
        print(f"  planet {planet}: 40 frames OK, sprite bank OK -> planet {img.rw(DS, 0x2356)}")
        advanced.append(planet)

    ok = advanced == [1, 2, 3, 4, 5] and story_intro_planet == 0
    print(f"\nlevels advanced cleanly: {advanced}; planet 0 -> {'9844 story intro' if story_intro_planet == 0 else 'UNEXPECTED'}")
    print("RESULT:", "PASS -- the cold game plays and advances through all six planets (the "
          "mothership's 9844 story intro is the only remaining front-end gap)" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
