"""The native (VM-free) front-end title/options render (native_video.front_end).

The whole title/options screen decodes from one container asset (OKMENU.ENC) through the already-
recovered pure codecs -- no VM.  The synthetic-independent, real-file case pins the decode byte-exact
(a stable checksum) and its shape; the byte-exact-vs-VM proof is
``overkill.probes.verify_native_front_end_image``.
"""
from __future__ import annotations

import hashlib
import pathlib

import pytest

from overkill.native_video.front_end import (
    FULLSCREEN_MENU_SCREENS,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    TITLE_OPTIONS,
    decode_fullscreen_image,
)

OVERKILL = pathlib.Path(__file__).resolve().parent.parent / "assets" / "OVERKILL"

# sha256[:16] of the decoded (200,320) title-screen indices -- pins the whole render byte-exact so a
# codec regression can't silently change the picture.
_TITLE_SHA16 = "c706277b3f8fc9b0"
# HISCORE.ENC decoded indices -- PROVEN byte-exact vs the VM's cold-boot high-scores screen
# (diff 0/64000 against the frontend_intro snapshot's B800, 2026-07-13); pinned so the attract's
# high-scores beat can't regress.
_HISCORE_SHA16 = "023ad6d080eb5559"


@pytest.mark.skipif(not OVERKILL.is_file(), reason="assets/OVERKILL not present")
def test_title_options_decodes_to_a_full_320x200_screen():
    img = decode_fullscreen_image(OVERKILL.read_bytes(), TITLE_OPTIONS)
    assert img.shape == (SCREEN_HEIGHT, SCREEN_WIDTH)
    assert img.dtype.name == "uint8"
    assert int(img.max()) <= 15 and int(img.min()) >= 0     # 4-bit palette indices
    assert img.any()                                        # not a blank screen
    assert hashlib.sha256(img.tobytes()).hexdigest()[:16] == _TITLE_SHA16


@pytest.mark.skipif(not OVERKILL.is_file(), reason="assets/OVERKILL not present")
def test_hiscore_decodes_byte_exact_to_the_vm_high_scores_screen():
    """HISCORE.ENC is the cold-boot attract's high-scores beat; its native decode was diffed 0/64000
    against the VM's actual high-scores B800 (see run_status 2026-07-13).  Pin the render byte-exact."""
    img = decode_fullscreen_image(OVERKILL.read_bytes(), "HISCORE.ENC")
    assert img.shape == (SCREEN_HEIGHT, SCREEN_WIDTH)
    assert hashlib.sha256(img.tobytes()).hexdigest()[:16] == _HISCORE_SHA16


@pytest.mark.skipif(not OVERKILL.is_file(), reason="assets/OVERKILL not present")
def test_all_fullscreen_menu_screens_decode():
    # OKMENU + HISCORE / LEVSCR / WINSCR / CALIB / REDEF are all full 320x200 menu screens (they
    # deplanarize to exactly 160*200 bytes), so decode_fullscreen_image renders each directly.
    container = OVERKILL.read_bytes()
    assert TITLE_OPTIONS in FULLSCREEN_MENU_SCREENS
    for name in FULLSCREEN_MENU_SCREENS:
        img = decode_fullscreen_image(container, name)
        assert img.shape == (SCREEN_HEIGHT, SCREEN_WIDTH), name
        assert int(img.max()) <= 15 and int(img.min()) >= 0, name
        assert img.any(), name                              # not a blank screen


@pytest.mark.skipif(not OVERKILL.is_file(), reason="assets/OVERKILL not present")
def test_story_intro_and_ending_pages_decode():
    # The story pages named in the image's own DS:1323 table -- the five IPAGE intro pages and the ten
    # OPAGE ending pages -- are all full 320x200 screens, so decode_fullscreen_image renders each.
    # play_native's _run_intro plays IPAGE1..5; this pins that they decode to real, non-blank pages.
    container = OVERKILL.read_bytes()
    pages = [f"IPAGE{i}.ENC" for i in range(1, 6)] + [f"OPAGE{i}.ENC" for i in range(1, 11)]
    for name in pages:
        img = decode_fullscreen_image(container, name)
        assert img.shape == (SCREEN_HEIGHT, SCREEN_WIDTH), name
        assert int(img.max()) <= 15 and int(img.min()) >= 0, name
        assert img.any(), name                                  # not a blank screen


@pytest.mark.skipif(not OVERKILL.is_file(), reason="assets/OVERKILL not present")
def test_non_fullscreen_dialog_fails_loud():
    # CHOOSE.ENC deplanarizes to a smaller PLACED dialog (per-scene x/y placement not recovered yet):
    # decode_fullscreen_image must raise, not mangle a wrong-sized buffer.
    with pytest.raises(ValueError):
        decode_fullscreen_image(OVERKILL.read_bytes(), "CHOOSE.ENC")
