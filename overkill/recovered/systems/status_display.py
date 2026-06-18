"""Pure recovered HUD / status-display layout rules.

Source-like rules extracted from the live status-display hooks.  No VM, no
``cpu``/``mem``, no addresses -- ordinary values only (audited VM-free).
"""
from __future__ import annotations

# Bytes the status/HUD video cursor advances per status-cell column, indexed by
# the renderer video mode (CS:95BC: 0/1/2).  This single rule was encoded twice
# in the original -- once forwards in the 1010:613E cursor-advance jump table
# (+2 / +1 / +4) and once backwards in the 1010:615A cursor-retreat table
# (-2 / -1 / -4).  Lifting it here makes the two live hooks share one named rule.
STATUS_CURSOR_STRIDE_BY_MODE = {0: 2, 1: 1, 2: 4}


def status_cursor_stride(video_mode: int) -> int:
    """Return the per-status-cell video-cursor stride for ``video_mode``.

    Raises ``ValueError`` for an unrecognised mode -- the original jump tables
    have no entry there, so the live adapters must fail loudly rather than guess.
    """
    try:
        return STATUS_CURSOR_STRIDE_BY_MODE[video_mode & 0xFFFF]
    except KeyError:
        raise ValueError(f"no status cursor stride for video mode {video_mode:#06x}") from None
