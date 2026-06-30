"""Pure per-asset decode dispatcher -- the VM-free form of the OVERKILL loader at 1010:0248/0283.

The loader opens an asset file, reads a one-byte *asset type*, and dispatches to one of five codecs,
each decoding the rest of the stream into the destination ES:DI byte buffer until its terminator:

    type 0 -> 1010:02C3  byte marker-RLE
    type 1 -> 1010:02F2  word marker-RLE     (LE words -> bytes)
    type 2 -> 1010:0324  word-pair RLE       (LE words -> bytes)
    type 3 -> 1010:0367  linear byte RLE
    type 4 -> 1010:03A8  vertical byte RLE   (column-major strided writes)
    type >=5             loader error (AX=FFFF at 1010:02B2)

Every codec writes a flat byte region, so this returns the decoded asset as ``bytes`` -- exactly the
ES:DI buffer the VM loader leaves behind for a fresh (zeroed) destination.  The file *read* half (open
the file, fill the stream) is trivial Python I/O for a standalone loader and is not modelled here; this
takes the already-read asset bytes (the type byte first, as it sits in the file).
"""
from __future__ import annotations

from .rle import (
    decode_byte_single_marker_rle,
    decode_linear_byte_rle_bytes,
    decode_vertical_rle_columns_writes,
    decode_word_pair_rle_words,
    decode_word_single_marker_rle_words,
)

ASSET_TYPE_BYTE_MARKER = 0
ASSET_TYPE_WORD_MARKER = 1
ASSET_TYPE_WORD_PAIR = 2
ASSET_TYPE_BYTE_RLE = 3
ASSET_TYPE_VERTICAL_RLE = 4


def _bytes_to_le_words(data) -> list[int]:
    return [(data[i] & 0xFF) | ((data[i + 1] & 0xFF) << 8) for i in range(0, len(data) - 1, 2)]


def _le_words_to_bytes(words) -> bytes:
    out = bytearray()
    for word in words:
        out.append(word & 0xFF)
        out.append((word >> 8) & 0xFF)
    return bytes(out)


def _apply_strided_writes(writes) -> bytes:
    if not writes:
        return b""
    size = max(offset for offset, _ in writes) + 1
    buf = bytearray(size)
    for offset, value in writes:
        buf[offset] = value & 0xFF
    return bytes(buf)


def decode_asset(stream) -> bytes:
    """Decode one OVERKILL asset stream (type byte first) into its flat byte buffer.

    The VM-free twin of the loader dispatcher at 1010:0283: read the leading asset-type byte, then run
    the matching pure codec over the remaining bytes.  Returns the decoded bytes as the VM loader would
    leave them in a freshly-zeroed ES:DI destination.  Raises ``ValueError`` for an unknown type (the
    AX=FFFF loader-error path), the fail-loud equivalent of the ASM's error return.
    """
    data = bytes(b & 0xFF for b in stream)
    if not data:
        raise ValueError("empty OVERKILL asset stream (no type byte)")
    asset_type = data[0]
    body = data[1:]

    if asset_type == ASSET_TYPE_BYTE_MARKER:
        return decode_byte_single_marker_rle(body)
    if asset_type == ASSET_TYPE_BYTE_RLE:
        return decode_linear_byte_rle_bytes(body)
    if asset_type == ASSET_TYPE_WORD_MARKER:
        return _le_words_to_bytes(decode_word_single_marker_rle_words(_bytes_to_le_words(body)))
    if asset_type == ASSET_TYPE_WORD_PAIR:
        return _le_words_to_bytes(decode_word_pair_rle_words(_bytes_to_le_words(body)))
    if asset_type == ASSET_TYPE_VERTICAL_RLE:
        return _apply_strided_writes(decode_vertical_rle_columns_writes(body))
    raise ValueError(f"unknown OVERKILL asset type {asset_type} (loader error path)")
