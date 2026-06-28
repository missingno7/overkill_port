"""Pure, VM-independent tests for the recovered rendering rasterizer.

These exercise the blit operations directly against a plain byte buffer -- no
CPU, no hooks, no VM -- which is the point of lifting them out of the address
leaves: the rendering primitives are now ordinary, testable native code.
"""
from overkill.rendering.rasterizer import (
    composite_masked_rows,
    copy_word_rows,
    or_inverted_word_rows,
)


class Buffer:
    """A minimal real-mode memory: seg:off word/byte access over 1 MiB."""

    def __init__(self):
        self.data = bytearray(0x100000)

    def _lin(self, seg, off):
        return ((seg << 4) + (off & 0xFFFF)) & 0xFFFFF

    def rb(self, seg, off):
        return self.data[self._lin(seg, off)]

    def wb(self, seg, off, value):
        self.data[self._lin(seg, off)] = value & 0xFF

    def rw(self, seg, off):
        lin = self._lin(seg, off)
        return self.data[lin] | (self.data[(lin + 1) & 0xFFFFF] << 8)

    def ww(self, seg, off, value):
        lin = self._lin(seg, off)
        self.data[lin] = value & 0xFF
        self.data[(lin + 1) & 0xFFFFF] = (value >> 8) & 0xFF


DS, ES = 0x1000, 0x2000


def test_copy_word_rows_copies_and_strides():
    mem = Buffer()
    src = [0x1111, 0x2222, 0x3333, 0x4444]  # 2 rows x 2 words
    for i, w in enumerate(src):
        mem.ww(DS, i * 2, w)
    si, di = copy_word_rows(mem, ds=DS, es=ES, si=0, di=0, rows=2,
                            words_per_row=2, row_stride=0x10, stride_on="di", step=2)
    assert (mem.rw(ES, 0), mem.rw(ES, 2)) == (0x1111, 0x2222)      # row 0
    assert (mem.rw(ES, 0x14), mem.rw(ES, 0x16)) == (0x3333, 0x4444)  # row 1 after +0x10
    assert si == 8                       # 4 words * 2
    # DI: row0 0->4 +0x10 -> 0x14; row1 ->0x18 +0x10 -> 0x28 (stride after every row)
    assert di == 0x28


def test_copy_word_rows_strides_source_when_requested():
    mem = Buffer()
    for i in range(2):
        mem.ww(DS, i * 2, 0xABCD)
    si, di = copy_word_rows(mem, ds=DS, es=ES, si=0, di=0, rows=1,
                            words_per_row=2, row_stride=0x20, stride_on="si", step=2)
    assert si == 4 + 0x20 and di == 4    # the row stride lands on SI, not DI


def test_composite_masked_rows_and_or():
    mem = Buffer()
    mem.ww(DS, 0, 0x0F0F)   # mask
    mem.ww(DS, 2, 0x00F0)   # data
    mem.ww(ES, 0, 0xFFFF)   # existing dest
    si, di, ax = composite_masked_rows(mem, ds=DS, es=ES, si=0, di=0, rows=1,
                                       words_per_row=1, row_stride=0x10, step=2)
    assert mem.rw(ES, 0) == ((0x0F0F & 0xFFFF) | 0x00F0)  # (mask & dest) | data
    assert ax == mem.rw(ES, 0)
    assert si == 4 and di == 2 + 0x10    # mask+data consumed; DI advanced + stride


def test_or_inverted_word_rows():
    mem = Buffer()
    mem.ww(DS, 0, 0x0F0F)   # source
    mem.ww(ES, 0, 0x0000)   # dest starts clear
    si, di, ax = or_inverted_word_rows(mem, ds=DS, es=ES, si=0, di=0, rows=1,
                                       words_per_row=1, row_stride=0x08)
    assert ax == (~0x0F0F) & 0xFFFF
    assert mem.rw(ES, 0) == ((~0x0F0F) & 0xFFFF)   # 0 | ~src
    assert si == 4 and di == 2 + 0x08              # SI+=4, DI+=2, then row stride


def test_tandy_b800_next_row_geometry():
    from overkill.rendering.rasterizer import tandy_b800_next_row
    # within the four interleaved banks the row step is +0x2000
    assert tandy_b800_next_row(0x0000) == 0x2000
    assert tandy_b800_next_row(0x2000) == 0x4000
    assert tandy_b800_next_row(0x4000) == 0x6000
    # crossing past the banks (>= 0x8000) wraps to the next 4-scanline group (+0x80A0)
    assert tandy_b800_next_row(0x6000) == 0x00A0   # 0x8000 -> 0x8000+0x80A0
    assert tandy_b800_next_row(0x6050) == 0x00F0   # 0x8050 -> 0x8050+0x80A0
