"""Unit tests for the pure recovered starfield (overkill.recovered.systems.starfield)."""
from __future__ import annotations

from overkill.recovered.domain.starfield import PAGE_ROW_STRIDE, Star, StarfieldState
from overkill.recovered.systems.starfield import (
    advance_starfield,
    erase_starfield,
    plot_starfield,
    star_page_offset,
)


def _field(rows):
    return StarfieldState(tuple(Star(r, 0, 0x0F) for r in rows))


def test_layer_cadence_2_4_8():
    # 40 stars, distinct rows so we can see which advanced. Layers: 0..19 / 20..29 / 30..39.
    f = _field(list(range(40)))
    rows0 = [s.row for s in f.stars]
    # Frame 1: counter c0 -> 1 (odd) => nothing moves.
    f = advance_starfield(f)
    assert [s.row for s in f.stars] == rows0
    # Frame 2: c0 -> 0 => layer A moves; c1 -> 1 => B,C stay.
    f = advance_starfield(f)
    rows = [s.row for s in f.stars]
    assert rows[:20] == [r + 1 for r in rows0[:20]]      # A advanced
    assert rows[20:] == rows0[20:]                        # B, C unchanged
    # Frames 3,4: A advances again on frame 4; at frame 4 c1 -> 0 => B advances too.
    f = advance_starfield(f)   # frame 3: nothing
    f = advance_starfield(f)   # frame 4: A and B
    rows = [s.row for s in f.stars]
    assert rows[:20] == [r + 2 for r in rows0[:20]]
    assert rows[20:30] == [r + 1 for r in rows0[20:30]]
    assert rows[30:] == rows0[30:]                        # C still waiting (every 8)


def test_row_wraps_at_192():
    f = _field([0xBF] + [0] * 39)  # 0xBF = 191
    f = advance_starfield(f)  # c0 odd -> no move
    f = advance_starfield(f)  # c0 even -> A moves: 191 -> wrap 0
    assert f.stars[0].row == 0


def test_disabled_field_does_not_move():
    f = StarfieldState(tuple(Star(r, 0, 1) for r in range(40)), enabled=False)
    assert advance_starfield(f).stars == f.stars


def test_page_offset_formula():
    assert star_page_offset(Star(7, 0x0E, 0x0F), 0x1318) == (7 * PAGE_ROW_STRIDE + 0x1318 + 0x0E) & 0xFFFF


def test_plot_skips_occupied_and_records():
    f = _field([1, 2, 3] + [0] * 37)
    page = {}
    page[star_page_offset(f.stars[1], 0)] = 9  # pre-occupy star 1's pixel
    plotted = plot_starfield(f, 0, lambda o: page.get(o, 0), lambda o, v: page.__setitem__(o, v))
    off0 = star_page_offset(f.stars[0], 0)
    off1 = star_page_offset(f.stars[1], 0)
    assert off0 in plotted and off1 not in plotted   # star 1 skipped (occupied)
    assert page[off0] == 0x0F                          # star 0 plotted its color


def test_erase_clears_offsets():
    page = {10: 5, 20: 7, 30: 9}
    erase_starfield([10, 30], lambda o, v: page.__setitem__(o, v))
    assert page == {10: 0, 20: 7, 30: 0}
