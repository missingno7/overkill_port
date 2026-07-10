"""Native full-HUD-panel composer -- the VM-free form of the OVERKILL right-third status panel.

Composes the WHOLE panel (pixel columns 216..319) into a packed Tandy B800 page from the
natively-decoded ``PANEL.ENC`` cell library, exactly as the original layers it:

1. **the backdrop** -- ONE panel cell (directory index ``0x25``) pasted at ``(cell-col 0x1B,
   row 0)``: ``1010:5C9A`` draws it through the ``5C46`` progressive-wipe blitter at level entry;
   the wipe's END state equals a plain :func:`hud_chrome.paste_panel_cell`;
2. **the 859E status-cell groups** (WEAPON/MISSILES/GADGETS/UPGRADES rows);
3. **the 61DC counter cells** (the ship-status circle + trailing markers);
4. **the 5EDB score line** (the ``2318`` label escapes + the eight BCD score digits);
5. **the 60E3 block** -- the ``235C`` escape string + ONE planet digit from ``DS:2362[planet]``,
   through the same ``518C``/``3153`` character path.

``panel_source`` must byte-equal the VM's decoded PANEL segment (``CS:[95B4]``); the native
decode ``deplanarize_tandy(load_container_asset(container, "PANEL.ENC"), sprite_mode=False,
emit_item_headers=True)`` is proven byte-exact against it (see run_status 2026-07-06).
``verify_native_hud_panel`` gates this composer byte-exact against the L1 cache frame-0 page.
"""
from __future__ import annotations

import numpy as np

from overkill.native_video.hud_chrome import (
    PAGE_SIZE,
    compose_status_cells_859e,
    compose_status_counters_61dc,
    paste_panel_cell,
    xy_to_di_5a00,
)
from overkill.native_video.hud_text import (
    compose_status_string_518c,
    compose_status_text_5edb,
    draw_glyph_char,
)
from overkill.native_video.page_raster import decode_tandy_b800_indices

#: the 5C9A backdrop: PANEL directory cell 0x25 at byte col 0x6C (pixel col 216).
BACKDROP_DIR_INDEX = 0x25
BACKDROP_BYTE_COL = 0x6C
#: the 5C46/375B curtain-wipe's FINAL row layout, ORACLE-PINNED by driving the ORIGINAL 5C9A on a
#: snapshot with a zeroed B800 and mapping every scanline back to its source cell row (see
#: run_status 2026-07-07): scanlines 0..4 and 194..199 stay BLACK; scanlines 5..100 carry cell
#: row ``y-1`` (the top half lands one row LOW); scanlines 101..193 carry cell row ``y``.  The
#: game never redraws most of the backdrop, so this end-state IS the visible panel; the dynamic
#: layers (859E/61DC/60F3/77F6/60E3/5EDB) overdraw their own regions at exact positions.
BACKDROP_TOP_BLACK_END = 5      # scanlines 0..4 black
BACKDROP_SHIFT_SPLIT = 101      # scanlines 5..100 -> cell row y-1; 101..193 -> cell row y
BACKDROP_BOTTOM_BLACK_START = 194

#: the 60F3 lives row: [2358] ship icons (dir cell 0x1E) then 3-[2358] empty caps (dir 0x1F),
#: from (cell-col 0x1F, scanline 0x50), each icon advancing di by 4 (two 613E +2 steps).
LIVES_ROW_DI = xy_to_di_5a00(0x1F, 0x50)
LIVES_SHIP_CELL = 0x1E
LIVES_EMPTY_CELL = 0x1F
LIVES_MAX = 3

#: the 77F6 energy bar: from (cell-col 0x1D, scanline 0x5F) growing UPWARD, ``[A97A] >> 1`` filled
#: units (words 0xFFCE @di, 0xC4EE @di+2), then the 789A tail zeroes ``0x2C - (A97A >> 1)`` more.
#: EACH UNIT SKIPS A SCANLINE: the ASM does the `sub di,0x2000` bank-step (with the `test di,0x6000`
#: / `add di,0x7F60` wrap) TWICE per unit, so the column paints every OTHER scanline and the gaps
#: between the bars are the untouched backdrop rows.  Drawing them contiguously -- as this composer
#: did -- produced a solid meter, which is what the owner saw.
ENERGY_BAR_X_CELL = 0x1D
ENERGY_BAR_Y = 0x5F
ENERGY_BAR_ROWS = 0x2C          # units, not scanlines: the column spans 2 * 0x2C = 88 scanlines
ENERGY_BAR_SCANLINE_STEP = 2
ENERGY_FILL_WORDS = (0xFFCE, 0xC4EE)
#: the panel's leftmost pixel column (byte col 0x6C * 2 px/byte).
PANEL_LEFT_PX = 216


def _row_base(y: int) -> int:
    return ((y & 3) * 0x2000 + (y >> 2) * 0xA0) & 0xFFFF


