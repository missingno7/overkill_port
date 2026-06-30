"""The pure marker-RLE loader codecs (asset types 0 and 1), verified against the real ASM.

decode_byte_single_marker_rle (1010:02C3, type 0) and decode_word_single_marker_rle_words (1010:02F2,
type 1) are the inline codecs the loader dispatcher selects; they have no standalone hook (they live
inside the dispatcher), so the airtight check steps the *real game code* out of the 1MB runtime image
from the codec entry until it reaches the shared loader-dispatch continuation (1010:02A8), then compares
ES:DI output (and the DI-advance count) to the pure form -- the gold-standard "pure vs interpreted ASM"
gate, sourcing the ASM from the image rather than a hand-pasted blob.
"""
from __future__ import annotations

import pathlib

import pytest

from dos_re.cpu import CPU8086, CPUState
from dos_re.memory import Memory

from overkill.asset_codecs import (
    decode_byte_single_marker_rle,
    decode_word_single_marker_rle_words,
)

MB = 0xFF        # a byte sentinel
MW = 0xAAAA      # a word sentinel

IMAGE = pathlib.Path(__file__).resolve().parent.parent / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"
CODE_SEG = 0x1010
DS_SEG = 0x25CC      # the loader's data segment -- buffer/ptr/dest vars live here at runtime
OUT_SEG = 0x9000
DISPATCH_OK_IP = 0x02A8


# --- pure unit coverage --------------------------------------------------------------------------

def test_byte_marker_empty():
    assert decode_byte_single_marker_rle([MB, MB, 0x00]) == b""


def test_byte_marker_literal():
    assert decode_byte_single_marker_rle([MB, 0x10, MB, 0x00]) == b"\x10"


def test_byte_marker_run():
    assert decode_byte_single_marker_rle([MB, MB, 0x03, 0xAA, MB, 0x00]) == b"\xaa\xaa\xaa"


def test_byte_marker_mixed():
    stream = [MB, 0x10, 0x20, MB, 0x03, 0xAA, 0x30, MB, 0x00]
    assert decode_byte_single_marker_rle(stream) == b"\x10\x20\xaa\xaa\xaa\x30"


def test_byte_marker_masks():
    assert decode_byte_single_marker_rle([0x1FF, 0x110, 0x1FF, 0x100]) == b"\x10"


def test_word_marker_empty():
    assert decode_word_single_marker_rle_words([MW, MW, 0x0000]) == []


def test_word_marker_literal():
    assert decode_word_single_marker_rle_words([MW, 0x1111, MW, 0x0000]) == [0x1111]


def test_word_marker_run():
    assert decode_word_single_marker_rle_words([MW, MW, 0x0003, 0xBEEF, MW, 0x0000]) == [0xBEEF] * 3


def test_word_marker_mixed():
    stream = [MW, 0x1111, 0x2222, MW, 0x0003, 0xBEEF, 0x3333, MW, 0x0000]
    assert decode_word_single_marker_rle_words(stream) == [0x1111, 0x2222, 0xBEEF, 0xBEEF, 0xBEEF, 0x3333]


def test_word_marker_masks():
    assert decode_word_single_marker_rle_words([0x1AAAA, 0x11111, 0x1AAAA, 0x10000]) == [0x1111]


# --- airtight cross-check: pure form vs the real ASM stepped from the image -----------------------

def _run_asm(entry_ip, stream_bytes, start_di=0x40):
    mem = Memory()
    data = IMAGE.read_bytes()
    mem.data[: len(data)] = data
    cpu = CPU8086(mem, CPUState(cs=CODE_SEG, ds=DS_SEG, ss=0x6000, sp=0x8000, ip=entry_ip, flags=0x0202))
    cpu.trace_enabled = False
    mem.load(DS_SEG, 0x0410, bytes(b & 0xFF for b in stream_bytes))
    mem.ww(DS_SEG, 0x0610, 0x0410)  # stream pointer at buffer start (short streams -> no DOS refill)
    mem.ww(DS_SEG, 0x023A, OUT_SEG)
    mem.ww(DS_SEG, 0x023C, start_di)
    mem.ww(DS_SEG, 0x0244, 0)
    for _ in range(200000):
        if cpu.s.cs == CODE_SEG and cpu.s.ip == DISPATCH_OK_IP:
            break
        cpu.step()
    else:
        raise AssertionError("codec did not reach the dispatch continuation; ip=%04x" % cpu.s.ip)
    return cpu, mem


def _words_to_bytes(words):
    out = bytearray()
    for w in words:
        out.append(w & 0xFF)
        out.append((w >> 8) & 0xFF)
    return bytes(out)


@pytest.mark.skipif(not IMAGE.is_file(), reason="static_runtime_bundle/memory_1mb.bin not present")
def test_byte_marker_matches_real_asm():
    start_di = 0x40
    cases = [
        [MB, MB, 0x00],                                          # empty
        [MB, 0x10, MB, 0x00],                                    # one literal
        [MB, MB, 0x03, 0xAA, MB, 0x00],                          # one run
        [MB, 0x10, 0x20, MB, 0x03, 0xAA, 0x30, MB, 0x00],        # mixed
        [MB, MB, 0xFF, 0x7E, MB, 0x00],                          # max run (255)
    ]
    for stream in cases:
        pure = decode_byte_single_marker_rle(stream)
        cpu, mem = _run_asm(0x02C3, stream, start_di)
        got = bytes(mem.rb(OUT_SEG, (start_di + i) & 0xFFFF) for i in range(len(pure)))
        assert got == pure, stream
        assert cpu.s.di == (start_di + len(pure)) & 0xFFFF, stream


@pytest.mark.skipif(not IMAGE.is_file(), reason="static_runtime_bundle/memory_1mb.bin not present")
def test_word_marker_matches_real_asm():
    start_di = 0x40
    cases = [
        [MW, MW, 0x0000],                                                  # empty
        [MW, 0x1111, MW, 0x0000],                                          # one literal
        [MW, MW, 0x0003, 0xBEEF, MW, 0x0000],                             # one run
        [MW, 0x1111, 0x2222, MW, 0x0003, 0xBEEF, 0x3333, MW, 0x0000],     # mixed
    ]
    for words in cases:
        pure = decode_word_single_marker_rle_words(words)
        cpu, mem = _run_asm(0x02F2, _words_to_bytes(words), start_di)
        got = [mem.rw(OUT_SEG, (start_di + 2 * i) & 0xFFFF) for i in range(len(pure))]
        assert got == pure, words
        assert cpu.s.di == (start_di + 2 * len(pure)) & 0xFFFF, words
