#!/usr/bin/env python
"""Run the native video backend (modern pygame presentation of the recovered model).

This is the display adapter + session runner for ``overkill.native_video`` — the
pygame-coupled half that must stay out of the VM-independent backend package. It
opens a window and presents the backend's frames at the monitor refresh.

Modes:
  --snapshot DIR   present a single captured snapshot (the recovered frame) at the
                   display refresh — the guaranteed-runnable proof of the native
                   render+present path (no game thread).
  --demo DIR       replay a demo on a background game thread, publishing a
                   RenderSnapshot per game tick, while the main thread presents at
                   refresh (the live decoupled-loops path).

Examples:
    python scripts/native_play.py --snapshot artifacts/demos/<demo>/snapshot
    python scripts/native_play.py --demo artifacts/demos/<demo> --scale 3
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from overkill.native_video.backend import NativeOverkillVideoBackend  # noqa: E402
from overkill.native_video.config import load_config  # noqa: E402
from overkill.native_video.loop import PresentationLoop  # noqa: E402
from overkill.recovered.systems.tandy_screen import SCREEN_HEIGHT, SCREEN_WIDTH  # noqa: E402


def _require_pygame():
    try:
        import pygame  # noqa: F401
        return pygame
    except Exception as exc:  # pragma: no cover - environment dependent
        raise SystemExit(f"native_play needs pygame: {exc}")


class PygameDisplay:
    """Blit a PresentedFrame's RGB to an SDL window, scaled, flipping at vsync."""

    def __init__(self, *, scale: int = 3, vsync: bool = True, title: str = "OVERKILL — native") -> None:
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


def _load_snapshot_render(snapshot_dir: Path):
    """Extract one RenderSnapshot from a captured memory snapshot."""
    from dos_re.memory import Memory
    from overkill.recovered.adapters.render_snapshot_adapter import extract_render_snapshot

    mem = Memory()
    mem.data[:] = (snapshot_dir / "memory_1mb.bin").read_bytes()
    cpu = json.loads((snapshot_dir / "state.json").read_text(encoding="utf-8"))["cpu_snapshot"]
    ds = int(re.search(r"DS=([0-9A-Fa-f]{4})", cpu).group(1), 16)
    return extract_render_snapshot(mem, ds, frame_id=1, timestamp=time.monotonic())


def _present_on_main(backend: NativeOverkillVideoBackend, display: PygameDisplay) -> None:
    """Drive the present loop on the main thread (SDL-safe), flipping at vsync."""
    loop = PresentationLoop(backend, display.draw)
    last_title = 0.0
    while display.pump():
        if backend.ready:
            loop.run_once()  # present + blit + vsync flip
        now = time.monotonic()
        if now - last_title > 0.5:
            d = backend.diagnostics()
            display.set_title(
                f"OVERKILL native — present {d.present_fps:5.1f}Hz  source {d.source_fps:5.1f}Hz  "
                f"cache {d.cache_hits}/{d.cache_hits + d.cache_misses}  render {d.native_render_ms:.2f}ms"
            )
            last_title = now


def run_snapshot(args) -> int:
    backend = NativeOverkillVideoBackend(load_config())
    backend.submit_source_frame(_load_snapshot_render(Path(args.snapshot)))
    display = PygameDisplay(scale=args.scale, vsync=not args.no_vsync)
    try:
        _present_on_main(backend, display)
    finally:
        display.close()
    return 0


def run_demo(args) -> int:
    """Replay a demo on a background game thread; present on the main thread."""
    from dos_re.input_demo import InputDemoPlayback
    import overkill.hooks  # noqa: F401 - registers hooks
    from overkill.runtime import load_overkill_snapshot
    from overkill.recovered.adapters.render_snapshot_adapter import extract_render_snapshot

    demo = InputDemoPlayback.load(Path(args.demo))
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", demo.snapshot_path(),
                                game_root=ROOT / "assets")
    rt.cpu.trace_enabled = False
    rt.cpu.coverage_telemetry = None
    backend = NativeOverkillVideoBackend(load_config())
    stop = threading.Event()

    PRESENT_IP, TIMER_IP, RETRACE_IP = 0x3354, 0x0679, 0x50C9
    boundary_ips = {PRESENT_IP, TIMER_IP, RETRACE_IP}

    def game_thread() -> None:
        s = rt.cpu.s
        step = rt.cpu.step
        boundary = 0
        demo_boundary = 0
        demo.apply_to_runtime(0, rt)
        frame_id = 0
        while not stop.is_set():
            if s.cs == 0x1010 and s.ip in boundary_ips:
                boundary += 1
                if boundary > demo_boundary:
                    demo_boundary = boundary
                    if demo.finished(demo_boundary):
                        break
                    demo.apply_to_runtime(demo_boundary, rt)
                if s.ip == PRESENT_IP:  # one game frame produced -> publish a snapshot
                    frame_id += 1
                    backend.submit_source_frame(
                        extract_render_snapshot(rt.cpu.mem, s.ds & 0xFFFF,
                                                frame_id=frame_id, timestamp=time.monotonic())
                    )
            step()

    worker = threading.Thread(target=game_thread, name="overkill-game", daemon=True)
    worker.start()
    display = PygameDisplay(scale=args.scale, vsync=not args.no_vsync)
    try:
        _present_on_main(backend, display)
    finally:
        stop.set()
        display.close()
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--snapshot", help="present a single captured snapshot directory")
    src.add_argument("--demo", help="replay a demo live on a background game thread")
    p.add_argument("--scale", type=int, default=3, help="integer window scale (default 3)")
    p.add_argument("--no-vsync", action="store_true", help="do not request vsync")
    args = p.parse_args(argv)
    return run_demo(args) if args.demo else run_snapshot(args)


if __name__ == "__main__":
    raise SystemExit(main())
