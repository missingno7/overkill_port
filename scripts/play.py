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
runtime snapshot.  F11 toggles deterministic input-demo recording: it writes a
start snapshot and records VM-delivered keyboard events until F11 is pressed
again.  Esc and any other key are forwarded too (full keyboard), in case a screen
wants them.

Run:
    python scripts/play.py [--video cga|ega|tandy] [--game-hz 30] [--palette 1h] [--scale 2]
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

from dos_re.interrupts import deliver_scancode
from dos_re.keyboard import KeyDispatcher
from overkill.verification import (
    HookVerifierConfig,
    HookVerifyDivergence,
    install_hook_verifier,
    parse_addr as parse_verify_addr,
)
from dos_re.dos import ConsoleInputWouldBlock
from dos_re.cpu import HaltExecution
from overkill.runtime import create_overkill_runtime
from overkill.runtime import load_overkill_snapshot
from dos_re.snapshot import write_snapshot
from dos_re.memory import EGA_APERTURE, EGA_SHADOW_SIZE
from overkill.coverage import (
    CoverageDashboardTk,
    CoverageTelemetry,
    OverkillCoverageClassifier,
)
from overkill.sounds import AsyncTimerIrqDriver, OVERKILL_PIT_HZ
from overkill.launch import build_command_tail
from dos_re.input_demo import InputDemoPlayback, InputDemoRecorder, dos_key_value
from render_frame import CGA_PALETTES

CGA_PRESENT_HOOK = (0x1010, 0x447B)  # mode-0 CGA frame-present blit
EGA_PRESENT_HOOK = (0x1010, 0x2750)  # mode-1 EGA frame-present blit
TANDY_PRESENT_HOOK = (0x1010, 0x3354)  # mode-2 Tandy frame-present blit
TIMER_WAIT_HOOK = (0x1010, 0x0679)  # game frame/timer wait; one call == one logical frame
RETRACE_WAIT_HOOK = (0x1010, 0x50C9)  # VGA retrace wait used heavily by intro/menu/transitions
B800_BASE = 0xB8000
B800_SIZE = 0x4000
A000_BASE = EGA_APERTURE
TANDY_SIZE = 0x8000

# Boss-key wait loops are tiny two-instruction polls.  CPU.run() can yield after
# any instruction in the loop, not just at the loop head, so the interactive
# wait detector must recognize the whole instruction window.  Otherwise F9 can
# deterministically enter the text-mode boss screen but miss the cooperative
# publish boundary until the large no-boundary frame budget expires, which looks
# like frozen gameplay with increasing audio underruns.
BOSS_KEY_WAIT_WINDOWS = (
    (0x07C4, 0x07CA),  # wait while DS:9907 == 1, i.e. original F9 held
    (0x07D0, 0x07D6),  # wait while DS:98C3 == 0, i.e. no return key yet
    (0x07D7, 0x07DD),  # wait while DS:9907 == 1, i.e. return key held
)


