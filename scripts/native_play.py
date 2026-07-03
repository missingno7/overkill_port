#!/usr/bin/env python
"""Native video backend viewer (modern pygame presentation of the recovered model).

The native backend presents at the monitor refresh, decoupled from the VM. Because
the pure-Python VM and the present loop cannot both have the GIL, the VM runs in a
*separate process*: ``play.py --backend native`` becomes the **presenter** parent
(this module's :func:`run_native_present`) and spawns a **VM child**
(``play.py --backend native --mp-publish <shm>``) whose
:func:`run_publisher` writes composed frames into a shared-memory channel. The
presenter free-runs and (later) interpolates between the child's frames.

Standalone, ``--snapshot DIR`` presents one captured frame (no VM).
"""
from __future__ import annotations

import argparse
import json
import re
import struct
import subprocess
import sys
import time
from multiprocessing import shared_memory
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from overkill.native_video.backend import NativeOverkillVideoBackend  # noqa: E402
from overkill.native_video.config import load_config, save_config  # noqa: E402
from overkill.recovered.systems.tandy_screen import SCREEN_HEIGHT, SCREEN_WIDTH  # noqa: E402

B800_BASE = 0xB8000
_FRAME_BYTES = SCREEN_WIDTH * SCREEN_HEIGHT  # 320x200 indexed (uint8)
_SLOTS = 3                                    # triple buffer (tear-free single-writer/reader)
_HEADER = 16                                  # counter (8) + reserved


class FrameChannel:
    """Lock-free shared-memory frame hand-off from the VM child to the presenter.

    The child writes the composed indexed frame to slot ``(counter+1) % 3`` then
    publishes the new counter; the presenter reads ``counter % 3``. With three
    slots the writer never overwrites the slot the reader is on, so no lock is
    needed for one writer + one reader.
    """

    def __init__(self, *, name: str | None = None, create: bool = False) -> None:
        if create:
            self.shm = shared_memory.SharedMemory(create=True, size=_HEADER + _SLOTS * _FRAME_BYTES)
            struct.pack_into("q", self.shm.buf, 0, 0)
        else:
            self.shm = shared_memory.SharedMemory(name=name)
        self.name = self.shm.name

    def write(self, frame_bytes: bytes) -> None:
        counter = struct.unpack_from("q", self.shm.buf, 0)[0]
        slot = (counter + 1) % _SLOTS
        off = _HEADER + slot * _FRAME_BYTES
        self.shm.buf[off:off + _FRAME_BYTES] = frame_bytes
        struct.pack_into("q", self.shm.buf, 0, counter + 1)  # publish only after the copy

    def peek_counter(self) -> int:
        """The current frame counter (cheap; no frame copy) — used to skip the
        64 KB copy when no new frame has arrived."""
        return struct.unpack_from("q", self.shm.buf, 0)[0]

    def read(self):
        counter = self.peek_counter()
        if counter == 0:
            return 0, None
        slot = counter % _SLOTS
        off = _HEADER + slot * _FRAME_BYTES
        return counter, bytes(self.shm.buf[off:off + _FRAME_BYTES])

    def close(self) -> None:
        self.shm.close()

    def unlink(self) -> None:
        try:
            self.shm.unlink()
        except FileNotFoundError:
            pass


_KEY_EVENT_CAPACITY = 256  # ring buffer slots; far more than one frame's worth of key taps
_KEY_EVENT_HEADER = 8      # write_index (u32) + read_index (u32)


class KeyEventChannel:
    """Lock-free shared-memory scan-code event queue, presenter -> VM child.

    ``--backend native`` splits the interactive session into a presenter process
    (owns the visible window and therefore real OS keyboard focus) and a VM child
    process (runs the emulator; headless, no window of its own -- see
    :func:`run_publisher`). Without this channel the presenter's key events had
    nowhere to go: it only handled its own hotkeys (F1/F11) and the VM child never
    read a keyboard at all, so gameplay input was silently dropped end to end.

    Each event is one byte using the XT make/break convention already used by
    ``dos_re.interrupts.deliver_scancode`` throughout this project: bits 0-6 are
    the scan code, bit 7 set means release. One writer (the presenter) advances
    the write index, one reader (the VM child) advances the read index, so no
    lock is needed.
    """

    def __init__(self, *, name: str | None = None, create: bool = False) -> None:
        if create:
            self.shm = shared_memory.SharedMemory(create=True, size=_KEY_EVENT_HEADER + _KEY_EVENT_CAPACITY)
            struct.pack_into("<II", self.shm.buf, 0, 0, 0)
        else:
            self.shm = shared_memory.SharedMemory(name=name)
        self.name = self.shm.name

    def post(self, event_byte: int) -> None:
        """Writer side (presenter): push one scan-code event byte."""
        w, r = struct.unpack_from("<II", self.shm.buf, 0)
        nxt = (w + 1) % _KEY_EVENT_CAPACITY
        if nxt == r:
            return  # ring full (a stuck reader) -- drop rather than block the presenter
        self.shm.buf[_KEY_EVENT_HEADER + w] = event_byte & 0xFF
        struct.pack_into("<I", self.shm.buf, 0, nxt)

    def drain(self) -> list[int]:
        """Reader side (VM child): pop every pending event byte."""
        w, r = struct.unpack_from("<II", self.shm.buf, 0)
        out = []
        while r != w:
            out.append(self.shm.buf[_KEY_EVENT_HEADER + r])
            r = (r + 1) % _KEY_EVENT_CAPACITY
        struct.pack_into("<I", self.shm.buf, 4, r)
        return out

    def close(self) -> None:
        self.shm.close()

    def unlink(self) -> None:
        try:
            self.shm.unlink()
        except FileNotFoundError:
            pass


