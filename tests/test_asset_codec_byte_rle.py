"""Unit tests for the pure linear byte-RLE decode (asset_codecs.decode_linear_byte_rle_bytes).

The pure (VM-free) form of the 1010:0367 hook (decode_linear_byte_rle), for the standalone loader.
Control byte: < 0x80 -> literal run of control+1 bytes; == 0x80 -> terminate; > 0x80 -> repeat run of
((-control) & 0xFF) + 1 copies of the next byte.
"""
from __future__ import annotations

from overkill.asset_codecs import decode_linear_byte_rle_bytes

END = 0x80


def test_empty_stream_terminates_immediately():
    assert decode_linear_byte_rle_bytes([END]) == b""


def test_single_literal_byte():
    # control 0x00 -> literal run of 1 byte.
    assert decode_linear_byte_rle_bytes([0x00, 0x41, END]) == b"\x41"


def test_literal_run():
    # control 0x03 -> 4 literal bytes.
    assert decode_linear_byte_rle_bytes([0x03, 0x10, 0x20, 0x30, 0x40, END]) == b"\x10\x20\x30\x40"


def test_repeat_run_min():
    # control 0xFF -> ((-0xFF)&0xFF)+1 = 2 copies.
    assert decode_linear_byte_rle_bytes([0xFF, 0xAB, END]) == b"\xab\xab"


def test_repeat_run_larger():
    # control 0xFD -> ((-0xFD)&0xFF)+1 = 3+1 = 4 copies.
    assert decode_linear_byte_rle_bytes([0xFD, 0x7E, END]) == b"\x7e" * 4


def test_repeat_run_max():
    # control 0x81 -> ((-0x81)&0xFF)+1 = 0x7F+1 = 128 copies.
    assert decode_linear_byte_rle_bytes([0x81, 0x55, END]) == b"\x55" * 128


def test_max_literal_run():
    # control 0x7F -> 0x80 (128) literal bytes.
    payload = bytes(range(128))
    assert decode_linear_byte_rle_bytes([0x7F, *payload, END]) == payload


def test_mixed_literal_and_repeat():
    stream = [0x01, 0xAA, 0xBB,   # 2 literals
              0xFE, 0xCC,         # ((-0xFE)&0xFF)+1 = 3 copies of 0xCC
              0x00, 0xDD,         # 1 literal
              END]
    assert decode_linear_byte_rle_bytes(stream) == b"\xaa\xbb\xcc\xcc\xcc\xdd"


def test_bytes_are_masked():
    assert decode_linear_byte_rle_bytes([0x100, 0x141, 0x180]) == b"\x41"
