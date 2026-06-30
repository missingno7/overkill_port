"""Pure records for the OVERKILL parallax starfield (the background star layer).

The starfield is 40 stars over three parallax layers.  Each star is a ``{row, dx, color}`` triple
(the in-memory stream at ``DS:0xC6C1``); its page offset is ``row*0x68 + cursor + dx`` and it scrolls
down one scanline per layer tick, wrapping at the playfield height.  See
:mod:`overkill.recovered.systems.starfield` for the recovered logic and the address provenance.
"""
from __future__ import annotations

from dataclasses import dataclass

STAR_COUNT = 40
PLAYFIELD_ROWS = 0xC0          # 192; a star's row wraps to 0 here (1F8F:0962 cmp [si],0xC0)
PAGE_ROW_STRIDE = 0x68         # base[row] = row * 0x68 (DS:0x9A08 table; 0x68-byte page row = 208 px)

# The three parallax layers as [lo, hi) star-index bands (1F8F:0922 cx = 0x14 / 0xA / 0xA).
LAYER_BOUNDS = ((0, 20), (20, 30), (30, 40))


@dataclass(frozen=True)
class Star:
    """One star: ``row`` (0..191, scanline), ``dx`` (page byte offset within the row), ``color`` byte."""

    row: int
    dx: int
    color: int


@dataclass(frozen=True)
class StarfieldState:
    """The whole starfield: 40 stars + the three nested layer counters + the enable gate.

    ``layer_counters`` are the ``DS:0xC812/0xC814/0xC816`` toggles; ``enabled`` mirrors the
    ``DS:0xA95A != 0xFFFF`` gate (1F8F:0922) that suppresses movement when the field is inactive.
    """

    stars: tuple[Star, ...]
    layer_counters: tuple[int, int, int] = (0, 0, 0)
    enabled: bool = True
