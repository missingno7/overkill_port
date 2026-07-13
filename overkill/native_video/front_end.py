"""Native (VM-less) front-end scene rendering: decode the full-screen menu/title images.

The OVERKILL front-end screens (title/options ``OKMENU``, the difficulty ``CHOOSE``, the six planet
plaques ``PLAQ0..5``, ``HISCORE``, ``REDEF``, ``CALIB``, the win/level screens, ``THEND``) are stored
in the container as full-screen 320x200 4bpp images: a ``{rows, stride}`` 2-word header followed by
four bit-planes, ``stride`` (=40) bytes per plane per row.  They decode with the ALREADY-RECOVERED
pure codecs -- ``container.load_container_asset`` (``.ENC`` = LZ, ``.BIC`` = the 0283 dispatch) then
``planar.deplanarize_tandy`` -- so the whole title/menu can be drawn with **no VM and no ASM**, from
the game data alone.  This is the render half of the native front-end flow; the input/scene-flow half
lives in ``overkill.native_front_end`` (the recovered 558B menu-idle + level-select logic).

Proven: ``decode_fullscreen_image(container, "OKMENU.ENC")`` reproduces the title/options screen the VM
draws at cold boot, pixel-for-pixel (see ``tests/test_front_end_image.py`` + the byte-exact
``overkill/probes/verify_native_front_end_image.py``).
"""
from __future__ import annotations

import numpy as np

from overkill.asset_codecs.container import load_container_asset
from overkill.asset_codecs.planar import deplanarize_tandy
from overkill.native_video.level_select import cell_indices

SCREEN_WIDTH = 320
SCREEN_HEIGHT = 200
_BYTES_PER_ROW = SCREEN_WIDTH // 2   # 160: 2 pixels per byte (4bpp packed)

CS_SEGMENT = 0x1010
#: the shared cell DIRECTORY + BANK the 5A00/5A6C blit reads (same as the attract scene cells):
#: cell offset = CS:[0BE4 + id*2] in the CS:[95B4] bank.
CELL_DIRECTORY = 0x0BE4
CELL_BANK_SEG_CELL = 0x95B4

#: REDEFINE KEYS (1010:5732).  The BEC4 controls page IS ``REDEF.ENC`` (proven byte-exact: REDEF.ENC +
#: the prompt cell = the VM's redefine screen, diff 0/64000).  Each of the six slots blits a pre-drawn
#: "Press key for <action>" CELL (ids 0x50..0x55) via 553D's 5A00/5A6C -- NOT font text -- at column 1
#: (x = 1*8) and row ``[22CA]`` which starts 0x3F and steps +0x17 per slot, so the prompts STACK.
REDEFINE_PROMPT_CELL_IDS = (0x50, 0x51, 0x52, 0x53, 0x54, 0x55)   # Up/Down/Left/Right/Fire/Special
REDEFINE_PROMPT_ROW0 = 0x3F
REDEFINE_PROMPT_ROW_STEP = 0x17
REDEFINE_PROMPT_COL_PX = 1 * 8


def compose_redefine_screen(image, container_data, prompts_shown: int) -> np.ndarray:
    """The REDEFINE-KEYS screen as the original draws it: ``REDEF.ENC`` (the BEC4 controls page) with
    the first ``prompts_shown`` "Press key for <action>" prompt cells (0x50..) blit stacked, exactly as
    553D's 5A00/5A6C place them.  ``image`` is a live cold image (for the CS:[0BE4]/CS:[95B4] cell
    directory + bank).  Proven byte-exact vs the VM for the first prompt (tests/test_native_menu)."""
    out = decode_fullscreen_image(container_data, "REDEF.ENC").copy()
    bank_seg = image.rw(CS_SEGMENT, CELL_BANK_SEG_CELL)
    bank = np.frombuffer(bytes(image.data[bank_seg * 16: bank_seg * 16 + 0x10000]), dtype=np.uint8)
    for i in range(min(prompts_shown, len(REDEFINE_PROMPT_CELL_IDS))):
        cid = REDEFINE_PROMPT_CELL_IDS[i]
        cell = cell_indices(bank, image.rw(CS_SEGMENT, (CELL_DIRECTORY + cid * 2) & 0xFFFF))
        y = REDEFINE_PROMPT_ROW0 + i * REDEFINE_PROMPT_ROW_STEP
        x = REDEFINE_PROMPT_COL_PX
        h, w = cell.shape
        out[y:y + h, x:x + w] = cell[:max(0, SCREEN_HEIGHT - y), :max(0, SCREEN_WIDTH - x)]
    return out

