"""Native Tandy B800-packed HUD/status text composer.

Where :mod:`overkill.native_video.hud_glyph` renders a glyph into the backend's ``(H, W)``
colour-index image, this module composes the *packed Tandy B800 page* exactly as the VM's
``1010:3153`` writes it -- so the native HUD line can be witnessed byte-exact against the
real B800 digit band (the brief's HUD gate) and, in the standalone runtime, written straight
into the native page.  It owns the index/page form of the OVERKILL HUD/status text line
``1010:5EDB`` (the label string at ``DS:2318`` followed by the four score bytes at
``DS:2314``, both through the ``518C/519A/3153`` character path lifted in
``overkill/rendering/text.py``).

No VM: it takes the already-read font plus the recovered score/cursor state and writes a
flat page buffer (the project's dual-mode rule -- the hybrid path reads live VM memory, the
native runtime reads the recovered static data image, same composer).

Geometry recovered from ``1010:3153`` (see ``overkill/rendering/text.py`` for the lifted
hooks this mirrors, and ``page_raster`` for the same four-bank present geometry):

* a glyph cell is 8 rows x 8 px; each row is two words (4 bytes) at the cursor byte ``di``,
  ``di`` advancing ``+0x2000`` per row and wrapping ``+0x80A0`` when it crosses ``0x8000``
  (the four interleaved Tandy banks);
* ``di = DS:215E + DS:2160``; the inline ``0x11`` cursor escape sets ``row*0x140 -> 2160``
  and ``col*4 -> 215E``, and each drawn glyph advances ``col`` by 4, wrapping at ``0xA0`` to
  ``col = 0`` / ``row += 0x140``;
* the pixel write is ``expand[glyph_byte] & colour_mask``, opaque (clear bits -> 0), the
  colour mask being ``DS:215C``'s nibble replicated to every nibble, and ``expand`` the
  generated bit->0xF-nibble spread the VM keeps as data at ``DS:1514``.
"""
from __future__ import annotations

import numpy as np

from overkill.native_video.hud_glyph import GLYPH_H, read_glyph_font  # noqa: F401  (re-export)

# 1010:3153 cursor / bank geometry.
BANK_ADVANCE = 0x2000          # di += 0x2000 per glyph row (next Tandy bank)
BANK_WRAP = 0x80A0             # di += 0x80A0 after it crosses 0x8000
GLYPH_ADVANCE = 0x04           # DS:215E += 4 per glyph (Tandy char stride; status mode 2)
CURSOR_X_WRAP = 0xA0           # col wraps at 0xA0 -> next text row
TEXT_ROW_STRIDE = 0x0140       # DS:2160 += 0x140 per text row (8 screen rows)
CTRL_SET_COLOUR = 0x10         # inline escape: 0x10 <colour>
CTRL_SET_CURSOR = 0x11         # inline escape: 0x11 <row> <col>
DIGIT_ASCII_BASE = 0x30        # nibble -> '0'.. ('1010:5F06' add 30h)
SCORE_BYTES = 4                # DS:2314..2317
PAGE_SIZE = 0x10000            # di is a 16-bit page offset


def expand_glyph_byte(b: int) -> tuple[int, int, int, int]:
    """The four packed B800 bytes for one 8-pixel glyph row -- the generated form of the
    VM's ``DS:1514[b*4]`` table: each set bit (MSB = leftmost) becomes a ``0xF`` nibble,
    each clear bit a ``0`` nibble, two pixels per byte (high nibble = left pixel)."""
    b &= 0xFF
    nib = [0xF if (b >> (7 - j)) & 1 else 0 for j in range(8)]
    return (
        (nib[0] << 4) | nib[1],
        (nib[2] << 4) | nib[3],
        (nib[4] << 4) | nib[5],
        (nib[6] << 4) | nib[7],
    )


def colour_mask_byte(colour: int) -> int:
    """The per-byte colour mask ``3153`` ANDs into every glyph byte: ``DS:215C``'s nibble
    replicated (``((c<<4)&0xFF)|c``).  ANDed with the ``0xF``-nibble expand it selects the
    colour in set pixels and ``0`` in clear ones."""
    colour &= 0xFF
    return (((colour << 4) & 0xFF) | colour) & 0xFF


