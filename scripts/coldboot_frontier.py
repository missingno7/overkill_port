"""COLD-BOOT FORWARD: run the CPUless corpus from the TOP LEVEL and report the FIRST thing it cannot do.

THE METHOD THIS ENFORCES
------------------------
The cold-start path is grown as ONE continuous oracle-proven run from startup, not as a collection of
locally passing islands. So the work order is not ours to choose: boot the recovered program, let it
run until it hits something the port has not supplied, and THAT is the frontier. Repair that seam,
rerun from the beginning, and the next first-failure becomes the next task.

This exists because the alternative kept happening. Picking functions by call-graph analysis produced
a real result (the promotion cascade) but also two wrong turns: a seam named at `0B3E`, which performs
no DOS I/O at all, and a ten-function island set where four were needed and six were ordinary game
code. A cold boot cannot make either mistake -- it reports the earliest genuine gap, in execution
order, with no judgement call about what "looks" load-bearing.

WHY THE FAILURE IS THE ANSWER, NOT AN ERROR
-------------------------------------------
`FailLoudPlatform` raises and NAMES the missing service, and the recovered corpus never falls back to
a VM. So a `CpuStandaloneWitness` here is the instrument working: it is a precise, ordered statement
of what the port owes next. An exception is the output.

Usage:
    python scripts/coldboot_frontier.py [--root CS:IP] [--image PATH]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import traceback

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))

#: THE GAME'S TOP LEVEL: the front-end -> level-select -> gameplay main loop.  This is the root the
#: probe drives, and DEFAULT_IMAGE is a snapshot parked exactly on it (its own state.json records
#: ``cs=0x1010 ip=0x96C8, steps=0``), so entering here is reading the recorded state back, not a
#: guess about where to start.  `1010:96C8` is the `loop` at the bottom of the `call 50C9 ; loop`
#: idiom at `1010:96C5`; the IR gives it `exits: []` -- a no-exit top-level loop -- and NOTHING calls
#: it (`callers -> []`).
#:
#: >>> WHY NOT `254A:04D7`, WHICH THIS FILE USED TO NAME AS "the C-startup bootstrap the EXE's entry
#: far-jumps to".  THAT WAS FALSE, and it made the probe look like it was making progress when it was
#: not.  `254A:04D7` is the ASSET-CONTAINER OVERLAY-OPEN routine: `overkill/asset_codecs/container.py`
#: is the VM-free form of exactly that address, its IR record is `exits: ['retf'], ints: ['21']`, its
#: first block does INT 21h AX=3D02 (DOS open) and it returns ax=2 -- a FILE HANDLE.  It is far-CALLED
#: by game code from `1010:0248` and `1010:C679` and by nothing else.  So the probe's cheerful "BOOT
#: ROOT RAN TO COMPLETION" only ever meant "an overlay open returned a handle": complete on its first
#: run, complete on every run, byte-identical output forever, and with NO PATH ONWARD.  A root that
#: cannot fail is not an instrument.  Do not re-adopt it.
#:
#: There is also no static route from anywhere in the IR into the `1010:96xx` top level (checked over
#: all 626 functions).  The original arrives there by an intra-segment path plus a stack-based far
#: transfer -- a `retf` to a pushed address -- which a call graph cannot represent.  Driving the
#: promoted top level directly, over an image recorded at it, is therefore the honest entry, not a
#: shortcut around a missing edge.
TOP_LEVEL_ROOT = "1010:96C8"
#: The image the root is entered over: a cold front-end snapshot captured AT `1010:96C8`.  Still not a
#: TRUE from-EXE cold boot (that starts at the MZ entry `1C32:000E`, the LZEXE unpacker stub, recorded
#: in artifacts/boot_entry_snapshot with steps=0); it is the earliest image the CPUless corpus can
#: currently start from, and the frontier it reports is real either way.
DEFAULT_IMAGE = ROOT / "artifacts" / "frontend_intro_snapshot" / "memory_1mb.bin"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=TOP_LEVEL_ROOT,
                    help="entry to boot from (default: the game's top level)")
    ap.add_argument("--image", default=str(DEFAULT_IMAGE))
    ap.add_argument("--frames", type=int, default=200,
                    help="stop after this many frame boundaries (0 = run until it stops on its own)")
    args = ap.parse_args(argv)

    from dos_re.lift.platform import CPUlessPlatformRuntime

    from overkill.cpuless_driver import CPUlessFrameDriver
    from overkill.cpuless_host import install_import_guard, run_deep, run_recovered
    from overkill.recovered.adapters.flat_memory import MutFlatMemory

    image = pathlib.Path(args.image)
    state = image.parent / "state.json"
    if not (image.is_file() and state.is_file()):
        print(f"no boot image + state.json at {image.parent} -- build one from your own copy of the "
              f"game (docs/overkill/campaigns/cpuless_app.md)")
        return 2

    img = MutFlatMemory(image.read_bytes())
    # THE RECORDED REGISTERS, not invented ones.  The snapshot was captured AT the root, so its own
    # state.json IS the entry state; the previous version passed ds=es=<root segment>, ss=0x2000,
    # sp=0x1000, none of which the program was ever in.
    cpu = json.loads(state.read_text(encoding="utf-8"))["cpu"]
    regs = {r: cpu[r] for r in ("ax", "bx", "cx", "dx", "si", "di", "bp", "ds", "es", "ss", "sp")}
    # THE SHARED DEVICE MODEL, not the port's hand-rolled one. CPUlessPlatformRuntime owns a
    # dos_re DOSMachine (pure hardware; no instruction execution), so INT 21h/10h and the ports are
    # serviced by the framework's real DOS model over the game's own files. Writing INT 21h handlers
    # in the port would be DOS recreated unnecessarily -- and the framework's version already carries
    # details learned the hard way, e.g. allocating the LOWEST free file handle rather than a
    # monotonic counter, because a game indexing a fixed-size per-handle table overruns it otherwise.
    plat = CPUlessPlatformRuntime(img, ROOT / "assets")

    print(f"cold boot: {args.root} over {image.name} -- wall ARMED")
    print("  regs: " + " ".join(f"{r}={v:04X}" for r, v in sorted(regs.items())))
    install_import_guard()

    # THE FRAME DRIVER answers the boundary heads the GENERATED corpus calls (1010:0679, the timer
    # tick wait).  Without it every head is inert -- plat.boundary_cb is None, the wait is never
    # satisfied, and the generated body spins to its 20M-iteration guard.  That spin was this probe's
    # real frontier for as long as it pointed at a root that could not reach the top level.
    from overkill.cpuless_recovered.func_1010_06e5 import func_1010_06e5   # the game's own IRQ0 ISR

    class _Done(Exception):
        pass

    def present(frame):
        if args.frames and frame + 1 >= args.frames:
            raise _Done()

    driver = CPUlessFrameDriver(img, plat, func_1010_06e5, present=present).install(plat)

    try:
        out = run_deep(run_recovered, args.root, img, plat, **regs)
    except _Done:
        print(f"\nRAN {driver.frame} FRAMES with no missing seam "
              f"(last frame cut at {driver.head[0]:04X}:{driver.head[1]:04X}).")
        print("  raise --frames to push the frontier further out.")
        return 0
    except Exception as exc:  # noqa: BLE001 -- the exception IS the report
        print(f"\nFRONTIER after {driver.frame} frame(s): {type(exc).__name__}")
        print(f"  {exc}")
        frames = [f for f in traceback.extract_tb(sys.exc_info()[2])
                  if "cpuless_recovered" in (f.filename or "")]
        if frames:
            print("  call chain in recovered code:")
            for f in frames:
                print(f"    {pathlib.Path(f.filename).name}:{f.lineno} in {f.name}")
        print("\n  ^ this is the NEXT task: supply that seam, then rerun from frame 0.")
        return 1

    print(f"\nROOT RETURNED after {driver.frame} frame(s): {out}")
    print("  a no-exit top level returning is itself worth explaining before trusting it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