# The container names of the front-end images (all the same {rows,stride}+4-plane form).
# FULL-SCREEN (320x200) menu screens: OKMENU (title/options, byte-exact vs the VM) plus HISCORE / LEVSCR
# (level-select) / WINSCR / CALIB / REDEF -- these deplanarize to exactly 160*200 = 32000 chunky bytes, so
# decode_fullscreen_image renders them directly (structure verified; per-screen byte-exactness vs the VM
# is a follow-up). The genuinely SMALLER, placed images (CHOOSE, PLAQ0..5, PANEL) deplanarize to sub-screen
# buffers with their own on-screen x/y placement -- a per-scene layout not recovered yet;
# decode_fullscreen_image fails loud on those rather than mangling a wrong-sized buffer.
TITLE_OPTIONS = "OKMENU.ENC"

#: The full-screen (320x200) front-end menu screens decode_fullscreen_image handles (OKMENU + 5 others).
FULLSCREEN_MENU_SCREENS = (
    "OKMENU.ENC", "HISCORE.ENC", "LEVSCR.ENC", "WINSCR.ENC", "CALIB.ENC", "REDEF.ENC",
)


def _chunky_to_indices(chunky: bytes, width: int, height: int) -> np.ndarray:
    """A block-mode ``deplanarize_tandy`` chunky buffer (2 px/byte) -> ``(height,width)`` 4-bit indices."""
    bpr = width // 2
    buf = np.frombuffer(bytes(chunky[: bpr * height]), dtype=np.uint8).reshape(height, bpr)
    out = np.empty((height, width), dtype=np.uint8)
    out[:, 0::2] = (buf >> 4) & 0x0F   # high nibble = left pixel
    out[:, 1::2] = buf & 0x0F
    return out


#: The menu SELECTION-HIGHLIGHT mechanism (measured against the live VM, 2026-07-13): the original
#: recolors the selected option's own white text pixels to orange -- index 15 -> 12 -- inside the
#: word's region.  Nothing else changes: the whole live-menu-vs-OKMENU delta is exactly this recolor
#: (276 px for the boot default keyboard+both, every one 15->12).  The regions below are the words'
#: OKMENU geometry (inclusive y0,y1,x0,x1 spans of their white text runs); the two boot-default
#: regions are VM-WITNESSED byte-exact (keyboard: 186 px, both: 90 px -- the cluster sums match the
#: witnessed diffs exactly), the rest are the same rows' word runs from the image itself.
MENU_TEXT_COLOR = 15
MENU_HIGHLIGHT_COLOR = 12
#: control-method regions by the 558B ``[0010]`` value (0=keyboard, 1=joystick, 2=amstrad).
MENU_CONTROL_HIGHLIGHT = {
    0: (65, 73, 77, 130),      # "eyboard"          -- VM-witnessed (186 px, all 15->12)
    1: (83, 91, 79, 127),      # "oystick"          -- OKMENU word geometry
    2: (65, 73, 170, 249),     # "mstrad joystick"  -- OKMENU word geometry
}
#: sound-mode regions by the 558B ``[22B5] & 3`` value (0=music, 1=fx, 2=both, 3=none).
MENU_SOUND_HIGHLIGHT = {
    0: (122, 128, 91, 111),    # "usic" (after the boxed M) -- OKMENU word geometry
    1: (122, 128, 129, 139),   # "fx"                       -- OKMENU word geometry
    2: (122, 128, 161, 182),   # "both"             -- VM-witnessed (90 px, all 15->12)
    3: (122, 128, 202, 224),   # "none"                     -- OKMENU word geometry
}


def apply_menu_selection_highlights(indices: np.ndarray, control: int, sound_mode: int) -> np.ndarray:
    """Recolor the CURRENT menu selections exactly as the original does: the selected control
    option's and sound option's white text (15) turns orange (12) inside the word's region.
    Returns a copy; ``indices`` is the decoded OKMENU screen."""
    out = indices.copy()
    for y0, y1, x0, x1 in (MENU_CONTROL_HIGHLIGHT[control], MENU_SOUND_HIGHLIGHT[sound_mode & 3]):
        region = out[y0:y1 + 1, x0:x1 + 1]
        region[region == MENU_TEXT_COLOR] = MENU_HIGHLIGHT_COLOR
    return out


def decode_fullscreen_image(container_data, name: str) -> np.ndarray:
    """Decode a FULL-SCREEN (320x200) front-end image to ``(200,320)`` 4-bit indices, VM-free.

    Uses only the recovered container decode + ``deplanarize_tandy``.  Raises if the asset is not a
    full 320x200 image (the smaller centred dialogs like ``CHOOSE``/``PLAQn`` need a per-scene
    placement the front-end flow has yet to recover -- fail loud rather than mangle a wrong-sized buffer).
    """
    chunky = deplanarize_tandy(load_container_asset(container_data, name), sprite_mode=False)
    expected = _BYTES_PER_ROW * SCREEN_HEIGHT
    if len(chunky) != expected:
        raise ValueError(
            f"{name} deplanarizes to {len(chunky)} bytes, not a full 320x200 screen ({expected}); "
            "it is a smaller placed dialog whose per-scene layout is not recovered yet")
    return _chunky_to_indices(chunky, SCREEN_WIDTH, SCREEN_HEIGHT)
