"""Pure unit tests for the VM-free sprite-texture decoder.

The byte-exact-vs-live-compositor check lives in
``overkill/probes/verify_sprite_decode.py`` (needs the VM); these cover the pure
decode/composite math headlessly.
"""
from __future__ import annotations

import numpy as np
import pytest

from overkill.recovered.systems.sprite_textures import (
    MASKED_COMPOSITORS,
    OR_INVERTED_COMPOSITORS,
    composite_indices,
    composite_words,
    decode_masked_sprite,
    decode_or_inverted_delta,
)


def _word_bytes(mask: int, data: int) -> bytes:
    """One source word pair: little-endian mask word then data word."""
    return bytes([mask & 0xFF, (mask >> 8) & 0xFF, data & 0xFF, (data >> 8) & 0xFF])


def test_decode_one_word_clean_sprite():
    # mask 0xF00F -> opaque where nibble==0: px0 opaque, px1/px2 transparent, px3 opaque.
    # data 0x0530 -> px0=3, px1=0, px2=0, px3=5 (clean: transparent pixels carry 0).
    tex = decode_masked_sprite(_word_bytes(0xF00F, 0x0530), words_per_row=1, rows=1)
    assert (tex.width, tex.height) == (4, 1)
    assert list(tex.pixels[0]) == [3, 0, 0, 5]
    assert list(tex.opaque[0]) == [True, False, False, True]


def test_composite_indices_keeps_background_where_transparent():
    tex = decode_masked_sprite(_word_bytes(0xF00F, 0x0530), 1, 1)
    bg = np.full((1, 4), 9, dtype=np.uint8)
    assert list(composite_indices(tex, bg)[0]) == [3, 9, 9, 5]


def test_composite_words_is_the_faithful_compositor_op():
    tex = decode_masked_sprite(_word_bytes(0xF00F, 0x0530), 1, 1)
    bg_words = np.array([[0x9999]], dtype=np.uint16)
    assert int(composite_words(tex, bg_words)[0, 0]) == ((0x9999 & 0xF00F) | 0x0530)


def test_render_form_matches_faithful_for_clean_masks():
    # A 2x2-word block: assert the pixels/opaque composite equals (bg & mask)|data.
    src = b"".join(_word_bytes(m, d) for m, d in
                   [(0xF00F, 0x0530), (0x0000, 0x1234), (0xFFFF, 0x0000), (0x00FF, 0x1200)])
    tex = decode_masked_sprite(src, words_per_row=2, rows=2)
    bg_words = np.array([[0x1357, 0x2468], [0xABCD, 0x0F0F]], dtype=np.uint16)
    faithful = composite_words(tex, bg_words)
    # rebuild words from the pixels/opaque render form over the same bg
    blo, bhi = (bg_words & 0xFF).astype(np.uint8), (bg_words >> 8).astype(np.uint8)
    bg_px = np.stack([blo >> 4, blo & 0xF, bhi >> 4, bhi & 0xF], -1).reshape(2, 8)
    out = np.where(tex.opaque, tex.pixels, bg_px).astype(np.uint8).reshape(2, 2, 4)
    out_words = ((out[:, :, 0] << 4 | out[:, :, 1]).astype(np.uint16)
                 | ((out[:, :, 2] << 4 | out[:, :, 3]).astype(np.uint16) << 8))
    assert np.array_equal(out_words, faithful)


def test_decode_rejects_short_source():
    with pytest.raises(ValueError):
        decode_masked_sprite(b"\x00\x00", words_per_row=2, rows=2)


def test_recovered_compositor_geometry():
    assert MASKED_COMPOSITORS[0x2E6E] == (8, 0x0058, None)
    assert MASKED_COMPOSITORS[0x2F81] == (4, 0x0060, None)
    assert MASKED_COMPOSITORS[0x2FB6] == (2, 0x0064, 8)


def _or_word_bytes(plane: int, skipped: int = 0xFFFF) -> bytes:
    """One OR-inverted source group: the used plane word, then the skipped word."""
    return bytes([plane & 0xFF, (plane >> 8) & 0xFF, skipped & 0xFF, (skipped >> 8) & 0xFF])


def test_decode_or_inverted_delta_is_notted_source():
    # plane 0x0F30 -> nibbles [3,0,0,F]; delta = 0xF ^ nibble = [C,F,F,0].
    delta = decode_or_inverted_delta(_or_word_bytes(0x0F30), words_per_row=1, rows=1)
    assert delta.shape == (1, 4)
    assert list(delta[0]) == [0xC, 0xF, 0xF, 0x0]


def test_decode_or_inverted_ignores_the_skipped_second_word():
    # The second word of each 4-byte group is not read; changing it must not change the delta.
    a = decode_or_inverted_delta(_or_word_bytes(0x1234, 0x0000), 1, 1)
    b = decode_or_inverted_delta(_or_word_bytes(0x1234, 0xFFFF), 1, 1)
    assert np.array_equal(a, b)


def test_decode_or_inverted_rejects_short_source():
    with pytest.raises(ValueError):
        decode_or_inverted_delta(b"\x00\x00", words_per_row=2, rows=2)


def test_recovered_or_inverted_geometry():
    assert OR_INVERTED_COMPOSITORS[0x2F40] == (4, 0x0060)
    assert OR_INVERTED_COMPOSITORS[0x2ECB] == (8, 0x0058)
