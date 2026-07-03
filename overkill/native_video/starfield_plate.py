"""Native starfield background plate — the VM-free source of the playfield's background layer.

The playfield is ``background plate + sprite layer`` (see
:mod:`overkill.native_video.playfield`).  Until now the *plate* — the persistent sparse
parallax pixel starfield decoded just before the frame's first sprite — was still captured
from the VM page.  This module builds it from the recovered :class:`StarfieldState` instead,
closing the last VM dependency in the standalone playfield compose.

How: the starfield is an otherwise-zero source page with each star plotted at its recovered
page offset ``row*0x68 + cursor + dx`` (``1010:4D15``; a page byte written only if that byte
is still 0, so star-on-star overlaps are skipped exactly as the plotter does), then decoded
through the same verified present-blit geometry the backend already uses
(:func:`~overkill.native_video.page_raster.render_present_page_indices`).  The result is the
byte-exact ``(H, W)`` index plate — proven equal to the VM plate across the gameplay demos by
``overkill.probes.verify_native_starfield_plate``.
"""
from __future__ import annotations

import numpy as np

from overkill.native_video.page_raster import (
    PRESENT_ROW_BYTES,
    PRESENT_ROWS,
    render_present_page_indices,
)
from overkill.recovered.domain.starfield import StarfieldState
from overkill.recovered.systems.starfield import star_page_offset

# The present blit reads the window ``[cursor, cursor + PRESENT_ROWS*PRESENT_ROW_BYTES)`` of the
# source page.  Star offsets are 16-bit (segment-relative); as long as that whole window stays
# inside one 64 KiB paragraph the star plot and the blit read agree with the VM's segment
# arithmetic (which is the case for every observed scroll cursor).  Guard it so a future level
# with a larger cursor fails loud instead of silently truncating (never fake a gap).
_PAGE_SIZE = 0x10000
_WINDOW_BYTES = PRESENT_ROWS * PRESENT_ROW_BYTES  # 192 * 0x68 = 0x4E00


def render_starfield_plate(state: StarfieldState, cursor: int) -> np.ndarray:
    """Build the ``(H, W)`` indexed starfield background plate from ``state``, VM-free.

    ``cursor`` is the present scroll cursor (``DS:[234C]``).  Returns the palette-independent
    index image the backend composites sprites onto — byte-exact vs the VM's decoded playfield
    plate.  Raises if ``cursor`` would push the star window across the 64 KiB page boundary
    (unmodelled segment wrap), rather than produce a silently-wrong plate.
    """
    cur = cursor & 0xFFFF
    if cur + _WINDOW_BYTES > _PAGE_SIZE:
        raise ValueError(
            f"scroll cursor {cur:#06x} + starfield window {_WINDOW_BYTES:#x} crosses the 64KiB "
            "page boundary; the segment-wrap case is not modelled (recover it before relying on it)"
        )
    page = np.zeros(_PAGE_SIZE, dtype=np.uint8)
    for star in state.stars:
        off = star_page_offset(star, cur)
        if page[off] == 0:  # 1010:4D15 skips already-lit page bytes (star-on-star overlap)
            page[off] = star.color & 0xFF
    return render_present_page_indices(page, 0, cur)
