"""Interactive OVERKILL viewer: run the emulator live and control it.

The interpreter runs on a background thread so the UI remains responsive during
long bursts spent decoding the next screen.  Gameplay is paced from the game's
modelled timer wait (``1010:0679``), while intro/menu/transition screens also
pace from the VGA retrace wait (``1010:50C9``).  Visible video-memory snapshots
(CGA ``B800h`` or EGA ``A000h`` shadow planes) are published to the Tk thread whenever a timed boundary changed the screen, and the
emulator waits until that exact snapshot is consumed before continuing.  That
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
runtime snapshot, Esc quits.  Any other key is forwarded too (full keyboard), in
case a screen wants it.

Run:
    python scripts/play.py [--video cga|ega|tandy] [--game-hz 30] [--fps 30] [--palette 1h] [--scale 2]
"""
from __future__ import annotations

import argparse
from datetime import datetime
from queue import Empty, SimpleQueue
import sys
import tempfile
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
from overkill_port.runtime import create_runtime
from overkill_port.snapshot import load_snapshot, write_snapshot
from overkill_port.memory import EGA_APERTURE, EGA_SHADOW_SIZE
from render_cga import CGA_PALETTES, render_ppm, render_ega_ppm, render_tandy_ppm

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

# Full Tk keysym -> XT make scan code map so any key can be forwarded.
KEYSYM_SCAN: dict[str, int] = {
    "Escape": 0x01, "minus": 0x0C, "equal": 0x0D, "BackSpace": 0x0E, "Tab": 0x0F,
    "bracketleft": 0x1A, "bracketright": 0x1B, "Return": 0x1C, "KP_Enter": 0x1C,
    "Control_L": 0x1D, "Control_R": 0x1D, "semicolon": 0x27, "apostrophe": 0x28,
    "grave": 0x29, "Shift_L": 0x2A, "backslash": 0x2B, "comma": 0x33, "period": 0x34,
    "slash": 0x35, "Shift_R": 0x36, "Alt_L": 0x38, "Alt_R": 0x38, "space": 0x39,
    "Caps_Lock": 0x3A,
    "F1": 0x3B, "F2": 0x3C, "F3": 0x3D, "F4": 0x3E, "F5": 0x3F, "F6": 0x40,
    "F7": 0x41, "F8": 0x42, "F9": 0x43, "F10": 0x44, "F11": 0x57, "F12": 0x58,
    # Arrows use the keypad scan codes most DOS games expect.
    "Up": 0x48, "Down": 0x50, "Left": 0x4B, "Right": 0x4D,
    "KP_7": 0x47, "KP_8": 0x48, "KP_9": 0x49, "KP_Subtract": 0x4A,
    "KP_4": 0x4B, "KP_5": 0x4C, "KP_6": 0x4D, "KP_Add": 0x4E,
    "KP_1": 0x4F, "KP_2": 0x50, "KP_3": 0x51, "KP_0": 0x52, "KP_Decimal": 0x53,
}
for _i, _ch in enumerate("1234567890"):
    KEYSYM_SCAN[_ch] = 0x02 + _i
for _i, _ch in enumerate("qwertyuiop"):
    KEYSYM_SCAN[_ch] = 0x10 + _i
for _i, _ch in enumerate("asdfghjkl"):
    KEYSYM_SCAN[_ch] = 0x1E + _i
for _i, _ch in enumerate("zxcvbnm"):
    KEYSYM_SCAN[_ch] = 0x2C + _i


def scancode_for(event) -> int | None:
    if event.keysym in KEYSYM_SCAN:
        return KEYSYM_SCAN[event.keysym]
    key = (event.keysym or "").lower()
    if key in KEYSYM_SCAN:
        return KEYSYM_SCAN[key]
    if event.char and event.char.lower() in KEYSYM_SCAN:
        return KEYSYM_SCAN[event.char.lower()]
    return None


class TimerPacer:
    """Throttle the game to ``hz`` frames/second."""

    def __init__(self, hz: float) -> None:
        self.period = 1.0 / hz if hz > 0 else 0.0
        self._next: float | None = None

    def __call__(self) -> None:
        if self.period <= 0:
            return
        now = time.perf_counter()
        if self._next is None:
            self._next = now + self.period
            return
        delay = self._next - now
        if delay > 0:
            time.sleep(delay)
            self._next += self.period
        else:
            self._next = now + self.period  # fell behind (e.g. after a load): resync


class FramePresented(Exception):
    """Internal control-flow signal used to stop CPU.run exactly at one frame."""


