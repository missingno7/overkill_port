"""Pure recovered OVERKILL starfield -- the parallax background star layer, VM-free.

Recovered from the original routines (verified produced-vs-VM byte-exact; see
``overkill/probes/verify_native_starfield.py``):

* **move** ``1F8F:0922`` (+ ``1F8F:0960``): three parallax layers gated by nested toggle counters
  (``DS:0xC812/0xC814/0xC816``) -- layer A (stars 0..19) ticks every 2 frames, B (20..29) every 4,
  C (30..39) every 8; each tick does ``row = (row + 1) % 192`` (``inc [si]; cmp [si],0xC0; je ->0``).
  Gated off when ``DS:0xA95A == 0xFFFF``.
* **plot** ``1010:4D15`` (set up by ``4CED``): page offset ``= DS:[0x9A08+row*2] (= row*0x68) +
  DS:[0x234C] (cursor) + dx``; the pixel is written only if the page byte there is 0 (skip occupied),
  and the written offset is recorded into the working list ``DS:0xC7B1`` for next frame's erase.
* **erase** ``1010:4D64``: zero each offset in the working list (Tandy: a single page byte each).

The page is the linear source page (``0x68``-byte rows); the present blit (``1010:3354``) does the Tandy
bank interleave, so a star is a single page byte here.  These functions own only the gameplay-shaped
arithmetic; a bridge supplies the page bytes (read/write) and the cursor.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from overkill.recovered.domain.starfield import (
    LAYER_BOUNDS,
    PAGE_ROW_STRIDE,
    PLAYFIELD_ROWS,
    Star,
    StarfieldState,
)


def _advance_band(stars: list[Star], lo: int, hi: int) -> None:
    """In place: ``row = (row + 1) % 192`` for stars [lo, hi) (1F8F:0960)."""
    for k in range(lo, hi):
        r = (stars[k].row + 1) & 0xFFFF
        stars[k] = replace(stars[k], row=0 if r == PLAYFIELD_ROWS else r)


def advance_starfield(state: StarfieldState) -> StarfieldState:
    """Advance one frame: the nested-counter parallax move (1F8F:0922).

    Layer A ticks when its toggle returns to 0 (every 2 frames); only then is layer B's toggle
    advanced (so B ticks every 4 frames), and likewise C every 8.  Disabled fields do not move.
    """
    if not state.enabled:
        return state
    stars = list(state.stars)
    c0, c1, c2 = state.layer_counters

    c0 = (c0 + 1) & 1
    if c0 != 0:
        return replace(state, layer_counters=(c0, c1, c2))
    _advance_band(stars, *LAYER_BOUNDS[0])

    c1 = (c1 + 1) & 1
    if c1 != 0:
        return replace(state, stars=tuple(stars), layer_counters=(c0, c1, c2))
    _advance_band(stars, *LAYER_BOUNDS[1])

    c2 = (c2 + 1) & 1
    if c2 != 0:
        return replace(state, stars=tuple(stars), layer_counters=(c0, c1, c2))
    _advance_band(stars, *LAYER_BOUNDS[2])

    return replace(state, stars=tuple(stars), layer_counters=(c0, c1, c2))


def star_page_offset(star: Star, cursor: int) -> int:
    """The page byte offset a star plots to: ``row*0x68 + cursor + dx`` (1010:4D15)."""
    return (star.row * PAGE_ROW_STRIDE + cursor + star.dx) & 0xFFFF


def plot_starfield(
    state: StarfieldState,
    cursor: int,
    page_read: Callable[[int], int],
    page_write: Callable[[int, int], None],
) -> list[int]:
    """Plot every star, skipping occupied page bytes; return the new working list of plotted offsets.

    Mirrors ``1010:4D15``: for each star, if ``page_read(offset) == 0`` write ``color & 0xFF`` and
    record the offset; occupied pixels are skipped (not recorded).
    """
    plotted: list[int] = []
    for star in state.stars:
        off = star_page_offset(star, cursor)
        if page_read(off) == 0:
            page_write(off, star.color & 0xFF)
            plotted.append(off)
    return plotted


def erase_starfield(prev_offsets: list[int], page_write: Callable[[int, int], None]) -> None:
    """Zero each offset from the previous frame's working list (1010:4D64)."""
    for off in prev_offsets:
        page_write(off, 0)
