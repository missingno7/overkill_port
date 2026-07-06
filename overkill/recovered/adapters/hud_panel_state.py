"""Read the HUD-panel compose inputs from a live DGROUP/machine image (ADR-1: the image IS the
game state) and hand them to the pure :mod:`overkill.native_video.hud_panel` composer.

This is the ONE place the panel's state cells are named; both the byte-exact gate
(``verify_native_hud_panel``) and the standalone runtime (``scripts/play_native.py``) assemble
their compose through it, so the gate proves exactly what the product draws.
"""
from __future__ import annotations

import numpy as np

from overkill.native_video.hud_glyph import read_glyph_font
from overkill.native_video.hud_panel import compose_hud_panel_page

CS = 0x1010
DS = 0x25CC
#: the four 859E status-cell descriptors (SS:9682/968C/9696/96A0).
CHROME_DESCRIPTORS = (0x9682, 0x968C, 0x9696, 0x96A0)
DIR_OFF = 0x0BE4          # CS:0BE4 -- the PANEL cell-offset directory (256 words)
LABEL_OFF = 0x2318        # the 5EDB score-line label (NUL-terminated escape string)
MAX_LABEL = 96
STATUS_BLOCK_OFF = 0x235C  # the 60E3 escape block (NUL-terminated, sits just before 2362)
PLANET_DIGITS_OFF = 0x2362  # DS:2362[planet 2356] -> the panel's planet digit char


def read_hud_dir_table(image) -> "list[int]":
    """The CS:0BE4 PANEL cell-offset directory from the machine image."""
    return [image.rw(CS, (DIR_OFF + 2 * k) & 0xFFFF) for k in range(0x100)]


def read_hud_font(image) -> np.ndarray:
    """The DGROUP glyph font (DS:1816) as ``read_glyph_font`` returns it."""
    mem = np.frombuffer(bytes(image.data), dtype=np.uint8)
    return read_glyph_font(mem, DS)


def compose_hud_panel_from_image(image, *, panel_source: np.ndarray, dir_table,
                                 font: np.ndarray) -> np.ndarray:
    """Compose the full panel page from the image's LIVE state cells (see hud_panel's layer
    docs; the cell reads here mirror the VM routines' own operands)."""
    # 859E: marker [95FA], match via the 95FC marker->descriptor table, [BDAC]/[BE16] highlight.
    marker = image.rw(DS, 0x95FA)
    bdac = image.rw(DS, 0xBDAC)
    be16 = image.rw(DS, 0xBE16)
    cells = []
    for idx, bp in enumerate(CHROME_DESCRIPTORS):
        color0 = image.rw(DS, bp)
        di_base = image.rw(DS, (bp + 0x02) & 0xFFFF)
        src_idx = image.rw(DS, (bp + 0x04) & 0xFFFF)
        if marker == 0xFFFF:
            match = 0
        else:
            match = 1 if bp == image.rw(DS, ((marker << 1) + 0x95FC) & 0xFFFF) else 0
        color_idx = be16 if (bdac == 1 and idx == marker) else color0
        cells.append((di_base, src_idx, color_idx, match))
    counters = tuple(image.rw(DS, (0x2368 + 2 * k) & 0xFFFF) for k in range(6))
    a95a = image.rw(DS, 0xA95A)
    label = [image.rb(DS, (LABEL_OFF + i) & 0xFFFF) for i in range(MAX_LABEL)]
    score = [image.rb(DS, (0x2314 + i) & 0xFFFF) for i in range(4)]
    status_block = [image.rb(DS, (STATUS_BLOCK_OFF + i) & 0xFFFF)
                    for i in range(PLANET_DIGITS_OFF - STATUS_BLOCK_OFF)]
    planet_char = image.rb(DS, (PLANET_DIGITS_OFF + (image.rw(DS, 0x2356) & 0xFF)) & 0xFFFF)
    return compose_hud_panel_page(
        panel_source=panel_source, dir_table=dir_table, font=font,
        chrome_cells=cells, counters=counters, a95a=a95a,
        draw_trailing=a95a != image.rw(DS, 0x2374),
        lives=image.rw(DS, 0x2358), energy_a97a=image.rw(DS, 0xA97A),
        score_label_bytes=label, score_bytes=score,
        status_block_bytes=status_block, planet_char=planet_char,
        colour=image.rw(DS, 0x215C) & 0xFF, col=image.rw(DS, 0x215E) & 0xFF,
        row_base=image.rw(DS, 0x2160))
