"""play_cpuless.py -- the standalone CPUless OVERKILL runner.

Runs the UNIFIED game with the CPUless wall ARMED before anything else loads: the manual gameplay port
(``native_frame``, the coarse override at the frame boundary -- ADR-2) and the generated corpus compose
over the one DGROUP image, and NO CPU carrier (the interpreter, the VM runtime, the VMless installer,
the CPU-ABI adapters) may be imported. A breach raises ``CpuStandaloneWitness`` instead of silently
falling back to the VM, so this runner's ENTIRE import + run closure is proven carrier-free every launch
(scripts/check_cpuless_wall.py is the CI gate for the same claim on paths a given run doesn't take).

BOTH halves of the unification run here:

* GAMEPLAY comes from the MANUAL override (``native_frame``, the coarse ADR-2 seam) over a
  snapshot/bundle image -- the default mode, a thin wall-armed entry over play_native;
* the FRONT-END (``--menu``) comes from the GENERATED corpus: it executes the menu root over the
  data-only boot image and presents what the recovered code drew into B800 through the native Tandy
  renderer, with the host keyboard written into the image's own INT9 key table so the menu really
  responds to input.

``--menu --play`` JOINS them: the generated front-end runs until it reports a selection, then hands that
selection to the gameplay half.  LEVEL-LOAD is deliberately the MANUAL side -- play_native cold-starts a
level from the decoded container with no INT 21h -- which is ADR-2 working as intended: the generated
corpus fills what we lack manual code for, and here we have it.  (The generated level-select ``D390``
would additionally need the DOS file-I/O shim and the ``065C`` sp-as-data capability; neither is on the
critical path while the manual level-start exists.)

Still short of a true COLD boot: the front-end starts from a data-only boot image (post-C-startup),
which is what bypasses the DOS surface a from-EXE boot would need.  See
docs/overkill/campaigns/cpuless_app.md.

Usage:
    python scripts/play_cpuless.py                 # play (live window), gameplay from the default bundle
    python scripts/play_cpuless.py --menu          # the CPUless FRONT-END (generated corpus), interactive
    python scripts/play_cpuless.py --menu --play   # THE CHAIN: front-end -> selection -> gameplay
    python scripts/play_cpuless.py --snapshot DIR  # start from a captured image (it IS the state)
    python scripts/play_cpuless.py --frames N --no-sound   # headless self-test: N frames then exit
    python scripts/play_cpuless.py --menu --auto-select --play --seconds 2   # headless chain self-test
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
#: the game DGROUP, and the image's own INT9 key-state table the front-end polls
#: (1 = pressed) -- the same table the gameplay runner writes the host keyboard into.
_DS = 0x25CC
_KEY_TABLE = 0x98C4
#: the front-end's chosen level / difficulty, read at the JOIN into gameplay.
_LEVEL_CELL = 0xBEDA
_DIFFICULTY_CELL = 0xBEDC
#: scancode the front-end acts on (select / fire).
_SELECT_SCANCODE = 0x39


def run_menu(scale: int = 3, seconds: float = 0.0, then_play: bool = False,
             auto_select: bool = False) -> int:
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

    def step():
        """One pass of the front-end over the image, returning its live outputs.

        run_deep: the front-end's tail-dispatch loops are BOUNDED but are emitted as nested _dyn calls,
        so they need stack headroom (a runtime accommodation -- see dos_re.lift.standalone)."""
        return run_deep(run_recovered, MENU_ROOT, img, plat,
                        ds=_DS, es=_DS, ss=0x2000, sp=0x1000)

    def frame():
        return decode_tandy_b800_indices(np.frombuffer(bytes(img.data), dtype=np.uint8), 0xB8000)

    out = step()
    print(f"[cpuless] front-end {MENU_ROOT} drew {int((frame() != 0).sum())} lit pixels "
          f"-- NO CPU, NO interpreter", flush=True)
    if plat.video_ports:
        print(f"[cpuless] video registers: {({hex(k): hex(v) for k, v in plat.video_ports.items()})}")

    import scripts.play_native as play_native      # under the wall; proven carrier-free
    display = play_native.PygameDisplay(scale=scale, title="OVERKILL - CPUless front-end")
    pygame = display.pygame
    scan_map = play_native._build_scan_map(pygame)
    clock = pygame.time.Clock()
    elapsed = 0.0
    while True:
        # The host keyboard goes into the image's OWN INT9 key-state table, exactly as the gameplay
        # runner does it -- the recovered front-end polls that table, so this is real input, not a
        # side channel. Space (the select/fire key) is what the menu acts on.
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                display.close()
                return 0
            if ev.type in (pygame.KEYDOWN, pygame.KEYUP):
                sc = scan_map.get(ev.key)
                if sc is not None:
                    img.wb(_DS, (_KEY_TABLE + (sc & 0x7F)) & 0xFFFF,
                           1 if ev.type == pygame.KEYDOWN else 0)
        if auto_select:                           # headless: press the select key ourselves
            img.wb(_DS, (_KEY_TABLE + _SELECT_SCANCODE) & 0xFFFF, 1)
        out = step()                              # re-run the front-end over the evolving image
        if out.get("ax", 0xFFFF) == 0:            # the menu made a selection (observed: ax 9 -> 0)
            level = img.rw(_DS, _LEVEL_CELL)
            difficulty = img.rw(_DS, _DIFFICULTY_CELL)
            print(f"[cpuless] front-end SELECTED (ax=0, bx={out.get('bx', 0):#06x}) -- "
                  f"level {level + 1}, difficulty {difficulty}", flush=True)
            display.close()
            if not then_play:
                return 0
            # THE JOIN: hand the front-end's selection to the gameplay half.  Level-load is the
            # MANUAL side (play_native cold-starts a level from the decoded container -- no INT 21h),
            # exactly as ADR-2 intends: the generated corpus fills what we lack manual code for, and
            # here we have it.  Gameplay itself is the manual override; both halves stay carrier-free.
            print("[cpuless] -> handing off to the gameplay half (manual override)", flush=True)
            import scripts.play_native as play_native_mod
            return play_native_mod.main(["--level", str(level), "--no-title"]
                                        + (["--frames", str(int(seconds * 30))] if seconds else []))
        display.draw(frame())
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
        then_play = "--play" in args
        if then_play:
            args.remove("--play")
        auto_select = "--auto-select" in args
        if auto_select:
            args.remove("--auto-select")
        if "--scale" in args:
            i = args.index("--scale"); scale = int(args[i + 1]); del args[i:i + 2]
        if "--seconds" in args:
            i = args.index("--seconds"); seconds = float(args[i + 1]); del args[i:i + 2]
        return run_menu(scale=scale, seconds=seconds, then_play=then_play,
                        auto_select=auto_select)
    import scripts.play_native as play_native  # imported under the wall (proven carrier-free)
    return play_native.main(args)


if __name__ == "__main__":
    raise SystemExit(main())
