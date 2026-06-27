"""Pure recovered Tandy mode-2 presentation format — geometry + palette + unpack.

OVERKILL's Tandy mode-2 present (1010:3354) uses the 320x200x16 packed layout:
one byte holds two horizontal pixels (high nibble = left), and scanlines are
split across four 8 KiB banks::

    di(x, y) = (y & 3) * 0x2000 + (y >> 2) * 160 + (x >> 1)

This module owns the full format the rasterizer needs to turn the composited
source page (`PresentComposition.source_page`) into RGB: the di <-> (x, y)
geometry (mapping an object's projected ``screen_di`` — object record +0C — back
to a screen pixel and forward again), the fixed 16-colour palette
(`TANDY_PALETTE_RGB`), and the packed-byte pixel unpack (`unpack_pixel_byte`).
The enhanced renderer uses the geometry to place sprites and interpolate in
screen space (lerp the decoded (x, y), then re-encode), and the palette/unpack to
produce pixels. Verified against ``scripts/render_frame.py``'s framebuffer decode,
which is diffed pixel-exact against the VM. No VM here.
"""
from __future__ import annotations

from overkill.recovered.islands import recovered_island

TANDY_BANK_STRIDE = 0x2000
TANDY_BYTES_PER_ROW = 160
SCREEN_WIDTH = 320
SCREEN_HEIGHT = 200

# The fixed PCjr/Tandy 16-colour IRGB palette for mode-2 (320x200x16). OVERKILL
# never reprograms it — there are no palette-register writes in the render island
# (witnessed) — so these 16 RGB triples are the entire colour space: the rasterizer
# maps each 4-bit pixel index straight through this table. It is the canonical copy
# (identical to the standard EGA default palette the verified viewer/render_frame
# decode uses; a drift-guard test keeps them in lockstep).
TANDY_PALETTE_RGB: tuple[tuple[int, int, int], ...] = (
    (0x00, 0x00, 0x00), (0x00, 0x00, 0xAA), (0x00, 0xAA, 0x00), (0x00, 0xAA, 0xAA),
    (0xAA, 0x00, 0x00), (0xAA, 0x00, 0xAA), (0xAA, 0x55, 0x00), (0xAA, 0xAA, 0xAA),
    (0x55, 0x55, 0x55), (0x55, 0x55, 0xFF), (0x55, 0xFF, 0x55), (0x55, 0xFF, 0xFF),
    (0xFF, 0x55, 0x55), (0xFF, 0x55, 0xFF), (0xFF, 0xFF, 0x55), (0xFF, 0xFF, 0xFF),
)


def unpack_pixel_byte(value: int) -> tuple[int, int]:
    """Split one mode-2 packed byte into its (left, right) 4-bit colour indices.

    Two pixels share a byte; the **high** nibble is the left pixel (matches the
    framebuffer decode in ``scripts/render_frame.py``).
    """
    return (value >> 4) & 0x0F, value & 0x0F


def pixel_rgb(index: int) -> tuple[int, int, int]:
    """RGB triple for a 4-bit Tandy colour ``index`` (0..15)."""
    return TANDY_PALETTE_RGB[index & 0x0F]


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
