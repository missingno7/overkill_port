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


# ---- the menu SELECTION HIGHLIGHTS (the 15->12 recolor, VM-measured 2026-07-13) ----

@pytest.mark.skipif(not _HAVE, reason="bundle / container not present")
def test_menu_highlight_boot_default_matches_the_vm_witness():
    """The boot-default compose (keyboard + both) must recolor EXACTLY the VM-witnessed delta:
    276 px total (186 in the Keyboard word, 90 in the both word), every one 15 -> 12 -- the whole
    measured live-menu-vs-OKMENU difference."""
    import numpy as np
    from overkill.native_video.front_end import (
        MENU_HIGHLIGHT_COLOR, MENU_TEXT_COLOR, apply_menu_selection_highlights,
        decode_fullscreen_image)
    ok = decode_fullscreen_image(CONTAINER.read_bytes(), "OKMENU.ENC")
    out = apply_menu_selection_highlights(ok, control=0, sound_mode=2)
    d = out != ok
    assert int(d.sum()) == 276
    ys, xs = np.where(d)
    assert all(ok[y, x] == MENU_TEXT_COLOR and out[y, x] == MENU_HIGHLIGHT_COLOR
               for y, x in zip(ys, xs))
    in_kbd = (ys >= 65) & (ys <= 73) & (xs >= 77) & (xs <= 130)
    in_both = (ys >= 122) & (ys <= 128) & (xs >= 161) & (xs <= 182)
    assert int(in_kbd.sum()) == 186 and int(in_both.sum()) == 90
    assert int((in_kbd | in_both).sum()) == 276          # nothing outside the two witnessed bands


@pytest.mark.skipif(not _HAVE, reason="bundle / container not present")
def test_menu_highlight_states_recolor_only_their_own_word():
    """Every control/sound state recolors only white pixels inside its own word region (the counts
    are the words' OKMENU text geometry, locked as regressions; keyboard/both are the VM witness)."""
    from overkill.native_video.front_end import (
        MENU_CONTROL_HIGHLIGHT, MENU_SOUND_HIGHLIGHT, apply_menu_selection_highlights,
        decode_fullscreen_image)
    ok = decode_fullscreen_image(CONTAINER.read_bytes(), "OKMENU.ENC")
    control_px = {0: 186, 1: 71, 2: 276}                 # keyboard / joystick / amstrad words
    sound_px = {0: 69, 1: 36, 2: 90, 3: 85}              # music / fx / both / none words
    for control, cn in control_px.items():
        for sound, sn in sound_px.items():
            out = apply_menu_selection_highlights(ok, control=control, sound_mode=sound)
            d = out != ok
            assert int(d.sum()) == cn + sn, (control, sound)
            y0, y1, x0, x1 = MENU_CONTROL_HIGHLIGHT[control]
            assert int(d[y0:y1 + 1, x0:x1 + 1].sum()) == cn
            y0, y1, x0, x1 = MENU_SOUND_HIGHLIGHT[sound]
            assert int(d[y0:y1 + 1, x0:x1 + 1].sum()) == sn


# ---- the REDEFINE-KEYS screen (the real cell render, byte-exact vs the VM 2026-07-13) ----

@pytest.mark.skipif(not _HAVE, reason="bundle / container not present")
def test_redefine_screen_is_the_real_cell_render_not_a_font_overlay():
    """The redefine screen is REDEF.ENC + the "Press key for <action>" prompt CELLS (0x50..0x55) blit
    stacked by 553D's 5A00/5A6C -- proven byte-exact vs the VM (REDEF.ENC + cell 0x50 = the VM's screen,
    diff 0/64000).  Locks the structural facts + the first-prompt render sha."""
    import hashlib
    import numpy as np
    from overkill.recovered.adapters.cold_level_start import build_cold_level_start_image
    from overkill.native_video.front_end import compose_redefine_screen, decode_fullscreen_image

    bundle = BUNDLE.read_bytes()
    container = CONTAINER.read_bytes()
    img = build_cold_level_start_image(bundle, 0, container)
    redef = decode_fullscreen_image(container, "REDEF.ENC")

    assert np.array_equal(compose_redefine_screen(img, container, 0), redef)   # no prompts = the page
    one = compose_redefine_screen(img, container, 1)
    # the first prompt adds exactly cell 0x50 (735 px) -- the measured VM-vs-REDEF delta
    assert int((one != redef).sum()) == 735
    assert hashlib.sha256(one.tobytes()).hexdigest()[:16] == "994f21ca2ad27a7a"
    # the six prompts stack (sum of the six cells' pixel counts), none overwriting the page elsewhere
    assert int((compose_redefine_screen(img, container, 6) != redef).sum()) == 4302
