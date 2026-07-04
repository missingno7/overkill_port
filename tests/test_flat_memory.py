"""The shared flat-image memory shape (adapters/flat_memory)."""
from __future__ import annotations

import pytest

from overkill.recovered.adapters.flat_memory import FlatMemory, MutFlatMemory


def test_flat_memory_reads_seg_off_little_endian():
    img = bytearray(0x100000)
    img[0x25CC * 16 + 0x1234] = 0x34
    img[0x25CC * 16 + 0x1235] = 0x12
    mem = FlatMemory(bytes(img))
    assert mem.rb(0x25CC, 0x1234) == 0x34
    assert mem.rw(0x25CC, 0x1234) == 0x1234
    # seg/off wrap masking (offsets are 16-bit, physical is 20-bit)
    assert mem.rw(0x25CC, 0x11234 & 0xFFFF) == 0x1234


def test_flat_memory_is_read_only():
    mem = FlatMemory(b"\x00" * 32)
    assert not hasattr(mem, "ww")
    with pytest.raises(TypeError):
        mem.data[0] = 1  # bytes, not bytearray


def test_mut_flat_memory_round_trips_words_on_a_private_copy():
    src = b"\x00" * 0x100000
    mem = MutFlatMemory(src)
    mem.ww(0x25CC, 0x2358, 0xBEEF)
    assert mem.rw(0x25CC, 0x2358) == 0xBEEF
    assert mem.rb(0x25CC, 0x2358) == 0xEF
    assert src == b"\x00" * 0x100000  # the source image is never mutated
