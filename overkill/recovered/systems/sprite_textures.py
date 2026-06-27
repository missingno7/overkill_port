"""Pure OVERKILL sprite-texture decode (Tandy mode-2 masked sprites).

Lifts the masked-sprite compositor format into a VM-free texture decoder. The
original leaves (1010:2E6E / 2F81 / 2FB6, recovered in
``overkill/rendering/tandy.py`` as ``_masked_word_composite_rows``) composite a
sprite into the page one 16-bit word at a time:

    dest_word = (dest_word & MASK) | DATA

with the source holding **interleaved ``(mask, data)`` word pairs** (4 source
bytes per output word), ``words_per_row`` words per row, drawn top-to-bottom.
A nibble of ``mask`` is ``0`` where the sprite is opaque (``data`` shows) and
``0xF`` where transparent (the background shows through).

This module turns those source bytes into a background-independent
:class:`SpriteTexture` (indexed pixels + an opaque mask) — the semantic sprite
state the native renderer draws at (interpolated) positions, instead of diffing
sprites out of the already-composited page. It is verified byte-exact against the
live compositor by ``overkill/probes/verify_sprite_decode.py``.

Tandy mode-2 packing: one 16-bit word -> 2 bytes -> 4 pixels, 2 px/byte, the high
nibble is the left pixel; the word is little-endian so its low byte is the left
pixel pair.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

PX_PER_WORD = 4
SRC_BYTES_PER_WORD = 4  # interleaved mask word (2) + data word (2)

# Recovered geometry of the masked-sprite compositor leaves (IP -> spec). The
# row stride (``row_add``) is the ``ADD DI,BX`` advance between rows; ``rows`` is
# fixed for the unrolled 2FB6 block and taken from CX for the LOOP-based leaves.
#   width(px) = words_per_row * PX_PER_WORD  (2E6E=32, 2F81=16, 2FB6=8)
MASKED_COMPOSITORS: dict[int, tuple[int, int, int | None]] = {
    0x2E6E: (8, 0x0058, None),   # (words_per_row, row_add, fixed_rows | None=CX)
    0x2F81: (4, 0x0060, None),
    0x2FB6: (2, 0x0064, 8),
}


@dataclass(frozen=True)
class SpriteTexture:
    """A decoded, background-independent mode-2 masked sprite.

    ``pixels`` / ``opaque`` are the convenient render form (colour index per
    pixel, and where the sprite actually draws). ``mask_words`` / ``data_words``
    are the faithful source words the compositor consumes; compositing with them
    (``(bg & mask) | data``) is exactly the original op and is what verification
    checks. For clean sprites the two agree (see :func:`composite_indices`).
    """

    pixels: np.ndarray       # (h, w) uint8 colour indices
    opaque: np.ndarray       # (h, w) bool  True where the sprite draws
    mask_words: np.ndarray   # (h, words_per_row) uint16 AND mask
    data_words: np.ndarray   # (h, words_per_row) uint16 OR data

    @property
    def height(self) -> int:
        return int(self.pixels.shape[0])

    @property
    def width(self) -> int:
        return int(self.pixels.shape[1])


def _bytes_to_nibbles(lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    """Two byte planes (rows, words) -> pixels (rows, words*4), left-to-right.

    Per word the screen order is the low byte's two nibbles then the high byte's
    (little-endian word, high nibble = left pixel)."""
    quad = np.stack([lo >> 4, lo & 0x0F, hi >> 4, hi & 0x0F], axis=-1)
    return quad.reshape(lo.shape[0], lo.shape[1] * PX_PER_WORD)


def decode_masked_sprite(source: bytes, words_per_row: int, rows: int) -> SpriteTexture:
    """Decode interleaved ``(mask, data)`` mode-2 source into a :class:`SpriteTexture`.

    ``source`` must hold at least ``words_per_row * rows * 4`` bytes laid out as
    the compositor reads them: per output word, the mask word then the data word,
    ``words_per_row`` words per row, rows contiguous (the source has no per-row
    stride; only the destination does).
    """
    need = words_per_row * rows * SRC_BYTES_PER_WORD
    if len(source) < need:
        raise ValueError(f"masked sprite needs {need} source bytes, got {len(source)}")
    quad = np.frombuffer(bytes(source[:need]), dtype=np.uint8).reshape(rows, words_per_row, 4)
    mlo, mhi, dlo, dhi = quad[:, :, 0], quad[:, :, 1], quad[:, :, 2], quad[:, :, 3]
    mask_words = (mlo.astype(np.uint16) | (mhi.astype(np.uint16) << 8))
    data_words = (dlo.astype(np.uint16) | (dhi.astype(np.uint16) << 8))
    pixels = _bytes_to_nibbles(dlo, dhi).astype(np.uint8)
    opaque = _bytes_to_nibbles(mlo, mhi) == 0
    return SpriteTexture(pixels=pixels, opaque=opaque, mask_words=mask_words, data_words=data_words)


def composite_indices(texture: SpriteTexture, bg: np.ndarray) -> np.ndarray:
    """Draw the texture over a background index block ``bg`` (h, w) -> (h, w).

    The native-render form of the compositor's ``(bg & mask) | data``: the
    sprite's pixel where it is opaque, otherwise the background pixel."""
    return np.where(texture.opaque, texture.pixels, bg).astype(np.uint8)


def composite_words(texture: SpriteTexture, bg_words: np.ndarray) -> np.ndarray:
    """The faithful word-level op ``(bg & mask) | data`` (h, words_per_row).

    This is exactly what the original compositor writes; verification compares
    the live result against this."""
    return ((bg_words & texture.mask_words) | texture.data_words).astype(np.uint16)
