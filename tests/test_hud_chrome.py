"""Synthetic-ASM oracle for the native PANEL-cell blit (``hud_chrome.paste_panel_cell``).

The in-game 306F render path runs only at cold-boot/level-load (before every snapshot demo -- see
loop_blockers.md), so there is no gameplay-demo witness.  Instead this pins ``paste_panel_cell``
byte-exact against the **original 1010:306F opcodes**: it assembles the exact routine bytes (from
the project disassembler), runs them on a real ``CPU8086`` over synthetic PANEL cells, and asserts
the packed B800 page the ASM writes is byte-identical to ``paste_panel_cell``.  Same "synthetic
fixtures + interpreted ASM" gate the asset codecs use.
"""
from __future__ import annotations

import numpy as np

from dos_re.cpu import CPU8086, CPUState
from dos_re.memory import Memory
from overkill.native_video.hud_chrome import PAGE_SIZE, paste_panel_cell

# The exact 1010:306F opcodes (verified via scripts/lindis.py):
#   lodsw; mov cx,ax; lodsw; mov es,cs:[95A4]; shl ax,1; shl ax,1; mov bp,ax;
#   .row: push cx; mov cx,bp; rep movsb; sub di,bp; add di,2000h; test di,8000h;
#         jz +4; add di,80A0h; pop cx; loop .row; ret
CODE_306F = bytes.fromhex(
    "ad" "8bc8" "ad" "2e8e06a495" "d1e0" "d1e0" "8be8"
    "51" "8bcd" "f3a4" "2bfd" "81c70020" "f7c70080" "7404" "81c7a080" "59" "e2e8" "c3"
)
CS = 0x1010
IP0 = 0x306F
PAGE_SEG_OFF = 0x95A4      # CS:[95A4] = present page segment (ES source)
RET_SENTINEL = 0xFFFF


def _run_306f_asm(cell: bytes, di: int, *, page_seg=0xB800, ds=0x2000, si=0x0040,
                  ss=0x3000, sp=0x1000) -> np.ndarray:
    """Execute the real 306F opcodes over ``cell`` and return the resulting B800 page."""
    mem = Memory()
    code_phys = (CS << 4) + IP0
    for i, b in enumerate(CODE_306F):
        mem.data[code_phys + i] = b
    mem.ww(CS, PAGE_SEG_OFF, page_seg)          # CS:[95A4] = page segment
    for i, b in enumerate(cell):
        mem.wb(ds, (si + i) & 0xFFFF, b)
    mem.ww(ss, sp, RET_SENTINEL)                # near-ret target
    cpu = CPU8086(mem, CPUState(cs=CS, ip=IP0, ds=ds, si=si, ss=ss, sp=sp,
                                di=di & 0xFFFF, es=0, flags=0x0002))  # DF=0 (forward rep movsb)
    for _ in range(1_000_000):
        if (cpu.s.ip & 0xFFFF) == RET_SENTINEL:
            break
        cpu.step()
    else:  # pragma: no cover
        raise AssertionError("306F oracle did not return")
    base = (page_seg << 4) & 0xFFFFF
    return np.frombuffer(mem.data, dtype=np.uint8)[base:base + PAGE_SIZE].copy()


def _native(cell: bytes, di: int) -> np.ndarray:
    page = np.zeros(PAGE_SIZE, dtype=np.uint8)
    paste_panel_cell(page, np.frombuffer(cell, dtype=np.uint8), 0, di)
    return page


def _cell(rows: int, width: int, seed: int = 1) -> bytes:
    """A {rows,width} header + rows*width*4 distinct nonzero pixel bytes."""
    stride = width * 4
    pixels = bytes(((seed + i) % 255 + 1) for i in range(rows * stride))
    return bytes([rows & 0xFF, rows >> 8, width & 0xFF, width >> 8]) + pixels


def _assert_match(cell, di):
    asm = _run_306f_asm(cell, di)
    native = _native(cell, di)
    assert np.array_equal(asm, native), (
        f"mismatch at di={di:#06x}: {int(np.count_nonzero(asm != native))} diff bytes"
    )


def test_single_word_cell():
    _assert_match(_cell(rows=2, width=1), di=0x00A0)


def test_multi_word_cell():
    _assert_match(_cell(rows=3, width=2, seed=17), di=0x00A0)


def test_wide_cell():
    _assert_match(_cell(rows=4, width=5, seed=40), di=0x0100)


def test_bank_wrap_is_reproduced():
    # di near 0x8000 so the +0x2000 row step crosses it and triggers the +0x80A0 wrap
    _assert_match(_cell(rows=3, width=2, seed=7), di=0x7F00)


def test_single_row_cell():
    _assert_match(_cell(rows=1, width=3, seed=99), di=0x0200)


def test_native_matches_asm_across_many_cursors():
    cell = _cell(rows=2, width=2, seed=3)
    for di in (0x0000, 0x00A0, 0x1000, 0x3FFE, 0x6000, 0x7FFE):
        _assert_match(cell, di)
