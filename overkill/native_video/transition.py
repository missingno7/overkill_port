"""Native screen SQUEEZE / UNSQUEEZE transition -- the VM-free form of the 5C46 / 5960 effect.

Between the level-select screen and the level, the original plays a vertical squeeze: ``1010:5C46``
draws the target screen with a growing vertical extent ``[5901]`` (from 6, ``+2`` per retrace, up to
``[58FD]`` = the full height), through a video-mode blit -- the image starts compressed into a thin
band across the screen centre and UNSQUEEZES open to full height.  ``1010:5960`` is the reverse
(``[5901]`` counts down): the departing screen SQUEEZES shut.

We reproduce the visible effect: vertically scale the full ``(200, 320)`` index frame into ``height``
rows centred on screen.  ``height`` animates 6 -> 200 (unsqueeze) or 200 -> 6 (squeeze), matching the
5C46/5960 ``[5901]`` sweep (``+2`` / ``-2`` per step).
"""
from __future__ import annotations

import numpy as np

SCREEN_H, SCREEN_W = 200, 320
#: 5C46 seeds [5901] = 6 and steps +2 per retrace up to [58FD]; the full-height target is the screen.
SQUEEZE_MIN_H = 6
SQUEEZE_STEP = 2


def vertical_squeeze_frame(frame: np.ndarray, height: int) -> np.ndarray:
    """Return a ``(200, 320)`` frame with ``frame`` vertically scaled into ``height`` rows, centred
    (the 5C46 blit's compressed band).  ``height >= 200`` returns the frame unchanged."""
    height = max(0, min(int(height), SCREEN_H))
    out = np.zeros((SCREEN_H, SCREEN_W), dtype=frame.dtype)
    if height <= 0:
        return out
    if height >= SCREEN_H:
        out[:] = frame
        return out
    src_rows = (np.arange(height) * SCREEN_H) // height          # nearest-row vertical downscale
    top = (SCREEN_H - height) // 2                               # centred, like [5905]/[5907]
    out[top:top + height] = frame[src_rows]
    return out


def squeeze_heights(*, opening: bool) -> "list[int]":
    """The 5C46 (opening) / 5960 (closing) height sweep: 6..200 by +2, or 200..6 by -2."""
    up = list(range(SQUEEZE_MIN_H, SCREEN_H + 1, SQUEEZE_STEP))
    return up if opening else up[::-1]