def paste_backdrop_5c9a(page: np.ndarray, panel_source: np.ndarray, cell_off: int) -> None:
    """Write the 5C9A backdrop's FINAL (post-wipe) state -- the oracle-pinned row layout above."""
    rows = int(panel_source[cell_off]) | (int(panel_source[cell_off + 1]) << 8)
    width = int(panel_source[cell_off + 2]) | (int(panel_source[cell_off + 3]) << 8)
    stride = (width << 2) & 0xFFFF
    pixels = cell_off + 4
    for y in range(200):
        base = (_row_base(y) + BACKDROP_BYTE_COL) & 0xFFFF
        if y < BACKDROP_TOP_BLACK_END or y >= BACKDROP_BOTTOM_BLACK_START:
            page[base: base + stride] = 0
            continue
        src_row = (y - 1) if y < BACKDROP_SHIFT_SPLIT else y
        if src_row >= rows:
            page[base: base + stride] = 0
            continue
        s = pixels + src_row * stride
        page[base: base + stride] = panel_source[s: s + stride]


def compose_lives_row_60f3(page: np.ndarray, panel_source: np.ndarray, dir_table,
                           lives: int) -> None:
    """The 60F3 lives row: ``lives`` ship cells then ``3 - lives`` empty cells, 8 bytes apart
    (613E's Tandy step is ``di += 4``, called twice per icon)."""
    di = LIVES_ROW_DI
    lives = max(0, min(LIVES_MAX, lives))
    for k in range(LIVES_MAX):
        cell = LIVES_SHIP_CELL if k < lives else LIVES_EMPTY_CELL
        paste_panel_cell(page, panel_source, dir_table[cell], (di + k * 8) & 0xFFFF)


def compose_energy_bar_77f6(page: np.ndarray, a97a: int) -> None:
    """The 77F6 energy column: ``a97a >> 1`` filled units growing UP from (0x1D, 0x5F), then the
    789A tail zeroes the remaining ``0x2C - (a97a >> 1)``.  Units are TWO scanlines apart -- the
    ASM steps ``di`` up a scanline twice per unit -- so the bar has gaps between its bars."""
    filled = (a97a & 0xFFFF) >> 1
    lo, hi = ENERGY_FILL_WORDS[0], ENERGY_FILL_WORDS[1]
    fill = np.array([lo & 0xFF, (lo >> 8) & 0xFF, hi & 0xFF, (hi >> 8) & 0xFF], dtype=np.uint8)
    for k in range(ENERGY_BAR_ROWS):
        y = ENERGY_BAR_Y - k * ENERGY_BAR_SCANLINE_STEP
        base = (_row_base(y) + ENERGY_BAR_X_CELL * 4) & 0xFFFF
        page[base: base + 4] = fill if k < filled else 0


def compose_hud_panel_page(*, panel_source: np.ndarray, dir_table, font: np.ndarray,
                           chrome_cells, counters, a95a: int, draw_trailing: bool,
                           lives: int, energy_a97a: int,
                           score_label_bytes, score_bytes,
                           status_block_bytes, planet_char: int,
                           colour: int, col: int, row_base: int) -> np.ndarray:
    """Compose the full panel into a fresh zeroed page and return it (see the module doc for
    the layer order).  ``chrome_cells``/``counters``/``a95a``/``draw_trailing`` are the resolved
    859E/61DC inputs; ``score_label_bytes``/``score_bytes`` the 5EDB line; ``status_block_bytes``
    the ``235C`` escape string and ``planet_char`` the ``2362[planet]`` byte; ``colour``/``col``/
    ``row_base`` the entry ``215C/215E/2160`` cursor state (the escapes override them)."""
    page = np.zeros(PAGE_SIZE, dtype=np.uint8)
    paste_backdrop_5c9a(page, panel_source, dir_table[BACKDROP_DIR_INDEX])
    compose_status_cells_859e(page, panel_source, dir_table, chrome_cells)
    compose_status_counters_61dc(page, panel_source, dir_table, counters,
                                 a95a=a95a, draw_trailing=draw_trailing)
    compose_lives_row_60f3(page, panel_source, dir_table, lives)
    compose_energy_bar_77f6(page, energy_a97a)
    cur = compose_status_text_5edb(page, font=font, label_bytes=score_label_bytes,
                                   score_bytes=score_bytes,
                                   colour=colour, col=col, row_base=row_base)
    # 60E3: the 235C escape block, then ONE planet digit through the same 519A/3153 path.
    cur = compose_status_string_518c(page, font=font, string_bytes=status_block_bytes,
                                     colour=cur["colour"], col=cur["col"],
                                     row_base=cur["row_base"])
    draw_glyph_char(page, font, planet_char & 0xFF, cur["col"], cur["row_base"], cur["colour"])
    return page


def panel_indices_from_page(page: np.ndarray) -> np.ndarray:
    """The panel's colour-index pixels ``(200, 320-216)`` decoded from the composed page."""
    return decode_tandy_b800_indices(page)[:, PANEL_LEFT_PX:]
