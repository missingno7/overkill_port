"""Pure reader for OVERKILL's asset container -- the VM-free form of the 254A:04D7 overlay open.

The game's assets live in ``assets/OVERKILL`` (an MZ executable with an overlay pack appended).  The
container open at 254A:04D7 computes the overlay base, reads a 12-byte overlay header, validates a
6-byte signature, then walks a directory of fixed-size, XOR-encrypted entries by name and seeks to the
matching payload.  This module does that as a pure byte transform over the already-read file image
(the file open/read is plain Python I/O for a standalone loader):

    overlay base = (e_cp-1)*512 + e_cblp   for an MZ file, else 0   (CS:07AA/07AC at 254A:053C)
    overlay header @base: count u16 @0, XOR seed u16 @2, b"SHADOW" @4..10, entry-size u16 @10
    directory @base+12: ``count`` entries of ``entry-size`` bytes, XOR-decrypted with a key that rolls
        across the whole directory (al ^= byte; al += ah, ah = seed>>8 constant; 254A:05BF)
    entry (decrypted): payload offset u32 @+5 (relative to base), length u32 @+9, name @+0x0D (NUL-term)

Verified against the real assets/OVERKILL: all 58 payloads abut exactly and fit the file, and every
payload decodes (see tests/test_asset_container.py).  The asset codec is by extension (observed
convention): ``.BIC`` -> the 0283 type-dispatch (:func:`decode_asset`); ``.ENC`` -> LZ
(:func:`decode_lz_bytes`).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

from .loader import decode_asset
from .lz import decode_lz_bytes

CONTAINER_SIGNATURE = b"SHADOW"
_ENTRY_OFFSET_FIELD = 5
_ENTRY_LENGTH_FIELD = 9
_ENTRY_NAME_FIELD = 0x0D


@dataclass(frozen=True)
class OverkillContainerEntry:
    """One directory entry: an asset name and the absolute file span of its (still-coded) payload."""

    name: str
    offset: int  # absolute file offset of the payload
    length: int


def _u16(data, off: int) -> int:
    return struct.unpack_from("<H", data, off)[0]


def _normalize_name(name: str) -> str:
    # 254A:05D9 compares names uppercased and space-insensitive.
    return name.upper().replace(" ", "")


def parse_overkill_container(data) -> list[OverkillContainerEntry]:
    """Parse the OVERKILL container image into its directory entries (in file order).

    Raises ``ValueError`` if the overlay signature is not ``b"SHADOW"`` (not a valid container).
    """
    data = bytes(data)
    base = (_u16(data, 4) - 1) * 512 + _u16(data, 2) if data[:2] == b"MZ" else 0

    count = _u16(data, base)
    seed = _u16(data, base + 2)
    signature = data[base + 4 : base + 10]
    if signature != CONTAINER_SIGNATURE:
        raise ValueError(f"not an OVERKILL container: signature {signature!r} != {CONTAINER_SIGNATURE!r}")
    entry_size = _u16(data, base + 10)

    key = seed & 0xFF
    key_step = (seed >> 8) & 0xFF
    pos = base + 12
    entries: list[OverkillContainerEntry] = []
    for _ in range(count):
        encrypted = data[pos : pos + entry_size]
        pos += entry_size
        decrypted = bytearray(len(encrypted))
        for j, byte in enumerate(encrypted):
            decrypted[j] = byte ^ key
            key = (key + key_step) & 0xFF
        name = bytes(decrypted[_ENTRY_NAME_FIELD:]).split(b"\x00")[0].decode("latin1")
        offset = int.from_bytes(decrypted[_ENTRY_OFFSET_FIELD : _ENTRY_OFFSET_FIELD + 4], "little")
        length = int.from_bytes(decrypted[_ENTRY_LENGTH_FIELD : _ENTRY_LENGTH_FIELD + 4], "little")
        entries.append(OverkillContainerEntry(name, base + offset, length))
    return entries


def read_container_asset(data, name: str) -> bytes:
    """Return the raw (still codec-compressed) payload bytes for ``name``.  Raises ``KeyError``."""
    data = bytes(data)
    target = _normalize_name(name)
    for entry in parse_overkill_container(data):
        if _normalize_name(entry.name) == target:
            return data[entry.offset : entry.offset + entry.length]
    raise KeyError(name)


def load_container_asset(data, name: str) -> bytes:
    """Return the fully-decoded asset bytes for ``name``.

    Picks the codec by extension, the observed game convention (verified across all 58 assets):
    ``.ENC`` payloads are LZ (:func:`decode_lz_bytes`); everything else (``.BIC``) goes through the
    0283 type-dispatch (:func:`decode_asset`).
    """
    blob = read_container_asset(data, name)
    if _normalize_name(name).endswith(".ENC"):
        return decode_lz_bytes(blob)
    return decode_asset(blob)
