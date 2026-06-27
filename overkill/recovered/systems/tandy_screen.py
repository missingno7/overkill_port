"""Pure recovered Tandy screen geometry — the di <-> (x, y) mapping.

OVERKILL's Tandy mode-2 present (1010:3354) uses the 320x200x16 packed layout:
one byte holds two horizontal pixels (high nibble = left), and scanlines are
split across four 8 KiB banks::

    di(x, y) = (y & 3) * 0x2000 + (y >> 2) * 160 + (x >> 1)

This is the geometry that maps an object's projected destination ``screen_di``
(object record +0C) back to a screen pixel and forward again. The enhanced
renderer uses it to place sprites and to interpolate in screen space (lerp the
decoded (x, y), then re-encode). Verified against ``scripts/render_frame.py``'s
framebuffer decode, which is diffed pixel-exact against the VM. No VM here.
"""
from __future__ import annotations

from overkill.recovered.islands import recovered_island

TANDY_BANK_STRIDE = 0x2000
TANDY_BYTES_PER_ROW = 160
SCREEN_WIDTH = 320
SCREEN_HEIGHT = 200


@recovered_island(
    asm="1010:3354",
    contract="Tandy mode-2 screen pixel (x,y) -> packed VRAM byte offset (di)",
    status="ASM_MATCHED",
    merge_target="RenderBackend",
)
def screen_to_di(x: int, y: int) -> int:
    """VRAM byte offset of the byte containing screen pixel ``(x, y)``.

    ``x`` in [0, 320), ``y`` in [0, 200). Two pixels share a byte, so the even and
    odd ``x`` of a pair map to the same ``di`` (the high/low nibble).
    """
    return (y & 3) * TANDY_BANK_STRIDE + (y >> 2) * TANDY_BYTES_PER_ROW + (x >> 1)


@recovered_island(
    asm="1010:3354",
    contract="Tandy mode-2 packed VRAM byte offset (di) -> screen pixel (x,y) (left pixel of the byte)",
    status="ASM_MATCHED",
    merge_target="RenderBackend",
)
def di_to_screen(di: int) -> tuple[int, int]:
    """Screen ``(x, y)`` of the left pixel of the byte at ``di`` (inverse of
    :func:`screen_to_di`)."""
    bank = di // TANDY_BANK_STRIDE
    within = di % TANDY_BANK_STRIDE
    y = (within // TANDY_BYTES_PER_ROW) * 4 + bank
    x = (within % TANDY_BYTES_PER_ROW) * 2
    return x, y


def on_screen(di: int) -> bool:
    """True when ``di`` lands inside the 320x200 aperture."""
    x, y = di_to_screen(di)
    return 0 <= x < SCREEN_WIDTH and 0 <= y < SCREEN_HEIGHT
