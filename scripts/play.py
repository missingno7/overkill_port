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

Controls: Q/A/O/P move, Z or Space fire (the game's own scheme), F7 saves a
runtime snapshot.  F8 toggles deterministic input-demo recording: it writes a
start snapshot and records VM-delivered keyboard events until F8 is pressed
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
# The dos_re submodule's repo root (the package is one level deeper). Without
# this, running under an interpreter with no pip-editable dos_re install (e.g.
# PyPy) resolves `dos_re` to the repo dir as a bare namespace package.
sys.path.insert(0, str(ROOT / "dos_re"))

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
from dos_re.repro_artifacts import write_runtime_repro_snapshot
from dos_re.memory import EGA_APERTURE, EGA_SHADOW_SIZE
from overkill.coverage import (
    CoverageDashboardTk,
    CoverageTelemetry,
    OverkillCoverageClassifier,
)
from overkill.sounds import AsyncTimerIrqDriver, OVERKILL_PIT_HZ
from overkill.launch import build_command_tail
from dos_re.input_demo import InputDemoPlayback, InputDemoRecorder, dos_key_value
from overkill.input_waits import overlay_menu_key_wait, pump_demo_frame, title_fire_release_wait
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
DEFAULT_FRAME_BUDGET = 6_000_000
DEFAULT_CPU_CHUNK_STEPS = 1000
COVERAGE_CACHE = ROOT / "artifacts" / "hook_coverage_cache.json"

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
    p = argparse.ArgumentParser(
        description="OVERKILL player and strict verification runner"
    )

    launch = p.add_argument_group("launch / replay")
    launch.add_argument("--video", choices=("cga", "ega", "tandy"), default="tandy",
                        help="launch/render the original game in this video mode")
    launch.add_argument("--sound", choices=("pc", "adlib", "roland"), default="pc",
                        help="select the original optional music driver")
    launch.add_argument("--dos-args", default=None,
                        help="raw PSP command-tail override; bypasses --video/--sound")
    launch.add_argument("--snapshot", default=None,
                        help="load a saved snapshot directory")
    launch.add_argument("--play-demo", "--demo", dest="demo", default=None, metavar="DIR",
                        help="replay an input demo directory/json; loads its start snapshot unless "
                             "--snapshot is also given (--demo is the deprecated alias)")
    launch.add_argument("--demo-continue", action="store_true",
                        help="keep running/verifying after the input demo ends")
    launch.add_argument("--safe-hooks", action="store_true",
                        help="standard play.py flag; OVERKILL has no write-set-classified safe-hook "
                             "tier yet, so this fails loud instead of running something else")
    launch.add_argument("--headless", action="store_true",
                        help="standard play.py flag; OVERKILL's threaded viewer has no plain headless "
                             "run yet (fails loud) — headless verification is --verify-hooks/--verify-frames")
    launch.add_argument("--no-replacements", action="store_true",
                        help="ORACLE mode: run the pure original ASM with no recovered hooks (record "
                             "ground-truth cold-start demos; the reference side of the cold-start verifier)")
    launch.add_argument("--record-demo", default=None, metavar="NAME",
                        help="start recording an input demo at launch (boundary 0).  With a fresh boot "
                             "(no --snapshot) this records a COLD-START demo (no start snapshot) -- press "
                             "F8 or quit to stop; combine with --no-replacements for a pure-ASM oracle demo")

    viewer = p.add_argument_group("interactive viewer")
    viewer.add_argument("--game-hz", type=float, default=36.4,
                        help="real-time game speed for interactive play")
    viewer.add_argument("--retrace-hz", type=float, default=None,
                        help="interactive hardware-retrace pacing; default is 60 Hz")
    viewer.add_argument("--palette", default="1h", choices=sorted(CGA_PALETTES),
                        help="CGA palette used by the viewer/frame renderer")
    viewer.add_argument("--scale", type=int, default=2,
                        help="SDL viewer pixel scale")
    viewer.add_argument("--adlib-audio", choices=("auto", "off"), default="auto",
                        help="when --sound adlib is active, stream OPL writes through dos_re's OPL3 "
                             "backend (opl3-fast by default, no build needed)")
    viewer.add_argument("--adlib-chunk-ms", type=float, default=46.0,
                        help="SDL AdLib PCM chunk size in milliseconds")
    viewer.add_argument("--save-snapshot-root", default=str(ROOT / "artifacts"),
                        help="root directory for F7 runtime snapshots")
    viewer.add_argument("--save-demo-root", default=str(ROOT / "artifacts" / "demos"),
                        help="root directory for F8 input demos")
    viewer.add_argument("--save-repro-root", default=str(ROOT / "artifacts" / "repros"),
                        help="root directory for F8 demo suffixes, verifier divergence repro demos, and crash snapshots")
    viewer.add_argument("--no-crash-snapshot", action="store_true",
                        help="do not save a repro snapshot under --save-repro-root when gameplay crashes")

    verify = p.add_argument_group("verification")
    verify.add_argument("--verify-hooks", action="store_true",
                        help="headless strict hook verifier; use --verify-preview to show SDL while verifying")
    verify.add_argument("--verify-hook", action="append", default=[], metavar="CS:IP",
                        help="verify one hook address; may be repeated and implies hook verification")
    verify.add_argument("--verify-frames", action="store_true",
                        help="headless differential frame verifier: reference ASM runtime vs hooked runtime")
    verify.add_argument("--verify-max", type=int, default=None,
                        help="hook verifier success limit; headless default is 1000")
    verify.add_argument("--verify-step-budget", type=int, default=4_000_000,
                        help="headless hook-verifier outer CPU step budget")
    verify.add_argument("--verify-preview", action="store_true",
                        help="show a live SDL preview while a verifier runs")
    verify.add_argument("--verify-frame-max", type=int, default=60,
                        help="stop frame verifier after N frame/timer/retrace boundaries")
    verify.add_argument("--verify-frame-source", choices=("rgb", "vram", "both"), default="both",
                        help="frame verifier comparison source")
    verify.add_argument("--verify-frame-dump-dir", default=str(ROOT / "artifacts" / "frame_verify"),
                        help="directory for frame verifier divergence PNG/VRAM/report artifacts")
    verify.add_argument("--verify-open-diff", action="store_true",
                        help="open the frame compare image when frame verification finds a diff")
    verify.add_argument("--verify-frame-trace-raw", action="store_true",
                        help="on frame divergence, include recent candidate hooks that changed sampled raw frame bytes")
    verify.add_argument("--verify-frame-trace-raw-from", type=int, default=1,
                        help="first frame number where raw-frame tracing starts")

    diagnostics = p.add_argument_group("diagnostics")
    diagnostics.add_argument("--coverage-dashboard", action="store_true",
                             help="open a live Tk ASM / Hook Coverage dashboard next to the gameplay window")
    diagnostics.add_argument("--coverage-refresh-hz", type=float, default=4.0,
                             help="Tk coverage dashboard refresh rate")
    diagnostics.add_argument("--no-coverage-summary", action="store_true",
                             help="do not print the final ASM / Hook Coverage summary on exit")

    args = p.parse_args(argv)

    if args.verify_frames and (args.verify_hooks or args.verify_hook):
        p.error("choose either --verify-frames or --verify-hooks/--verify-hook, not both")
    # Standard play.py vocabulary, fail-loud where OVERKILL has no such tier yet
    # (never silently run something else than what the flag promises).
    if args.safe_hooks:
        p.error("--safe-hooks: OVERKILL has no write-set-classified safe-hook tier yet")
    if args.headless:
        p.error("--headless: OVERKILL's threaded viewer has no plain headless run yet; "
                "headless verification is --verify-hooks / --verify-frames")

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
            if demo_playback.is_cold_start:
                # a cold-start demo replays from power-on: boot a FRESH runtime with the demo's
                # own recorded boot params so replay is deterministic regardless of CLI defaults
                meta = demo_playback.manifest.get("metadata", {})
                args.video = str(meta.get("video", args.video))
                args.sound = str(meta.get("sound", args.sound))
                if args.dos_args is None and meta.get("command_tail") is not None:
                    command_tail = str(meta["command_tail"])
                print(f"cold-start demo replay: fresh boot, video={args.video} "
                      f"sound={args.sound} tail={command_tail!r}")
            else:
                args.snapshot = str(demo_playback.snapshot_path())

    explicit_verify_hooks = {parse_verify_addr(text) for text in args.verify_hook}
    if (args.verify_hooks or explicit_verify_hooks) and not args.verify_preview:
        from overkill.headless_verification import HeadlessHookVerifyConfig, run_headless_hook_verifier

        return run_headless_hook_verifier(
            HeadlessHookVerifyConfig(
                exe=exe,
                game_root=assets,
                snapshot=args.snapshot,
                demo=args.demo,
                demo_continue=args.demo_continue,
                video=args.video,
                sound=args.sound,
                command_tail=command_tail,
                verify_all=args.verify_hooks,
                hooks=explicit_verify_hooks,
                max_verified=args.verify_max if args.verify_max is not None else 1000,
                max_steps=args.verify_step_budget,
                repro_root=Path(args.save_repro_root),
            )
        )

    if args.verify_frames and args.verify_preview:
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
            if False:
                return 0
            if False:
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
                frame_demo_boundary["n"], _ = pump_demo_frame(
                    demo_playback, frame_demo_boundary["n"], (ref_rt, cand_rt), ref_rt.cpu)
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

        def save_frame_divergence_repro(ref_rt, cand_rt, ref_sample, cand_sample, report: str) -> None:
            metadata = {
                "program": "overkill",
                "video": args.video,
                "sound": args.sound,
                "command_tail": command_tail.decode("latin1") if isinstance(command_tail, bytes) else str(command_tail),
                "created_by": "scripts/play.py --verify-frames --verify-preview divergence",
                "frame": ref_sample.frame_no,
                "boundary": frame_demo_boundary["n"],
                "reference_boundary": f"{ref_sample.kind} {ref_sample.hook[0]:04X}:{ref_sample.hook[1]:04X}",
                "candidate_boundary": f"{cand_sample.kind} {cand_sample.hook[0]:04X}:{cand_sample.hook[1]:04X}",
                "reference_continuation": f"{ref_sample.cs:04X}:{ref_sample.ip:04X}",
                "candidate_continuation": f"{cand_sample.cs:04X}:{cand_sample.ip:04X}",
                "repro_state": "candidate_pre_divergent_frame",
                "frame_report_tail": report[-20000:],
            }
            if demo_playback is not None:
                try:
                    out = demo_playback.write_suffix(
                        cand_rt,
                        root=Path(args.save_repro_root),
                        name=f"frame_divergence_{args.video}",
                        boundary=frame_demo_boundary["n"],
                        status=(
                            f"frame verifier candidate pre-divergent-frame snapshot "
                            f"before frame {ref_sample.frame_no}"
                        ),
                        metadata=metadata,
                    )
                    print(f"FRAME VERIFY repro demo saved: {out}", flush=True)
                    status["text"] = f"FRAME VERIFY repro demo saved: {out}"
                except Exception as save_exc:
                    print(f"FRAME VERIFY repro demo save failed: {type(save_exc).__name__}: {save_exc}", flush=True)
            else:
                try:
                    out = write_runtime_repro_snapshot(
                        cand_rt,
                        root=Path(args.save_repro_root),
                        name=f"frame_divergence_{args.video}",
                        status=(
                            f"frame verifier candidate pre-divergent-frame snapshot "
                            f"before frame {ref_sample.frame_no}"
                        ),
                        metadata={
                            **metadata,
                            "replay_hint": "python scripts/play.py --snapshot <this-directory> --verify-frames",
                        },
                    )
                    print(f"FRAME VERIFY repro snapshot saved: {out}", flush=True)
                    status["text"] = f"FRAME VERIFY repro snapshot saved: {out}"
                except Exception as save_exc:
                    print(f"FRAME VERIFY repro snapshot save failed: {type(save_exc).__name__}: {save_exc}", flush=True)

        def queue_dos_key(scancode: int, text: str) -> None:
            dos_key_events.put((scancode, text))

        def queue_snapshot_save() -> None:
            status["text"] = "F7 snapshots are disabled during live frame verification"

        def queue_demo_toggle() -> None:
            status["text"] = "F8 input-demo recording is disabled during live frame verification"

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
                        frame_budget=DEFAULT_FRAME_BUDGET,
                        source=args.verify_frame_source,
                        dump_dir=Path(args.verify_frame_dump_dir),
                        stop_on_diff=True,
                        preview_on_diff=args.verify_open_diff,
                        trace_sample_changes=args.verify_frame_trace_raw,
                        trace_sample_change_start=args.verify_frame_trace_raw_from,
                        ega_start_address_units="byte",
                    ),
                    publish_candidate=publish_candidate,
                    pump_inputs=pump_inputs,
                    on_divergence=save_frame_divergence_repro,
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
            frame_demo_boundary["n"], _ = pump_demo_frame(
                demo_playback, frame_demo_boundary["n"], (ref_rt, cand_rt), ref_rt.cpu)
            frame_demo_boundary["n"] += 1

        def demo_finished() -> bool:
            return (
                demo_playback is not None
                and not args.demo_continue
                and demo_playback.finished(frame_demo_boundary["n"])
            )

        def save_frame_divergence_repro(ref_rt, cand_rt, ref_sample, cand_sample, report: str) -> None:
            metadata = {
                "program": "overkill",
                "video": args.video,
                "sound": args.sound,
                "command_tail": command_tail.decode("latin1") if isinstance(command_tail, bytes) else str(command_tail),
                "created_by": "scripts/play.py --verify-frames divergence",
                "frame": ref_sample.frame_no,
                "boundary": frame_demo_boundary["n"],
                "reference_boundary": f"{ref_sample.kind} {ref_sample.hook[0]:04X}:{ref_sample.hook[1]:04X}",
                "candidate_boundary": f"{cand_sample.kind} {cand_sample.hook[0]:04X}:{cand_sample.hook[1]:04X}",
                "reference_continuation": f"{ref_sample.cs:04X}:{ref_sample.ip:04X}",
                "candidate_continuation": f"{cand_sample.cs:04X}:{cand_sample.ip:04X}",
                "repro_state": "candidate_pre_divergent_frame",
                "frame_report_tail": report[-20000:],
            }
            if demo_playback is not None:
                try:
                    out = demo_playback.write_suffix(
                        cand_rt,
                        root=Path(args.save_repro_root),
                        name=f"frame_divergence_{args.video}",
                        boundary=frame_demo_boundary["n"],
                        status=(
                            f"frame verifier candidate pre-divergent-frame snapshot "
                            f"before frame {ref_sample.frame_no}"
                        ),
                        metadata=metadata,
                    )
                    print(f"FRAME VERIFY repro demo saved: {out}", flush=True)
                except Exception as save_exc:
                    print(f"FRAME VERIFY repro demo save failed: {type(save_exc).__name__}: {save_exc}", flush=True)
            else:
                try:
                    out = write_runtime_repro_snapshot(
                        cand_rt,
                        root=Path(args.save_repro_root),
                        name=f"frame_divergence_{args.video}",
                        status=(
                            f"frame verifier candidate pre-divergent-frame snapshot "
                            f"before frame {ref_sample.frame_no}"
                        ),
                        metadata={
                            **metadata,
                            "replay_hint": "python scripts/play.py --snapshot <this-directory> --verify-frames",
                        },
                    )
                    print(f"FRAME VERIFY repro snapshot saved: {out}", flush=True)
                except Exception as save_exc:
                    print(f"FRAME VERIFY repro snapshot save failed: {type(save_exc).__name__}: {save_exc}", flush=True)

        return run_frame_verifier(
            exe=exe,
            assets=assets,
            snapshot=args.snapshot,
            command_tail=command_tail,
            config=FrameVerifyConfig(
                video=args.video,
                palette=args.palette,
                max_frames=args.verify_frame_max,
                frame_budget=DEFAULT_FRAME_BUDGET,
                source=args.verify_frame_source,
                dump_dir=Path(args.verify_frame_dump_dir),
                stop_on_diff=True,
                preview_on_diff=args.verify_open_diff,
                trace_sample_changes=args.verify_frame_trace_raw,
                trace_sample_change_start=args.verify_frame_trace_raw_from,
                ega_start_address_units="byte",
            ),
            pump_inputs=pump_demo_inputs if demo_playback is not None else None,
            on_divergence=save_frame_divergence_repro,
            stop_requested=demo_finished if demo_playback is not None else None,
        )

    if args.snapshot:
        rt = load_overkill_snapshot(exe, args.snapshot, game_root=assets)
    else:
        rt = create_overkill_runtime(exe, game_root=assets, command_tail=command_tail)
        rt.dos.text_mode_active = False
    # --no-replacements handled below, after the viewer's pacing/present hooks are captured + reinstalled:
    # the interactive viewer needs the timer-wait (0679), frame-present, retrace, and LZEXE-boot hooks to
    # run and detect frames, so they are kept while every recovered GAME-LOGIC hook is dropped (pure ASM).
    rt.dos.console_input_fallback = None
    rt.cpu.trace_enabled = False
    coverage = CoverageTelemetry(
        classifier=OverkillCoverageClassifier(ROOT / "symbols.json"),
        cache_path=COVERAGE_CACHE,
        enabled=True,
    )
    rt.cpu.coverage_telemetry = coverage
    status = {"text": ""}
    hook_verifier = None
    if args.verify_hooks or explicit_verify_hooks:
        hook_verifier = install_hook_verifier(
            rt,
            HookVerifierConfig.strict(
                verify_all=args.verify_hooks,
                hooks=explicit_verify_hooks,
                max_verified=args.verify_max,
                asm_max_steps=5_000_000,
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
        if False:
            return 0
        if False:
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
        if force and not (False):
            visible_key = (mode_key, page_key, visible["n"] + 1, display_start)
        else:
            crc = video_crc(cpu)
            visible_key = (mode_key, page_key, crc, display_start)
            if not force and last_video_crc["value"] == visible_key:
                return False
        last_video_crc["value"] = visible_key
        visible["n"] += 1
        if False:
            if crc is None:
                crc = video_crc(cpu)
            print(
                f"EGA publish visible={visible['n']} blits={blits['n']} "
                f"raw_start={raw_display_start:04X} render_start={display_start:04X} "
                f"crc={crc:08X}",
                flush=True,
            )
        if True:
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
        if getattr(rt.cpu, "_hook_verify_live_depth", 0) > 0:
            return
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

    def is_title_fire_release_wait() -> bool:
        """Detect the title/attract screen's wait-for-FIRE-release loop.

        The D318 title frame loop polls FIRE at D352; once FIRE (bit 10h of
        DS:98BE) is pressed it falls into a tight release loop:
        CALL 0162; TEST byte [98BE],10h; JNZ D35C.  Unlike the D318 body, this
        loop contains no 0679 timer wait or 50C9 retrace wait, so it never
        produces a play boundary.  During --demo replay that is fatal: the
        recorded FIRE-release event is keyed to a later boundary that can never
        be reached while the boundary counter is frozen here, so the demo
        deadlocks waiting for a release it can never deliver.  Treat it as an
        interactive wait (same as the D390 menu release loop) so the boundary
        advances and queued input/the recorded release can land.
        """
        # Shared with the frame verifier via overkill.input_waits so the same
        # boundary-less wait loop is handled identically across interactive play,
        # --verify-hooks, and --verify-frames.
        return title_fire_release_wait(rt.cpu)


    def is_overlay_menu_key_wait() -> bool:
        """Detect the overlay-segment menu key wait (099B..09DF).

        Shared with the frame verifier via overkill.input_waits so the same boundary-less wait loop
        is handled identically across interactive play, --verify-hooks and --verify-frames -- the
        same reason is_title_fire_release_wait delegates.  It was NOT shared before, so headless
        demo replay wedged here (FRAME VERIFY TIMEOUT at 1F8F:09D3) while interactive play was fine.
        """
        return overlay_menu_key_wait(rt.cpu)

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
        if args.video != "ega" or (cpu.mem.ega_display_start & 0xFFFF) == 0:
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
        if args.video != "ega" or blits["n"] == 0:
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
        if args.video != "ega" or blits["n"] == 0:
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
        if args.video != "ega" or (cpu.mem.ega_display_start & 0xFFFF) == 0:
            publish_video_if_changed(cpu, force=True, wait_for_viewer=False)
        last_boundary["kind"] = "verify-present"
        cpu.hook_verifier_live_yield_requested = True

    def timer_frame_hook_verify_live(cpu) -> None:
        """Live-side timer boundary that publishes/paces but does not break verify."""
        base_timer_wait(cpu)
        async_timer_irq.reset_after_synchronous_ticks(2)
        timers["n"] += 1
        if args.video != "ega" or blits["n"] == 0:
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
        # Do NOT call async_timer_irq.poll() here.  This function runs as the
        # live side of a passthrough retrace boundary inside an outer verified
        # parent hook (e.g. 5C74).  Delivering a timer ISR tick increments
        # CS:066B on the live CPU; the outer oracle runs raw ASM from the
        # pre-hook clone and never calls poll(), so the two sides diverge.
        if base_retrace_wait is not None:
            base_retrace_wait(cpu)
        retraces["n"] += 1
        if args.video != "ega" or blits["n"] == 0:
            publish_video_if_changed(cpu, wait_for_viewer=False)
        retrace_pacer()
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

    if args.no_replacements:
        # ORACLE / cold-start-recording mode: drop every recovered GAME-LOGIC hook so the game runs the
        # pure original ASM (sprite drawing + all gameplay = ASM), keeping only the viewer's pacing/present
        # wrappers installed just above + the LZEXE boot hook (so boot skips the slow real self-unpack).
        # The kept present wrapper still blits + publishes the pure-ASM-drawn frame and the 0679 timer
        # wrapper still paces one game tick, so the session is watchable/recordable yet the recorded input
        # is ground truth -- no errors from our recovered hooks.  These are pacing/present infra (the frame
        # verifier's reference keeps the same env hooks), not game logic.
        LZEXE_BOOT_HOOK = (0x1B65, 0x0069)
        keep = {present_hook_addr, TIMER_WAIT_HOOK, RETRACE_WAIT_HOOK, LZEXE_BOOT_HOOK}
        for key in [k for k in rt.cpu.replacement_hooks if k not in keep]:
            rt.cpu.replacement_hooks.pop(key, None)
            rt.cpu.hook_names.pop(key, None)
        print(f"--no-replacements: pure-ASM game logic "
              f"(kept {len(rt.cpu.replacement_hooks)} pacing/present/boot hooks)", flush=True)

    demo_recorder = InputDemoRecorder(
        root=Path(args.save_demo_root),
        name=args.record_demo or f"play_{args.video}",
        metadata={
            "program": "overkill",
            "video": args.video,
            "sound": args.sound,
            "command_tail": command_tail.decode("latin1") if isinstance(command_tail, bytes) else str(command_tail),
            "no_replacements": bool(args.no_replacements),
        },
    )
    if args.record_demo:
        # Auto-start at launch (boundary 0).  A fresh boot (no --snapshot) records a COLD-START demo: no
        # start snapshot, so playback boots a fresh runtime from the metadata and replays from power-on.
        cold_start = args.snapshot is None
        started_dir = demo_recorder.start(rt, boundary=boundary["n"], write_start_snapshot=not cold_start)
        print(f"recording {'cold-start ' if cold_start else ''}input demo -> {started_dir}", flush=True)

    def deliver_live_scancode(sc: int) -> None:
        deliver_scancode(rt, sc)
        demo_recorder.record_scan(boundary=boundary["n"], scancode=sc)

    def save_runtime_crash_snapshot(exc: BaseException, *, context: str) -> Path | None:
        if args.no_crash_snapshot:
            return None
        cs, ip = rt.cpu.addr()
        exc_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-20000:]
        try:
            return write_runtime_repro_snapshot(
                rt,
                root=Path(args.save_repro_root),
                name=f"crash_{args.video}_{type(exc).__name__}",
                status=f"{context} crash at {cs:04X}:{ip:04X}: {type(exc).__name__}: {exc}",
                metadata={
                    "program": "overkill",
                    "video": args.video,
                    "sound": args.sound,
                    "command_tail": command_tail.decode("latin1") if isinstance(command_tail, bytes) else str(command_tail),
                    "created_by": "scripts/play.py crash handler",
                    "context": context,
                    "exception_type": type(exc).__name__,
                    "exception": str(exc),
                    "traceback_tail": exc_text,
                    "boundary": boundary["n"],
                    "visible": visible["n"],
                    "blits": blits["n"],
                    "timers": timers["n"],
                    "retraces": retraces["n"],
                    "direct_video": direct_video["n"],
                    "source_snapshot": str(args.snapshot) if args.snapshot else None,
                    "source_demo": str(args.demo) if args.demo else None,
                    "replay_hint": "python scripts/play.py --snapshot <this-directory>",
                },
            )
        except Exception as save_exc:
            print(f"crash repro snapshot save failed: {type(save_exc).__name__}: {save_exc}", flush=True)
            return None

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
        demo_toggle_requests.put(None)
        if demo_playback is not None:
            status["text"] = "demo suffix save queued"
        else:
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
        if demo_playback is not None:
            out = demo_playback.write_suffix(
                rt,
                root=Path(args.save_repro_root),
                name=f"suffix_play_{args.video}",
                boundary=boundary["n"],
                status="interactive F8 demo suffix snapshot",
                metadata={
                    "program": "overkill",
                    "video": args.video,
                    "sound": args.sound,
                    "command_tail": command_tail.decode("latin1") if isinstance(command_tail, bytes) else str(command_tail),
                    "created_by": "scripts/play.py F8 while replaying --demo",
                },
            )
            status["text"] = f"demo suffix saved: {out}"
            print(f"[demo] suffix saved: {out}", flush=True)
        elif demo_recorder.active:
            out = demo_recorder.stop(boundary=boundary["n"])
            status["text"] = f"input demo saved: {out}"
            print(f"[demo] STOPPED, saved: {out}", flush=True)
        else:
            out = demo_recorder.start(rt, boundary=boundary["n"])
            status["text"] = f"input demo recording: {out}"
            print(f"[demo] RECORDING started (press F8 again to stop): {out}", flush=True)

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
                    # The emulator thread does the write.  Report the RESULT on the console: the
                    # UI thread's "[hotkey] snapshot requested" only proves the key arrived, and
                    # the success message used to live in the SDL caption, invisible while playing.
                    try:
                        write_snapshot(
                            rt,
                            out,
                            status="interactive F7 snapshot",
                            steps=rt.cpu.instruction_count,
                            trace_tail=(),
                        )
                    except Exception as snap_exc:  # noqa: BLE001 -- report, keep playing
                        status["text"] = f"snapshot FAILED: {type(snap_exc).__name__}: {snap_exc}"
                        print(f"[snapshot] FAILED: {type(snap_exc).__name__}: {snap_exc}", flush=True)
                    else:
                        status["text"] = f"snapshot saved: {out}"
                        print(f"[snapshot] saved: {out}", flush=True)
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
                    boundary["n"], applied = pump_demo_frame(demo_playback, boundary["n"], (rt,), rt.cpu)
                    if applied:
                        status["text"] = f"input demo replay boundary={boundary['n']} events={applied}"
                else:
                    keyboard.pump(allow_release=last_boundary["kind"] != "present")
                target = boundary["n"] + 1
                used = 0
                while boundary["n"] < target and used < DEFAULT_FRAME_BUDGET and not stop.is_set():
                    try:
                        rt.cpu.run(max(1, int(DEFAULT_CPU_CHUNK_STEPS)))
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
                    if is_title_fire_release_wait():
                        async_timer_irq.poll(rt.cpu)
                        publish_video_if_changed(rt.cpu, poll_audio_while_waiting=True)
                        boundary["n"] += 1
                        last_boundary["kind"] = "wait"
                        cs, ip = rt.cpu.addr()
                        status["text"] = f"waiting for title fire release @ {cs:04X}:{ip:04X}"
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
                    used += max(1, int(DEFAULT_CPU_CHUNK_STEPS))
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
                    elif demo_playback is not None and not demo_playback.exhausted:
                        # Safety net for --demo replay: the VM made no visual or
                        # timer boundary for a whole frame budget, yet the demo
                        # still has input to deliver.  That means we are parked in
                        # a boundary-less wait loop the wait detectors above do not
                        # recognize, and demo events are gated on the boundary
                        # counter -- so without advancing it the replay would hang
                        # forever waiting for input it can never deliver.  Advance
                        # the boundary so the next recorded event can land.  This
                        # only triggers after a genuine stall, so it cannot perturb
                        # demos that already replay cleanly.
                        boundary["n"] += 1
                        last_boundary["kind"] = "wait"
                        status["text"] = (
                            f"demo stall recovery: advancing boundary at {cs:04X}:{ip:04X} "
                            f"(consider adding a wait detector here)"
                        )
                        print(status["text"], flush=True)
                    else:
                        status["text"] = f"stall (no visual/timer boundary in {used} steps) @ {cs:04X}:{ip:04X}"
            except HookVerifyDivergence as exc:
                cs, ip = rt.cpu.addr()
                repro_rt = exc.repro_runtime if exc.repro_runtime is not None else rt
                repro_cs, repro_ip = repro_rt.cpu.addr()
                status["text"] = f"HOOK VERIFY DIVERGENCE @ {cs:04X}:{ip:04X} (see console)"
                print(exc, flush=True)
                repro_metadata = {
                    "program": "overkill",
                    "video": args.video,
                    "sound": args.sound,
                    "command_tail": command_tail.decode("latin1") if isinstance(command_tail, bytes) else str(command_tail),
                    "created_by": "scripts/play.py --verify-preview divergence",
                    "divergence_at": f"{cs:04X}:{ip:04X}",
                    "repro_entry_at": f"{repro_cs:04X}:{repro_ip:04X}",
                    "repro_state": "pre_hook" if exc.repro_runtime is not None else "live_after_divergence_fallback",
                    "boundary": boundary["n"],
                    **exc.repro_metadata,
                }
                if demo_playback is not None:
                    try:
                        out = demo_playback.write_suffix(
                            repro_rt,
                            root=Path(args.save_repro_root),
                            name=f"divergence_{args.video}",
                            boundary=boundary["n"],
                            status=(
                                f"hook verifier divergence pre-hook snapshot at {repro_cs:04X}:{repro_ip:04X}"
                                if exc.repro_runtime is not None
                                else f"hook verifier divergence live fallback snapshot at {cs:04X}:{ip:04X}"
                            ),
                            metadata=repro_metadata,
                        )
                        print(f"HOOK VERIFY repro demo saved: {out}", flush=True)
                    except Exception as save_exc:
                        print(f"HOOK VERIFY repro demo save failed: {type(save_exc).__name__}: {save_exc}", flush=True)
                else:
                    try:
                        out = write_runtime_repro_snapshot(
                            repro_rt,
                            root=Path(args.save_repro_root),
                            name=f"hook_verify_divergence_{args.video}",
                            status=(
                                f"hook verifier divergence pre-hook snapshot at {repro_cs:04X}:{repro_ip:04X}"
                                if exc.repro_runtime is not None
                                else f"hook verifier divergence live fallback snapshot at {cs:04X}:{ip:04X}"
                            ),
                            metadata={
                                **repro_metadata,
                                "replay_hint": "python scripts/play.py --snapshot <this-directory> --verify-hooks",
                            },
                        )
                        print(f"HOOK VERIFY repro snapshot saved: {out}", flush=True)
                    except Exception as save_exc:
                        print(f"HOOK VERIFY repro snapshot save failed: {type(save_exc).__name__}: {save_exc}", flush=True)
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
                out = save_runtime_crash_snapshot(exc, context="interactive gameplay")
                if out is not None:
                    print(f"CRASH repro snapshot saved: {out}", flush=True)
                    status["text"] = f"CRASH repro snapshot saved: {out}"
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
