"""Airtight cross-check: the pure VM-free RLE codecs vs the oracle-verified VM hook bodies.

The pure forms (decode_word_pair_rle_words / decode_linear_byte_rle_bytes /
decode_vertical_rle_columns_writes) are the standalone-loader twins of the cpu/VM hooks in
overkill/asset_codecs/rle.py.  Those hooks are themselves ASM-oracle-verified, so running a hook on a
synthetic packed buffer and comparing its ES:DI output to the pure form proves the pure form matches
the VM byte-for-byte -- not just my reading of it.  This is the same "predicted state vs interpreted
ASM" gate the collision chain uses, lifted to the loader codecs.

The packed reader (1010:0624/0615) refills a 512-byte DS buffer (0x0410..0x0610) via DOS INT 21h; all
streams here stay under 512 bytes so no refill (and so no interrupt handler) is needed.  The vertical
decoder reads its stride from CS:03A4, so -- as in the real runtime -- DS == CS for these fixtures.
"""
from __future__ import annotations

from dos_re.cpu import CPU8086, CPUState
from dos_re.memory import Memory

from overkill.asset_codecs import (
    decode_linear_byte_rle,
    decode_linear_byte_rle_bytes,
    decode_vertical_rle_columns,
    decode_vertical_rle_columns_writes,
    decode_word_pair_rle,
    decode_word_pair_rle_words,
)
from overkill.asset_codecs.asm_adapters import OVERKILL_LOAD_DISPATCH_CONTINUATION_IP

SEG = 0x1010      # DS == CS, as in the real loader runtime
OUT_SEG = 0x4000  # ES output segment, well clear of the DS scratch/buffer
BUFFER_START = 0x0410


def _run_hook(hook, stream_bytes, *, start_di=0):
    """Drive a codec hook on a synthetic packed buffer; return (cpu, mem) after it terminates."""
    mem = Memory()
    cpu = CPU8086(mem, CPUState(cs=SEG, ds=SEG, ss=0x5000, sp=0x9000, ip=0x0300, flags=0x0202))
    cpu.trace_enabled = False
    mem.load(SEG, BUFFER_START, bytes(b & 0xFF for b in stream_bytes))
    mem.ww(SEG, 0x0610, BUFFER_START)  # stream pointer at the buffer start
    mem.ww(SEG, 0x023A, OUT_SEG)       # ES output segment
    mem.ww(SEG, 0x023C, start_di)      # DI output start
    hook(cpu)
    # Every codec jumps to the shared loader dispatch continuation on clean completion.
    assert cpu.s.ip == OVERKILL_LOAD_DISPATCH_CONTINUATION_IP, hex(cpu.s.ip)
    return cpu, mem


def _words_to_bytes(words):
    out = bytearray()
    for w in words:
        out.append(w & 0xFF)
        out.append((w >> 8) & 0xFF)
    return bytes(out)


def _header(word0, stride, word2):
    return [word0 & 0xFF, word0 >> 8, stride & 0xFF, stride >> 8, word2 & 0xFF, word2 >> 8]


# --- word-pair RLE (1010:0324) -------------------------------------------------------------------

M = 0xAAAA


def test_word_pair_hook_matches_pure():
    cases = [
        [M, M, 0x0000],                                              # empty
        [M, 0x1111, 0x2222, M, 0x0000],                             # one literal pair
        [M, M, 0x0003, 0x1111, 0x2222, M, 0x0000],                  # repeat x3
        [M, 0x1111, 0x2222, M, 0x0002, 0x3333, 0x4444, 0x5555, 0x6666, M, 0x0000],  # mixed
    ]
    start_di = 0x40
    for words in cases:
        pure = decode_word_pair_rle_words(words)
        cpu, mem = _run_hook(decode_word_pair_rle, _words_to_bytes(words), start_di=start_di)
        got = [mem.rw(OUT_SEG, (start_di + 2 * i) & 0xFFFF) for i in range(len(pure))]
        assert got == pure, words
        # DI advanced by exactly one word per output element (no extra/missing STOSW).
        assert cpu.s.di == (start_di + 2 * len(pure)) & 0xFFFF, words


# --- linear byte RLE (1010:0367) -----------------------------------------------------------------

def test_linear_byte_hook_matches_pure():
    cases = [
        [0x80],                                                      # empty
        [0x03, 0x10, 0x20, 0x30, 0x40, 0x80],                       # literal run
        [0xFD, 0x7E, 0x80],                                          # repeat run (4 copies)
        [0x01, 0xAA, 0xBB, 0xFE, 0xCC, 0x00, 0xDD, 0x80],           # mixed
    ]
    start_di = 0x40
    for stream in cases:
        pure = decode_linear_byte_rle_bytes(stream)
        cpu, mem = _run_hook(decode_linear_byte_rle, stream, start_di=start_di)
        got = bytes(mem.rb(OUT_SEG, (start_di + i) & 0xFFFF) for i in range(len(pure)))
        assert got == pure, stream
        # DI advanced by exactly one byte per output element.
        assert cpu.s.di == (start_di + len(pure)) & 0xFFFF, stream


# --- vertical byte RLE (1010:03A8) ---------------------------------------------------------------

def test_vertical_hook_matches_pure():
    cases = [
        _header(0, 1, 0) + [0x01, 0xAA, 0xBB, 0x80],                                 # 1 col, literal
        _header(0, 2, 0) + [0xFF, 0x55, 0x80, 0x80],                                 # repeat down col 0
        _header(0, 2, 0) + [0x01, 0x10, 0x11, 0x80, 0x01, 0x20, 0x21, 0x80],         # full 2x2 image
        _header(0x1234, 3, 0x5678) + [0x01, 0xA0, 0xA1, 0x80, 0x80, 0x80],           # stride 3, header ignored
    ]
    start_di = 0x40
    for stream in cases:
        pure = decode_vertical_rle_columns_writes(stream)
        _cpu, mem = _run_hook(decode_vertical_rle_columns, stream, start_di=start_di)
        for offset, byte in pure:
            assert mem.rb(OUT_SEG, (start_di + offset) & 0xFFFF) == byte, (stream, offset)
