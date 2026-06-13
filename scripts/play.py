"""Interactive OVERKILL viewer: run the emulator live and control it.

The interpreter runs on a background thread so the UI remains responsive during
long bursts spent decoding the next screen.  Gameplay is paced from the game's
modelled timer wait (``1010:0679``), while intro/menu/transition screens also
pace from the VGA retrace wait (``1010:50C9``).  Visible video-memory snapshots
(CGA ``B800h`` or EGA ``A000h`` shadow planes) are published to the SDL viewer
thread whenever a timed boundary changed the screen, and the emulator waits until
that exact snapshot is consumed before continuing.  That
producer/consumer handoff prevents the emulator from executing several visible
states before the UI/input side gets a chance to react.

Threading model (CPython GIL keeps this safe):
  * emulator thread: the only thread that mutates CPU/DOS/memory; runs the game
    one visible/timed boundary at a time and delivers queued key scan codes via
    the game's installed INT 09h handler.  Gameplay normally reaches the PIT
    timer wait at 1010:0679 once per frame, but intro/menu/transition code also
    uses the VGA retrace wait at 1010:50C9 for timing and can modify B800h
    without going through the gameplay timer path;
  * UI thread: renders the latest published immutable memory snapshot and then
    wakes the emulator so the next frame can execute; key events go through a
    frame-accurate KeyDispatcher.

Controls: Q/A/O/P move, Z or Space fire (the game's own scheme), F12 saves a
runtime snapshot.  Esc and any other key are forwarded too (full keyboard), in
case a screen wants them.

Run:
    python scripts/play.py [--video cga|ega|tandy] [--game-hz 30] [--fps 30] [--palette 1h] [--scale 2]
"""
from __future__ import annotations

import argparse
from datetime import datetime
from queue import Empty, SimpleQueue
import sys
import threading
import time
import traceback
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from overkill_port.interrupts import deliver_scancode
from overkill_port.keyboard import KeyDispatcher
from overkill_port.hook_verify import HookVerifierConfig, install_hook_verifier, parse_addr as parse_verify_addr
from overkill_port.dos import ConsoleInputWouldBlock
from overkill_port.cpu import HaltExecution
from overkill_port.runtime import create_runtime
from overkill_port.snapshot import load_snapshot, write_snapshot
from overkill_port.memory import EGA_APERTURE, EGA_SHADOW_SIZE
from overkill_port.coverage import (
    CoverageDashboardTk,
    CoverageTelemetry,
    OverkillCoverageClassifier,
)
from overkill_port.games.overkill.sounds import AsyncTimerIrqDriver, OVERKILL_PIT_HZ
from render_cga import CGA_PALETTES

CGA_PRESENT_HOOK = (0x1010, 0x447B)  # mode-0 CGA frame-present blit
EGA_PRESENT_HOOK = (0x1010, 0x2750)  # mode-1 EGA frame-present blit
TANDY_PRESENT_HOOK = (0x1010, 0x3354)  # mode-2 Tandy frame-present blit
TIMER_WAIT_HOOK = (0x1010, 0x0679)  # game frame/timer wait; one call == one logical frame
RETRACE_WAIT_HOOK = (0x1010, 0x50C9)  # VGA retrace wait used heavily by intro/menu/transitions
B800_BASE = 0xB8000
B800_SIZE = 0x4000
A000_BASE = EGA_APERTURE
TANDY_SIZE = 0x8000

# 58DF is verified for CGA and is important for collapsing post-copy/retrace
# loading bursts on the planet/difficulty selection screen.  Keep it enabled for
# default CGA play, but remove it below for EGA/Tandy because that lifted loop is
# currently mode-0-only.  The CCAA/CCC4/CCF0 dirty-copy helpers are left enabled:
# their earlier suspicion was downstream of the old EGA shadow-plane aliasing.
NON_CGA_INTERACTIVE_DISABLE = {
    (0x1010, 0x58DF),
}


class TimerPacer:
    """Throttle the game to ``hz`` frames/second."""

    def __init__(self, hz: float) -> None:
        self.period = 1.0 / hz if hz > 0 else 0.0
        self._next: float | None = None

    def __call__(self, units: int = 1, *, poll=None, poll_interval: float | None = None) -> None:
        if self.period <= 0:
            return
        units = max(1, int(units))
        period = self.period * units
        now = time.perf_counter()
        if self._next is None:
            self._next = now + period
            return
        delay = self._next - now
        if delay > 0:
            if poll is None:
                time.sleep(delay)
            else:
                deadline = now + delay
                interval = poll_interval if poll_interval is not None else min(delay, 0.005)
                interval = max(0.001, float(interval))
                while True:
                    remaining = deadline - time.perf_counter()
                    if remaining <= 0:
                        break
                    time.sleep(min(remaining, interval))
                    poll()
            self._next += period
        else:
            self._next = now + period  # fell behind (e.g. after a load): resync


