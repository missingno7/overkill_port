"""Headless smoke test of the native pygame display adapter (dummy SDL driver).

Exercises the real blit/scale/flip path without a window so the display glue is
covered in CI. Skips cleanly when pygame/numpy are unavailable.
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
        import numpy as np  # noqa: F401
        import pygame  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("pygame/numpy not installed")

    from native_play import PygameDisplay
    from overkill.native_video.backend import NativeOverkillVideoBackend
    from overkill.native_video.frame import RenderSnapshot, SceneKind

    be = NativeOverkillVideoBackend()
    be.submit_source_frame(RenderSnapshot(
        frame_id=1, timestamp=0.0, scene_kind=SceneKind.GAMEPLAY,
        composed_indices=np.full((200, 320), 5, dtype=np.uint8), composed_version=1,
        palette=tuple((i, 2 * i, 3 * i) for i in range(16)), palette_version=0, scroll_cursor=0,
    ))
    presented = be.present(0.0)

    display = PygameDisplay(scale=2, vsync=False)
    try:
        display.draw(presented)  # full blit/scale/flip path must not crash
        # the back surface holds the colorized frame (index 5 -> (5,10,15))
        assert tuple(display._surf.get_at((0, 0))[:3]) == (5, 10, 15)

        # the F1 settings overlay renders over the frame without crashing
        from native_play import NativeOverlay
        overlay = NativeOverlay(be, display)
        overlay.visible = True
        overlay.draw()
        display.flip()
    finally:
        display.close()
