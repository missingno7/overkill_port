"""play_cpuless.py -- the standalone CPUless OVERKILL runner.

Runs the UNIFIED game with the CPUless wall ARMED before anything else loads: the manual gameplay port
(``native_frame``, the coarse override at the frame boundary -- ADR-2) and the generated corpus compose
over the one DGROUP image, and NO CPU carrier (the interpreter, the VM runtime, the VMless installer,
the CPU-ABI adapters) may be imported. A breach raises ``CpuStandaloneWitness`` instead of silently
falling back to the VM, so this runner's ENTIRE import + run closure is proven carrier-free every launch
(scripts/check_cpuless_wall.py is the CI gate for the same claim on paths a given run doesn't take).

Today it plays GAMEPLAY from a snapshot/bundle image; the generated front-end (boot -> title/menu ->
level load) fills in as the video platform shim and the tail-dispatch capability land -- see
docs/overkill/campaigns/cpuless_app.md. It is a thin wall-armed entry over play_native (which is already
carrier-free): the point of a separate runner is that the wall is ARMED, making "CPUless" enforced here,
not merely true by habit.

Usage:
    python scripts/play_cpuless.py                 # play (live window), gameplay from the default bundle
    python scripts/play_cpuless.py --snapshot DIR  # start from a captured image (it IS the state)
    python scripts/play_cpuless.py --frames N --no-sound   # headless self-test: N frames then exit
    # ...all other play_native.py arguments pass straight through.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))

from overkill.cpuless_host import install_import_guard, run_deep, run_recovered  # noqa: E402

#: The front-end / title-menu loop.  Its whole closure is promoted, so the GENERATED corpus draws the
#: menu -- this is the front-end half of the unification (gameplay is the manual override).
MENU_ROOT = "1010:CC04"
#: The data-only boot image the front-end runs over (post-C-startup; the DOS surface a cold boot would
#: need is exactly what this image bypasses -- see the campaign doc).
BOOT_IMAGE = ROOT / "artifacts" / "frontend_intro_snapshot" / "memory_1mb.bin"


def run_menu(scale: int = 3, seconds: float = 0.0) -> int:
    """Run the CPUless FRONT-END: execute the menu root from the generated corpus over the boot image
    and present what it drew into video memory through the native Tandy renderer.

    Nothing here touches a CPU: the menu is produced by the recovered corpus under the armed wall, and
    the renderer only decodes the B800 bytes the recovered code wrote.  ``seconds`` > 0 exits after that
    long (headless self-test); otherwise the window stays until closed."""
    import numpy as np

    from overkill.cpuless_runtime import OverkillPlatform
    from overkill.native_video.page_raster import decode_tandy_b800_indices
    from overkill.recovered.adapters.flat_memory import MutFlatMemory

    if not BOOT_IMAGE.is_file():
        raise SystemExit(f"play_cpuless --menu: no boot image at {BOOT_IMAGE} -- build one from your "
                         f"own copy of the game (see docs/overkill/campaigns/cpuless_app.md).")

    img = MutFlatMemory(BOOT_IMAGE.read_bytes())
    plat = OverkillPlatform()
    # run_deep: the front-end's tail-dispatch loops are BOUNDED but are emitted as nested _dyn calls,
    # so they need stack headroom (a runtime accommodation -- see dos_re.lift.standalone).
    run_deep(run_recovered, MENU_ROOT, img, plat, ds=0x25CC, es=0x25CC, ss=0x2000, sp=0x1000)

    indices = decode_tandy_b800_indices(np.frombuffer(bytes(img.data), dtype=np.uint8), 0xB8000)
    lit = int((indices != 0).sum())
    print(f"[cpuless] front-end {MENU_ROOT} drew {lit} lit pixels -- NO CPU, NO interpreter",
          flush=True)
    if plat.video_ports:
        print(f"[cpuless] video registers: {({hex(k): hex(v) for k, v in plat.video_ports.items()})}")

    import scripts.play_native as play_native      # under the wall; proven carrier-free
    display = play_native.PygameDisplay(scale=scale, title="OVERKILL - CPUless front-end")
    pygame = display.pygame
    display.draw(indices)
    clock = pygame.time.Clock()
    elapsed = 0.0
    while True:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                display.close()
                return 0
        display.draw(indices)
        elapsed += clock.tick(30) / 1000.0
        if seconds and elapsed >= seconds:
            display.close()
            return 0


def main(argv=None) -> int:
    # Arm the CPUless wall FIRST, so everything below imports under it.
    install_import_guard()
    args = list(sys.argv[1:] if argv is None else argv)
    if "--menu" in args:
        args.remove("--menu")
        scale, seconds = 3, 0.0
        if "--scale" in args:
            i = args.index("--scale"); scale = int(args[i + 1]); del args[i:i + 2]
        if "--seconds" in args:
            i = args.index("--seconds"); seconds = float(args[i + 1]); del args[i:i + 2]
        return run_menu(scale=scale, seconds=seconds)
    import scripts.play_native as play_native  # imported under the wall (proven carrier-free)
    return play_native.main(args)


if __name__ == "__main__":
    raise SystemExit(main())
