"""OverKill-specific rendering helpers.

This package contains game-source-level rendering logic lifted from OVERKILL's
original real-mode program.  It is intentionally not part of the generic VM:
addresses, row tables, packed-pixel geometry, and fail-fast target names are all
specific to OVERKILL.
"""


from .text import (
    TextRenderRuntime,
    run_score_nibble_text_5f06,
    run_tandy_text_glyph_3153,
    run_text_dispatch_519a,
)
