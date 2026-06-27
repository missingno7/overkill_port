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
            loop.run_once()       # present + blit + vsync flip (vsync paces + yields the GIL)
        else:
            time.sleep(0.005)     # nothing to show yet — yield to the booting game thread
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


# Boundary IPs that mark a stable instruction point to sample the frame at. The
# menu/scenes don't fire the gameplay present (3354) — they advance via the
# timer/retrace waits — so sampling on any of these (throttled) captures every
# scene, not just gameplay.
_BOUNDARY_IPS = {0x3354, 0x0679, 0x50C9}
_RETRACE_IP = 0x50C9          # the per-frame vsync wait — pace realtime here
_SOURCE_PUBLISH_HZ = 70.0
_TARGET_TICK_HZ = 60.0        # pace the VM to ~realtime (and yield the GIL)


def _run_game_loop(rt, backend, stop, demo=None) -> None:
    """Step the runtime; pace it to realtime and publish a throttled RenderSnapshot.

    The pure-Python VM can run faster than realtime, so we pace it at the retrace
    boundary (one per frame) to ``_TARGET_TICK_HZ`` — the sleep both keeps the game
    at a watchable speed AND yields the GIL so the main present thread runs smoothly.
    With ``demo`` set, also drives the recorded input boundary clock. Snapshots are
    published wall-clock throttled (~70 Hz) at a boundary IP (stable read point) so
    every scene (menu/gameplay) is captured.
    """
    from overkill.recovered.adapters.render_snapshot_adapter import extract_render_snapshot

    s = rt.cpu.s
    step = rt.cpu.step
    boundary = 0
    demo_boundary = 0
    if demo is not None:
        demo.apply_to_runtime(0, rt)
    frame_id = 0
    last_pub = 0.0
    pub_period = 1.0 / _SOURCE_PUBLISH_HZ
    tick_period = 1.0 / _TARGET_TICK_HZ
    next_tick = time.monotonic()
    while not stop.is_set():
        if s.cs == 0x1010 and s.ip in _BOUNDARY_IPS:
            if demo is not None:
                boundary += 1
                if boundary > demo_boundary:
                    demo_boundary = boundary
                    if demo.finished(demo_boundary):
                        break
                    demo.apply_to_runtime(demo_boundary, rt)
            if s.ip == _RETRACE_IP:  # one retrace ~ one frame: pace + yield the GIL
                now = time.monotonic()
                if now < next_tick:
                    time.sleep(next_tick - now)
                    now = time.monotonic()
                next_tick = max(next_tick + tick_period, now)
            now = time.monotonic()
            if now - last_pub >= pub_period:
                last_pub = now
                frame_id += 1
                backend.submit_source_frame(
                    extract_render_snapshot(rt.cpu.mem, s.ds & 0xFFFF, frame_id=frame_id, timestamp=now)
                )
        step()


def _run_live(rt, args, *, demo=None, title="OVERKILL — native") -> int:
    """Run the game on a background thread, present on the main thread."""
    rt.cpu.trace_enabled = False
    rt.cpu.coverage_telemetry = None
    backend = NativeOverkillVideoBackend(load_config())
    # Open the window FIRST so the (slow, pkg_resources-heavy) pygame import runs
    # unimpeded; only then start the GIL-heavy game thread. Starting the game thread
    # first starves the import and looks like a hang.
    print("native: opening window...", flush=True)
    display = PygameDisplay(scale=args.scale, vsync=not args.no_vsync, title=title)
    stop = threading.Event()
    worker = threading.Thread(target=_run_game_loop, args=(rt, backend, stop),
                              kwargs={"demo": demo}, name="overkill-game", daemon=True)
    worker.start()
    print("native: window up; running game thread (Esc / close window to quit)", flush=True)
    try:
        _present_on_main(backend, display)
    finally:
        stop.set()
        worker.join(timeout=2.0)
        display.close()
    return 0


def run_demo(args) -> int:
    """Replay a demo live: game on a background thread, present on the main thread."""
    from dos_re.input_demo import InputDemoPlayback
    import overkill.hooks  # noqa: F401 - registers hooks
    from overkill.runtime import load_overkill_snapshot

    demo = InputDemoPlayback.load(Path(args.demo))
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", demo.snapshot_path(),
                                game_root=ROOT / "assets")
    return _run_live(rt, args, demo=demo)


def run_cold(args) -> int:
    """Cold-boot the game and present it natively (intro -> title -> menu -> attract).

    Boot is slow (asset decode runs at interpreter speed), so expect a blank window
    until the first frame; input is not forwarded yet, so the game runs autonomously.
    """
    import overkill.hooks  # noqa: F401 - registers hooks
    from overkill.launch import build_command_tail
    from overkill.runtime import create_overkill_runtime

    rt = create_overkill_runtime(ROOT / "assets" / "OVERKILL", game_root=ROOT / "assets",
                                 command_tail=build_command_tail("tandy", "pc"))
    return _run_live(rt, args, demo=None, title="OVERKILL — native (cold boot)")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    src = p.add_mutually_exclusive_group()
    src.add_argument("--snapshot", help="present a single captured snapshot directory")
    src.add_argument("--demo", help="replay a demo live on a background game thread")
    src.add_argument("--cold", action="store_true", help="cold-boot the game and present it natively")
    p.add_argument("--scale", type=int, default=3, help="integer window scale (default 3)")
    p.add_argument("--no-vsync", action="store_true", help="do not request vsync")
    args = p.parse_args(argv)
    if args.demo:
        return run_demo(args)
    if args.snapshot:
        return run_snapshot(args)
    return run_cold(args)  # default: cold boot


if __name__ == "__main__":
    raise SystemExit(main())
