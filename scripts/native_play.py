#!/usr/bin/env python
"""Native video backend viewer (modern pygame presentation of the recovered model).

This is the pygame-coupled half of ``overkill.native_video`` — kept out of the
VM-independent backend package. It presents the backend's frames at the monitor
refresh, forwards keyboard input to the game, and hosts the F1 settings overlay.

Live gameplay runs through ``play.py``: ``play.py --backend native [--demo DIR]``
keeps play.py's proven emulator loop + timing (timer-IRQ, pacing, the burst model)
and swaps only the viewer — :func:`run_native_ui` consumes the same ``FrameSync``
the SDL viewer does, forwards keys to the same ``keyboard`` dispatcher, and presents
via the native backend (decoupled present clock + caching + opt-in interpolation).
Standalone, ``--snapshot DIR`` presents one captured frame (no game loop).
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from overkill.native_video.backend import NativeOverkillVideoBackend  # noqa: E402
from overkill.native_video.config import load_config, save_config  # noqa: E402
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
    """An SDL window that blits scaled (200,320,3) RGB frames + overlay text."""

    def __init__(self, *, scale: int = 3, vsync: bool = True, title: str = "OVERKILL - native") -> None:
        self.pygame = _require_pygame()
        import numpy as np
        self._np = np
        self.pygame.init()
        self.pygame.font.init()
        self.scale = scale
        self.vsync = vsync
        self.title = title
        self.size = (SCREEN_WIDTH * scale, SCREEN_HEIGHT * scale)
        self._open()
        self._surf = self.pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        self.font = self.pygame.font.SysFont("consolas,monospace", 16)
        self.font_big = self.pygame.font.SysFont("consolas,monospace", 20, bold=True)

    def _open(self) -> None:
        try:
            self.screen = self.pygame.display.set_mode(self.size, vsync=1 if self.vsync else 0)
        except TypeError:  # older SDL/pygame without the vsync kwarg
            self.screen = self.pygame.display.set_mode(self.size)
        self.pygame.display.set_caption(self.title)

    def set_vsync(self, vsync: bool) -> None:
        if vsync != self.vsync:
            self.vsync = vsync
            self._open()

    def blit_frame(self, rgb) -> None:
        """Blit a (200,320,3) frame to the (scaled) back buffer (no flip)."""
        self.pygame.surfarray.blit_array(self._surf, self._np.transpose(rgb, (1, 0, 2)))
        self.pygame.transform.scale(self._surf, self.size, self.screen)

    def flip(self) -> None:
        self.pygame.display.flip()

    def draw(self, presented) -> None:
        """Blit + flip in one call (used by the standalone --snapshot path)."""
        self.blit_frame(presented.rgb)
        self.flip()

    def set_title(self, text: str) -> None:
        self.pygame.display.set_caption(text)

    def close(self) -> None:
        self.pygame.quit()


# Present-rate cycle: None = vsync (sync to monitor), 0 = uncapped, else a Hz cap.
_PRESENT_RATES = [None, 60, 120, 144, 240, 0]


def _rate_label(rate) -> str:
    if rate is None:
        return "VSync (monitor)"
    if rate == 0:
        return "Uncapped"
    return f"{rate} Hz"


class NativeOverlay:
    """F1 settings overlay drawn over the game (settings persisted to the config)."""

    def __init__(self, backend: NativeOverkillVideoBackend, display: PygameDisplay) -> None:
        self.backend = backend
        self.display = display
        self.visible = False

    def toggle(self) -> None:
        self.visible = not self.visible

    def handle_key(self, key, pygame) -> None:
        if key in (pygame.K_F1, pygame.K_ESCAPE):
            self.visible = False
        elif key in (pygame.K_LEFT, pygame.K_a):
            self._cycle_rate(-1)
        elif key in (pygame.K_RIGHT, pygame.K_d, pygame.K_RETURN, pygame.K_SPACE):
            self._cycle_rate(+1)

    def _cycle_rate(self, direction: int) -> None:
        cur = self.backend.config.target_present_hz
        idx = _PRESENT_RATES.index(cur) if cur in _PRESENT_RATES else 0
        new = _PRESENT_RATES[(idx + direction) % len(_PRESENT_RATES)]
        cfg = dataclasses.replace(self.backend.config, target_present_hz=new, present_vsync=(new is None))
        self.backend.config = cfg
        save_config(cfg)

    def draw(self) -> None:
        pygame = self.display.pygame
        w, h = self.display.size
        panel = pygame.Surface((w, h), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 180))
        y = 24
        panel.blit(self.display.font_big.render("NATIVE BACKEND   -   F1 to close", True, (255, 255, 0)), (24, y))
        y += 42
        panel.blit(self.display.font.render(
            f"> Present rate:  {_rate_label(self.backend.config.target_present_hz)}   "
            f"(Left/Right to change)", True, (120, 255, 120)), (24, y))
        y += 38
        d = self.backend.diagnostics()
        total = d.cache_hits + d.cache_misses
        for line in (
            f"present {d.present_fps:6.1f} Hz     source {d.source_fps:6.1f} Hz",
            f"render  {d.native_render_ms:5.2f} ms     cache {d.cache_hits}/{total}",
            "",
            "Object interpolation: WIP - needs the sprite/background",
            "separation lift (sprites are baked into the page).",
        ):
            panel.blit(self.display.font.render(line, True, (180, 200, 255)), (24, y))
            y += 24
        self.display.screen.blit(panel, (0, 0))


def _decode_composed_snapshot(snapshot_bytes, frame_id):
    """Fast path: a RenderSnapshot with only the composed page (no interpolation)."""
    import numpy as np
    from overkill.native_video.frame import RenderSnapshot, SceneKind
    from overkill.native_video.page_raster import decode_tandy_b800_indices
    from overkill.recovered.systems.tandy_screen import TANDY_PALETTE_RGB

    composed = decode_tandy_b800_indices(np.frombuffer(snapshot_bytes, dtype=np.uint8), B800_BASE)
    return RenderSnapshot(
        frame_id=frame_id, timestamp=time.monotonic(), scene_kind=SceneKind.GAMEPLAY,
        composed_indices=composed, composed_version=frame_id,
        palette=TANDY_PALETTE_RGB, palette_version=0, scroll_cursor=0,
    )


def _build_source_frame(snapshot_bytes, frame_id, backend, live_ds):
    """Build the source frame from the composed page (the faithful frame).

    Object interpolation (interpolating sprite positions between frames) needs the
    sprite/background separation lift — until then the live path presents the
    faithful composed frame and the present clock only decouples/holds (no
    in-between motion is invented).
    """
    return _decode_composed_snapshot(snapshot_bytes, frame_id)


def _update_title(backend, display, last_title):
    now = time.monotonic()
    if now - last_title <= 0.5:
        return last_title
    d = backend.diagnostics()
    total = d.cache_hits + d.cache_misses
    display.set_title(
        f"OVERKILL native - present {d.present_fps:5.1f}Hz  source {d.source_fps:5.1f}Hz  "
        f"cache {d.cache_hits}/{total}  render {d.native_render_ms:.2f}ms   [F1 settings]"
    )
    return now


def run_native_ui(*, args, frame_sync, stop, keyboard=None, live_ds=None, **_ignored) -> None:
    """Native viewer: consume play.py's frames, forward input, present + overlay.

    Runs on the main thread while play.py's emulator_loop publishes frames from a
    background thread. Keys are posted to play.py's ``keyboard`` dispatcher (the
    emulator loop pumps them); F1 toggles the settings overlay.
    """
    if getattr(args, "video", "tandy") not in ("tandy", "cga"):
        print(f"native: --backend native currently decodes Tandy/CGA (B800); "
              f"--video {args.video} is not supported yet.", flush=True)
        return
    pygame = _require_pygame()
    from sdl_view import _build_pygame_scan
    scan = _build_pygame_scan()

    backend = NativeOverkillVideoBackend(load_config())
    display = PygameDisplay(scale=args.scale, vsync=backend.config.target_present_hz is None)
    overlay = NativeOverlay(backend, display)
    last_shown = 0
    source_id = 0
    last_title = 0.0
    next_present = time.monotonic()
    print("native: window up - WASD/arrows + Z/Space play; F1 = settings; close window to quit", flush=True)
    try:
        running = True
        while running and not stop.is_set():
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    running = False
                elif ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_F1:
                        overlay.toggle()
                    elif overlay.visible:
                        overlay.handle_key(ev.key, pygame)
                    elif keyboard is not None:
                        sc = scan.get(ev.key)
                        if sc is not None:
                            keyboard.post_down(sc)
                elif ev.type == pygame.KEYUP:
                    if not overlay.visible and keyboard is not None:
                        sc = scan.get(ev.key)
                        if sc is not None:
                            keyboard.post_up(sc)

            pending = frame_sync.take_pending()
            if pending is not None and pending[0] > last_shown:
                last_shown = pending[0]
                source_id += 1
                backend.submit_source_frame(_build_source_frame(pending[1], source_id, backend, live_ds))
                frame_sync.mark_displayed(pending[0])  # unblock the emulator's publish_and_wait

            # Present-rate control (decoupled from the source): VSync syncs the flip
            # to the monitor; a Hz cap paces manually with vsync off; uncapped free-runs.
            target = backend.config.target_present_hz
            want_vsync = target is None
            if display.vsync != want_vsync:
                display.set_vsync(want_vsync)
                next_present = time.monotonic()

            if backend.ready:
                presented = backend.present(time.monotonic())
                display.blit_frame(presented.rgb)
                if overlay.visible:
                    overlay.draw()
                display.flip()
            else:
                time.sleep(0.003)

            if target and target > 0:  # explicit Hz cap (vsync off): pace to it
                now = time.monotonic()
                if now < next_present:
                    time.sleep(next_present - now)
                next_present = max(next_present + 1.0 / target, time.monotonic())
            else:
                next_present = time.monotonic()

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
    pygame = display.pygame
    last_title = 0.0
    try:
        running = True
        while running:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                    running = False
            if backend.ready:
                display.draw(backend.present(time.monotonic()))
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