def boss_key_wait_window(ip: int) -> tuple[int, int] | None:
    ip &= 0xFFFF
    for start, end in BOSS_KEY_WAIT_WINDOWS:
        if start <= ip <= end:
            return start, end
    return None

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
                # The loop exits as soon as the wall-clock deadline is reached.
                # Without this final poll, a sleep that lands exactly on the PIT
                # deadline can miss the IRQ0 tick until the next UI/emulator
                # boundary.  Intro/menu code spends a lot of time in retrace
                # pacing, so that off-by-one poll made the AdLib driver advance
                # irregularly and audibly slow/choppy even when ASM coverage was
                # already high.
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
        self._pending: tuple[int, bytes, int, int, int] | None = None
        self._closed = False

    def publish_and_wait(
        self,
        memory: bytearray,
        *,
        display_start: int = 0,
        video_mode: int = 0xFF,
        video_page: int = 0,
        wait_poll=None,
        wait_poll_interval: float = 0.004,
    ) -> None:
        snapshot = bytes(memory)
        with self._cond:
            if self._closed:
                return
            self._next_id += 1
            frame_id = self._next_id
            self._pending = (frame_id, snapshot, display_start & 0xFFFF, video_mode & 0xFF, video_page & 0xFF)
            self._cond.notify_all()

        # In the original PC, PIT IRQ0 keeps firing while the foreground code is
        # waiting for the display retrace or while the CRT simply shows a static
        # menu screen.  Our SDL handoff can block the emulator thread until the
        # UI has consumed the snapshot; if no asynchronous IRQ polling happens
        # during that wait, AdLib music in intro/menu screens advances in uneven
        # bursts.  Poll outside the condition lock so the callback can safely
        # run the original INT 08h path and mutate CPU/DOS state.
        interval = max(0.001, min(0.25, float(wait_poll_interval)))
        while True:
            with self._cond:
                if self._closed or self._displayed_id >= frame_id:
                    return
                self._cond.wait(timeout=interval if wait_poll is not None else 0.25)
                if self._closed or self._displayed_id >= frame_id:
                    return
            if wait_poll is not None:
                wait_poll()

    def publish_nowait(
        self,
        memory: bytearray | memoryview,
        *,
        display_start: int = 0,
        video_mode: int = 0xFF,
        video_page: int = 0,
    ) -> None:
        """Queue a frame for the viewer without waiting for consumption.

        Interactive hook verification can spend a long time proving the first
        gameplay slice before it reaches the next real presenter/timer boundary.
        Queueing the loaded snapshot immediately avoids a misleading black SDL
        window during that initial verifier work.
        """
        snapshot = bytes(memory)
        with self._cond:
            if self._closed:
                return
            self._next_id += 1
            frame_id = self._next_id
            self._pending = (frame_id, snapshot, display_start & 0xFFFF, video_mode & 0xFF, video_page & 0xFF)
            self._cond.notify_all()

    def take_pending(self) -> tuple[int, bytes, int, int, int] | None:
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
    p.add_argument("--sound", choices=("pc", "adlib", "roland"), default="pc",
                   help="select the original optional music driver; pc keeps the built-in PC-speaker path")
    p.add_argument("--adlib-audio", choices=("auto", "off"), default="auto",
                   help="when --sound adlib is active, stream OPL writes through optional nuked_opl3 if available")
    p.add_argument("--adlib-chunk-ms", type=float, default=46.0,
                   help="SDL AdLib PCM chunk size in milliseconds (default: 46; increase to smooth underruns)")
    p.add_argument("--dos-args", default=None,
                   help="override the PSP command tail passed to the original EXE, e.g. raw compact bytes via tests/diagnostics")
    p.add_argument("--game-hz", type=float, default=36.4,
                   help="real-time game speed (frames/sec); original timer cadence is ~36.4. Lower if choppy.")
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
    p.add_argument("--save-demo-root", default=str(ROOT / "artifacts" / "demos"),
                   help="root directory for F11 input demos")
    p.add_argument("--demo", default=None,
                   help="replay an input demo directory/json; loads its start snapshot unless --snapshot is also given")
    p.add_argument("--demo-continue", action="store_true",
                   help="keep running after the input demo ends instead of stopping the game when it finishes")
    p.add_argument("--no-present-sync", action="store_true",
                   help="debug only: do not wait for the viewer to consume each timer-frame snapshot")
    p.add_argument("--retrace-hz", type=float, default=None,
                   help="pace hardware retrace waits used by intro/menu; default is 60 Hz, not the 36.4 Hz game timer")
    p.add_argument("--verify-hooks", action="store_true",
                   help="differentially verify all hooks at hook boundaries while playing")
    p.add_argument("--verify-hooks-strict", action="store_true",
                   help="verify all hooks using the slow/simple automatic-continuation oracle")
    p.add_argument("--verify-hook", action="append", default=[],
                   help="differentially verify one hook address while playing; may be repeated")
    p.add_argument("--verify-strict", action="store_true",
                   help="make --verify-hooks/--verify-hook use the slow/simple automatic-continuation oracle")
    p.add_argument("--verify-max", type=int, default=None,
                   help="stop after N verified hook calls")
    p.add_argument("--verify-stop-on-diff", action="store_true",
                   help="stop the emulator thread on the first hook divergence")
    p.add_argument("--verify-log-diffs", action="store_true",
                   help="print detailed hook divergence reports and continue")
    p.add_argument("--verify-fast-ranges", action="store_true",
                   help="debug/perf only: compare named memory ranges instead of the full memory image")
    p.add_argument("--verify-require-metadata", action="store_true",
                   help="fail instead of silently skipping a hook that has no verifier continuation metadata")
    p.add_argument("--verify-no-nested", action="store_true",
                   help="legacy/perf mode: do not recursively verify child hooks reached inside a verified parent hook")
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
    p.add_argument("--verify-frame-trace-raw", action="store_true",
                   help="on frame divergence, include recent candidate hooks that changed the sampled raw frame bytes")
    p.add_argument("--verify-frame-trace-raw-from", type=int, default=1,
                   help="first frame number where --verify-frame-trace-raw starts sampling; useful for late divergences")
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

    exe = ROOT / "assets" / "OVERKILL"
    assets = ROOT / "assets"
    if args.dos_args is not None:
        command_tail: bytes | str = args.dos_args
    else:
        command_tail = build_command_tail(args.video, args.sound)

    demo_playback: InputDemoPlayback | None = None
    if args.demo:
        demo_playback = InputDemoPlayback.load(args.demo)
        if args.snapshot is None:
            args.snapshot = str(demo_playback.snapshot_path())

    if args.verify_frames and args.verify_frame_preview:
        from overkill.frame_verify import FrameSample, FrameVerifyConfig, run_frame_verifier

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
            mode = rt.dos.video_mode if rt.dos.text_mode_active and rt.dos.video_mode in (0, 1, 2, 3, 7) else 0xFF
            frame_sync.publish_and_wait(
                rt.program.memory.data,
                display_start=sample.display_start,
                video_mode=mode,
                video_page=rt.dos.video_page,
            )

        frame_demo_boundary = {"n": 0}

        def pump_inputs(ref_rt, cand_rt) -> None:
            if demo_playback is not None:
                demo_playback.apply_to_runtimes(frame_demo_boundary["n"], (ref_rt, cand_rt))
                frame_demo_boundary["n"] += 1
                return
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
                key = dos_key_value(scancode, text)
                if key is None:
                    continue
                ref_rt.dos.key_queue.append(key)
                cand_rt.dos.key_queue.append(key)

        keyboard = KeyDispatcher(lambda sc: scancode_events.put(sc))

        def queue_dos_key(scancode: int, text: str) -> None:
            dos_key_events.put((scancode, text))

        def queue_snapshot_save() -> None:
            status["text"] = "F12 snapshots are disabled during live frame verification"

        def queue_demo_toggle() -> None:
            status["text"] = "F11 input-demo recording is disabled during live frame verification"

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
                        trace_sample_changes=args.verify_frame_trace_raw,
                        trace_sample_change_start=args.verify_frame_trace_raw_from,
                        ega_start_address_units=args.ega_start_address_units,
                    ),
                    publish_candidate=publish_candidate,
                    pump_inputs=pump_inputs,
                    stop_requested=lambda: stop.is_set() or (
                        demo_playback is not None
                        and not args.demo_continue
                        and demo_playback.finished(frame_demo_boundary["n"])
                    ),
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
                queue_demo_toggle=queue_demo_toggle,
                queue_dos_key=queue_dos_key,
                ega_render_start=ega_render_start,
                live_memory=lambda: b"",
                live_display_start=lambda: 0,
                live_video_mode=lambda: 0xFF,
                live_video_page=lambda: 0,
                speaker_events=None,
                adlib_events=None,
            )
        finally:
            stop.set()
            frame_sync.close()
        return 0

    if args.verify_frames:
        from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier

        frame_demo_boundary = {"n": 0}

        def pump_demo_inputs(ref_rt, cand_rt) -> None:
            if demo_playback is None:
                return
            demo_playback.apply_to_runtimes(frame_demo_boundary["n"], (ref_rt, cand_rt))
            frame_demo_boundary["n"] += 1

        def demo_finished() -> bool:
            return (
                demo_playback is not None
                and not args.demo_continue
                and demo_playback.finished(frame_demo_boundary["n"])
            )

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
                trace_sample_changes=args.verify_frame_trace_raw,
                trace_sample_change_start=args.verify_frame_trace_raw_from,
                ega_start_address_units=args.ega_start_address_units,
            ),
            pump_inputs=pump_demo_inputs if demo_playback is not None else None,
            stop_requested=demo_finished if demo_playback is not None else None,
        )

    if args.snapshot:
        rt = load_overkill_snapshot(exe, args.snapshot, game_root=assets)
    else:
        rt = create_overkill_runtime(exe, game_root=assets, command_tail=command_tail)
        rt.dos.text_mode_active = False
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
    explicit_verify_hooks = {parse_verify_addr(text) for text in args.verify_hook}
    use_strict_hook_oracle = args.verify_strict or args.verify_hooks_strict
    if args.verify_hooks or args.verify_hooks_strict or explicit_verify_hooks:
        if use_strict_hook_oracle:
            verifier_config = HookVerifierConfig.strict(
                verify_all=args.verify_hooks or args.verify_hooks_strict,
                hooks=explicit_verify_hooks,
                max_verified=args.verify_max,
                asm_max_steps=1_000_000,
                progress_callback=lambda text: status.__setitem__("text", text),
            )
        else:
            verifier_config = HookVerifierConfig(
                verify_all=args.verify_hooks,
                hooks=explicit_verify_hooks,
                max_verified=args.verify_max,
                stop_on_diff=args.verify_stop_on_diff or args.verify_hooks or bool(explicit_verify_hooks),
                log_diffs=args.verify_log_diffs,
                full_memory=not args.verify_fast_ranges,
                require_metadata=args.verify_require_metadata,
                verify_nested_hooks=not args.verify_no_nested,
                asm_max_steps=1_000_000,
                progress_callback=lambda text: status.__setitem__("text", text),
            )
        hook_verifier = install_hook_verifier(rt, verifier_config)

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
    # 1010:50C9 is a hardware vertical-retrace wait, not the 1010:0679 game
    # timer frame wait.  Pacing it at --game-hz made menu/intro paths run at
    # ~36.4 Hz and starved the async AdLib IRQ cadence in screens that mostly
    # idle on retrace.  Default to the PC-family 60 Hz display cadence; tests and
    # diagnostics can still override this explicitly with --retrace-hz.
    retrace_pacer = TimerPacer(args.retrace_hz if args.retrace_hz is not None else 60.0)
    async_timer_irq = AsyncTimerIrqDriver()
    frame_sync = FrameSync()

    boundary = {"n": 0}
    visible = {"n": 0}
    blits = {"n": 0}
    timers = {"n": 0}
    retraces = {"n": 0}
    direct_video = {"n": 0}
    last_boundary: dict[str, str | None] = {"kind": None}
    last_video_crc: dict[str, tuple[int, int, int, int] | None] = {"value": None}
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
    # The SDL presenter hooks are UI pacing boundaries.  Verifying them inline
    # during interactive ``--verify-hooks`` can delay visible frames for a very
    # long time, making the window appear black even though the VM is working.
    # Keep them as passthrough by default; verify a presenter explicitly with
    # ``--verify-hook 1010:3354`` or use ``--verify-frames`` for visual proof.
    verify_presenter_inline = present_hook_addr in explicit_verify_hooks
    base_timer_wait = rt.cpu.replacement_hooks.get(TIMER_WAIT_HOOK)
    base_timer_wait_name = rt.cpu.hook_names.get(TIMER_WAIT_HOOK, "replacement")
    base_retrace_wait = rt.cpu.replacement_hooks.get(RETRACE_WAIT_HOOK)
    base_retrace_wait_name = rt.cpu.hook_names.get(RETRACE_WAIT_HOOK, "replacement")
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

    def is_text_display_active() -> bool:
        return rt.dos.text_mode_active and rt.dos.video_mode in (0, 1, 2, 3, 7)

    def published_video_mode() -> int:
        return rt.dos.video_mode if is_text_display_active() else 0xFF

    def video_crc(cpu) -> int:
        data = cpu.mem.data
        if is_text_display_active():
            base = 0xB0000 if rt.dos.video_mode == 7 else 0xB8000
            page = (rt.dos.video_page & 0x07) * 0x1000
            return zlib.crc32(data[base + page:base + page + 0x0FA0]) & 0xFFFFFFFF
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

    def publish_video_if_changed(
        cpu,
        *,
        force: bool = False,
        poll_audio_while_waiting: bool = False,
        wait_for_viewer: bool = True,
    ) -> bool:
        raw_display_start = cpu.mem.ega_display_start if args.video == "ega" else 0
        display_start = ega_render_start(raw_display_start) if args.video == "ega" else 0
        crc: int | None = None
        mode_key = published_video_mode()
        page_key = (rt.dos.video_page & 0xFF) if is_text_display_active() else 0
        if force and not (args.ega_log_starts and args.video == "ega"):
            visible_key = (mode_key, page_key, visible["n"] + 1, display_start)
        else:
            crc = video_crc(cpu)
            visible_key = (mode_key, page_key, crc, display_start)
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
            wait_poll = (lambda: async_timer_irq.poll(cpu, max_catchup=1)) if poll_audio_while_waiting else None
            wait_poll_interval = async_timer_irq.period * 0.5 if async_timer_irq.period > 0 else 0.004
            if is_text_display_active():
                frame_memory = cpu.mem.data
                frame_display_start = 0
                frame_video_mode = rt.dos.video_mode
            elif args.video == "ega":
                frame_memory = memoryview(cpu.mem.data)[video_base:video_base + video_size]
                frame_display_start = display_start
                frame_video_mode = published_video_mode()
            else:
                frame_memory = cpu.mem.data
                frame_display_start = display_start
                frame_video_mode = published_video_mode()

            if wait_for_viewer:
                frame_sync.publish_and_wait(
                    frame_memory,
                    display_start=frame_display_start,
                    video_mode=frame_video_mode,
                    video_page=rt.dos.video_page,
                    wait_poll=wait_poll,
                    wait_poll_interval=wait_poll_interval,
                )
            else:
                frame_sync.publish_nowait(
                    frame_memory,
                    display_start=frame_display_start,
                    video_mode=frame_video_mode,
                    video_page=rt.dos.video_page,
                )
        return True

    def stop_cpu_burst() -> None:
        boundary["n"] += 1
        raise FramePresented()

    def queue_dos_key(scancode: int, text: str) -> None:
        cs, ip = rt.cpu.addr()
        in_high_score_editor = cs == 0x1010 and 0x5300 <= ip <= 0x5650
        in_text_mode = is_text_display_active()
        if direct_video["n"] == 0 and not in_high_score_editor and not in_text_mode:
            return
        key = dos_key_value(scancode, text)
        if key is None:
            return
        rt.dos.key_queue.append(key)
        demo_recorder.record_dos_key(
            boundary=boundary["n"],
            scancode=scancode,
            text=text,
            value=key,
        )

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

    def is_menu_fire_select_wait() -> bool:
        cs, ip = rt.cpu.addr()
        if cs != 0x1010 or ip not in (0x55F1, 0x55F4, 0x55F9):
            return False
        mem = rt.cpu.mem
        if mem.block(cs, 0x55F1, 12) != bytes.fromhex("e8 4c ab 80 3e be 98 10 74 03 e9"):
            return False
        return mem.rb(rt.cpu.s.ds & 0xFFFF, 0x98BE) != 0x10

    def is_menu_fire_release_wait() -> bool:
        """Detect menu transition loops that wait for FIRE to be released.

        The main menu SPACE/FIRE path falls through a tight D390..D398 poll loop:
        CALL 0162; TEST byte [98BE],10h; JNZ D390.  There is no presenter or
        timer wait there, so a held fire key can otherwise make the emulator chew
        through the full no-boundary budget before the UI gets another turn.
        """
        cs, ip = rt.cpu.addr()
        if cs != 0x1010 or ip not in (0xD390, 0xD393, 0xD396, 0xD398):
            return False
        mem = rt.cpu.mem
        if mem.block(cs, 0xD390, 10) != bytes.fromhex("e8 cf 2d f6 06 be 98 10 75 f6"):
            return False
        return (mem.rb(rt.cpu.s.ds & 0xFFFF, 0x98BE) & 0x10) != 0

    def is_input_selector_wait() -> bool:
        """Detect the level/difficulty selector's idle poll gate.

        1010:D445 is now a one-iteration hook for the original selector
        busy-wait.  Treating it as an interactive wait lets the SDL side keep
        rendering, release keys, and process F12 snapshots while the game waits
        for the next level-select key.
        """
        cs, ip = rt.cpu.addr()
        if cs != 0x1010 or ip != 0xD445:
            return False
        mem = rt.cpu.mem
        return mem.block(cs, 0xD445, 7) == bytes.fromhex("80 3e e4 98 01 75")

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

    def is_boss_key_screen_wait() -> bool:
        """Detect the F9 boss-key text screen's interactive wait loops.

        F9 arms DS:9907 through OVERKILL's own INT 09h keyboard ISR.  The
        per-frame 073C service gate then switches to BIOS text mode 3, draws the
        fake DOS-like boss-key screen, and waits in three tight loops:

        * 07C4 waits for the original F9 press to be released;
        * 07D0 waits for any key to leave the boss screen;
        * 07D7 waits for that return key to be released before restoring the
          game video mode.

        None of those loops reaches a gameplay presenter, timer wait, or retrace
        wait.  Treat them as cooperative UI boundaries so the text screen is
        published immediately and key-up/F12 events are not starved behind the
        full no-boundary frame budget.
        """
        cs, ip = rt.cpu.addr()
        window = boss_key_wait_window(ip)
        if cs != 0x1010 or window is None:
            return False
        mem = rt.cpu.mem
        start, _end = window
        if start == 0x07C4:
            if mem.block(cs, 0x07C4, 7) != bytes.fromhex("80 3e 07 99 01 74 f9"):
                return False
            return mem.rb(rt.cpu.s.ds & 0xFFFF, 0x9907) == 1
        if start == 0x07D0:
            if mem.block(cs, 0x07D0, 7) != bytes.fromhex("80 3e c3 98 00 74 f9"):
                return False
            return mem.rb(rt.cpu.s.ds & 0xFFFF, 0x98C3) == 0
        if mem.block(cs, 0x07D7, 7) != bytes.fromhex("80 3e 07 99 01 74 f9"):
            return False
        return mem.rb(rt.cpu.s.ds & 0xFFFF, 0x9907) == 1

    def present_hook(cpu) -> None:
        if base_present is not None:
            if hook_verifier is not None and verify_presenter_inline:
                hook_verifier.verify(cpu, present_hook_addr, base_present, base_present_name)
            else:
                base_present(cpu)
        blits["n"] += 1
        rt.dos.text_mode_active = False
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
        # cpu.step() deliberately treats the interactive timer wrapper as
        # verifier-pass-through because the wrapper publishes/paces and raises
        # FramePresented.  Still verify the pure install-time 0679 hook at this
        # outer boundary; only nested calls inside a verified parent use the
        # publish-only live passthrough below.
        if hook_verifier is not None:
            hook_verifier.verify(cpu, TIMER_WAIT_HOOK, base_timer_wait, base_timer_wait_name)
        else:
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
            if hook_verifier is not None:
                hook_verifier.verify(cpu, RETRACE_WAIT_HOOK, base_retrace_wait, base_retrace_wait_name)
            else:
                base_retrace_wait(cpu)
        retraces["n"] += 1
        # Intro/menu/fade code often draws first and then waits for retrace.  For
        # EGA, publish these timed snapshots only until the first explicit EGA
        # presenter runs; after that, keep retrace as a pacing boundary only.
        if args.video != "ega" or args.ega_publish_timed_boundaries or blits["n"] == 0:
            publish_video_if_changed(cpu, poll_audio_while_waiting=True)
        retrace_pacer(
            poll=lambda: async_timer_irq.poll(cpu, max_catchup=1),
            poll_interval=async_timer_irq.period * 0.5 if async_timer_irq.period > 0 else None,
        )
        last_boundary["kind"] = "retrace"
        stop_cpu_burst()

    def present_hook_verify_live(cpu) -> None:
        """Live-side presenter used inside differential hook transactions.

        A verified parent hook must run atomically to its continuation, so the
        normal interactive presenter cannot raise FramePresented from inside the
        transaction.  Still publish a nowait frame from the live CPU after
        applying the exact base presenter side effects; otherwise --verify-hooks
        can show only the pre-verification snapshot until a very large parent
        hook finishes.
        """
        if base_present is not None:
            base_present(cpu)
        blits["n"] += 1
        rt.dos.text_mode_active = False
        if args.video != "ega" or args.ega_publish_all_presents or (cpu.mem.ega_display_start & 0xFFFF) == 0:
            publish_video_if_changed(cpu, force=True, wait_for_viewer=False)
        last_boundary["kind"] = "verify-present"
        cpu.hook_verifier_live_yield_requested = True

    def timer_frame_hook_verify_live(cpu) -> None:
        """Live-side timer boundary that publishes/paces but does not break verify."""
        base_timer_wait(cpu)
        async_timer_irq.reset_after_synchronous_ticks(2)
        timers["n"] += 1
        if args.video != "ega" or args.ega_publish_timed_boundaries or blits["n"] == 0:
            publish_video_if_changed(cpu, wait_for_viewer=False)
        # Do not raise FramePresented inside a parent-hook transaction, but do
        # keep the same real-time pacing.  Without this, verified parent hooks
        # that contain one or more 0679 waits can fast-forward gameplay and make
        # keyboard input appear unresponsive until the transaction returns.
        timer_pacer(2)
        last_boundary["kind"] = "verify-timer"
        cpu.hook_verifier_live_yield_requested = True

    def retrace_frame_hook_verify_live(cpu) -> None:
        """Live-side retrace boundary that publishes/paces but does not break verify."""
        async_timer_irq.poll(cpu)
        if base_retrace_wait is not None:
            base_retrace_wait(cpu)
        retraces["n"] += 1
        if args.video != "ega" or args.ega_publish_timed_boundaries or blits["n"] == 0:
            publish_video_if_changed(cpu, wait_for_viewer=False)
        retrace_pacer(
            poll=lambda: async_timer_irq.poll(cpu, max_catchup=1),
            poll_interval=async_timer_irq.period * 0.5 if async_timer_irq.period > 0 else None,
        )
        last_boundary["kind"] = "verify-retrace"
        cpu.hook_verifier_live_yield_requested = True

    rt.cpu.hook_verifier_live_yield_callback = stop_cpu_burst
    rt.cpu.replacement_hooks[present_hook_addr] = present_hook
    rt.cpu.replacement_hooks[TIMER_WAIT_HOOK] = timer_frame_hook
    if base_retrace_wait is not None:
        rt.cpu.replacement_hooks[RETRACE_WAIT_HOOK] = retrace_frame_hook
    # These three hooks are UI pacing wrappers in play.py.  Let them execute
    # directly; present_hook manually verifies the underlying real presenter
    # before publishing to Tk.
    rt.cpu.hook_verifier_passthrough.update({present_hook_addr, TIMER_WAIT_HOOK, RETRACE_WAIT_HOOK})
    rt.cpu.hook_verifier_live_passthrough_overrides[present_hook_addr] = present_hook_verify_live
    rt.cpu.hook_verifier_live_passthrough_overrides[TIMER_WAIT_HOOK] = timer_frame_hook_verify_live
    if base_retrace_wait is not None:
        rt.cpu.hook_verifier_live_passthrough_overrides[RETRACE_WAIT_HOOK] = retrace_frame_hook_verify_live

    demo_recorder = InputDemoRecorder(
        root=Path(args.save_demo_root),
        name=f"play_{args.video}",
        metadata={
            "program": "overkill",
            "video": args.video,
            "sound": args.sound,
            "command_tail": command_tail.decode("latin1") if isinstance(command_tail, bytes) else str(command_tail),
        },
    )

    def deliver_live_scancode(sc: int) -> None:
        deliver_scancode(rt, sc)
        demo_recorder.record_scan(boundary=boundary["n"], scancode=sc)

    keyboard = KeyDispatcher(deliver_live_scancode)
    stop = threading.Event()
    snapshot_requests: SimpleQueue[Path] = SimpleQueue()
    demo_toggle_requests: SimpleQueue[None] = SimpleQueue()
    speaker_events: SimpleQueue[tuple[bool, float]] = SimpleQueue()
    adlib_events: SimpleQueue[tuple[int, int]] | None = SimpleQueue() if args.sound == "adlib" else None
    rt.dos.set_speaker_callback(lambda enabled, freq: speaker_events.put((enabled, freq)), emit_current=True)
    if adlib_events is not None:
        rt.dos.set_adlib_callback(lambda reg, value: adlib_events.put((reg, value)), emit_current=True)

    def queue_snapshot_save() -> None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = Path(args.save_snapshot_root) / f"snapshot_play_{args.video}_{stamp}"
        snapshot_requests.put(out)
        status["text"] = f"snapshot queued: {out}"

    def queue_demo_toggle() -> None:
        if demo_playback is not None:
            status["text"] = "F11 recording disabled while replaying --demo"
            return
        demo_toggle_requests.put(None)
        status["text"] = "input demo toggle queued"

    def handle_demo_toggles() -> None:
        toggled = False
        while True:
            try:
                demo_toggle_requests.get_nowait()
            except Empty:
                break
            toggled = True
        if not toggled:
            return
        if demo_recorder.active:
            out = demo_recorder.stop(boundary=boundary["n"])
            status["text"] = f"input demo saved: {out}"
        else:
            out = demo_recorder.start(rt, boundary=boundary["n"])
            status["text"] = f"input demo recording: {out}"

    def sleep_with_async_irqs(cpu, seconds: float = 0.01) -> None:
        deadline = time.perf_counter() + max(0.0, float(seconds))
        interval = async_timer_irq.period * 0.5 if async_timer_irq.period > 0 else 0.004
        interval = max(0.001, min(0.01, interval))
        while True:
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                break
            time.sleep(min(remaining, interval))
            async_timer_irq.poll(cpu, max_catchup=1)

    def emulator_loop() -> None:
        while not stop.is_set():
            try:
                handle_demo_toggles()
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
                if demo_playback is not None:
                    if not args.demo_continue and demo_playback.finished(boundary["n"]):
                        status["text"] = f"input demo finished at boundary={boundary['n']}"
                        print(status["text"], flush=True)
                        stop.set()
                        break
                    applied = demo_playback.apply_to_runtime(boundary["n"], rt)
                    if applied:
                        status["text"] = f"input demo replay boundary={boundary['n']} events={applied}"
                else:
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
                        publish_video_if_changed(rt.cpu, poll_audio_while_waiting=True)
                        boundary["n"] += 1
                        last_boundary["kind"] = "wait"
                        cs, ip = rt.cpu.addr()
                        status["text"] = f"waiting for DOS console input @ {cs:04X}:{ip:04X}"
                        sleep_with_async_irqs(rt.cpu, 0.01)
                        break
                    if is_redefine_key_wait():
                        async_timer_irq.poll(rt.cpu)
                        publish_video_if_changed(rt.cpu, poll_audio_while_waiting=True)
                        boundary["n"] += 1
                        last_boundary["kind"] = "wait"
                        cs, ip = rt.cpu.addr()
                        status["text"] = f"waiting for redefine-key input @ {cs:04X}:{ip:04X}"
                        sleep_with_async_irqs(rt.cpu, 0.01)
                        break
                    if is_menu_fire_select_wait():
                        async_timer_irq.poll(rt.cpu)
                        publish_video_if_changed(rt.cpu, poll_audio_while_waiting=True)
                        boundary["n"] += 1
                        last_boundary["kind"] = "wait"
                        cs, ip = rt.cpu.addr()
                        status["text"] = f"waiting for menu select input @ {cs:04X}:{ip:04X}"
                        sleep_with_async_irqs(rt.cpu, 0.01)
                        break
                    if is_menu_fire_release_wait():
                        async_timer_irq.poll(rt.cpu)
                        publish_video_if_changed(rt.cpu, poll_audio_while_waiting=True)
                        boundary["n"] += 1
                        last_boundary["kind"] = "wait"
                        cs, ip = rt.cpu.addr()
                        status["text"] = f"waiting for menu fire release @ {cs:04X}:{ip:04X}"
                        sleep_with_async_irqs(rt.cpu, 0.01)
                        break
                    if is_input_selector_wait():
                        async_timer_irq.poll(rt.cpu)
                        publish_video_if_changed(rt.cpu, poll_audio_while_waiting=True)
                        boundary["n"] += 1
                        last_boundary["kind"] = "wait"
                        cs, ip = rt.cpu.addr()
                        status["text"] = f"waiting for selector input @ {cs:04X}:{ip:04X}"
                        sleep_with_async_irqs(rt.cpu, 0.01)
                        break
                    if is_overlay_menu_key_wait():
                        async_timer_irq.poll(rt.cpu)
                        publish_video_if_changed(rt.cpu, poll_audio_while_waiting=True)
                        boundary["n"] += 1
                        last_boundary["kind"] = "wait"
                        cs, ip = rt.cpu.addr()
                        status["text"] = f"waiting for menu screen input @ {cs:04X}:{ip:04X}"
                        sleep_with_async_irqs(rt.cpu, 0.01)
                        break
                    if is_gameplay_exit_confirm_wait():
                        async_timer_irq.poll(rt.cpu)
                        publish_video_if_changed(rt.cpu, force=True, poll_audio_while_waiting=True)
                        boundary["n"] += 1
                        last_boundary["kind"] = "wait"
                        cs, ip = rt.cpu.addr()
                        status["text"] = f"waiting for exit confirmation @ {cs:04X}:{ip:04X}"
                        sleep_with_async_irqs(rt.cpu, 0.01)
                        break
                    if is_boss_key_screen_wait():
                        async_timer_irq.poll(rt.cpu)
                        # Force the boss-key text screen out even if its B800h
                        # contents match the previous boss screen.  Otherwise a
                        # second F9 on a static game frame can look like a freeze:
                        # the VM is correctly waiting in text mode, but the SDL
                        # side is still showing the old graphics frame because
                        # the text CRC was de-duplicated.
                        publish_video_if_changed(rt.cpu, force=True, poll_audio_while_waiting=True)
                        boundary["n"] += 1
                        last_boundary["kind"] = "wait"
                        cs, ip = rt.cpu.addr()
                        status["text"] = f"waiting on boss-key screen @ {cs:04X}:{ip:04X}"
                        sleep_with_async_irqs(rt.cpu, 0.01)
                        break
                    used += max(1, int(args.cpu_chunk_steps))
                    async_timer_irq.poll(rt.cpu)
                    # Long screen loads can run for many chunks without a
                    # visible/timer boundary.  Drain key-up events during those
                    # bursts so a short FIRE tap from the menu is not still held
                    # when the newly loaded level-select screen first polls input.
                    if demo_playback is None:
                        keyboard.pump_events()
                if boundary["n"] < target and not stop.is_set():
                    cs, ip = rt.cpu.addr()
                    if publish_video_if_changed(rt.cpu, poll_audio_while_waiting=True):
                        direct_video["n"] += 1
                        boundary["n"] += 1
                        last_boundary["kind"] = "direct"
                        status["text"] = f"direct video publish @ {cs:04X}:{ip:04X}"
                    else:
                        status["text"] = f"stall (no visual/timer boundary in {used} steps) @ {cs:04X}:{ip:04X}"
            except HookVerifyDivergence as exc:
                cs, ip = rt.cpu.addr()
                status["text"] = f"HOOK VERIFY DIVERGENCE @ {cs:04X}:{ip:04X} (see console)"
                print(exc, flush=True)
                # A divergence is a fatal verification result: stop the emulator
                # and wake the UI so the window closes instead of hanging on a
                # dead emulator thread.
                stop.set()
                frame_sync.close()
                return
            except Exception as exc:
                cs, ip = rt.cpu.addr()
                status["text"] = f"CRASH @ {cs:04X}:{ip:04X} - {type(exc).__name__}: {exc}"
                traceback.print_exc()
                stop.set()
                frame_sync.close()
                return

    try:
        from sdl_view import run_sdl_ui
    except Exception as exc:
        print(f"the interactive viewer requires pygame and numpy: {exc}")
        return 1

    # Show the loaded/current snapshot immediately.  This is especially important
    # with interactive hook verification: the verifier may spend a long time
    # proving object/update hooks before the next natural present boundary, and
    # otherwise SDL keeps showing its initial black window.
    publish_video_if_changed(rt.cpu, force=True, wait_for_viewer=False)

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
            queue_demo_toggle=queue_demo_toggle,
            queue_dos_key=queue_dos_key,
            ega_render_start=ega_render_start,
            live_memory=lambda: bytes(rt.program.memory.data),
            live_display_start=lambda: rt.program.memory.ega_display_start,
            live_video_mode=published_video_mode,
            live_video_page=lambda: rt.dos.video_page,
            speaker_events=speaker_events,
            adlib_events=adlib_events,
        )
    finally:
        stop.set()
        frame_sync.close()
        if dashboard is not None:
            dashboard.close()
        if demo_recorder.active:
            try:
                out = demo_recorder.stop(boundary=boundary["n"])
                print(f"input demo saved: {out}", flush=True)
            except Exception as exc:
                print(f"input demo save failed: {type(exc).__name__}: {exc}", flush=True)
        coverage.save_cache()
        if not args.no_coverage_summary:
            print(coverage.format_summary(), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
