"""Compatibility shim for moved OVERKILL startup graphics helpers.

The 4-plane startup graphics materializers belong to the rendering-preparation
island, not to file/overlay asset decoding.  The implementation lives in
:mod:`overkill_port.games.overkill.rendering.startup_graphics`; this module keeps
old imports working without carrying a second copy of the lifted ASM code.
"""

from __future__ import annotations

from ..rendering.startup_graphics import (
    expand_4plane_block_4511,
    expand_4plane_list_450c,
    expand_4plane_row_4537,
    expand_bits_45cb,
    pack_four_pixels_45f6,
)

__all__ = [
    "pack_four_pixels_45f6",
    "expand_bits_45cb",
    "expand_4plane_block_4511",
    "expand_4plane_row_4537",
    "expand_4plane_list_450c",
]
