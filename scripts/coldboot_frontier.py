"""COLD-BOOT FORWARD: run the CPUless corpus from the BOOT ROOT and report the FIRST thing it cannot do.

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
import pathlib
import sys
import traceback

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))

#: The C-startup bootstrap the EXE's entry far-jumps to -- the first game code a cold boot runs.
BOOT_ROOT = "254A:04D7"
#: Post-C-startup image. Still not a TRUE cold boot (see the campaign doc); it is the earliest image
#: the port can currently start from, and the frontier it reports is real either way.
DEFAULT_IMAGE = ROOT / "artifacts" / "frontend_intro_snapshot" / "memory_1mb.bin"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=BOOT_ROOT, help="entry to boot from (default: the C startup)")
    ap.add_argument("--image", default=str(DEFAULT_IMAGE))
    ap.add_argument("--ds", type=lambda s: int(s, 0), default=None,
                    help="initial DS/ES (default: the root's own segment)")
    args = ap.parse_args(argv)

    from overkill.cpuless_host import install_import_guard, run_deep, run_recovered
    from overkill.cpuless_runtime import OverkillPlatform
    from overkill.recovered.adapters.flat_memory import MutFlatMemory

    image = pathlib.Path(args.image)
    if not image.is_file():
        print(f"no boot image at {image} -- build one from your own copy of the game "
              f"(docs/overkill/campaigns/cpuless_app.md)")
        return 2

    seg = int(args.root.split(":")[0], 16)
    ds = args.ds if args.ds is not None else seg
    img = MutFlatMemory(image.read_bytes())
    plat = OverkillPlatform()

    print(f"cold boot: {args.root} over {image.name} (ds={ds:04X}) -- wall ARMED")
    install_import_guard()
    try:
        out = run_deep(run_recovered, args.root, img, plat, ds=ds, es=ds, ss=0x2000, sp=0x1000)
    except Exception as exc:  # noqa: BLE001 -- the exception IS the report
        print(f"\nFRONTIER: {type(exc).__name__}")
        print(f"  {exc}")
        frames = [f for f in traceback.extract_tb(sys.exc_info()[2])
                  if "cpuless_recovered" in (f.filename or "")]
        if frames:
            print("  in recovered code:")
            for f in frames[-4:]:
                print(f"    {pathlib.Path(f.filename).name}:{f.lineno} in {f.name}")
        print("\n  ^ this is the NEXT task: supply that seam, then rerun from the beginning.")
        return 1

    print(f"\nBOOT ROOT RAN TO COMPLETION: {out}")
    print("  the frontier has moved past this root -- extend the run (or the root) to find the next.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
