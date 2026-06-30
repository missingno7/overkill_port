"""Headless tests for the cold-level playfield render (scripts/native_play_cold.playfield_frame)."""
from __future__ import annotations

import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

from native_play_cold import playfield_frame  # noqa: E402
from overkill.native_video.page_raster import PLAYFIELD_H, PLAYFIELD_W, colorize  # noqa: E402


def test_playfield_frame_shape_and_window():
    # A synthetic terrain taller than the playfield: rows colored by their value.
    terrain = np.zeros((400, PLAYFIELD_W), dtype=np.uint8)
    terrain[100:300] = 5  # a band of index 5
    rgb = playfield_frame(terrain, 100, (PLAYFIELD_W + 99, PLAYFIELD_H + 99))  # ship off-frame
    assert rgb.shape == (PLAYFIELD_H, PLAYFIELD_W, 3)
    # The window at scroll 100 is all index 5 -> palette[5] everywhere.
    pal5 = colorize(np.array([[5]], dtype=np.uint8))[0, 0]
    assert np.all(rgb[0, 0] == pal5)


def test_playfield_frame_draws_ship_marker():
    terrain = np.zeros((400, PLAYFIELD_W), dtype=np.uint8)
    rgb = playfield_frame(terrain, 0, (104, 150))
    # The ship marker is a distinct blue not present in the (index-0) background.
    assert np.any(np.all(rgb == (80, 160, 255), axis=-1)), "ship marker not drawn"
    # It is near the ship position, not at the corners.
    ys, xs = np.where(np.all(rgb == (80, 160, 255), axis=-1))
    assert 95 <= int(xs.mean()) <= 113 and 140 <= int(ys.mean()) <= 156


def test_scroll_is_clamped():
    terrain = np.zeros((300, PLAYFIELD_W), dtype=np.uint8)
    # Over-scroll past the end must not raise or produce a wrong shape (clamped).
    assert playfield_frame(terrain, 10_000, (104, 150)).shape == (PLAYFIELD_H, PLAYFIELD_W, 3)
    assert playfield_frame(terrain, -50, (104, 150)).shape == (PLAYFIELD_H, PLAYFIELD_W, 3)
