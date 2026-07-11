"""Native HIGH-SCORE TABLE read + index-space render (the 532D screen body).

The game keeps a table of 8 entries at ``DS:21D8`` (stride ``0x10``): a 12-byte name followed by a
4-byte little-endian score.  ``532D`` finds the new score's rank (5332: multi-byte compare of the
player's score against each entry, LSB ``[bx+12]`` first), inserts the entry, and draws the table
through the ``518C``/``5EE4`` glyph path -- the score printed MSB-first as eight BCD digits (as in
:func:`overkill.native_video.hud_text.compose_status_text_5edb`).

This module reads the table and renders it in index space (the ``(200,320)`` frame play_native
composes) with the recovered ``DS:1816`` glyph font, so play_native's game-over high-score screen shows
the real table with the player's new entry at its rank.
"""
from __future__ import annotations

import numpy as np

from overkill.native_video.hud_glyph import GLYPH_W, draw_glyph_string

TABLE_OFF = 0x21D8          # DS:21D8: the 8-entry high-score table
TABLE_COUNT = 8
ENTRY_STRIDE = 0x10
NAME_LEN = 12
SCORE_OFF = 12              # score bytes at entry+12..15 (little-endian)
SCORE_LEN = 4
PLAYER_SCORE_CELL = 0x2314  # DS:2314..2317: the player's score (little-endian)


def read_table(mem: np.ndarray, ds: int) -> "list[tuple[str, bytes]]":
    """Read the 8 (name, score_bytes) entries from ``DS:21D8``."""
    base = ds * 16 + TABLE_OFF
    out = []
    for i in range(TABLE_COUNT):
        e = base + i * ENTRY_STRIDE
        name = bytes(mem[e:e + NAME_LEN]).split(b"\0")[0].rstrip()
        score = bytes(mem[e + SCORE_OFF:e + SCORE_OFF + SCORE_LEN])
        out.append(("".join(chr(c) for c in name if 32 <= c < 127), score))
    return out


def score_digits(score_bytes: bytes) -> str:
    """The eight BCD digits ``5EDB`` prints: the score bytes most-significant-first, high nibble then
    low, each ``+0x30`` (here as ASCII)."""
    return "".join(f"{(b >> 4) & 0xF}{b & 0xF}" for b in reversed(score_bytes[:SCORE_LEN]))


def player_rank(table, player_score: bytes) -> int:
    """The rank (0..8) the player's score earns -- the first entry whose score it meets or beats
    (5332's compare, little-endian).  8 means it does not make the table."""
    pv = int.from_bytes(bytes(player_score[:SCORE_LEN]), "little")
    for i, (_name, s) in enumerate(table):
        if pv >= int.from_bytes(bytes(s[:SCORE_LEN]), "little"):
            return i
    return len(table)


def compose_table(frame: np.ndarray, font: np.ndarray, table, *, sy: int, sx: int, color: int,
                  row_h: int = 12, editing_rank: "int | None" = None, editing_name: str = "",
                  editing_score: "bytes | None" = None, caret: bool = False) -> np.ndarray:
    """Draw the high-score table onto a COPY of ``frame`` (index space).  If ``editing_rank`` is a
    valid rank, the player's row is inserted there (name being typed + caret) and the rest shift down,
    exactly as 532D inserts the new entry."""
    out = frame.copy()
    rows = list(table)
    if editing_rank is not None and 0 <= editing_rank < TABLE_COUNT:
        disp = f"{editing_name}{'_' if caret else ' '}"
        rows.insert(editing_rank, (disp, editing_score or b"\0\0\0\0"))
        rows = rows[:TABLE_COUNT]
    score_x = sx + (NAME_LEN + 2) * GLYPH_W
    for r, (name, score) in enumerate(rows):
        y = sy + r * row_h
        draw_glyph_string(out, y, sx, [ord(c) for c in name[:NAME_LEN + 1].ljust(1)], font, color)
        draw_glyph_string(out, y, score_x, [ord(c) for c in score_digits(score)], font, color)
    return out
