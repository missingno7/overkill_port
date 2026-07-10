"""THE END (1010:9844) native signal + resume -- the mothership-beaten arcade-loop transition.

When the mothership (planet 0) is beaten, 9734 sees ``DS:2356 == 0`` and shows THE END (WINSCR.ENC),
then falls into 9744 -- advancing ``[2356]`` 0 -> 1 and looping back to the first planet.  native_frame
is headless, so ``_level_advance_9734`` raises the recognized :class:`TheEndReached` carrying a
``resume()`` that runs the 9744 continuation.  These tests confirm the WIRING (the byte-exact demo
witness that THE END loads winscr.enc at this boundary is
``overkill.probes.verify_native_the_end_9844``); a normal (planet 1..5) completion must NOT raise.
"""
from __future__ import annotations

import pathlib

import pytest

from overkill.native_frame import TheEndReached, _level_advance_9734
from overkill.recovered.adapters.cold_level_start import build_cold_level_start_image

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"
CONTAINER = ROOT / "assets" / "OVERKILL"
DS = 0x25CC
_HAVE_ASSETS = BUNDLE.is_file() and CONTAINER.exists()


def _assets():
    from scripts.play_native import make_level_assets
    bundle = BUNDLE.read_bytes()
    return bundle, make_level_assets(CONTAINER.read_bytes(), bundle)


@pytest.mark.skipif(not _HAVE_ASSETS, reason="static bundle / OVERKILL container not present")
def test_mothership_beaten_raises_the_end_and_resumes_to_planet_1():
    bundle, level_assets = _assets()
    img = build_cold_level_start_image(bundle, 0, CONTAINER.read_bytes())  # level 0 -> planet 0
    img.ww(DS, 0x2356, 0)                                                  # THE END boundary

    with pytest.raises(TheEndReached) as ei:
        _level_advance_9734(img, level_assets)

    # the signal is a recovered transition, not a fail-loud gap
    from overkill.recovered.domain.gaps import RecoveryGap
    assert not isinstance(ei.value, RecoveryGap)

    ei.value.resume()                                                     # run the 9744 continuation
    assert img.rw(DS, 0x2356) == 1                                        # looped back to the first planet


@pytest.mark.skipif(not _HAVE_ASSETS, reason="static bundle / OVERKILL container not present")
def test_ordinary_completion_advances_without_the_end():
    bundle, level_assets = _assets()
    img = build_cold_level_start_image(bundle, 1, CONTAINER.read_bytes())  # level 1 -> planet 2
    planet = img.rw(DS, 0x2356)
    assert planet != 0                                                    # not the mothership
    _level_advance_9734(img, level_assets)                                # must NOT raise
    assert img.rw(DS, 0x2356) == (planet + 1) % 6
