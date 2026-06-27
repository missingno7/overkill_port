"""Bridge: extract a native :class:`RenderSnapshot` from live VM memory.

This is the VM↔semantic boundary for the native video backend. The *extractor*
(here, on the game thread) is allowed to read the game's composed page and produce
normalized, palette-independent render-state layers; the native backend then
consumes only those layers and never touches VM memory (enforced by
``tests/test_native_video_independence.py``). Deplanarization happens **once per
game tick** here, not per display frame.

Tailored to OVERKILL: ``composed_indices`` is the visible composed page (the
page-baked composite of background + HUD/chrome + baked sprites) decoded to 4-bit
indices — the faithful baseline the backend colorizes. ``playfield_indices`` is the
source page ``[9598]`` alone (the scrolling playfield sublayer) carried for
camera/object interpolation. The palette is fixed, so ``palette_version`` is a
constant; the content versions are cheap CRCs so identical static scenes
(menu/title) reuse the colorize cache across ticks.
"""
from __future__ import annotations

import zlib

import numpy as np

from overkill.native_video.frame import RenderSnapshot, SceneKind
from overkill.native_video.page_raster import (
    decode_tandy_b800_indices,
    render_present_page_indices,
)
from overkill.recovered.adapters.frame_snapshot_adapter import extract_frame_snapshot
from overkill.recovered.systems.tandy_screen import TANDY_PALETTE_RGB

VIDEO_PAGE_PTR = 0x95A4    # CS:[95A4] -> visible composed aperture (B800)
SOURCE_PAGE_PTR = 0x9598   # CS:[9598] -> scrolling source page (playfield)
SOURCE_CURSOR = 0x234C     # DS:[234C] -> present blit start offset (scroll)
OVERKILL_CODE_SEGMENT = 0x1010
TANDY_PALETTE_VERSION = 0  # OVERKILL's palette is fixed


def extract_render_snapshot(
    mem,
    ds: int,
    *,
    frame_id: int,
    timestamp: float,
    cs: int = OVERKILL_CODE_SEGMENT,
    scene_kind: SceneKind = SceneKind.GAMEPLAY,
) -> RenderSnapshot:
    """Reconstruct one game-tick :class:`RenderSnapshot` from VM memory ``mem``."""
    ds &= 0xFFFF
    cs &= 0xFFFF
    mem_arr = np.frombuffer(mem.data, dtype=np.uint8)

    video_page = mem.rw(cs, VIDEO_PAGE_PTR)
    source_page = mem.rw(cs, SOURCE_PAGE_PTR)
    cursor = mem.rw(ds, SOURCE_CURSOR)

    composed = decode_tandy_b800_indices(mem_arr, ((video_page & 0xFFFF) << 4) & 0xFFFFF)
    playfield = render_present_page_indices(mem_arr, source_page, cursor)
    fs = extract_frame_snapshot(mem, ds, cs)

    return RenderSnapshot(
        frame_id=frame_id,
        timestamp=timestamp,
        scene_kind=scene_kind,
        composed_indices=composed,
        composed_version=zlib.crc32(composed.tobytes()),
        palette=TANDY_PALETTE_RGB,
        palette_version=TANDY_PALETTE_VERSION,
        scroll_cursor=cursor,
        playfield_indices=playfield,
        playfield_version=zlib.crc32(playfield.tobytes()),
        sprites=fs.playfield.sprites,
        snapshot=fs,
    )
