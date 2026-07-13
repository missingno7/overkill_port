"""SUB-FRAME FRONT-END FLOW tracer: the real intro/attract/menu screen sequence, grounded in the
attract SCENE MACHINE + video mode -- NOT guessed from decoded pixels.

Motivation (2026-07-13, owner: "see the real intro/menu flow, not guessing from pixels").  Every prior
front-end attempt sampled a decoded framebuffer at a GUESSED step count and tried to recognise the
screen -- which repeatedly produced wrong conclusions (a "composed menu" that wasn't, a "calibration
screen" that was the attract demo misdecoded).  The correct instrument reads the game's OWN control
flow instead:

* The front end has NO 1010:0679 gameplay frame wait -- so `advance_frames_fast` (which keys on 0679)
  can never advance it, and every attempt to do so stalled.  The front end is the CC04 loop:
  `CE97` composes the menu, then `CC4F` runs the `D007`/`D04D` attract scene machine, which advances the
  scene id `DS:BE06` 0 -> 0x13 with a per-scene countdown `DS:BE08`, until the START flag `DS:98C3` is
  set (fire, `0162` input poll sets it to 0x39) -> `971A` starts the game -> `D390` level-select.
* So the flow IS the (video_mode, BE06 scene, 98C3 start) tuple over time.  This traps the draw/flow
  routines and emits the RUN-LENGTH-COMPRESSED timeline of that tuple -- the real screen sequence, each
  transition a real control-flow event.

Reads the video mode from the ref runtime's `dos.video_mode` (the BIOS 0040:0049 byte is stale in this
VM -- the game sets modes through its own int10 path).  Runs over a cold-start demo through the frame
verifier, which delivers the real IRQ0 at the boot/pacing waits (no faked timing).

Usage:
    python -m overkill.probes.trace_frontend_flow [demo_name] [max_frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))

import overkill.frame_verify as fv  # noqa: E402
from overkill.probes._harness import load_demo, run_ref_step_probe_cold_start  # noqa: E402

CS = 0x1010
DEFAULT_DEMO = "demo_cold_start_intro_20260711_203259"

#: front-end draw/flow routines -- each entry is a real per-frame control-flow event that identifies
#: what the front end is doing this frame (the screen), grounded in the game's own code.
FLOW_ROUTINES = {
    0x0D42: "bootAssets",   # shared-startup-asset loads (load_shared_startup_assets)
    0xCE97: "menuCompose",  # the CE97 menu-cell compose
    0xCC4F: "attract",      # the CC4F attract-scene player
    0xD04D: "attrDraw",     # the D04D attract scene-cell draw
    0x3354: "present",      # the 3354 present blit (a frame shown)
    0x5C46: "squeeze",      # the 5C46 screen-squeeze transition
    0xD305: "plaque",       # the D305 level-start mission plaque
    0x971A: "startGame",    # 971A -- START pressed, leaving the front-end loop
    0xD390: "levelSelect",  # the D390 level-select screen
    0x9844: "theEnd",       # 9844 THE END win splash
}
TRAP = frozenset((CS, ip) for ip in FLOW_ROUTINES)

SCENE_CELL = 0xBE06         # DS:BE06 attract scene id (0..0x13)
COUNTDOWN_CELL = 0xBE08     # DS:BE08 per-scene countdown
START_FLAG = 0x98C3         # DS:98C3 front-end START flag (0x39 once fire is pressed)


def trace(demo_name: str, max_frames: "int | None"):
    """Return the run-length-compressed front-end flow: a list of
    ``{start, end, frames, mode, scene, startflag, cd_lo, cd_hi, routines}`` runs."""
    demo = load_demo(demo_name, demo_name)
    grabbed: dict = {}
    orig_load = fv._load_runtime

    def grab(exe, assets, snap, tail):
        rt = orig_load(exe, assets, snap, tail)
        grabbed.setdefault("ref", rt)   # the first runtime loaded is the ref (pure-VM) side
        return rt

    runs: list[dict] = []
    st = {"prev": None, "run0": 0, "n": 0}

    def close(cd, routines):
        if st["prev"] is None:
            return
        mode, scene, start = st["prev"]
        runs.append(dict(start=st["run0"], end=st["n"] - 1, frames=st["n"] - st["run0"],
                         mode=mode, scene=scene, startflag=start,
                         cd_lo=st["cd_lo"], cd_hi=st["cd_hi"], routines=sorted(st["routines"])))

    def on_ref(cpu):
        name = FLOW_ROUTINES.get(cpu.s.ip & 0xFFFF)
        if name is None:
            return
        ref = grabbed.get("ref")
        mode = ref.dos.video_mode if ref is not None else -1
        ds = cpu.s.ds & 0xFFFF
        scene = cpu.mem.rw(ds, SCENE_CELL)
        start = cpu.mem.rb(ds, START_FLAG)
        cd = cpu.mem.rw(ds, COUNTDOWN_CELL)
        st["n"] += 1
        key = (mode, scene, start)
        if key != st["prev"]:
            close(cd, name)
            st["prev"] = key
            st["run0"] = st["n"] - 1
            st["cd_lo"] = st["cd_hi"] = cd
            st["routines"] = {name}
        else:
            st["cd_lo"] = min(st["cd_lo"], cd)
            st["cd_hi"] = max(st["cd_hi"], cd)
            st["routines"].add(name)

    fv._load_runtime = grab
    try:
        run_ref_step_probe_cold_start(demo, max_frames, on_ref, trap=TRAP)
    finally:
        fv._load_runtime = orig_load
    close(0, "")
    return runs


def main(argv) -> int:
    demo = argv[0] if argv else DEFAULT_DEMO
    max_frames = int(argv[1]) if len(argv) > 1 else None
    print(f"front-end flow: {demo}")
    runs = trace(demo, max_frames)
    for r in runs:
        print(f"  #{r['start']:5d}..{r['end']:<5d} x{r['frames']:<4d} mode={r['mode']:<2d} "
              f"scene={r['scene']:#06x} start={r['startflag']:#04x} cd={r['cd_lo']}..{r['cd_hi']} "
              f"{{{','.join(r['routines'])}}}")
    print(f"== {len(runs)} runs, {sum(r['frames'] for r in runs)} draw-events ==")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
