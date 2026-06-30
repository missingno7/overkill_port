"""Unit tests for the pure vertical byte-RLE decode (asset_codecs.decode_vertical_rle_columns_writes).

The pure (VM-free) form of the 1010:03A8 hook (decode_vertical_rle_columns), for the standalone loader.
Stream = 3 LE header words (word1 = vertical stride AND column count) then per-column control bytes.
For column c the decoder fills down the column -- byte row r lands at offset c + r*stride -- with the
same RLE as the byte codec (< 0x80 literal run of control+1; == 0x80 ends the column; > 0x80 repeat).
The result is the (offset, byte) writes relative to di = 0.
"""
from __future__ import annotations

from overkill.asset_codecs import decode_vertical_rle_columns_writes

END = 0x80


def _header(word0: int, stride: int, word2: int) -> list[int]:
    """3 little-endian header words as a byte list."""
    return [word0 & 0xFF, word0 >> 8, stride & 0xFF, stride >> 8, word2 & 0xFF, word2 >> 8]


def test_zero_columns_yields_nothing():
    # stride 0 -> range(0) -> no columns, no data consumed.
    assert decode_vertical_rle_columns_writes(_header(0, 0, 0)) == []


def test_single_column_literal_run_descends_by_stride():
    # stride 1, one column, literal run of 2 -> offsets 0 and 1 (r*stride with stride 1).
    stream = _header(0, 1, 0) + [0x01, 0xAA, 0xBB, END]
    assert decode_vertical_rle_columns_writes(stream) == [(0, 0xAA), (1, 0xBB)]


def test_stride_spacing_between_rows():
    # stride 3 -> rows in a column are 3 apart; columns 1 and 2 are empty (immediate END).
    stream = _header(0, 3, 0) + [0x01, 0xA0, 0xA1, END, END, END]
    assert decode_vertical_rle_columns_writes(stream) == [(0, 0xA0), (3, 0xA1)]


def test_two_columns_advance_by_one():
    # stride 2 -> two columns; each starts one offset further right.
    stream = _header(0, 2, 0) + [0x00, 0xC0, END, 0x00, 0xC1, END]
    assert decode_vertical_rle_columns_writes(stream) == [(0, 0xC0), (1, 0xC1)]


def test_repeat_run_down_a_column():
    # stride 2; column 0 repeats 0x55 twice (control 0xFF) down the column; column 1 empty.
    stream = _header(0, 2, 0) + [0xFF, 0x55, END, END]
    assert decode_vertical_rle_columns_writes(stream) == [(0, 0x55), (2, 0x55)]


def test_full_two_by_two_image_is_column_major():
    # A 2-wide x 2-tall image filled column-major: col0 = offsets 0,2; col1 = offsets 1,3.
    stream = _header(0, 2, 0) + [0x01, 0x10, 0x11, END, 0x01, 0x20, 0x21, END]
    assert decode_vertical_rle_columns_writes(stream) == [(0, 0x10), (2, 0x11), (1, 0x20), (3, 0x21)]


def test_header_words_0_and_2_are_ignored():
    # word0 and word2 are consumed but do not affect the geometry; only word1 (stride) matters.
    stream = _header(0x1234, 1, 0x5678) + [0x00, 0xAB, END]
    assert decode_vertical_rle_columns_writes(stream) == [(0, 0xAB)]


def test_data_bytes_are_masked():
    stream = _header(0, 1, 0) + [0x00, 0x1AB, END]
    assert decode_vertical_rle_columns_writes(stream) == [(0, 0xAB)]
