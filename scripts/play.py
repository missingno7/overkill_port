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

Controls: Q/A/O/P move, Z or Space fire (the game's own scheme), Esc quits.  Any
other key is forwarded too (full keyboard), in case a screen wants it.

Run:
    python scripts/play.py [--video cga|ega|tandy] [--game-hz 30] [--fps 30] [--palette 1h] [--scale 2]
"""
from __future__ import annotations

import argparse
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
from overkill_port.runtime import create_runtime
from overkill_port.snapshot import load_snapshot
from render_cga import CGA_PALETTES, render_ppm, render_ega_ppm, render_tandy_ppm

CGA_PRESENT_HOOK = (0x1010, 0x447B)  # mode-0 CGA frame-present blit
EGA_PRESENT_HOOK = (0x1010, 0x2750)  # mode-1 EGA frame-present blit
TANDY_PRESENT_HOOK = (0x1010, 0x3354)  # mode-2 Tandy frame-present blit
TIMER_WAIT_HOOK = (0x1010, 0x0679)  # game frame/timer wait; one call == one logical frame
RETRACE_WAIT_HOOK = (0x1010, 0x50C9)  # VGA retrace wait used heavily by intro/menu/transitions
B800_BASE = 0xB8000
B800_SIZE = 0x4000
A000_BASE = 0xA0000
EGA_SHADOW_SIZE = 0x8000
TANDY_SIZE = 0x8000

# These hooks were added during the last performance pass and are not yet safe
# enough for the interactive player.  In particular, the starfield/menu dirty
# update path can leave trails when one of these lifted routines is even slightly
# off.  Keep them available for oracle tests and profiling, but default play.py
# back to the interpreted ASM until the live regression is understood.
UNSAFE_INTERACTIVE_HOOKS = {
    (0x1010, 0x41A6),
    (0x1010, 0x4D15),
    # 58DF calls the 50C9 retrace-wait helper directly inside one Python hook.
    # Disable it for interactive play so every retrace wait remains visible to
    # play.py's pacing/sync wrapper instead of being fast-forwarded internally.
    (0x1010, 0x58DF),
    (0x1010, 0xCCAA),
    (0x1010, 0xCCC4),
    (0x1010, 0xCCF0),
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
        self._pending: tuple[int, bytes] | None = None
        self._closed = False

    def publish_and_wait(self, memory: bytearray) -> None:
        snapshot = bytes(memory)
        with self._cond:
            if self._closed:
                return
            self._next_id += 1
            frame_id = self._next_id
            self._pending = (frame_id, snapshot)
            self._cond.notify_all()
            while not self._closed and self._displayed_id < frame_id:
                self._cond.wait(timeout=0.25)

    def take_pending(self) -> tuple[int, bytes] | None:
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
    p.add_argument("--unsafe-render-hooks", action="store_true",
                   help="enable newest lifted render/dirty hooks; off by default because they currently ghost the starfield")
    p.add_argument("--no-present-sync", action="store_true",
                   help="debug only: do not wait for Tk to consume each timer-frame snapshot")
    p.add_argument("--retrace-hz", type=float, default=None,
                   help="pace VGA retrace waits used by intro/menu; defaults to --game-hz")
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

    if not args.unsafe_render_hooks:
        for key in UNSAFE_INTERACTIVE_HOOKS:
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
    last_video_crc: dict[str, int | None] = {"value": None}
    if args.video == "ega":
        present_hook_addr = EGA_PRESENT_HOOK
        video_base = A000_BASE
        video_size = EGA_SHADOW_SIZE
        render_frame = lambda snapshot: render_ega_ppm(snapshot, 0xA000, args.scale)
    elif args.video == "tandy":
        present_hook_addr = TANDY_PRESENT_HOOK
        video_base = B800_BASE
        video_size = TANDY_SIZE
        render_frame = lambda snapshot: render_tandy_ppm(snapshot, 0xB800, args.scale)
    else:
        present_hook_addr = CGA_PRESENT_HOOK
        video_base = B800_BASE
        video_size = B800_SIZE
        render_frame = lambda snapshot: render_ppm(snapshot, 0xB800, args.palette, args.scale)

    base_present = rt.cpu.replacement_hooks.get(present_hook_addr)
    base_timer_wait = rt.cpu.replacement_hooks.get(TIMER_WAIT_HOOK)
    base_retrace_wait = rt.cpu.replacement_hooks.get(RETRACE_WAIT_HOOK)
    if base_timer_wait is None:
        print(f"missing required timer wait hook {TIMER_WAIT_HOOK[0]:04X}:{TIMER_WAIT_HOOK[1]:04X}")
        return 1

    def video_crc(cpu) -> int:
        data = cpu.mem.data
        return zlib.crc32(data[video_base:video_base + video_size]) & 0xFFFFFFFF

    def publish_video_if_changed(cpu, *, force: bool = False) -> bool:
        crc = video_crc(cpu)
        if not force and last_video_crc["value"] == crc:
            return False
        last_video_crc["value"] = crc
        visible["n"] += 1
        if not args.no_present_sync:
            frame_sync.publish_and_wait(cpu.mem.data)
        return True

    def stop_cpu_burst() -> None:
        boundary["n"] += 1
        raise FramePresented()

    def present_hook(cpu) -> None:
        if base_present is not None:
            base_present(cpu)
        blits["n"] += 1
        publish_video_if_changed(cpu, force=True)
        # A visible blit is a safe place to hand control back to the UI.  The
        # following 0679 timer wait still performs the actual gameplay sleep, so
        # this does not invent an additional gameplay delay.
        stop_cpu_burst()

    def timer_frame_hook(cpu) -> None:
        base_timer_wait(cpu)
        timers["n"] += 1
        # Some paths update B800h directly and only use the timer wait as their
        # boundary.  Publish only when the visible memory differs from the last
        # snapshot; gameplay's 447B blit will normally have published already.
        publish_video_if_changed(cpu)
        timer_pacer()
        stop_cpu_burst()

    def retrace_frame_hook(cpu) -> None:
        if base_retrace_wait is not None:
            base_retrace_wait(cpu)
        retraces["n"] += 1
        # Intro/menu/fade code often draws first and then waits for retrace.  This
        # is the missing timing source that made those screens disappear while the
        # gameplay demo looked correct.  Pace every retrace wait, but publish only
        # when B800h changed so static delay loops do not thrash Tk with duplicates.
        publish_video_if_changed(cpu)
        retrace_pacer()
        stop_cpu_burst()

    rt.cpu.replacement_hooks[present_hook_addr] = present_hook
    rt.cpu.replacement_hooks[TIMER_WAIT_HOOK] = timer_frame_hook
    if base_retrace_wait is not None:
        rt.cpu.replacement_hooks[RETRACE_WAIT_HOOK] = retrace_frame_hook

    keyboard = KeyDispatcher(lambda sc: deliver_scancode(rt, sc))
    stop = threading.Event()
    status = {"text": ""}

    def emulator_loop() -> None:
        while not stop.is_set():
            try:
                keyboard.pump()  # frame-accurate key make/break delivery
                target = boundary["n"] + 1
                used = 0
                while boundary["n"] < target and used < args.frame_budget and not stop.is_set():
                    try:
                        rt.cpu.run(8000)
                    except FramePresented:
                        break
                    used += 8000
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
            frame_id, snapshot = pending
            width, height, ppm = render_frame(snapshot)
            frame_path.write_bytes(ppm)
            ui["img"] = tk.PhotoImage(file=str(frame_path))
            label.configure(image=ui["img"])
            frame_sync.mark_displayed(frame_id)
        elif args.no_present_sync:
            # Debug escape hatch: old unsynchronised sampling mode.  Normal play
            # intentionally does *not* do this, because sampling live B800 while
            # the emulator is in the middle of drawing a frame causes exactly the
            # choppy/partial-frame look we are avoiding.
            width, height, ppm = render_frame(bytes(rt.program.memory.data))
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