def _require_pygame():
    try:
        import pygame  # noqa: F401
        return pygame
    except Exception as exc:  # pragma: no cover - environment dependent
        raise SystemExit(f"native_play needs pygame: {exc}")


def _raise_timer_resolution():
    """Windows ``time.sleep`` is ~15.6 ms-granular by default (the GetTickCount64
    period that also made ``time.monotonic`` read ~64 Hz); raise it to ~1 ms so the
    capped present pacing is accurate. No-op off Windows / on failure."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.winmm.timeBeginPeriod(1)
        except Exception:  # pragma: no cover - environment dependent
            pass


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
        self.fullscreen = False
        self.title = title
        self.size = (SCREEN_WIDTH * scale, SCREEN_HEIGHT * scale)
        self._open()
        self._surf = self.pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        self.font = self.pygame.font.SysFont("consolas,monospace", 16)
        self.font_big = self.pygame.font.SysFont("consolas,monospace", 20, bold=True)

    def _open(self) -> None:
        pygame = self.pygame
        # SCALED renders at the logical size (self.size) and GPU-scales it to the
        # actual window preserving aspect ratio (letterboxed); RESIZABLE lets the
        # window be dragged/maximised. FULLSCREEN+SCALED fills the monitor.
        flags = (pygame.FULLSCREEN | pygame.SCALED) if self.fullscreen else (pygame.SCALED | pygame.RESIZABLE)
        try:
            self.screen = pygame.display.set_mode(self.size, flags, vsync=1 if self.vsync else 0)
        except TypeError:
            self.screen = pygame.display.set_mode(self.size, flags)
        except pygame.error:
            # fullscreen / SCALED renderer creation can fail on some drivers; fall
            # back to a plain resizable window instead of crashing the presenter.
            self.fullscreen = False
            self.screen = pygame.display.set_mode(self.size, pygame.RESIZABLE)
        pygame.display.set_caption(self.title)

    def set_vsync(self, vsync: bool) -> None:
        if vsync != self.vsync:
            self.vsync = vsync
            self._open()

    def toggle_fullscreen(self) -> None:
        self.fullscreen = not self.fullscreen
        self._open()

    def blit_frame(self, rgb) -> None:
        self.pygame.surfarray.blit_array(self._surf, self._np.transpose(rgb, (1, 0, 2)))
        self.pygame.transform.scale(self._surf, self.size, self.screen)

    def flip(self) -> None:
        self.pygame.display.flip()

    def draw(self, presented) -> None:
        self.blit_frame(presented.rgb)
        self.flip()

    def set_title(self, text: str) -> None:
        self.pygame.display.set_caption(text)

    def close(self) -> None:
        self.pygame.quit()


_PRESENT_RATES = [None, 60, 120, 144, 240, 0]  # None = vsync, 0 = uncapped


def _rate_label(rate) -> str:
    if rate is None:
        return "VSync (monitor)"
    return "Uncapped" if rate == 0 else f"{rate} Hz"


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
        import dataclasses
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
            "Object interpolation: WIP (needs the sprite lift, in progress)",
        ):
            panel.blit(self.display.font.render(line, True, (180, 200, 255)), (24, y))
            y += 24
        self.display.screen.blit(panel, (0, 0))


def _update_title(backend, display, last_title, loop_fps=0.0, flip_ms=0.0):
    now = time.perf_counter()
    if now - last_title <= 0.5:
        return last_title
    d = backend.diagnostics()
    total = d.cache_hits + d.cache_misses
    display.set_title(
        f"OVERKILL native - present {d.present_fps:5.1f}Hz  source {d.source_fps:5.1f}Hz  "
        f"loop {loop_fps:6.0f}Hz  flip {flip_ms:4.1f}ms  "
        f"cache {d.cache_hits}/{total}  render {d.native_render_ms:.2f}ms   [F1 settings]"
    )
    return now


def _composed_snapshot(composed_indices, frame_id):
    from overkill.native_video.frame import RenderSnapshot, SceneKind
    from overkill.recovered.systems.tandy_screen import TANDY_PALETTE_RGB
    return RenderSnapshot(
        frame_id=frame_id, timestamp=time.perf_counter(), scene_kind=SceneKind.GAMEPLAY,
        composed_indices=composed_indices, composed_version=frame_id,
        palette=TANDY_PALETTE_RGB, palette_version=0, scroll_cursor=0,
    )


# ----- VM child: publish composed frames into the shared-memory channel ----------

def run_publisher(channel_name, *, frame_sync, stop, video="tandy",
                  input_channel_name=None, keyboard=None) -> None:
    """Child side (inside play.py's VM process): consume play.py's published frames
    and write the composed indexed page into the shared-memory channel.

    ``input_channel_name``/``keyboard``: this process is headless (no window, so no
    keyboard focus of its own); if the presenter forwarded a :class:`KeyEventChannel`,
    drain it every loop and feed the same ``KeyDispatcher`` the interactive
    ``play.py`` loop already pumps into the VM each frame -- the only missing link
    for native-backend gameplay input (see :class:`KeyEventChannel`).
    """
    import numpy as np
    from overkill.native_video.page_raster import decode_tandy_b800_indices
    channel = FrameChannel(name=channel_name)
    input_channel = KeyEventChannel(name=input_channel_name) if input_channel_name else None
    last_shown = 0
    try:
        while not stop.is_set():
            if input_channel is not None and keyboard is not None:
                for event_byte in input_channel.drain():
                    if event_byte & 0x80:
                        keyboard.post_up(event_byte & 0x7F)
                    else:
                        keyboard.post_down(event_byte)
            pending = frame_sync.take_pending()
            if pending is not None and pending[0] > last_shown:
                last_shown = pending[0]
                composed = decode_tandy_b800_indices(np.frombuffer(pending[1], dtype=np.uint8), B800_BASE)
                channel.write(np.ascontiguousarray(composed, dtype=np.uint8).tobytes())
                frame_sync.mark_displayed(pending[0])  # unblock the emulator (no viewer wait)
            else:
                time.sleep(0.001)
    finally:
        channel.close()
        if input_channel is not None:
            input_channel.close()


# ----- Presenter parent: free-run the present loop reading the channel -----------

def run_native_present(channel, *, args, input_channel=None) -> None:
    """Parent side: present the child's frames at the monitor refresh (decoupled).

    This process owns the visible window, so it is the only one with real OS
    keyboard focus; ``input_channel`` (a :class:`KeyEventChannel`), when given,
    forwards gameplay key events to the headless VM child (see
    :func:`run_publisher`). F1/F11 and, while the settings overlay is open, every
    other key stay local (unchanged) -- only keys the overlay does not consume are
    forwarded as gameplay input.
    """
    import numpy as np
    from sdl_view import _build_pygame_scan
    _raise_timer_resolution()
    pygame = _require_pygame()
    backend = NativeOverkillVideoBackend(load_config())
    display = PygameDisplay(scale=args.scale, vsync=backend.config.target_present_hz is None)
    overlay = NativeOverlay(backend, display)
    scan_map = _build_pygame_scan() if input_channel is not None else {}
    last_counter = 0
    source_id = 0
    last_title = 0.0
    next_present = time.perf_counter()
    loop_n = 0
    loop_t0 = time.perf_counter()
    loop_fps = 0.0
    flip_ms = 0.0
    acc = {"chan": 0.0, "present": 0.0, "blit": 0.0, "flip": 0.0, "pace": 0.0, "n": 0, "distinct": 0}
    diag_t0 = time.perf_counter()
    print("native: presenter up - F1 = settings; close window to quit", flush=True)
    try:
        running = True
        while running:
            loop_n += 1
            if loop_n >= 120:  # sample the raw loop iteration rate (independent of present)
                now = time.perf_counter()
                loop_fps = loop_n / (now - loop_t0)
                loop_n, loop_t0 = 0, now
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    running = False
                elif ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_F1:
                        overlay.toggle()
                    elif ev.key == pygame.K_F11:
                        display.toggle_fullscreen()
                    elif overlay.visible:
                        overlay.handle_key(ev.key, pygame)
                    elif input_channel is not None:
                        sc = scan_map.get(ev.key)
                        if sc is not None:
                            input_channel.post(sc)
                elif ev.type == pygame.KEYUP and not overlay.visible and input_channel is not None:
                    sc = scan_map.get(ev.key)
                    if sc is not None:
                        input_channel.post(sc | 0x80)

            t0 = time.perf_counter()
            if channel.peek_counter() > last_counter:  # new VM frame -> decode it
                counter, frame = channel.read()
                if counter > last_counter:
                    last_counter = counter
                    source_id += 1
                    composed = np.frombuffer(frame, dtype=np.uint8).reshape(SCREEN_HEIGHT, SCREEN_WIDTH)
                    backend.submit_source_frame(_composed_snapshot(composed, source_id))
            t_chan = time.perf_counter()

            target = backend.config.target_present_hz
            want_vsync = target is None
            if display.vsync != want_vsync:
                display.set_vsync(want_vsync)
                next_present = time.perf_counter()

            t_pres = t_blit = t_chan
            if backend.ready:
                presented = backend.present(time.perf_counter())
                if not presented.from_cache:   # a newly rendered frame = real content change
                    acc["distinct"] += 1
                t_pres = time.perf_counter()
                display.blit_frame(presented.rgb)
                if overlay.visible:
                    overlay.draw()
                t_blit = time.perf_counter()
                display.flip()
                flip_ms = (time.perf_counter() - t_blit) * 1000.0  # ~16ms => the flip is the cap
            else:
                time.sleep(0.003)
            t_flip = time.perf_counter()

            if target and target > 0:
                now = time.perf_counter()
                if now < next_present:
                    time.sleep(next_present - now)
                next_present = max(next_present + 1.0 / target, time.perf_counter())
            else:
                next_present = time.perf_counter()

            t_pace = time.perf_counter()
            acc["chan"] += t_chan - t0
            acc["present"] += t_pres - t_chan
            acc["blit"] += t_blit - t_pres
            acc["flip"] += t_flip - t_blit
            acc["pace"] += t_pace - t_flip
            acc["n"] += 1
            if t_pace - diag_t0 >= 2.0:  # per-section breakdown to find any cap
                n = max(1, acc["n"])
                window = t_pace - diag_t0
                d = backend.diagnostics()
                # content = distinct rendered frames/sec; == source until interpolation
                # adds in-between frames (then it climbs toward present).
                print(f"native diag: loop={loop_fps:6.0f}Hz present={d.present_fps:6.1f}Hz "
                      f"content={acc['distinct']/window:5.1f}Hz source={d.source_fps:5.1f}Hz "
                      f"vsync={display.vsync} target={target} | per-iter ms: "
                      f"chan={acc['chan']/n*1e3:.2f} present={acc['present']/n*1e3:.2f} "
                      f"blit={acc['blit']/n*1e3:.2f} flip={acc['flip']/n*1e3:.2f} pace={acc['pace']/n*1e3:.2f}",
                      flush=True)
                acc = {"chan": 0.0, "present": 0.0, "blit": 0.0, "flip": 0.0, "pace": 0.0, "n": 0, "distinct": 0}
                diag_t0 = t_pace

            last_title = _update_title(backend, display, last_title, loop_fps, flip_ms)
    finally:
        display.close()


def run_mp(args) -> int:
    """Parent launcher: spawn the VM child process and present its frames."""
    channel = FrameChannel(create=True)
    # Demo replay drives input from the recorded file, not the keyboard (matching the
    # existing interactive/verify convention); only forward live keys otherwise.
    input_channel = KeyEventChannel(create=True) if not getattr(args, "demo", None) else None
    cmd = [sys.executable, str(ROOT / "scripts" / "play.py"), "--backend", "native",
           "--mp-publish", channel.name, "--video", getattr(args, "video", "tandy")]
    if input_channel is not None:
        cmd += ["--mp-input", input_channel.name]
    if getattr(args, "demo", None):
        cmd += ["--demo", args.demo]
    if getattr(args, "sound", None):
        cmd += ["--sound", args.sound]
    if getattr(args, "snapshot", None):
        cmd += ["--snapshot", args.snapshot]
    print("native: launching VM child (decoupled present): " + " ".join(cmd), flush=True)
    child = subprocess.Popen(cmd)
    try:
        run_native_present(channel, args=args, input_channel=input_channel)
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.kill()
        channel.close()
        channel.unlink()
        if input_channel is not None:
            input_channel.close()
            input_channel.unlink()
    return 0


def run_snapshot(args) -> int:
    """Standalone: present one captured snapshot at the display refresh (no VM)."""
    from dos_re.memory import Memory
    from overkill.recovered.adapters.render_snapshot_adapter import extract_render_snapshot

    snap = Path(args.snapshot)
    mem = Memory()
    mem.data[:] = (snap / "memory_1mb.bin").read_bytes()
    cpu = json.loads((snap / "state.json").read_text(encoding="utf-8"))["cpu_snapshot"]
    ds = int(re.search(r"DS=([0-9A-Fa-f]{4})", cpu).group(1), 16)

    backend = NativeOverkillVideoBackend(load_config())
    backend.submit_source_frame(extract_render_snapshot(mem, ds, frame_id=1, timestamp=time.perf_counter()))
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
                display.draw(backend.present(time.perf_counter()))
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
