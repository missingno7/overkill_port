"""Tandy screen geometry: di <-> (x, y) round-trips and matches the layout."""
from __future__ import annotations

import sys
from pathlib import Path

from overkill.recovered.systems.tandy_screen import (
    TANDY_BANK_STRIDE,
    TANDY_BYTES_PER_ROW,
    TANDY_PALETTE_RGB,
    di_to_screen,
    on_screen,
    pixel_rgb,
    screen_to_di,
    unpack_pixel_byte,
)

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def test_known_layout_points():
    assert screen_to_di(0, 0) == 0
    assert screen_to_di(2, 0) == 1          # two pixels per byte
    assert screen_to_di(0, 1) == TANDY_BANK_STRIDE      # row 1 -> bank 1
    assert screen_to_di(0, 2) == 2 * TANDY_BANK_STRIDE  # row 2 -> bank 2
    assert screen_to_di(0, 4) == TANDY_BYTES_PER_ROW    # row 4 -> bank 0, next line


def test_round_trip_di_to_screen_to_di():
    # every byte offset in the aperture round-trips (x lands on the byte's left pixel)
    for y in range(0, 200, 7):
        for x in range(0, 320, 2):
            di = screen_to_di(x, y)
            assert di_to_screen(di) == (x, y)


def test_witnessed_sprite_di_decode_on_screen():
    # destinations witnessed from the live 5AC8 draws (L5 demo) all land on-screen
    for di in (0x7A70, 0x7A84, 0x4127, 0x4750, 0x7052, 0x7E8A, 0x3A70, 0x3AB7):
        assert on_screen(di), f"{di:04X} decoded off-screen: {di_to_screen(di)}"
        x, y = di_to_screen(di)
        assert 0 <= x < 320 and 0 <= y < 200


def test_palette_is_16_valid_rgb():
    assert len(TANDY_PALETTE_RGB) == 16
    for r, g, b in TANDY_PALETTE_RGB:
        assert 0 <= r < 256 and 0 <= g < 256 and 0 <= b < 256


def test_palette_matches_reference_decode():
    # Drift guard: the recovered palette is the single source of truth and must
    # stay identical to the verified framebuffer decoder's palette (which is
    # diffed pixel-exact against the VM).
    from render_frame import EGA_PALETTE

    assert TANDY_PALETTE_RGB == tuple(tuple(c) for c in EGA_PALETTE)


def test_unpack_pixel_byte_high_nibble_first():
    assert unpack_pixel_byte(0xAB) == (0x0A, 0x0B)
    assert unpack_pixel_byte(0x00) == (0, 0)
    assert unpack_pixel_byte(0xF0) == (0x0F, 0x00)


def test_pixel_rgb_maps_index_through_palette():
    assert pixel_rgb(0) == (0x00, 0x00, 0x00)
    assert pixel_rgb(15) == (0xFF, 0xFF, 0xFF)
    assert pixel_rgb(0x1F) == pixel_rgb(0x0F)  # masks to 4 bits
