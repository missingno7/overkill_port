"""Native playfield composition: ``playfield = background plate + sprite layer``.

This is the crystallised, VM-independent form of the gameplay playfield, proven
byte-exact against the emulator by ``overkill/probes/verify_playfield_compose.py``
(30/30 L2 frames). The playfield is two layers:

* the **background plate** — the persistent *pixel* starfield, an ``(H, W)`` index
  image (decoded before the frame's first sprite). It is sparse (mostly index 0);
  the stars are individual pixels, not tiles/sprites, and scroll as their own layer.
* the **sprite layer** — the per-frame masked-compositor blocks (the verified
  ``CapturedSprite -> SnapshotSprite`` path), composited on top via
  :func:`overkill.native_video.sprite_layer.composite_sprites`.

The backend composes through this seam instead of reading the VM's ``[9598]`` page:
hand it a ``BackgroundLayer`` plate and the semantic sprite blocks and it returns the
playfield indices to colorize. (Until the starfield generator is recovered the plate
may be a captured one; the composition itself is native and verified.)
"""
from __future__ import annotations

from typing import Iterable

import numpy as np

from overkill.native_video.sprite_layer import composite_sprites


def compose_playfield_indices(background: np.ndarray, sprites: Iterable, cursor: int,
                              di_shift: int = 0) -> np.ndarray:
    """Compose the playfield indices = sprite blocks over the ``background`` plate.

    ``background`` is the ``(H, W)`` uint8 index image of the starfield plate; it is
    copied, not mutated. ``sprites`` are :class:`SnapshotSprite` blocks; ``cursor`` is
    the present scroll cursor (``DS:[234C]``) used to place each block. ``di_shift``
    offsets every block uniformly (whole-frame interpolation). Returns the composed
    playfield indices — equal, byte-for-byte, to the VM's decoded ``[9598]`` playfield.
    """
    plate = np.array(background, dtype=np.uint8, copy=True)
    return composite_sprites(plate, sprites, cursor, di_shift)
