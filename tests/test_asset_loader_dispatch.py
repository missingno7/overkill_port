"""The pure per-asset decode dispatcher (asset_codecs.decode_asset), verified end-to-end vs real ASM.

decode_asset reads the leading asset-type byte and routes to the matching pure codec (the VM-free twin
of the loader dispatcher at 1010:0283).  The airtight check steps the *real loader ASM* out of the 1MB
runtime image from 0283 -- which reads the type byte and dispatches -- to the shared dispatch
continuation (1010:02A8), then compares the ES:DI buffer to decode_asset for the byte/word codecs
(types 0-3).  Type 4 (vertical) reads its stride from CS:03A4 and so requires DS==CS, which the standalone
hook-body cross-check already covers; here type 4 is checked at the dispatch level (it routes to the
verified vertical codec) plus the unknown-type error path.
"""
from __future__ import annotations

import pathlib

import pytest

from dos_re.cpu import CPU8086, CPUState
from dos_re.memory import Memory

from overkill.asset_codecs import decode_asset
from overkill.asset_codecs.loader import _apply_strided_writes
from overkill.asset_codecs.rle import decode_vertical_rle_columns_writes

IMAGE = pathlib.Path(__file__).resolve().parent.parent / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"
CODE_SEG = 0x1010
DS_SEG = 0x25CC
OUT_SEG = 0x9000
DISPATCH_OK_IP = 0x02A8
DISPATCH_ENTRY_IP = 0x0283  # the type-byte read + dispatch


def _le(words):
    out = bytearray()
    for w in words:
        out.append(w & 0xFF)
        out.append((w >> 8) & 0xFF)
    return list(out)


# --- pure dispatch unit coverage -----------------------------------------------------------------

def test_dispatch_type0_byte_marker():
    assert decode_asset([0, 0xFF, 0x10, 0x20, 0xFF, 0x00]) == b"\x10\x20"


def test_dispatch_type3_byte_rle():
    assert decode_asset([3, 0x01, 0xAA, 0xBB, 0x80]) == b"\xaa\xbb"


def test_dispatch_type1_word_marker():
    assert decode_asset([1] + _le([0xAAAA, 0x1111, 0xAAAA, 0x0000])) == b"\x11\x11"


def test_dispatch_type2_word_pair():
    assert decode_asset([2] + _le([0xAAAA, 0x1111, 0x2222, 0xAAAA, 0x0000])) == b"\x11\x11\x22\x22"


def test_dispatch_type4_vertical_routes_to_codec():
    body = bytes([0, 0, 2, 0, 0, 0, 0x01, 0x10, 0x11, 0x80, 0x01, 0x20, 0x21, 0x80])
    expected = _apply_strided_writes(decode_vertical_rle_columns_writes(body))
    assert decode_asset([4, *body]) == expected
    assert expected == b"\x10\x20\x11\x21"  # 2x2 image, row-major


def test_dispatch_empty_stream_raises():
    with pytest.raises(ValueError):
        decode_asset([])


def test_dispatch_unknown_type_raises():
    # type >=5 is the loader's AX=FFFF error path (1010:02B2).
    with pytest.raises(ValueError):
        decode_asset([5, 0x00, 0x00])


# --- airtight cross-check: decode_asset vs the real dispatcher ASM (byte/word codecs) -------------

def _run_dispatch_asm(stream, start_di=0x40):
    mem = Memory()
    data = IMAGE.read_bytes()
    mem.data[: len(data)] = data
    cpu = CPU8086(mem, CPUState(cs=CODE_SEG, ds=DS_SEG, ss=0x6000, sp=0x8000, ip=DISPATCH_ENTRY_IP, flags=0x0202))
    cpu.trace_enabled = False
    mem.load(DS_SEG, 0x0410, bytes(b & 0xFF for b in stream))
    mem.ww(DS_SEG, 0x0610, 0x0410)
    mem.ww(DS_SEG, 0x023A, OUT_SEG)
    mem.ww(DS_SEG, 0x023C, start_di)
    mem.ww(DS_SEG, 0x0244, 0)
    for off in range(512):  # fresh zeroed destination
        mem.wb(OUT_SEG, (start_di + off) & 0xFFFF, 0)
    for _ in range(200000):
        if cpu.s.cs == CODE_SEG and cpu.s.ip == DISPATCH_OK_IP:
            break
        cpu.step()
    else:
        raise AssertionError("dispatcher did not reach continuation; ip=%04x" % cpu.s.ip)
    return mem


@pytest.mark.skipif(not IMAGE.is_file(), reason="static_runtime_bundle/memory_1mb.bin not present")
def test_dispatch_matches_real_asm_byte_and_word_codecs():
    start_di = 0x40
    cases = [
        [0, 0xFF, 0x10, 0x20, 0xFF, 0x03, 0xAA, 0x30, 0xFF, 0x00],                   # type 0
        [3, 0x01, 0xAA, 0xBB, 0xFE, 0xCC, 0x80],                                     # type 3
        [1] + _le([0xAAAA, 0x1111, 0xAAAA, 0x0003, 0xBEEF, 0x2222, 0xAAAA, 0x0000]),  # type 1
        [2] + _le([0xAAAA, 0x1111, 0x2222, 0xAAAA, 0x0002, 0x3333, 0x4444, 0xAAAA, 0x0000]),  # type 2
    ]
    for stream in cases:
        pure = decode_asset(stream)
        mem = _run_dispatch_asm(stream, start_di)
        got = bytes(mem.rb(OUT_SEG, (start_di + i) & 0xFFFF) for i in range(len(pure)))
        assert got == pure, stream
