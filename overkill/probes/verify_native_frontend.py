"""THE FRONT-END LOCKSTEP GATE: does the native cold-boot front end reproduce the VM's SCREEN SEQUENCE?

The gameplay 9B2E lockstep proves the game frames; this is its front-end counterpart, built on
``dos_re.frontend_timeline`` (promoted from pre2_port's menu verification).  Both sides are captured on
the SAME coarse screen-id vocabulary:

* the VM (GROUND TRUTH): replay a cold-start demo through the pure reference VM, classifying each
  present-frame from its CS:IP + attract scene (the ``scripts/probe_coldstart_frontend.classify_screen``
  witness);
* the NATIVE side (CANDIDATE): drive play_native's actual cold-boot decision flow headless -- the menu
  loop then the ``NativeAttract`` scene machine -- classifying each frame the same way.

``diff_sequence`` then compares the run-length screen order + durations.  The first divergence IS the
front-end frontier (today: the attract's INITIAL display phase, which native skips -- see run_status).
This probe makes that gap a REPORTED, verifiable fact instead of a doc note, and will hold the line as
the front end is recovered piece by piece.  ``diff_pixels`` (byte-exact RGB) is the follow-up gate once
the sequence matches.

Usage:
    python -m overkill.probes.verify_native_frontend [demo_name] [max_frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))

from dos_re.frontend_timeline import FrameRecord, collapse, diff_sequence, format_sequence  # noqa: E402

DEFAULT_DEMO = "demo_cold_start_intro_20260711_203259"
#: the menu idle timeout play_native uses before rolling the attract (see _MENU_ATTRACT_IDLE_FRAMES).
MENU_IDLE_FRAMES = 300
#: scene-0 setup length: the D160 scroll-in walks [237E] 0xC0 -> 0x60 one step per frame.
SCENE0_SETUP_FRAMES = 0xC0 - 0x60


def vm_timeline(demo_name: str, max_frames: int) -> "list[FrameRecord]":
    """The GROUND TRUTH: the VM's per-present-frame screen timeline for the cold-start demo."""
    from scripts.probe_coldstart_frontend import capture, classify_screen
    rows, _ = capture(demo_name, max_frames)
    return [FrameRecord(r["f"], classify_screen(r), "") for r in rows]


#: play_native's app loop runs at 30 fps while the VM's present boundary is the ~60 Hz retrace, so ONE
#: native app frame spans TWO VM boundaries.  The timelines must share a clock for durations to compare:
#: the native side emits this many records per app frame (the wall-clock-equivalent boundary count).
BOUNDARIES_PER_APP_FRAME = 2


def native_timeline(max_frames: int) -> "list[FrameRecord]":
    """The CANDIDATE: play_native's cold-boot decision flow, driven headless on the same screen ids.

    Mirrors the app's flow faithfully -- the title/menu loop (idle to the attract timeout), then the
    ``NativeAttract`` machine (scene-0 setup, the cell scenes, the auto-fire gameplay scenes, terminal
    back to the menu).  No rendering: the SEQUENCE gate compares screen order/durations only.  Each app
    frame emits ``BOUNDARIES_PER_APP_FRAME`` records so durations are in VM-boundary units."""
    from overkill.native_attract import NativeAttract

    records: "list[FrameRecord]" = []
    f = 0

    def emit(screen: str) -> None:
        nonlocal f
        for _ in range(BOUNDARIES_PER_APP_FRAME):
            records.append(FrameRecord(f, screen, ""))
            f += 1

    # play_native cold boot: the title/menu screen until the idle timeout rolls the attract.
    for _ in range(MENU_IDLE_FRAMES):
        if f >= max_frames:
            return records
        emit("menu")
    # the attract: NativeAttract drives scene 0 (setup) -> cells -> gameplay -> terminal.
    driver = NativeAttract.start()
    setup_left = SCENE0_SETUP_FRAMES
    while f < max_frames:
        driver, action = driver.step(fire_pressed=False, any_key=False,
                                     setup_done=(setup_left <= 0))
        if action.kind == "exit":
            emit("menu")                      # terminal scene -> back to the menu screen
            continue
        if action.kind == "scene0_setup":
            setup_left -= 1
            emit("attract:scene0-setup")
        elif action.kind == "gameplay":
            emit(f"attract:scene-{action.scene:#04x}")
        else:
            emit(f"attract:scene-{action.scene:#04x}")
    return records


def main(argv) -> int:
    demo = argv[0] if argv else DEFAULT_DEMO
    max_frames = int(argv[1]) if len(argv) > 1 else 6300
    print(f"front-end lockstep: {demo} ({max_frames} frames)")
    vm = vm_timeline(demo, max_frames)
    nat = native_timeline(len(vm))
    vm_runs, nat_runs = collapse(vm), collapse(nat)
    print(f"\nVM     ({len(vm)} frames): {format_sequence(vm_runs)}")
    print(f"\nNATIVE ({len(nat)} frames): {format_sequence(nat_runs)}")
    d = diff_sequence(vm_runs, nat_runs, duration_tolerance=4)
    if d.ok:
        print("\nRESULT: PASS -- the native front end reproduces the VM's screen sequence")
        return 0
    print(f"\nFIRST DIVERGENCE at run {d.index}: {d.reason}")
    print(f"  VM:     {d.a}")
    print(f"  NATIVE: {d.b}")
    print("RESULT: FAIL -- this divergence is the front-end recovery frontier")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
