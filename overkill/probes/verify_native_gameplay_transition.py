"""Demo witness: the native gameplay-exit detector vs the live 1010:97B2 transition flags.

Replays a gameplay demo on the ref (hooks-stripped) side and, once per gameplay frame at ``1010:97CE``
(right after 9B2E returns to the 97B2 loop, where the exit flags hold this frame's verdict), compares:

* the VM's verdict -- the flags 97B2 tests in priority order (``A344`` -> ``A342`` -> ``A346``); and
* ``systems.frame_loop.detect_gameplay_transition`` fed the same DS cells (``A47C``, ``A95A``, ``A97A``,
  ``2326``, and the anchor slot's ``+08`` death counter ``DS:2384``, read post-9B2E = post-increment).

A PASS with transitions>0 grounds the composed detector against REAL death / level-end events (run it
on the player_death and L5_ending demos); a PASS with transitions==0 still proves the "no spurious
exit" verdict on every normal frame.  Coverage (frames + which exits were seen) is reported explicitly.

NOTE (harness limit): the death/level-end FRAME itself is instruction-heavy (explosion + scene setup)
and can exceed the frame-verifier's per-frame budget, so a full replay of a death demo may time out at
the transition.  Pass a ``max_frames`` that stops just before that frame to witness the run-up (and any
transition that fires earlier); the POSITIVE exit path is independently grounded by the component rules'
live cross-check in 9B2E and by ``tests/test_frame_loop.py``.

Usage:
    python -m overkill.probes.verify_native_gameplay_transition [demo_name] [max_frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from overkill.probes._harness import load_demo, run_ref_step_probe  # noqa: E402
from overkill.recovered.domain.frame_loop import GameplayExit  # noqa: E402
from overkill.recovered.systems.frame_loop import detect_gameplay_transition  # noqa: E402

CS = 0x1010
DISPATCH_97CE = 0x97CE
GAME_DS = 0x25CC
DEFAULT_DEMO = "demo_play_tandy_player_death_20260618_233821"
A344, A342, A346 = 0xA344, 0xA342, 0xA346
ANCHOR_DEATH_COUNTER = 0x2384   # the DS:237C anchor slot's +08 field (the 9AFF death countdown)


def _vm_exit(mem):
    """The exit 97B2 takes, read from the live flags in its own test priority (or None)."""
    if mem.rw(GAME_DS, A344) == 1:
        return GameplayExit.SCRIPTED
    if mem.rw(GAME_DS, A342) == 1:
        return GameplayExit.GAME_OVER
    if mem.rw(GAME_DS, A346) == 1:
        return GameplayExit.DEATH
    return None


def main(argv) -> int:
    demo = load_demo(argv[0] if argv else None, DEFAULT_DEMO)
    max_frames = int(argv[1]) if len(argv) > 1 else 4000
    st = {"frames": 0, "checked": 0, "fails": [], "seen": {}}

    def on_step(cpu):
        s = cpu.s
        if (s.cs & 0xFFFF) != CS or (s.ip & 0xFFFF) != DISPATCH_97CE:
            return
        m = cpu.mem
        st["frames"] += 1
        vm = _vm_exit(m)
        mine = detect_gameplay_transition(
            a47c=m.rw(GAME_DS, 0xA47C), a95a=m.rw(GAME_DS, 0xA95A), a97a=m.rw(GAME_DS, 0xA97A),
            v2326=m.rw(GAME_DS, 0x2326), anchor_counter_after_inc=m.rw(GAME_DS, ANCHOR_DEATH_COUNTER),
        )
        mine_exit = mine.exit if mine is not None else None
        st["checked"] += 1
        if vm is not None:
            st["seen"][vm.name] = st["seen"].get(vm.name, 0) + 1
        if mine_exit is not vm:
            st["fails"].append((st["frames"], vm.name if vm else None,
                                mine_exit.name if mine_exit else None))

    run_ref_step_probe(demo, max_frames, on_step)

    print(f"gameplay-transition witness ({demo.snapshot_path().parent.name}): "
          f"frames={st['frames']} checked={st['checked']} fails={len(st['fails'])}")
    print(f"  exits seen: {st['seen'] or '{} (no transition in this demo window)'}")
    for f in st["fails"][:8]:
        print("  FAIL frame", f)
    if st["checked"] == 0:
        print("RESULT: NO-WITNESS (the 97B2 gameplay loop never ran)")
        return 1
    if st["fails"]:
        print("RESULT: CHECK")
        return 1
    tag = "" if st["seen"] else " (no exit event exercised -- only the no-transition path proven)"
    print(f"RESULT: PASS -- detect_gameplay_transition matches the live 97B2 verdict{tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
