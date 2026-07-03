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
from overkill.native_video.hud_chrome import (
    PAGE_SIZE,
    compose_status_cells_859e,
    compose_status_counters_61dc,
    paste_panel_cell,
    xy_to_di_5a00,
)


def test_xy_to_di_5a00_matches_witnessed_samples():
    # (x,y) -> packed cell cursor, confirmed against the driven 61DC on snapshots
    assert xy_to_di_5a00(0x1F, 0x40) == 0x0A7C   # counter row
    assert xy_to_di_5a00(0x1F, 0x0C) == 0x025C   # trailing cell 1
    assert xy_to_di_5a00(0x21, 0x18) == 0x0444   # trailing cell 2
    assert xy_to_di_5a00(0x00, 0x01) == 0x2000   # (y&3)*0x2000 bank term


def test_compose_status_counters_places_six_cells_by_value():
    dir_table = [0] * 0x40
    dir_table[0x19] = 0x100      # value 0 -> dir[0x19]
    dir_table[0x1B] = 0x200      # value 2 -> dir[0x1B]
    panel = _panel_with_cells({0x100: 0x55, 0x200: 0x66})
    page = np.zeros(PAGE_SIZE, np.uint8)
    compose_status_counters_61dc(page, panel, dir_table, [0, 0, 2, 0, 0, 0],
                                 a95a=0, draw_trailing=False)
    base = xy_to_di_5a00(0x1F, 0x40)
    assert page[base] == 0x55                    # counter 0 (value 0) -> dir[0x19]
    assert page[(base + 2 * 4) & 0xFFFF] == 0x66  # counter 2 (value 2) -> dir[0x1B]


def test_compose_status_counters_trailing_cells_gated():
    dir_table = [0] * 0x40
    dir_table[0x19] = 0x100
    dir_table[0x23] = 0x200      # a95a=3 -> dir[3 + 0x20]
    dir_table[0x1E] = 0x300
    panel = _panel_with_cells({0x100: 0x11, 0x200: 0x22, 0x300: 0x33})
    off = np.zeros(PAGE_SIZE, np.uint8)
    compose_status_counters_61dc(off, panel, dir_table, [0] * 6, a95a=3, draw_trailing=False)
    assert off[xy_to_di_5a00(0x1F, 0x0C)] == 0    # trailing NOT drawn when gated off
    on = np.zeros(PAGE_SIZE, np.uint8)
    compose_status_counters_61dc(on, panel, dir_table, [0] * 6, a95a=3, draw_trailing=True)
    assert on[xy_to_di_5a00(0x1F, 0x0C)] == 0x22  # dir[a95a + 0x20]
    assert on[xy_to_di_5a00(0x21, 0x18)] == 0x33  # dir[0x1E]


def _panel_with_cells(specs):
    """Build a PANEL byte array with 1x1 cells {off: fill}; returns (bytes, dir helper)."""
    buf = bytearray(0x1000)
    for off, fill in specs.items():
        buf[off:off + 4] = bytes([1, 0, 1, 0])          # rows=1, width=1 -> 4 data bytes
        buf[off + 4:off + 8] = bytes([fill, fill, fill, fill])
    return np.frombuffer(bytes(buf), np.uint8)


def test_compose_status_cells_places_A_B_C_per_descriptor():
    # dir maps: src_idx 2 -> cell 0xAA (A); 0x17 -> 0xBB (B); color_idx 5 -> 0xCC (C)
    dir_table = [0] * 0x40
    dir_table[2], dir_table[0x17], dir_table[5] = 0x100, 0x200, 0x300
    panel = _panel_with_cells({0x100: 0xAA, 0x200: 0xBB, 0x300: 0xCC})
    page = np.zeros(PAGE_SIZE, np.uint8)
    di_base = 0x1000
    compose_status_cells_859e(page, panel, dir_table, [(di_base, 2, 5, 0)])
    assert page[di_base + 0x14] == 0xAA          # A: di_base + 0x14, dir[src_idx]
    assert page[(di_base - 0x04) & 0xFFFF] == 0xBB  # B: di_base - 0x04, dir[0x17]
    assert page[di_base] == 0xCC                  # C: di_base, dir[color_idx]


def test_compose_status_cells_match_bumps_A_and_B_to_next_cell():
    dir_table = [0] * 0x40
    dir_table[3], dir_table[0x18] = 0x100, 0x200   # src_idx+match=3, 0x17+match=0x18
    dir_table[5] = 0x300
    panel = _panel_with_cells({0x100: 0x11, 0x200: 0x22, 0x300: 0x33})
    page = np.zeros(PAGE_SIZE, np.uint8)
    di_base = 0x0800
    compose_status_cells_859e(page, panel, dir_table, [(di_base, 2, 5, 1)])  # match=1
    assert page[di_base + 0x14] == 0x11          # A uses dir[src_idx + 1]
    assert page[(di_base - 0x04) & 0xFFFF] == 0x22  # B uses dir[0x17 + 1]
    assert page[di_base] == 0x33                  # C unaffected by match

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
