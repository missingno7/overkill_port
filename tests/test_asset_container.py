"""The pure OVERKILL container reader (asset_codecs.container) -- synthetic + real-file validation.

parse_overkill_container is the VM-free form of the 254A:04D7 overlay open.  The synthetic cases pin the
parser logic (overlay base, the rolling XOR, entry field layout) on a hand-built pack; the real-file
case is the strong proof -- against the actual assets/OVERKILL every payload must abut the next and fit
the file (a wrong seed / entry-size / field offset would scramble them), and every asset must decode.
"""
from __future__ import annotations

import pathlib
import struct

import pytest

from overkill.asset_codecs import (
    load_container_asset,
    parse_overkill_container,
    read_container_asset,
)
from overkill.asset_codecs.container import CONTAINER_SIGNATURE

OVERKILL = pathlib.Path(__file__).resolve().parent.parent / "assets" / "OVERKILL"
ENTRY_SIZE = 26


def _build_container(entries, *, seed=0x0102, entry_size=ENTRY_SIZE):
    """Build a non-MZ (base 0) container image from (name, payload) pairs, mirroring the on-disk format."""
    count = len(entries)
    payload_start = 12 + count * entry_size
    directory = bytearray()
    payloads = bytearray()
    offset = payload_start
    for name, payload in entries:
        entry = bytearray(entry_size)
        entry[5:9] = offset.to_bytes(4, "little")          # payload offset (relative to base 0)
        entry[9:13] = len(payload).to_bytes(4, "little")    # payload length
        encoded = name.encode("latin1")
        entry[0x0D : 0x0D + len(encoded)] = encoded          # name, NUL-padded by zero-init
        directory += entry
        payloads += payload
        offset += len(payload)
    key = seed & 0xFF
    key_step = (seed >> 8) & 0xFF
    encrypted = bytearray(len(directory))
    for j, byte in enumerate(directory):
        encrypted[j] = byte ^ key
        key = (key + key_step) & 0xFF
    header = struct.pack("<HH", count, seed) + CONTAINER_SIGNATURE + struct.pack("<H", entry_size)
    return header + bytes(encrypted) + bytes(payloads)


# --- synthetic-container parser unit coverage ----------------------------------------------------

def test_parse_synthetic_entries():
    image = _build_container([("FOO.BIC", b"\x01\x02\x03"), ("BAR.ENC", b"\xAA\xBB")])
    entries = parse_overkill_container(image)
    assert [e.name for e in entries] == ["FOO.BIC", "BAR.ENC"]
    assert entries[0].length == 3 and entries[1].length == 2
    # payloads abut: entry 0 starts right after the directory, entry 1 right after entry 0.
    assert entries[0].offset == 12 + 2 * ENTRY_SIZE
    assert entries[1].offset == entries[0].offset + 3


def test_read_synthetic_payload_and_case_insensitive():
    image = _build_container([("FOO.BIC", b"\x01\x02\x03"), ("BAR.ENC", b"\xAA\xBB")])
    assert read_container_asset(image, "FOO.BIC") == b"\x01\x02\x03"
    assert read_container_asset(image, "bar.enc") == b"\xAA\xBB"  # normalized (upper) lookup


def test_missing_name_raises():
    image = _build_container([("FOO.BIC", b"\x01")])
    with pytest.raises(KeyError):
        read_container_asset(image, "NOPE.BIC")


def test_bad_signature_raises():
    image = bytearray(_build_container([("FOO.BIC", b"\x01")]))
    image[4:10] = b"NOPE!!"
    with pytest.raises(ValueError):
        parse_overkill_container(bytes(image))


# --- real assets/OVERKILL validation -------------------------------------------------------------

@pytest.mark.skipif(not OVERKILL.is_file(), reason="assets/OVERKILL not present")
def test_real_container_parses_and_is_consistent():
    data = OVERKILL.read_bytes()
    entries = parse_overkill_container(data)
    assert len(entries) == 58
    names = {e.name for e in entries}
    assert {"1X1.BIC", "LEV0MAP.BIC", "ADLIB.ENC", "OKMENU.ENC"} <= names
    # The killer check: every payload abuts the next and fits the file.
    for a, b in zip(entries, entries[1:]):
        assert a.offset + a.length == b.offset, (a.name, b.name)
    last = entries[-1]
    assert last.offset + last.length <= len(data)
    assert entries[0].offset > 0


@pytest.mark.skipif(not OVERKILL.is_file(), reason="assets/OVERKILL not present")
def test_real_container_assets_all_decode():
    data = OVERKILL.read_bytes()
    entries = parse_overkill_container(data)
    # Every asset decodes through the by-extension codec dispatch (27 .BIC + 31 .ENC).
    for entry in entries:
        out = load_container_asset(data, entry.name)
        assert len(out) > 0, entry.name
    # Regression anchors (decoded sizes for known assets).
    assert len(load_container_asset(data, "1X1.BIC")) == 4212      # type 4 vertical RLE
    assert len(load_container_asset(data, "ADLIB.ENC")) == 16318   # LZ
