#!/usr/bin/env python
"""Native video backend viewer (modern pygame presentation of the recovered model).

This is the pygame-coupled half of ``overkill.native_video`` — kept out of the
VM-independent backend package. It presents the backend's frames at the monitor
refresh.

Live gameplay runs through ``play.py``: ``play.py --backend native [--demo DIR]``
keeps play.py's proven emulator loop + timing (timer-IRQ, pacing, the burst model)
and swaps only the viewer — this module's :func:`run_native_ui` consumes the same
``FrameSync`` the SDL viewer does and presents via the native backend (decoupled
present clock + caching). Standalone, ``--snapshot DIR`` presents one captured
frame (no game loop) — the simplest proof of the native render path.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from overkill.native_video.backend import NativeOverkillVideoBackend  # noqa: E402
from overkill.native_video.config import load_config  # noqa: E402
from overkill.native_video.loop import PresentationLoop  # noqa: E402
from overkill.recovered.systems.tandy_screen import SCREEN_HEIGHT, SCREEN_WIDTH  # noqa: E402

# Tandy/CGA pack their aperture at the real B800 segment; the present decode is
# Tandy mode-2 (the native backend's only decode today).
B800_BASE = 0xB8000


def _require_pygame():
    try:
        import pygame  # noqa: F401
        return pygame
    except Exception as exc:  # pragma: no cover - environment dependent
        raise SystemExit(f"native_play needs pygame: {exc}")


class PygameDisplay:
    """Blit a PresentedFrame's RGB to an SDL window, scaled, flipping at vsync."""

    def __init__(self, *, scale: int = 3, vsync: bool = True, title: str = "OVERKILL - native") -> None:
        self.pygame = _require_pygame()
        import numpy as np
        self._np = np
        self.pygame.init()
        self.size = (SCREEN_WIDTH * scale, SCREEN_HEIGHT * scale)
        try:
            self.screen = self.pygame.display.set_mode(self.size, vsync=1 if vsync else 0)
        except TypeError:  # older SDL/pygame without the vsync kwarg
            self.screen = self.pygame.display.set_mode(self.size)
        self.pygame.display.set_caption(title)
        self._surf = self.pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))

    def draw(self, presented) -> None:
        # pygame.surfarray is (W,H,3); the frame is (H,W,3).
        self.pygame.surfarray.blit_array(self._surf, self._np.transpose(presented.rgb, (1, 0, 2)))
        self.pygame.transform.scale(self._surf, self.size, self.screen)
        self.pygame.display.flip()

    def pump(self) -> bool:
        """Process events; return False to quit."""
        for event in self.pygame.event.get():
            if event.type == self.pygame.QUIT:
                return False
            if event.type == self.pygame.KEYDOWN and event.key == self.pygame.K_ESCAPE:
                return False
        return True

    def set_title(self, text: str) -> None:
        self.pygame.display.set_caption(text)

    def close(self) -> None:
        self.pygame.quit()


def _decode_composed_snapshot(snapshot_bytes, frame_id):
    """Build a RenderSnapshot from a published memory snapshot (composed page only)."""
    import numpy as np
    from overkill.native_video.frame import RenderSnapshot, SceneKind
    from overkill.native_video.page_raster import decode_tandy_b800_indices
    from overkill.recovered.systems.tandy_screen import TANDY_PALETTE_RGB

    mem = np.frombuffer(snapshot_bytes, dtype=np.uint8)
    composed = decode_tandy_b800_indices(mem, B800_BASE)
    return RenderSnapshot(
        frame_id=frame_id, timestamp=time.monotonic(), scene_kind=SceneKind.GAMEPLAY,
        composed_indices=composed, composed_version=frame_id,
        palette=TANDY_PALETTE_RGB, palette_version=0, scroll_cursor=0,
    )


def _update_title(backend, display, last_title):
    now = time.monotonic()
    if now - last_title <= 0.5:
        return last_title
    d = backend.diagnostics()
    total = d.cache_hits + d.cache_misses
    display.set_title(
        f"OVERKILL native - present {d.present_fps:5.1f}Hz  source {d.source_fps:5.1f}Hz  "
        f"cache {d.cache_hits}/{total}  render {d.native_render_ms:.2f}ms"
    )
    return now


def run_native_ui(*, args, frame_sync, stop, **_ignored) -> None:
    """Native viewer: consume play.py's published frames, present via the backend.

    Runs on the main thread (SDL-safe) while play.py's emulator_loop publishes
    frames from a background thread. Decoupled: the game publishes at its cadence,
    the present loop draws at the monitor refresh (holding/caching between source
    frames). ``stop`` is the shared threading.Event; closing the window sets it.
    """
    if getattr(args, "video", "tandy") not in ("tandy", "cga"):
        print(f"native: --backend native currently decodes Tandy/CGA (B800); "
              f"--video {args.video} is not supported yet.", flush=True)
        return
    backend = NativeOverkillVideoBackend(load_config())
    display = PygameDisplay(scale=args.scale, vsync=True)
    loop = PresentationLoop(backend, display.draw)
    last_shown = 0
    source_id = 0
    last_title = 0.0
    try:
        while not stop.is_set() and display.pump():
            pending = frame_sync.take_pending()
            if pending is not None and pending[0] > last_shown:
                frame_id = pending[0]
                last_shown = frame_id
                source_id += 1
                backend.submit_source_frame(_decode_composed_snapshot(pending[1], source_id))
                frame_sync.mark_displayed(frame_id)  # unblock the emulator's publish_and_wait
            if backend.ready:
                loop.run_once()        # present + blit + vsync flip
            else:
                time.sleep(0.003)
            last_title = _update_title(backend, display, last_title)
    finally:
        display.close()


def run_snapshot(args) -> int:
    """Standalone: present one captured snapshot at the display refresh (no game loop)."""
    from dos_re.memory import Memory
    from overkill.recovered.adapters.render_snapshot_adapter import extract_render_snapshot

    snap = Path(args.snapshot)
    mem = Memory()
    mem.data[:] = (snap / "memory_1mb.bin").read_bytes()
    cpu = json.loads((snap / "state.json").read_text(encoding="utf-8"))["cpu_snapshot"]
    ds = int(re.search(r"DS=([0-9A-Fa-f]{4})", cpu).group(1), 16)

    backend = NativeOverkillVideoBackend(load_config())
    backend.submit_source_frame(extract_render_snapshot(mem, ds, frame_id=1, timestamp=time.monotonic()))
    display = PygameDisplay(scale=args.scale)
    loop = PresentationLoop(backend, display.draw)
    last_title = 0.0
    try:
        while display.pump():
            if backend.ready:
                loop.run_once()
            last_title = _update_title(backend, display, last_title)
    finally:
        display.close()
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--snapshot", required=True, help="present a single captured snapshot directory")
    p.add_argument("--scale", type=int, default=3, help="integer window scale (default 3)")
    p.epilog = "For live gameplay use: python scripts/play.py --backend native [--demo DIR]"
    args = p.parse_args(argv)
    return run_snapshot(args)


if __name__ == "__main__":
    raise SystemExit(main())
