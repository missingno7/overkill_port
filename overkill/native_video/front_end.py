"""Native (VM-less) front-end scene rendering: decode the full-screen menu/title images.

The OVERKILL front-end screens (title/options ``OKMENU``, the difficulty ``CHOOSE``, the six planet
plaques ``PLAQ0..5``, ``HISCORE``, ``REDEF``, ``CALIB``, the win/level screens, ``THEND``) are stored
in the container as full-screen 320x200 4bpp images: a ``{rows, stride}`` 2-word header followed by
four bit-planes, ``stride`` (=40) bytes per plane per row.  They decode with the ALREADY-RECOVERED
pure codecs -- ``container.load_container_asset`` (``.ENC`` = LZ, ``.BIC`` = the 0283 dispatch) then
``planar.deplanarize_tandy`` -- so the whole title/menu can be drawn with **no VM and no ASM**, from
the game data alone.  This is the render half of the native front-end flow; the input/scene-flow half
lives in ``overkill.native_front_end`` (the recovered 558B menu-idle + level-select logic).

Proven: ``decode_fullscreen_image(container, "OKMENU.ENC")`` reproduces the title/options screen the VM
draws at cold boot, pixel-for-pixel (see ``tests/test_front_end_image.py`` + the byte-exact
``overkill/probes/verify_native_front_end_image.py``).
"""
from __future__ import annotations

import numpy as np

from overkill.asset_codecs.container import load_container_asset
from overkill.asset_codecs.planar import deplanarize_tandy

SCREEN_WIDTH = 320
SCREEN_HEIGHT = 200
_BYTES_PER_ROW = SCREEN_WIDTH // 2   # 160: 2 pixels per byte (4bpp packed)

# The container names of the full-screen front-end images (all the same {rows,stride}+4-plane form).
# The title/options screen (full 320x200), verified byte-exact vs the VM. Other container screens
# (CHOOSE, PLAQ0..5, HISCORE, REDEF, ...) deplanarize to SMALLER images -- centred dialogs with their
# own on-screen placement, a per-scene layout the front-end flow still has to recover; decode_fullscreen
# _image fails loud on them rather than mangling a non-320x200 buffer.
TITLE_OPTIONS = "OKMENU.ENC"


def _chunky_to_indices(chunky: bytes, width: int, height: int) -> np.ndarray:
    """A block-mode ``deplanarize_tandy`` chunky buffer (2 px/byte) -> ``(height,width)`` 4-bit indices."""
    bpr = width // 2
    buf = np.frombuffer(bytes(chunky[: bpr * height]), dtype=np.uint8).reshape(height, bpr)
    out = np.empty((height, width), dtype=np.uint8)
    out[:, 0::2] = (buf >> 4) & 0x0F   # high nibble = left pixel
    out[:, 1::2] = buf & 0x0F
    return out


def decode_fullscreen_image(container_data, name: str) -> np.ndarray:
    """Decode a FULL-SCREEN (320x200) front-end image to ``(200,320)`` 4-bit indices, VM-free.

    Uses only the recovered container decode + ``deplanarize_tandy``.  Raises if the asset is not a
    full 320x200 image (the smaller centred dialogs like ``CHOOSE``/``PLAQn`` need a per-scene
    placement the front-end flow has yet to recover -- fail loud rather than mangle a wrong-sized buffer).
    """
    chunky = deplanarize_tandy(load_container_asset(container_data, name), sprite_mode=False)
    expected = _BYTES_PER_ROW * SCREEN_HEIGHT
    if len(chunky) != expected:
        raise ValueError(
            f"{name} deplanarizes to {len(chunky)} bytes, not a full 320x200 screen ({expected}); "
            "it is a smaller placed dialog whose per-scene layout is not recovered yet")
    return _chunky_to_indices(chunky, SCREEN_WIDTH, SCREEN_HEIGHT)
