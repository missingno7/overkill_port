"""Unit tests for the pure word-pair RLE decode (asset_codecs.decode_word_pair_rle_words).

The pure (VM-free) form of the 1010:0324 hook (decode_word_pair_rle), for the standalone loader.
The first word is the sentinel; a non-sentinel word is a literal pair (it + the next word); the
sentinel introduces a repeat count (0 terminates, else the next two words are the repeated pair).
"""
from __future__ import annotations

from overkill.asset_codecs import decode_word_pair_rle_words

M = 0xAAAA  # sentinel marker


def test_empty_stream_terminates_immediately():
    assert decode_word_pair_rle_words([M, M, 0x0000]) == []


def test_single_literal_pair():
    assert decode_word_pair_rle_words([M, 0x1111, 0x2222, M, 0x0000]) == [0x1111, 0x2222]


def test_multiple_literal_pairs():
    stream = [M, 0x1111, 0x2222, 0x3333, 0x4444, M, 0x0000]
    assert decode_word_pair_rle_words(stream) == [0x1111, 0x2222, 0x3333, 0x4444]


def test_repeated_pair():
    stream = [M, M, 0x0003, 0x1111, 0x2222, M, 0x0000]
    assert decode_word_pair_rle_words(stream) == [0x1111, 0x2222] * 3


def test_repeat_count_one():
    assert decode_word_pair_rle_words([M, M, 0x0001, 0xBEEF, 0xCAFE, M, 0x0000]) == [0xBEEF, 0xCAFE]


def test_mixed_literal_then_repeat():
    stream = [M, 0x1111, 0x2222, M, 0x0002, 0x3333, 0x4444, 0x5555, 0x6666, M, 0x0000]
    assert decode_word_pair_rle_words(stream) == [
        0x1111, 0x2222,            # literal
        0x3333, 0x4444, 0x3333, 0x4444,  # repeat x2
        0x5555, 0x6666,            # literal
    ]


def test_words_are_masked_to_16_bit():
    # Values above 0xFFFF (and a >16-bit marker) are masked; the marker still matches.
    out = decode_word_pair_rle_words([0x1AAAA, 0x11111, 0x22222, 0x1AAAA, 0x10000])
    assert out == [0x1111, 0x2222]


def test_literal_equal_to_marker_is_impossible_by_design():
    # A literal word never equals the marker (that is the sentinel); a marker word is always a
    # count introducer.  So a marker mid-stream with a nonzero count is a repeat, not a literal.
    assert decode_word_pair_rle_words([M, M, 0x0002, 0x0001, 0x0002, M, 0x0000]) == [1, 2, 1, 2]