class FramePresented(Exception):
    """Internal control-flow signal used to stop CPU.run exactly at one frame."""


class FrameSync:
    """One-frame-at-a-time handoff from emulator thread to the viewer thread.

    The previous player let the emulator keep executing while the UI sampled video
    memory on its own timer.  If the UI was late, several emulated presents could be
    overwritten before one was shown, producing the exact symptom reported by the
    user: intro/menu animations looked unpaced and key presses were hard to land.
    """

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._next_id = 0
        self._displayed_id = 0
        self._pending: tuple[int, bytes, int] | None = None
        self._closed = False

    def publish_and_wait(self, memory: bytearray, *, display_start: int = 0) -> None:
        snapshot = bytes(memory)
        with self._cond:
            if self._closed:
                return
            self._next_id += 1
            frame_id = self._next_id
            self._pending = (frame_id, snapshot, display_start & 0xFFFF)
            self._cond.notify_all()
            while not self._closed and self._displayed_id < frame_id:
                self._cond.wait(timeout=0.25)

    def take_pending(self) -> tuple[int, bytes, int] | None:
        with self._cond:
            return self._pending

    def mark_displayed(self, frame_id: int) -> None:
        with self._cond:
            if frame_id > self._displayed_id:
                self._displayed_id = frame_id
            if self._pending is not None and self._pending[0] <= self._displayed_id:
                self._pending = None
            self._cond.notify_all()

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify_all()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Interactive CGA/EGA/Tandy viewer for the OVERKILL runtime")
    p.add_argument("--video", choices=("cga", "ega", "tandy"), default="tandy",
                   help="launch/render the original game in CGA, EGA, or Tandy mode (default: tandy)")
    p.add_argument("--dos-args", default=None,
                   help="override the PSP command tail passed to the original EXE, e.g. ' /E'")
    p.add_argument("--game-hz", type=float, default=36.4,
                   help="real-time game speed (frames/sec); original timer cadence is ~36.4. Lower if choppy.")
    p.add_argument("--fps", type=int, default=30, help="legacy option; timing is controlled by --game-hz")
    p.add_argument("--palette", default="1h", choices=sorted(CGA_PALETTES))
    p.add_argument("--scale", type=int, default=2)
    p.add_argument("--frame-budget", type=int, default=6_000_000,
                   help="max interpreted steps to wait for one frame before reporting a stall")
    p.add_argument("--cpu-chunk-steps", type=int, default=1000,
                   help="interpreted steps per cooperative UI/sound poll while waiting for a boundary")
    p.add_argument("--snapshot", default=None,
                   help="load a saved snapshot dir to skip the ~11s asset-decode bootstrap")
    p.add_argument("--save-snapshot-root", default=str(ROOT / "artifacts"),
                   help="root directory for F12 runtime snapshots")
    p.add_argument("--no-present-sync", action="store_true",
                   help="debug only: do not wait for the viewer to consume each timer-frame snapshot")
    p.add_argument("--retrace-hz", type=float, default=None,
                   help="pace VGA retrace waits used by intro/menu; defaults to --game-hz")
    p.add_argument("--verify-hooks", action="store_true",
                   help="differentially verify all hooks at hook boundaries while playing")
    p.add_argument("--verify-hook", action="append", default=[],
                   help="differentially verify one hook address while playing; may be repeated")
    p.add_argument("--verify-max", type=int, default=None,
                   help="stop after N verified hook calls")
    p.add_argument("--verify-stop-on-diff", action="store_true",
                   help="stop the emulator thread on the first hook divergence")
    p.add_argument("--verify-log-diffs", action="store_true",
                   help="print detailed hook divergence reports and continue")
    p.add_argument("--verify-full-memory", action="store_true",
                   help="compare the full memory image instead of default named ranges")
    p.add_argument("--verify-require-metadata", action="store_true",
                   help="fail instead of silently skipping a hook that has no verifier continuation metadata")
    p.add_argument("--verify-frames", action="store_true",
                   help="headless differential frame verifier: reference ASM runtime vs hooked runtime")
    p.add_argument("--verify-frame-max", type=int, default=60,
                   help="stop frame verifier after N frame/timer/retrace boundaries")
    p.add_argument("--verify-frame-source", choices=("rgb", "vram", "both"), default="both",
                   help="frame verifier comparison source")
    p.add_argument("--verify-frame-dump-dir", default=str(ROOT / "artifacts" / "frame_verify"),
                   help="directory for frame verifier divergence PNG/VRAM/report artifacts")
    p.add_argument("--verify-frame-preview", action="store_true",
                   help="show a live SDL preview of the candidate runtime while frame verification runs")
    p.add_argument("--verify-frame-preview-on-diff", action="store_true",
                   help="open the frame compare image when frame verification finds a diff")
    p.add_argument("--ega-publish-timed-boundaries", action="store_true",
                   help="debug only: publish EGA snapshots at timer/retrace waits as well as the EGA presenter")
    p.add_argument("--ega-start-address-units", choices=("byte", "word", "ignore"), default="byte",
                   help="debug EGA CRTC start interpretation: byte offset, word address*2, or always zero")
    p.add_argument("--ega-log-starts", action="store_true",
                   help="print EGA display-start value and interpreted render offset for each published frame")
    p.add_argument("--ega-publish-all-presents", action="store_true",
                   help="debug only: publish every EGA present, including alternating off-screen page presents")
    p.add_argument("--coverage-dashboard", action="store_true",
                   help="open a live Tk ASM / Hook Coverage dashboard next to the gameplay window")
    p.add_argument("--coverage-refresh-hz", type=float, default=4.0,
                   help="Tk coverage dashboard refresh rate (default: 4 Hz)")
    p.add_argument("--coverage-cache", default=str(ROOT / "artifacts" / "hook_coverage_cache.json"),
                   help="JSON cache used to estimate hook ASM-equivalent cost outside --verify-hooks")
    p.add_argument("--no-coverage-summary", action="store_true",
                   help="do not print the final ASM / Hook Coverage summary on exit")
    args = p.parse_args(argv)

    exe = ROOT / "assets" / "OVERKILL.UNLZEXE.EXE"
    assets = ROOT / "assets"
    if args.dos_args is not None:
        command_tail: bytes | str = args.dos_args
    elif args.video == "ega":
        # The public packed EXE accepts the documented ASCII switch /E, but this
        # project runs the already-unpacked inner executable.  That inner module
        # is launched by the original stub with a compact binary PSP tail:
        #   PSP:81 = sound/music option byte, PSP:82 = video mode (0/1/2).
        # ASCII switches such as " /E" only work for EGA by accident because
        # '/' is outside 0..2 and the inner parser falls back to mode 1.  Use the
        # direct selector so non-default modes are unambiguous.
        command_tail = bytes((0x0D, 0x01))
    elif args.video == "tandy":
        # Mode 2 is Tandy/PCjr.  Passing the documented ASCII " /T" to the inner
        # executable would also fall back to EGA, so use the binary selector here.
        command_tail = bytes((0x0D, 0x02))
    else:
        # With an empty PSP tail the inner parser sees PSP:82 == 0 and selects
        # CGA mode 0.
        command_tail = b""

    if args.verify_frames and args.verify_frame_preview:
        from overkill_port.frame_verify import FrameSample, FrameVerifyConfig, run_frame_verifier

        frame_sync = FrameSync()
        stop = threading.Event()
        status = {"text": ""}
        visible = {"n": 0}
        boundary = {"n": 0}
        blits = {"n": 0}
        timers = {"n": 0}
        retraces = {"n": 0}
        direct_video = {"n": 0}
        scancode_events: SimpleQueue[int] = SimpleQueue()
        dos_key_events: SimpleQueue[tuple[int, str]] = SimpleQueue()

        def ega_render_start(raw: int) -> int:
            if args.ega_start_address_units == "ignore":
                return 0
            if args.ega_start_address_units == "word":
                return (raw << 1) & 0xFFFF
            return raw & 0xFFFF

        def publish_candidate(rt, sample: FrameSample) -> None:
            visible["n"] += 1
            boundary["n"] += 1
            if sample.kind == "present":
                blits["n"] += 1
            elif sample.kind == "timer":
                timers["n"] += 1
            elif sample.kind == "retrace":
                retraces["n"] += 1
            frame_sync.publish_and_wait(rt.program.memory.data, display_start=sample.display_start)

        def pump_inputs(ref_rt, cand_rt) -> None:
            keyboard.pump()
            while True:
                try:
                    sc = scancode_events.get_nowait()
                except Empty:
                    break
                deliver_scancode(ref_rt, sc)
                deliver_scancode(cand_rt, sc)
            while True:
                try:
                    scancode, text = dos_key_events.get_nowait()
                except Empty:
                    break
                if not text:
                    text = {
                        0x02: "1", 0x03: "2", 0x04: "3", 0x05: "4", 0x06: "5",
                        0x07: "6", 0x08: "7", 0x09: "8", 0x0A: "9", 0x0B: "0",
                        0x0C: "-", 0x0D: "=", 0x0E: "\b", 0x0F: "\t",
                        0x10: "q", 0x11: "w", 0x12: "e", 0x13: "r", 0x14: "t",
                        0x15: "y", 0x16: "u", 0x17: "i", 0x18: "o", 0x19: "p",
                        0x1A: "[", 0x1B: "]", 0x1C: "\r",
                        0x1E: "a", 0x1F: "s", 0x20: "d", 0x21: "f", 0x22: "g",
                        0x23: "h", 0x24: "j", 0x25: "k", 0x26: "l", 0x27: ";",
                        0x28: "'", 0x29: "`", 0x2B: "\\",
                        0x2C: "z", 0x2D: "x", 0x2E: "c", 0x2F: "v", 0x30: "b",
                        0x31: "n", 0x32: "m", 0x33: ",", 0x34: ".", 0x35: "/",
                        0x39: " ", 0x01: "\x1b",
                    }.get(scancode, "")
                if not text:
                    continue
                ch = ord(text[0])
                if ch < 0x20 and ch not in (0x08, 0x09, 0x0D, 0x1B):
                    continue
                key = (((scancode & 0xFF) << 8) | (ch & 0xFF)) & 0xFFFF
                ref_rt.dos.key_queue.append(key)
                cand_rt.dos.key_queue.append(key)

        keyboard = KeyDispatcher(lambda sc: scancode_events.put(sc))

        def queue_dos_key(scancode: int, text: str) -> None:
            dos_key_events.put((scancode, text))

        def queue_snapshot_save() -> None:
            status["text"] = "F12 snapshots are disabled during live frame verification"

        def verifier_loop() -> None:
            try:
                max_frames = 0 if args.verify_frame_max == 60 else args.verify_frame_max
                result = run_frame_verifier(
                    exe=exe,
                    assets=assets,
                    snapshot=args.snapshot,
                    command_tail=command_tail,
                    config=FrameVerifyConfig(
                        video=args.video,
                        palette=args.palette,
                        max_frames=max_frames,
                        frame_budget=args.frame_budget,
                        source=args.verify_frame_source,
                        dump_dir=Path(args.verify_frame_dump_dir),
                        stop_on_diff=True,
                        preview_on_diff=args.verify_frame_preview_on_diff,
                        ega_start_address_units=args.ega_start_address_units,
                    ),
                    publish_candidate=publish_candidate,
                    pump_inputs=pump_inputs,
                    stop_requested=stop.is_set,
                    status_callback=lambda text: status.__setitem__("text", text),
                )
                if result == 0:
                    status["text"] = "FRAME VERIFY stopped"
            except Exception as exc:
                status["text"] = f"FRAME VERIFY crash: {type(exc).__name__}: {exc}"
                traceback.print_exc()
            finally:
                stop.set()
                frame_sync.close()

        try:
            from sdl_view import run_sdl_ui
        except Exception as exc:
            print(f"the interactive viewer requires pygame and numpy: {exc}")
            return 1

        emu = threading.Thread(target=verifier_loop, name="overkill-frame-verify", daemon=True)
        emu.start()
        try:
            run_sdl_ui(
                args=args,
                frame_sync=frame_sync,
                keyboard=keyboard,
                stop=stop,
                status=status,
                counters={"visible": visible, "boundary": boundary, "blits": blits,
                          "timers": timers, "retraces": retraces, "direct_video": direct_video},
                queue_snapshot_save=queue_snapshot_save,
                queue_dos_key=queue_dos_key,
                ega_render_start=ega_render_start,
                live_memory=lambda: b"",
                live_display_start=lambda: 0,
                speaker_events=None,
            )
        finally:
            stop.set()
            frame_sync.close()
        return 0

    if args.verify_frames:
        from overkill_port.frame_verify import FrameVerifyConfig, run_frame_verifier

        return run_frame_verifier(
            exe=exe,
            assets=assets,
            snapshot=args.snapshot,
            command_tail=command_tail,
            config=FrameVerifyConfig(
                video=args.video,
                palette=args.palette,
                max_frames=args.verify_frame_max,
                frame_budget=args.frame_budget,
                source=args.verify_frame_source,
                dump_dir=Path(args.verify_frame_dump_dir),
                stop_on_diff=True,
                preview_on_diff=args.verify_frame_preview_on_diff,
                ega_start_address_units=args.ega_start_address_units,
            ),
        )

    if args.snapshot:
        rt = load_snapshot(exe, args.snapshot, game_root=assets)
    else:
        rt = create_runtime(exe, game_root=assets, command_tail=command_tail)
    rt.dos.console_input_fallback = None
    rt.cpu.trace_enabled = False
    coverage = CoverageTelemetry(
        classifier=OverkillCoverageClassifier(ROOT / "symbols.json"),
        cache_path=Path(args.coverage_cache) if args.coverage_cache else None,
        enabled=True,
    )
    rt.cpu.coverage_telemetry = coverage
    status = {"text": ""}
    hook_verifier = None
    if args.verify_hooks or args.verify_hook:
        hook_verifier = install_hook_verifier(
            rt,
            HookVerifierConfig(
                verify_all=args.verify_hooks,
                hooks={parse_verify_addr(text) for text in args.verify_hook},
                max_verified=args.verify_max,
                stop_on_diff=args.verify_stop_on_diff,
                log_diffs=args.verify_log_diffs,
                full_memory=args.verify_full_memory,
                require_metadata=args.verify_require_metadata,
                progress_callback=lambda text: status.__setitem__("text", text),
            ),
        )

    if args.video != "cga":
        for key in NON_CGA_INTERACTIVE_DISABLE:
            rt.cpu.replacement_hooks.pop(key, None)
            rt.cpu.hook_names.pop(key, None)

    # The replacement at 1010:0679 models the game's PIT/timer flag and is the
    # right pacing source for gameplay.  The intro/menu/transition code, however,
    # also uses the VGA retrace wait at 1010:50C9 as a real delay mechanism and
    # performs B800h updates around those waits.  If 50C9 returns instantly, the
    # title/menu path fast-forwards invisibly to the attract/gameplay demo even
    # though gameplay itself looks correctly paced.  So interactive play treats
    # both 0679 and 50C9 as timed boundaries, and publishes a new snapshot whenever
    # B800h actually changed.
    rt.cpu.timer_pacer = None
    timer_pacer = TimerPacer(args.game_hz * 2.0)
    retrace_pacer = TimerPacer(args.retrace_hz if args.retrace_hz is not None else args.game_hz)
    async_timer_irq = AsyncTimerIrqDriver()
    frame_sync = FrameSync()

    boundary = {"n": 0}
    visible = {"n": 0}
    blits = {"n": 0}
    timers = {"n": 0}
    retraces = {"n": 0}
    direct_video = {"n": 0}
    last_boundary: dict[str, str | None] = {"kind": None}
    last_video_crc: dict[str, tuple[int, int] | None] = {"value": None}
    if args.video == "ega":
        present_hook_addr = EGA_PRESENT_HOOK
        video_base = A000_BASE
        video_size = EGA_SHADOW_SIZE
    elif args.video == "tandy":
        present_hook_addr = TANDY_PRESENT_HOOK
        video_base = B800_BASE
        video_size = TANDY_SIZE
    else:
        present_hook_addr = CGA_PRESENT_HOOK
        video_base = B800_BASE
        video_size = B800_SIZE

    base_present = rt.cpu.replacement_hooks.get(present_hook_addr)
    base_present_name = rt.cpu.hook_names.get(present_hook_addr, "replacement")
    base_timer_wait = rt.cpu.replacement_hooks.get(TIMER_WAIT_HOOK)
    base_retrace_wait = rt.cpu.replacement_hooks.get(RETRACE_WAIT_HOOK)
    if base_timer_wait is None:
        print(f"missing required timer wait hook {TIMER_WAIT_HOOK[0]:04X}:{TIMER_WAIT_HOOK[1]:04X}")
        return 1

    def ega_render_start(raw_start: int) -> int:
        raw_start &= 0xFFFF
        if args.ega_start_address_units == "ignore":
            return 0
        if args.ega_start_address_units == "word":
            return (raw_start << 1) & 0xFFFF
        return raw_start

    def video_crc(cpu) -> int:
        data = cpu.mem.data
        if args.video == "ega":
            # Only hash the hardware-visible 320x200 window from each plane.
            # Hashing the full shadow store lets off-screen/work pages trigger a
            # viewer publish even when the displayed CRTC page did not change.
            start = ega_render_start(cpu.mem.ega_display_start)
            crc = 0
            for plane in range(4):
                plane_base = video_base + plane * 0x10000
                for y in range(200):
                    row = (start + y * 40) & 0xFFFF
                    if row <= 0x10000 - 40:
                        crc = zlib.crc32(data[plane_base + row:plane_base + row + 40], crc)
                    else:
                        tail = 0x10000 - row
                        crc = zlib.crc32(data[plane_base + row:plane_base + 0x10000], crc)
                        crc = zlib.crc32(data[plane_base:plane_base + (40 - tail)], crc)
            return crc & 0xFFFFFFFF
        return zlib.crc32(data[video_base:video_base + video_size]) & 0xFFFFFFFF

    def publish_video_if_changed(cpu, *, force: bool = False) -> bool:
        raw_display_start = cpu.mem.ega_display_start if args.video == "ega" else 0
        display_start = ega_render_start(raw_display_start) if args.video == "ega" else 0
        crc: int | None = None
        if force and not (args.ega_log_starts and args.video == "ega"):
            visible_key = (visible["n"] + 1, display_start)
        else:
            crc = video_crc(cpu)
            visible_key = (crc, display_start)
            if not force and last_video_crc["value"] == visible_key:
                return False
        last_video_crc["value"] = visible_key
        visible["n"] += 1
        if args.ega_log_starts and args.video == "ega":
            if crc is None:
                crc = video_crc(cpu)
            print(
                f"EGA publish visible={visible['n']} blits={blits['n']} "
                f"raw_start={raw_display_start:04X} render_start={display_start:04X} "
                f"crc={crc:08X}",
                flush=True,
            )
        if not args.no_present_sync:
            if args.video == "ega":
                frame_sync.publish_and_wait(
                    memoryview(cpu.mem.data)[video_base:video_base + video_size],
                    display_start=display_start,
                )
            else:
                frame_sync.publish_and_wait(cpu.mem.data, display_start=display_start)
        return True

    def stop_cpu_burst() -> None:
        boundary["n"] += 1
        raise FramePresented()

    def queue_dos_key(scancode: int, text: str) -> None:
        cs, ip = rt.cpu.addr()
        in_high_score_editor = cs == 0x1010 and 0x5300 <= ip <= 0x5650
        if direct_video["n"] == 0 and not in_high_score_editor:
            return
        if not text:
            text = {
                0x02: "1", 0x03: "2", 0x04: "3", 0x05: "4", 0x06: "5",
                0x07: "6", 0x08: "7", 0x09: "8", 0x0A: "9", 0x0B: "0",
                0x0C: "-", 0x0D: "=", 0x0E: "\b", 0x0F: "\t",
                0x10: "q", 0x11: "w", 0x12: "e", 0x13: "r", 0x14: "t",
                0x15: "y", 0x16: "u", 0x17: "i", 0x18: "o", 0x19: "p",
                0x1A: "[", 0x1B: "]", 0x1C: "\r",
                0x1E: "a", 0x1F: "s", 0x20: "d", 0x21: "f", 0x22: "g",
                0x23: "h", 0x24: "j", 0x25: "k", 0x26: "l", 0x27: ";",
                0x28: "'", 0x29: "`", 0x2B: "\\",
                0x2C: "z", 0x2D: "x", 0x2E: "c", 0x2F: "v", 0x30: "b",
                0x31: "n", 0x32: "m", 0x33: ",", 0x34: ".", 0x35: "/",
                0x39: " ", 0x01: "\x1b",
            }.get(scancode, "")
        if not text:
            return
        ch = ord(text[0])
        if ch < 0x20 and ch not in (0x08, 0x09, 0x0D, 0x1B):
            return
        rt.dos.key_queue.append((((scancode & 0xFF) << 8) | (ch & 0xFF)) & 0xFFFF)

    def is_redefine_key_wait() -> bool:
        cs, ip = rt.cpu.addr()
        if cs != 0x1010:
            return False
        if ip in (0x57AB, 0x57B0):
            return rt.cpu.mem.rb(rt.cpu.s.ds, 0x98C3) == 0
        if ip in (0x57DD, 0x57E0):
            key = rt.cpu.mem.rb(rt.cpu.s.ds, 0x98C3)
            return key != 0 and rt.cpu.mem.rb(rt.cpu.s.ds, (0x98C4 + key) & 0xFFFF) != 0
        return False

    def is_overlay_menu_key_wait() -> bool:
        cs, ip = rt.cpu.addr()
        if not (0x099B <= ip <= 0x09DF):
            return False
        mem = rt.cpu.mem
        if mem.block(cs, 0x099B, 7) != bytes.fromhex("80 3e 0f 99 01 74 47"):
            return False
        ds = rt.cpu.s.ds & 0xFFFF
        watched = (0x990F, 0x990C, 0x990D, 0x98D2, 0x9911,
                   0x9914, 0x9915, 0x98FD, 0x98E0, 0x98C5)
        return all(mem.rb(ds, off) != 1 for off in watched)

    def is_gameplay_exit_confirm_wait() -> bool:
        """Detect the in-game Esc "SURE ?" confirmation key loop.

        The original code draws the prompt between 1010:9875 and 1010:989B, then
        spins at 1010:989E..98B4 polling Y/N key-state bytes.  There is no Tandy
        presenter or timer wait inside that loop, so the interactive viewer must
        publish the direct VRAM update and yield for Y/N input.
        """
        cs, ip = rt.cpu.addr()
        if cs != 0x1010 or not (0x989E <= ip <= 0x98B6):
            return False
        mem = rt.cpu.mem
        if mem.block(cs, 0x989E, 24) != bytes.fromhex(
            "c6 06 b4 22 4e 80 3e f5 98 01 74 0c "
            "c6 06 b4 22 59 80 3e d9 98 01 75 e8"
        ):
            return False
        ds = rt.cpu.s.ds & 0xFFFF
        return mem.rb(ds, 0x98F5) != 1 and mem.rb(ds, 0x98D9) != 1

    def present_hook(cpu) -> None:
        if base_present is not None:
            if hook_verifier is not None:
                hook_verifier.verify(cpu, present_hook_addr, base_present, base_present_name)
            else:
                base_present(cpu)
        blits["n"] += 1
        # EGA gameplay alternates the CRTC start between 0000h and 2000h around
        # paired present calls.  The two presents are part of one page-flip/update
        # sequence; painting both through the viewer exposes the intermediate work page
        # as the visible "every other frame" blink.  Keep executing both in the
        # VM, but only publish the stable page unless the debug flag asks to see
        # every present boundary.
        if args.video != "ega" or args.ega_publish_all_presents or (cpu.mem.ega_display_start & 0xFFFF) == 0:
            publish_video_if_changed(cpu, force=True)
        # A visible blit is a safe place to hand control back to the UI.  The
        # following 0679 timer wait still performs the actual gameplay sleep, so
        # this does not invent an additional gameplay delay.
        last_boundary["kind"] = "present"
        stop_cpu_burst()

    def timer_frame_hook(cpu) -> None:
        base_timer_wait(cpu)
        async_timer_irq.reset_after_synchronous_ticks(2)
        timers["n"] += 1
        # Some paths update video memory directly and only use the timer wait as
        # their boundary.  EGA startup/menu can do this before the first 2750
        # present, but after EGA presenting starts, timed-boundary publishing can
        # expose intermediate dirty-panel states that the presenter has not
        # committed as a complete frame yet.
        if args.video != "ega" or args.ega_publish_timed_boundaries or blits["n"] == 0:
            publish_video_if_changed(cpu)
        # Pace one logical OVERKILL frame, not the number of IRQ0 ticks that
        # happened to be delivered inside this particular 0679 hook call.
        #
        # The timer ISR increments CS:066B on every other PIT tick.  If the
        # async IRQ driver already delivered the first half-tick during the
        # foreground work, 0679 only needs one more ISR to unblock.  Pacing by
        # that raw value makes the next frame sleep for 1/72.8s instead of the
        # intended 2/72.8s, so gameplay alternates between normal and too-fast
        # depending on CPU load.  Each 0679 return still represents one game
        # tick, i.e. two PIT tick units.
        timer_pacer(2)
        last_boundary["kind"] = "timer"
        stop_cpu_burst()

    def retrace_frame_hook(cpu) -> None:
        # Same rationale as present_hook: retrace waits are visual timing
        # boundaries, not PIT waits.  The original IRQ0 still fires during them.
        async_timer_irq.poll(cpu)
        if base_retrace_wait is not None:
            base_retrace_wait(cpu)
        retraces["n"] += 1
        # Intro/menu/fade code often draws first and then waits for retrace.  For
        # EGA, publish these timed snapshots only until the first explicit EGA
        # presenter runs; after that, keep retrace as a pacing boundary only.
        if args.video != "ega" or args.ega_publish_timed_boundaries or blits["n"] == 0:
            publish_video_if_changed(cpu)
        retrace_pacer(
            poll=lambda: async_timer_irq.poll(cpu, max_catchup=1),
            poll_interval=async_timer_irq.period * 0.5 if async_timer_irq.period > 0 else None,
        )
        last_boundary["kind"] = "retrace"
        stop_cpu_burst()

    rt.cpu.replacement_hooks[present_hook_addr] = present_hook
    rt.cpu.replacement_hooks[TIMER_WAIT_HOOK] = timer_frame_hook
    if base_retrace_wait is not None:
        rt.cpu.replacement_hooks[RETRACE_WAIT_HOOK] = retrace_frame_hook
    # These three hooks are UI pacing wrappers in play.py.  Let them execute
    # directly; present_hook manually verifies the underlying real presenter
    # before publishing to Tk.
    rt.cpu.hook_verifier_passthrough.update({present_hook_addr, TIMER_WAIT_HOOK, RETRACE_WAIT_HOOK})

    keyboard = KeyDispatcher(lambda sc: deliver_scancode(rt, sc))
    stop = threading.Event()
    snapshot_requests: SimpleQueue[Path] = SimpleQueue()
    speaker_events: SimpleQueue[tuple[bool, float]] = SimpleQueue()
    rt.dos.set_speaker_callback(lambda enabled, freq: speaker_events.put((enabled, freq)), emit_current=True)

    def queue_snapshot_save() -> None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = Path(args.save_snapshot_root) / f"snapshot_play_{args.video}_{stamp}"
        snapshot_requests.put(out)
        status["text"] = f"snapshot queued: {out}"

    def emulator_loop() -> None:
        while not stop.is_set():
            try:
                try:
                    out = snapshot_requests.get_nowait()
                except Empty:
                    out = None
                if out is not None:
                    write_snapshot(
                        rt,
                        out,
                        status="interactive F12 snapshot",
                        steps=rt.cpu.instruction_count,
                        trace_tail=(),
                    )
                    status["text"] = f"snapshot saved: {out}"
                # Tandy/CGA gameplay presents the frame before checking some
                # post-present one-shot keys such as Esc.  If a quick physical
                # tap is pressed before that presenter and released right after
                # it, releasing it at the next outer-loop pump would make the
                # original code miss the key entirely.  Keep breaks pending for
                # one more VM slice after present boundaries; no-frame busy-wait
                # pumping below can still release keys once the game reaches its
                # explicit key-release loop.
                keyboard.pump(allow_release=last_boundary["kind"] != "present")
                target = boundary["n"] + 1
                used = 0
                while boundary["n"] < target and used < args.frame_budget and not stop.is_set():
                    try:
                        rt.cpu.run(max(1, int(args.cpu_chunk_steps)))
                    except FramePresented:
                        break
                    except HaltExecution:
                        stop.set()
                        status["text"] = "program exited normally"
                        break
                    except ConsoleInputWouldBlock:
                        async_timer_irq.poll(rt.cpu)
                        publish_video_if_changed(rt.cpu)
                        boundary["n"] += 1
                        last_boundary["kind"] = "wait"
                        cs, ip = rt.cpu.addr()
                        status["text"] = f"waiting for DOS console input @ {cs:04X}:{ip:04X}"
                        time.sleep(0.01)
                        break
                    if is_redefine_key_wait():
                        async_timer_irq.poll(rt.cpu)
                        publish_video_if_changed(rt.cpu)
                        boundary["n"] += 1
                        last_boundary["kind"] = "wait"
                        cs, ip = rt.cpu.addr()
                        status["text"] = f"waiting for redefine-key input @ {cs:04X}:{ip:04X}"
                        time.sleep(0.01)
                        break
                    if is_overlay_menu_key_wait():
                        async_timer_irq.poll(rt.cpu)
                        publish_video_if_changed(rt.cpu)
                        boundary["n"] += 1
                        last_boundary["kind"] = "wait"
                        cs, ip = rt.cpu.addr()
                        status["text"] = f"waiting for menu screen input @ {cs:04X}:{ip:04X}"
                        time.sleep(0.01)
                        break
                    if is_gameplay_exit_confirm_wait():
                        async_timer_irq.poll(rt.cpu)
                        publish_video_if_changed(rt.cpu, force=True)
                        boundary["n"] += 1
                        last_boundary["kind"] = "wait"
                        cs, ip = rt.cpu.addr()
                        status["text"] = f"waiting for exit confirmation @ {cs:04X}:{ip:04X}"
                        time.sleep(0.01)
                        break
                    used += max(1, int(args.cpu_chunk_steps))
                    async_timer_irq.poll(rt.cpu)
                    # Long screen loads can run for many chunks without a
                    # visible/timer boundary.  Drain key-up events during those
                    # bursts so a short FIRE tap from the menu is not still held
                    # when the newly loaded level-select screen first polls input.
                    keyboard.pump_events()
                if boundary["n"] < target and not stop.is_set():
                    cs, ip = rt.cpu.addr()
                    if publish_video_if_changed(rt.cpu):
                        direct_video["n"] += 1
                        boundary["n"] += 1
                        last_boundary["kind"] = "direct"
                        status["text"] = f"direct video publish @ {cs:04X}:{ip:04X}"
                    else:
                        status["text"] = f"stall (no visual/timer boundary in {used} steps) @ {cs:04X}:{ip:04X}"
            except Exception as exc:
                cs, ip = rt.cpu.addr()
                status["text"] = f"CRASH @ {cs:04X}:{ip:04X} - {type(exc).__name__}: {exc}"
                traceback.print_exc()
                return

    try:
        from sdl_view import run_sdl_ui
    except Exception as exc:
        print(f"the interactive viewer requires pygame and numpy: {exc}")
        return 1

    dashboard = CoverageDashboardTk(coverage, refresh_hz=args.coverage_refresh_hz) if args.coverage_dashboard else None
    if dashboard is not None:
        dashboard.start()

    # Start the emulator thread, then run the pygame/SDL viewer on the main thread.
    emu = threading.Thread(target=emulator_loop, name="overkill-emu", daemon=True)
    emu.start()
    try:
        run_sdl_ui(
            args=args,
            frame_sync=frame_sync,
            keyboard=keyboard,
            stop=stop,
            status=status,
            counters={"visible": visible, "boundary": boundary, "blits": blits,
                      "timers": timers, "retraces": retraces, "direct_video": direct_video},
            queue_snapshot_save=queue_snapshot_save,
            queue_dos_key=queue_dos_key,
            ega_render_start=ega_render_start,
            live_memory=lambda: bytes(rt.program.memory.data),
            live_display_start=lambda: rt.program.memory.ega_display_start,
            speaker_events=speaker_events,
        )
    finally:
        stop.set()
        frame_sync.close()
        if dashboard is not None:
            dashboard.close()
        coverage.save_cache()
        if not args.no_coverage_summary:
            print(coverage.format_summary(), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