def blit_glyph_b800(page: np.ndarray, di: int, glyph_rows, mask_byte: int) -> None:
    """Blit one 8-row glyph into the packed ``page`` at cursor byte ``di`` exactly as
    ``1010:3153`` does: opaque ``expand & colour`` writes, advancing through the four Tandy
    banks.  ``glyph_rows`` is the 8-byte glyph (row 0 top, bit ``0x80`` = leftmost).  The
    glyph-tail cursor *column* advance is the caller's (see :func:`advance_cursor`), exactly
    as ``3153`` splits the write loop from its trailing ``215E += 4``."""
    cur = di & 0xFFFF
    for r in range(GLYPH_H):
        eb = expand_glyph_byte(int(glyph_rows[r]))
        for k in range(4):
            page[(cur + k) & 0xFFFF] = eb[k] & mask_byte
        cur = (cur + BANK_ADVANCE) & 0xFFFF
        if cur & 0x8000:
            cur = (cur + BANK_WRAP) & 0xFFFF


def advance_cursor(col: int, row_base: int) -> tuple[int, int]:
    """Advance the glyph cursor one cell -- the ``3153`` glyph tail: ``DS:215E += 4``,
    wrapping at ``0xA0`` to the next text row (``DS:215E = 0``, ``DS:2160 += 0x140``)."""
    col = (col + GLYPH_ADVANCE) & 0xFF
    if col >= CURSOR_X_WRAP:
        col = 0
        row_base = (row_base + TEXT_ROW_STRIDE) & 0xFFFF
    return col, row_base


def draw_glyph_char(page: np.ndarray, font: np.ndarray, ch: int, col: int, row_base: int,
                    colour: int) -> tuple[int, int]:
    """Draw one character glyph at the cursor and advance it (the ``3153`` normal path).
    Returns the advanced ``(col, row_base)``."""
    di = (col + row_base) & 0xFFFF
    blit_glyph_b800(page, di, font[ch & 0xFF], colour_mask_byte(colour))
    return advance_cursor(col, row_base)


def compose_status_string_518c(page: np.ndarray, *, font: np.ndarray, string_bytes,
                               colour: int, col: int, row_base: int) -> dict:
    """Compose one ``1010:518C`` NUL-terminated string (with ``3153``'s inline ``0x10`` colour /
    ``0x11`` cursor escapes) into the packed ``page`` -- the label loop of
    :func:`compose_status_text_5edb`, exposed for the OTHER 518C callers (``60E3`` draws the
    ``DS:235C`` block + the planet digit through this exact loop).  Returns the final
    ``{'colour', 'col', 'row_base'}`` cursor state."""
    i = 0
    n = len(string_bytes)
    while i < n and (string_bytes[i] & 0xFF) != 0:
        b = string_bytes[i] & 0xFF
        if b == CTRL_SET_COLOUR:
            colour = string_bytes[i + 1] & 0xFF
            i += 2
        elif b == CTRL_SET_CURSOR:
            row = string_bytes[i + 1] & 0xFF
            col_char = string_bytes[i + 2] & 0xFF
            row_base = (row * TEXT_ROW_STRIDE) & 0xFFFF
            col = (col_char << 2) & 0xFF
            i += 3
        else:
            col, row_base = draw_glyph_char(page, font, b, col, row_base, colour)
            i += 1
    return {"colour": colour, "col": col, "row_base": row_base}


def compose_status_text_5edb(page: np.ndarray, *, font: np.ndarray, label_bytes,
                             score_bytes, colour: int, col: int, row_base: int) -> dict:
    """Compose the full ``1010:5EDB`` HUD/status line into the packed ``page`` (mutated).

    First the NUL-terminated ``label_bytes`` are drawn through the ``518C`` string loop with
    ``3153``'s inline control bytes (``0x10 <colour>`` sets the colour, ``0x11 <row> <col>``
    sets the cursor).  Then the four ``score_bytes`` (given in address order, ``DS:2314``
    first) are drawn most-significant-byte-first as eight BCD digits -- ``5EDB`` walks
    ``2317..2314`` and ``5EF9`` emits the high nibble then the low nibble, each ``+0x30``.

    ``colour`` (``DS:215C``), ``col`` (``DS:215E``), ``row_base`` (``DS:2160``) are the entry
    cursor/colour; the label escapes may override them.  Returns the final
    ``{'colour', 'col', 'row_base'}`` -- the VM's ``215C/215E/2160`` after the line.
    """
    # 518C NUL-terminated string loop over the label, honouring 3153's inline escapes.
    cur = compose_status_string_518c(page, font=font, string_bytes=label_bytes,
                                     colour=colour, col=col, row_base=row_base)
    colour, col, row_base = cur["colour"], cur["col"], cur["row_base"]

    # The four score bytes, most-significant first, each as two BCD digits (high then low).
    for byte in reversed([sb & 0xFF for sb in score_bytes[:SCORE_BYTES]]):
        for nib in ((byte >> 4) & 0x0F, byte & 0x0F):
            ch = (nib + DIGIT_ASCII_BASE) & 0xFF
            col, row_base = draw_glyph_char(page, font, ch, col, row_base, colour)

    return {"colour": colour, "col": col, "row_base": row_base}