class FrameSync:
    """One-frame-at-a-time handoff from emulator thread to Tk thread.

    The previous player let the emulator keep executing while Tk sampled video
    memory on its own timer.  If Tk was late, several emulated presents could be
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
    p = argparse.ArgumentParser(description="Interactive CGA/EGA viewer for the OVERKILL runtime")
    p.add_argument("--video", choices=("cga", "ega", "tandy"), default="cga",
                   help="launch/render the original game in CGA, EGA, or Tandy mode")
    p.add_argument("--dos-args", default=None,
                   help="override the PSP command tail passed to the original EXE, e.g. ' /E'")
    p.add_argument("--game-hz", type=float, default=30.0,
                   help="real-time game speed (frames/sec); original is ~36. Lower if choppy.")
    p.add_argument("--fps", type=int, default=30, help="legacy option; timing is controlled by --game-hz")
    p.add_argument("--palette", default="1h", choices=sorted(CGA_PALETTES))
    p.add_argument("--scale", type=int, default=2)
    p.add_argument("--frame-budget", type=int, default=6_000_000,
                   help="max interpreted steps to wait for one frame before reporting a stall")
    p.add_argument("--snapshot", default=None,
                   help="load a saved snapshot dir to skip the ~11s asset-decode bootstrap")
    p.add_argument("--save-snapshot-root", default=str(ROOT / "artifacts"),
                   help="root directory for F12 runtime snapshots")
    p.add_argument("--no-present-sync", action="store_true",
                   help="debug only: do not wait for Tk to consume each timer-frame snapshot")
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
    p.add_argument("--ega-publish-timed-boundaries", action="store_true",
                   help="debug only: publish EGA snapshots at timer/retrace waits as well as the EGA presenter")
    p.add_argument("--ega-start-address-units", choices=("byte", "word", "ignore"), default="byte",
                   help="debug EGA CRTC start interpretation: byte offset, word address*2, or always zero")
    p.add_argument("--ega-log-starts", action="store_true",
                   help="print EGA display-start value and interpreted render offset for each published frame")
    p.add_argument("--ega-publish-all-presents", action="store_true",
                   help="debug only: publish every EGA present, including alternating off-screen page presents")
    args = p.parse_args(argv)

    try:
        import tkinter as tk
    except Exception as exc:  # pragma: no cover - environment dependent
        print(f"tkinter is required for the interactive viewer: {exc}")
        return 1

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
        # Keep the long-tested default CGA path unchanged.  With an empty PSP tail
        # the inner parser sees PSP:82 == 0 and selects mode 0.
        command_tail = b""

    if args.snapshot:
        rt = load_snapshot(exe, args.snapshot, game_root=assets)
    else:
        rt = create_runtime(exe, game_root=assets, command_tail=command_tail)
    rt.cpu.trace_enabled = False
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
    timer_pacer = TimerPacer(args.game_hz)
    retrace_pacer = TimerPacer(args.retrace_hz if args.retrace_hz is not None else args.game_hz)
    frame_sync = FrameSync()

    boundary = {"n": 0}
    visible = {"n": 0}
    blits = {"n": 0}
    timers = {"n": 0}
    retraces = {"n": 0}
    last_video_crc: dict[str, tuple[int, int] | None] = {"value": None}
    if args.video == "ega":
        present_hook_addr = EGA_PRESENT_HOOK
        video_base = A000_BASE
        video_size = EGA_SHADOW_SIZE
        render_frame = lambda snapshot, display_start: render_ega_ppm(snapshot, 0xA000, args.scale, display_start)
    elif args.video == "tandy":
        present_hook_addr = TANDY_PRESENT_HOOK
        video_base = B800_BASE
        video_size = TANDY_SIZE
        render_frame = lambda snapshot, display_start: render_tandy_ppm(snapshot, 0xB800, args.scale)
    else:
        present_hook_addr = CGA_PRESENT_HOOK
        video_base = B800_BASE
        video_size = B800_SIZE
        render_frame = lambda snapshot, display_start: render_ppm(snapshot, 0xB800, args.palette, args.scale)

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
            # Tk publish even when the displayed CRTC page did not change.
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

    def present_hook(cpu) -> None:
        if base_present is not None:
            if hook_verifier is not None:
                hook_verifier.verify(cpu, present_hook_addr, base_present, base_present_name)
            else:
                base_present(cpu)
        blits["n"] += 1
        # EGA gameplay alternates the CRTC start between 0000h and 2000h around
        # paired present calls.  The two presents are part of one page-flip/update
        # sequence; painting both through Tk exposes the intermediate work page
        # as the visible "every other frame" blink.  Keep executing both in the
        # VM, but only publish the stable page unless the debug flag asks to see
        # every present boundary.
        if args.video != "ega" or args.ega_publish_all_presents or (cpu.mem.ega_display_start & 0xFFFF) == 0:
            publish_video_if_changed(cpu, force=True)
        # A visible blit is a safe place to hand control back to the UI.  The
        # following 0679 timer wait still performs the actual gameplay sleep, so
        # this does not invent an additional gameplay delay.
        stop_cpu_burst()

    def timer_frame_hook(cpu) -> None:
        base_timer_wait(cpu)
        timers["n"] += 1
        # Some paths update video memory directly and only use the timer wait as
        # their boundary.  EGA startup/menu can do this before the first 2750
        # present, but after EGA presenting starts, timed-boundary publishing can
        # expose intermediate dirty-panel states that the presenter has not
        # committed as a complete frame yet.
        if args.video != "ega" or args.ega_publish_timed_boundaries or blits["n"] == 0:
            publish_video_if_changed(cpu)
        timer_pacer()
        stop_cpu_burst()

    def retrace_frame_hook(cpu) -> None:
        if base_retrace_wait is not None:
            base_retrace_wait(cpu)
        retraces["n"] += 1
        # Intro/menu/fade code often draws first and then waits for retrace.  For
        # EGA, publish these timed snapshots only until the first explicit EGA
        # presenter runs; after that, keep retrace as a pacing boundary only.
        if args.video != "ega" or args.ega_publish_timed_boundaries or blits["n"] == 0:
            publish_video_if_changed(cpu)
        retrace_pacer()
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
    status = {"text": ""}
    snapshot_requests: SimpleQueue[Path] = SimpleQueue()

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
                keyboard.pump()  # frame-accurate key make/break delivery
                target = boundary["n"] + 1
                used = 0
                while boundary["n"] < target and used < args.frame_budget and not stop.is_set():
                    try:
                        rt.cpu.run(8000)
                    except FramePresented:
                        break
                    used += 8000
                    # Long screen loads can run for many chunks without a
                    # visible/timer boundary.  Drain key-up events during those
                    # bursts so a short FIRE tap from the menu is not still held
                    # when the newly loaded level-select screen first polls input.
                    keyboard.pump_events()
                if boundary["n"] < target and not stop.is_set():
                    cs, ip = rt.cpu.addr()
                    status["text"] = f"stall (no visual/timer boundary in {used} steps) @ {cs:04X}:{ip:04X}"
            except Exception as exc:
                cs, ip = rt.cpu.addr()
                status["text"] = f"CRASH @ {cs:04X}:{ip:04X} - {type(exc).__name__}: {exc}"
                traceback.print_exc()
                return

    root = tk.Tk()
    root.title(f"OVERKILL (emulated {args.video.upper()})")
    label = tk.Label(root)
    label.pack()
    label.focus_set()
    ui = {"img": None}
    frame_path = Path(tempfile.gettempdir()) / "overkill_frame.ppm"

    def on_press(event) -> None:
        if event.keysym == "Escape":
            stop.set()
            root.destroy()
            return
        if event.keysym == "F12":
            queue_snapshot_save()
            return
        sc = scancode_for(event)
        if sc is not None:
            keyboard.post_down(sc)

    def on_release(event) -> None:
        sc = scancode_for(event)
        if sc is not None:
            keyboard.post_up(sc)

    # bind_all is more reliable than binding only the root/label: depending on
    # platform/window-manager focus, Tk can otherwise show frames but never route
    # menu key presses to our handlers.
    root.bind_all("<KeyPress>", on_press)
    root.bind_all("<KeyRelease>", on_release)
    root.focus_force()
    root.protocol("WM_DELETE_WINDOW", lambda: (stop.set(), root.destroy()))

    def ui_tick() -> None:
        pending = frame_sync.take_pending()
        if pending is not None:
            frame_id, snapshot, display_start = pending
            width, height, ppm = render_frame(snapshot, display_start)
            frame_path.write_bytes(ppm)
            ui["img"] = tk.PhotoImage(file=str(frame_path))
            label.configure(image=ui["img"])
            frame_sync.mark_displayed(frame_id)
        elif args.no_present_sync:
            # Debug escape hatch: old unsynchronised sampling mode.  Normal play
            # intentionally does *not* do this, because sampling live B800 while
            # the emulator is in the middle of drawing a frame causes exactly the
            # choppy/partial-frame look we are avoiding.
            live_start = ega_render_start(rt.program.memory.ega_display_start) if args.video == "ega" else 0
            width, height, ppm = render_frame(bytes(rt.program.memory.data), live_start)
            frame_path.write_bytes(ppm)
            ui["img"] = tk.PhotoImage(file=str(frame_path))
            label.configure(image=ui["img"])

        base = f"OVERKILL (emulated {args.video.upper()})  -  Q/A/O/P move, Z/Space fire"
        if boundary["n"] == 0 and not status["text"]:
            root.title("OVERKILL - decoding startup assets, please wait (~10-15s)...")
        elif status["text"]:
            root.title(f"{base}  |  {status['text']}  |  visible={visible['n']} boundaries={boundary['n']} blits={blits['n']} timers={timers['n']} retraces={retraces['n']}")
        else:
            root.title(f"{base}  |  visible={visible['n']} boundaries={boundary['n']} blits={blits['n']} timers={timers['n']} retraces={retraces['n']}")
        if not stop.is_set():
            # Do not use --fps as an additional frame pacer.  The emulator thread
            # is already paced by --game-hz at the DOS timer wait.  Tk should
            # consume pending snapshots quickly; otherwise --fps 30 plus
            # --game-hz 30 accidentally becomes a double throttle.
            root.after(1, ui_tick)

    emu = threading.Thread(target=emulator_loop, name="overkill-emu", daemon=True)
    emu.start()
    root.after(30, ui_tick)
    try:
        root.mainloop()
    finally:
        stop.set()
        frame_sync.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
