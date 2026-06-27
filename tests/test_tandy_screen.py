"""Tandy screen geometry: di <-> (x, y) round-trips and matches the layout."""
from __future__ import annotations

from overkill.recovered.systems.tandy_screen import (
    TANDY_BANK_STRIDE,
    TANDY_BYTES_PER_ROW,
    di_to_screen,
    on_screen,
    screen_to_di,
)


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
