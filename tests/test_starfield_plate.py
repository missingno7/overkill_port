"""VM-free unit tests for the native starfield plate (overkill.native_video.starfield_plate).

The plate is the background layer the standalone playfield composites sprites onto, built from
the recovered StarfieldState.  Geometry (grounded in native_video.page_raster): with source
page 0, a star at ``(row=R, dx=D)`` plots to page byte ``R*0x68 + cursor + D`` and, through the
present blit, lands at screen ``(y = 4 + R, x_byte = D)`` -> pixels ``x = 2*D`` (high nibble) and
``x = 2*D + 1`` (low nibble).  The produced-vs-VM byte-exactness is proven separately by
``overkill.probes.verify_native_starfield_plate``; these tests pin the pure geometry + skip rules.
"""
from __future__ import annotations

import numpy as np
import pytest

from overkill.native_video.starfield_plate import render_starfield_plate
from overkill.recovered.domain.starfield import STAR_COUNT, Star, StarfieldState


def _dark_field(*, extra=()):
    """40 stars: the given ``extra`` stars first, the rest colour 0 (plot no-op)."""
    stars = list(extra) + [Star(0, 0, 0) for _ in range(STAR_COUNT - len(extra))]
    return StarfieldState(tuple(stars))


def test_plate_shape_and_empty_is_zero():
    plate = render_starfield_plate(_dark_field(), cursor=0x1000)
    assert plate.shape == (200, 320)
    assert plate.dtype == np.uint8
    assert not plate.any()  # all colour-0 stars light nothing


def test_single_star_lands_at_expected_pixel():
    # High nibble set (0xF0): lights the even pixel x = 2*D at value 0xF, odd pixel stays 0.
    R, D = 10, 20
    plate = render_starfield_plate(_dark_field(extra=(Star(R, D, 0xF0),)), cursor=0x1000)
    lit = np.argwhere(plate != 0)
    assert lit.tolist() == [[4 + R, 2 * D]]
    assert plate[4 + R, 2 * D] == 0xF


def test_low_nibble_colour_lights_odd_pixel():
    R, D = 5, 7
    plate = render_starfield_plate(_dark_field(extra=(Star(R, D, 0x0A),)), cursor=0x0800)
    lit = np.argwhere(plate != 0)
    assert lit.tolist() == [[4 + R, 2 * D + 1]]
    assert plate[4 + R, 2 * D + 1] == 0xA


def test_cursor_shifts_nothing_in_screen_space():
    # The cursor cancels out (both the star offset and the blit read include it), so a star at a
    # given (row, dx) lands at the same screen pixel regardless of cursor.
    star = Star(30, 40, 0xF0)
    a = render_starfield_plate(_dark_field(extra=(star,)), cursor=0x0400)
    b = render_starfield_plate(_dark_field(extra=(star,)), cursor=0x1A00)
    assert np.array_equal(a, b)


def test_skip_occupied_first_star_wins():
    # Two stars on the same page byte: the plotter writes only the first (page byte still 0), the
    # second is skipped -- so the earlier colour survives.
    both = render_starfield_plate(
        _dark_field(extra=(Star(12, 33, 0xF0), Star(12, 33, 0xA0))), cursor=0x1000
    )
    first_only = render_starfield_plate(_dark_field(extra=(Star(12, 33, 0xF0),)), cursor=0x1000)
    assert np.array_equal(both, first_only)
    assert both[4 + 12, 2 * 33] == 0xF


def test_cursor_past_page_boundary_fails_loud():
    with pytest.raises(ValueError):
        render_starfield_plate(_dark_field(), cursor=0xC000)  # window would cross 64KiB
