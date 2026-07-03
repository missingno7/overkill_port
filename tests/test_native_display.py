"""Headless smoke test of the native (VM-less) pygame display adapter (dummy SDL driver).

Exercises the real indices -> palette -> blit/scale/flip path without a window so the display
glue is covered in CI. Skips cleanly when pygame/numpy are unavailable.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def test_pygame_display_blits_a_presented_frame(monkeypatch):
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    try:
        import numpy as np
        import pygame  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("pygame/numpy not installed")

    from play_native import PygameDisplay

    display = PygameDisplay(scale=2)
    try:
        indices = np.full((200, 320), 5, dtype=np.uint8)
        display.draw(indices)  # full indices -> palette -> blit/scale/flip path must not crash
        # the back surface holds the colorized frame (Tandy palette index 5)
        from overkill.recovered.systems.tandy_screen import TANDY_PALETTE_RGB
        assert tuple(display._surf.get_at((0, 0))[:3]) == tuple(TANDY_PALETTE_RGB[5])
    finally:
        display.close()
