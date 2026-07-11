"""The cold-start MENU selections (1010:558B) applied onto the game image are safe + faithful.

play_native's `_run_title_menu` recovers 558B's option dispatch: M cycles the sound mode ([22B5]
0..3), K/A pick the control method ([0010] = 0 keyboard / 2 amstrad), FIRE starts.  These tests
confirm the cells the menu writes are the ones 0162's input decode reads, that the supported choices
(0 and 2) play, and that the JOYSTICK mode (1) fail-louds -- which is exactly why the menu declines J.
"""
from __future__ import annotations

import pathlib

import pytest

from overkill.native_frame import advance_gameplay_frame_97b2
from overkill.recovered.adapters.cold_level_start import build_cold_level_start_image
from overkill.recovered.domain.gaps import RecoveryGap

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"
CONTAINER = ROOT / "assets" / "OVERKILL"
DS = 0x25CC
SOUND_MODE_CELL, CONTROL_CELL = 0x22B5, 0x0010
_HAVE = BUNDLE.is_file() and CONTAINER.exists()


def _cold(sound_mode, control):
    bundle = BUNDLE.read_bytes()
    img = build_cold_level_start_image(bundle, 0, CONTAINER.read_bytes())
    img.ww(DS, SOUND_MODE_CELL, sound_mode)
    img.ww(DS, CONTROL_CELL, control)
    from scripts.play_native import make_level_assets
    return img, make_level_assets(CONTAINER.read_bytes(), bundle)


def test_menu_constants_match_play_native():
    from scripts.play_native import _MENU_CONTROL_CELL, _MENU_SOUND_MODE_CELL
    assert (_MENU_SOUND_MODE_CELL, _MENU_CONTROL_CELL) == (SOUND_MODE_CELL, CONTROL_CELL)


@pytest.mark.skipif(not _HAVE, reason="bundle / container not present")
@pytest.mark.parametrize("sound_mode", [0, 1, 2, 3])
@pytest.mark.parametrize("control", [0, 2])          # keyboard (213E) and amstrad (2146) maps
def test_supported_menu_choices_play(sound_mode, control):
    img, level_assets = _cold(sound_mode, control)
    for _ in range(30):
        advance_gameplay_frame_97b2(img, isr_ticks=2, level_assets=level_assets, menu_pick=0)
    assert img.rw(DS, SOUND_MODE_CELL) == sound_mode


@pytest.mark.skipif(not _HAVE, reason="bundle / container not present")
def test_joystick_mode_fail_louds_so_the_menu_declines_j():
    img, level_assets = _cold(0, 1)                  # [0010] == 1 -> 0162's unsupported joystick mode
    with pytest.raises(RecoveryGap):
        advance_gameplay_frame_97b2(img, isr_ticks=2, level_assets=level_assets, menu_pick=0)
