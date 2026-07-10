"""Witness + native-signal gate for THE END (1010:9844), the mothership-beaten splash.

When the mothership (planet 0) is beaten, the original's 9734 level-complete sees ``DS:2356 == 0`` and
calls 9844: a presentation-only splash that loads and shows the full-screen ``WINSCR.ENC`` win image
(name @ ``DS:1440``, len ``0x7D04``), waits for FIRE, then falls into 9744 -- advancing ``[2356]`` 0 -> 1
and looping back to the first planet (an arcade loop; there is no credits-and-stop).

This screen is NOT lockstep-gateable end-to-end: every recording ends at the splash's fire-wait spin
(the player never presses fire on tape), so no demo returns through it to the level-1 load.  What IS
provable, and what this gate proves:

  PART A (demo WITNESS -- the transition + its asset are real):
      over ``demo_play_tandy_L6_mothership_end`` the pure ref VM reaches ``1010:9734`` with
      ``DS:2356 == 0`` and enters ``9844``, which loads the level-file whose name @ ``DS:1440`` is
      ``winscr.enc`` with length ``0x7D04`` -- i.e. THE END shows the real WINSCR image, not a guess.

  PART B (native SIGNAL + resume -- the recovered continuation):
      ``native_frame._level_advance_9734`` over an image with ``[2356] == 0`` raises the recognized
      :class:`TheEndReached` (NOT a RecoveryGap), and its ``resume()`` runs the 9744 path: ``[2356]``
      becomes 1 (looped to the first planet) and that planet's level data is loaded into the image.

Usage:
    python -m overkill.probes.verify_native_the_end_9844 [demo] [max_frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from overkill.probes._harness import load_demo, run_ref_step_probe  # noqa: E402
from overkill.native_frame import TheEndReached, _level_advance_9734  # noqa: E402
from overkill.recovered.adapters.cold_level_start import build_cold_level_start_image  # noqa: E402

CS = 0x1010
DS = 0x25CC
DEFAULT_DEMO = "demo_play_tandy_L6_mothership_end_20260618_230745"
DEFAULT_BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"
DEFAULT_CONTAINER = ROOT / "assets" / "OVERKILL"
EXPECTED_ASSET = "winscr.enc"
EXPECTED_LEN = 0x7D04


def _witness_the_end(demo, max_frames) -> "dict | None":
    """PART A: replay the demo; capture the THE END boundary + the loaded asset name/len."""
    st = {"boundary": False, "name": None, "len": None}

    def on_step(cpu):
        s = cpu.s
        if (s.cs & 0xFFFF) != CS:
            return
        ip = s.ip & 0xFFFF
        if ip == 0x9734 and cpu.mem.rw(DS, 0x2356) == 0:
            st["boundary"] = True
        elif ip == 0x984F and st["name"] is None:      # after 9844's far text render; loader done
            raw = bytes(cpu.mem.data[DS * 16 + 0x1440:DS * 16 + 0x1460])
            st["name"] = "".join(chr(c) for c in raw.split(b"\0")[0]).lower()
            st["len"] = cpu.mem.rw(DS, 0x21A8)

    run_ref_step_probe(demo, max_frames, on_step,
                       trap=frozenset({(CS, 0x9734), (CS, 0x984F)}))
    return st


def main(argv) -> int:
    demo = load_demo(argv[0] if argv else None, DEFAULT_DEMO)
    max_frames = int(argv[1]) if len(argv) > 1 else 700

    # --- PART A: the demo witness -------------------------------------------------------------
    w = _witness_the_end(demo, max_frames)
    a_ok = (w["boundary"] and w["name"] == EXPECTED_ASSET and w["len"] == EXPECTED_LEN)
    print(f"PART A witness: 9734[2356==0]={w['boundary']}  asset={w['name']!r} "
          f"len={w['len']:#06x} (expect {EXPECTED_ASSET!r} {EXPECTED_LEN:#06x})")

    # --- PART B: the native THE-END signal + resume -------------------------------------------
    from scripts.play_native import make_level_assets            # local: pulls pygame-free helpers only
    bundle = DEFAULT_BUNDLE.read_bytes()
    container = DEFAULT_CONTAINER.read_bytes()
    level_assets = make_level_assets(container, bundle)
    img = build_cold_level_start_image(bundle, 0, container)     # level 0 -> planet 0 (the mothership)
    img.ww(DS, 0x2356, 0)                                        # ensure THE END boundary
    raised = None
    try:
        _level_advance_9734(img, level_assets)
    except TheEndReached as end:
        raised = end
    signal_ok = raised is not None
    resumed_planet = None
    if signal_ok:
        raised.resume()                                         # run the 9744 continuation
        resumed_planet = img.rw(DS, 0x2356)
    b_ok = signal_ok and resumed_planet == 1                    # 9744: 0 -> 1 (loop to first planet)
    print(f"PART B native: raised TheEndReached={signal_ok}  resumed [2356]={resumed_planet} (expect 1)")

    ok = a_ok and b_ok
    print("RESULT:", "PASS -- THE END (9844) witnessed loading winscr.enc at the mothership-beaten "
          "boundary; native raises TheEndReached and resumes the arcade loop to planet 1"
          if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
