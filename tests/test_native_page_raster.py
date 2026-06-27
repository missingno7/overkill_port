"""The native page rasterizer reproduces the on-screen playfield from the
semantic page ``[9598]`` + cursor, with no VM framebuffer dependency.

A deterministic synthetic test pins the blit + decode geometry; a corpus test
grounds it against the live decoded framebuffer (B800) in the playfield region.
NumPy is imported inside each test so the core runner skips when it is absent.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEMOS = ROOT / "artifacts" / "demos"


def _np():
    try:
        import numpy as np
        return np
    except Exception:  # pragma: no cover - numpy optional for core tests
        pytest.skip("numpy not installed")


def test_replay_present_blit_places_rows():
    np = _np()
    from overkill.native_video.page_raster import replay_present_blit, PRESENT_ROW_BYTES

    mem = np.zeros(0x100000, dtype=np.uint8)
    page = 0x3000
    base = page << 4
    # Fill the source window with a known ramp so each byte is identifiable.
    src = (np.arange(PRESENT_ROW_BYTES * 0xC0, dtype=np.uint32) & 0xFF).astype(np.uint8)
    mem[base:base + src.size] = src

    scratch, written = replay_present_blit(mem, page, 0)

    # Row 0 lands at dest 0xA0; row 1 one bank down at 0x20A0 (the next scanline).
    assert scratch[0xA0] == src[0]
    assert scratch[0xA0 + 5] == src[5]
    assert scratch[0x20A0] == src[PRESENT_ROW_BYTES]      # second source row
    assert written[0xA0] and written[0x20A0]
    assert not written[0x00]                              # top strip untouched (HUD)
    assert int(written.sum()) == PRESENT_ROW_BYTES * 0xC0  # 0x68*192 bytes written


def test_decode_known_pixels_high_nibble_left():
    np = _np()
    from overkill.native_video.page_raster import decode_tandy_b800_rgb
    from overkill.recovered.systems.tandy_screen import TANDY_PALETTE_RGB

    buf = np.zeros(0x10000, dtype=np.uint8)
    buf[0xA0] = 0x1F            # byte at (x=0, y=4): left=1, right=15
    rgb = decode_tandy_b800_rgb(buf, 0)
    assert tuple(rgb[4, 0]) == TANDY_PALETTE_RGB[1]
    assert tuple(rgb[4, 1]) == TANDY_PALETTE_RGB[15]


def _snapshots():
    if not DEMOS.is_dir():
        return []
    return sorted(
        d / "snapshot"
        for d in DEMOS.glob("demo_*")
        if (d / "snapshot" / "memory_1mb.bin").is_file()
    )


def test_render_present_page_matches_framebuffer_on_corpus():
    np = _np()
    from overkill.native_video.page_raster import (
        decode_tandy_b800_rgb,
        playfield_pixel_mask,
        replay_present_blit,
        render_present_page_rgb,
    )

    snaps = _snapshots()
    if not snaps:
        pytest.skip("no corpus demos present")

    def rw(mem, seg, off):
        a = ((seg << 4) + off) & 0xFFFFF
        return int(mem[a]) | (int(mem[a + 1]) << 8)

    agreements = []
    exact = 0
    for snap in snaps:
        mem = np.frombuffer((snap / "memory_1mb.bin").read_bytes(), dtype=np.uint8)
        cpu = json.loads((snap / "state.json").read_text(encoding="utf-8"))["cpu_snapshot"]
        ds = int(re.search(r"DS=([0-9A-Fa-f]{4})", cpu).group(1), 16)
        page = rw(mem, 0x1010, 0x9598)
        cursor = rw(mem, ds, 0x234C)
        video = rw(mem, 0x1010, 0x95A4)

        page_rgb = render_present_page_rgb(mem, page, cursor)
        b800_rgb = decode_tandy_b800_rgb(mem, (video << 4) & 0xFFFFF)
        _, written = replay_present_blit(mem, page, cursor)
        mask = playfield_pixel_mask(written)

        agree = float(np.mean(np.all(page_rgb[mask] == b800_rgb[mask], axis=-1)))
        agreements.append(agree)
        if agree == 1.0:
            exact += 1

    # Several in-phase frames must match the framebuffer *exactly* — proving the
    # rasterizer is correct (not merely close) and VM-framebuffer-independent.
    assert exact >= 2, f"only {exact} exact frames; agreements={sorted(agreements)[:5]}"
    # The rest carry only the known one-present skew (the saved [9598] is a frame
    # of sprite motion ahead of the last-presented B800), so the static background
    # still dominates: the median frame reproduces the playfield to >95%.
    median = sorted(agreements)[len(agreements) // 2]
    assert median >= 0.95, f"median playfield agreement {median:.4f}"
