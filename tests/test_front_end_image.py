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
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    TITLE_OPTIONS,
    decode_fullscreen_image,
)

OVERKILL = pathlib.Path(__file__).resolve().parent.parent / "assets" / "OVERKILL"

# sha256[:16] of the decoded (200,320) title-screen indices -- pins the whole render byte-exact so a
# codec regression can't silently change the picture.
_TITLE_SHA16 = "c706277b3f8fc9b0"


@pytest.mark.skipif(not OVERKILL.is_file(), reason="assets/OVERKILL not present")
def test_title_options_decodes_to_a_full_320x200_screen():
    img = decode_fullscreen_image(OVERKILL.read_bytes(), TITLE_OPTIONS)
    assert img.shape == (SCREEN_HEIGHT, SCREEN_WIDTH)
    assert img.dtype.name == "uint8"
    assert int(img.max()) <= 15 and int(img.min()) >= 0     # 4-bit palette indices
    assert img.any()                                        # not a blank screen
    assert hashlib.sha256(img.tobytes()).hexdigest()[:16] == _TITLE_SHA16


@pytest.mark.skipif(not OVERKILL.is_file(), reason="assets/OVERKILL not present")
def test_non_fullscreen_dialog_fails_loud():
    # CHOOSE.ENC deplanarizes to a smaller centred dialog (per-scene placement not recovered yet):
    # decode_fullscreen_image must raise, not mangle a wrong-sized buffer.
    with pytest.raises(ValueError):
        decode_fullscreen_image(OVERKILL.read_bytes(), "CHOOSE.ENC")
