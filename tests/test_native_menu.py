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


def test_redefine_keys_cells_feed_the_input_decode():
    """558B 'r' REDEFINE KEYS writes DS:[2140-2145]; those are exactly the remappable slots of the
    eight-cell control map at DS:213E that 0162 packs, so a redefined key sets its action's bit."""
    from scripts.play_native import _REDEFINE_SLOTS
    from overkill.recovered.systems.input import (
        DEFAULT_CONTROL_MAP, pack_control_map_bits, key_state_from_pressed)
    base = 0x213E
    for _label, cell in _REDEFINE_SLOTS:
        idx = cell - base
        assert 2 <= idx <= 7                          # the six remappable slots (0/1 stay fixed)
        new_sc = 0x2D                                 # 'x' -- absent from the default map
        cmap = list(DEFAULT_CONTROL_MAP)
        cmap[idx] = new_sc
        bit = pack_control_map_bits(cmap, key_state_from_pressed({new_sc}))
        assert bit == (1 << (7 - idx))                # MSB-first: the redefined key sets its own bit


@pytest.mark.skipif(not _HAVE, reason="bundle / container not present")
def test_joystick_mode_fail_louds_so_the_menu_declines_j():
    img, level_assets = _cold(0, 1)                  # [0010] == 1 -> 0162's unsupported joystick mode
    with pytest.raises(RecoveryGap):
        advance_gameplay_frame_97b2(img, isr_ticks=2, level_assets=level_assets, menu_pick=0)
