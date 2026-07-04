"""Demo witness: the native 9AFF death-tail STAGE (the counter increment) vs the live 9B2E, on death.

The gameplay-transition witness proved the stateless verdict; this proves the STATEFUL half -- that
``systems.frame_loop.step_death_tail_9aff`` reproduces the anchor slot's ``+08`` death-counter
transition the VM writes each frame.  Per frame it samples the counter + reached-inputs at 9B2E ENTRY
(``1010:9B2E``, before the tail increments) and the counter + exit flags at 9B2E EXIT (``1010:97CE``),
then asserts the pure step reproduces the exit counter, the transition, and the anchor deactivation.

Run it on the player_death demo (cap max_frames before the heavy death FRAME -- see loop_blockers):
the counter run-up + the fire happen in the window.

Usage:
    python -m overkill.probes.verify_native_death_tail [demo_name] [max_frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from overkill.probes._harness import load_demo, run_ref_step_probe  # noqa: E402
from overkill.recovered.domain.frame_loop import GameplayExit  # noqa: E402
from overkill.recovered.systems.frame_loop import step_death_tail_9aff  # noqa: E402

CS = 0x1010
B2E_ENTRY = 0x9B2E
DISPATCH_97CE = 0x97CE
GAME_DS = 0x25CC
ANCHOR_ACTIVE = 0x237C          # the DS:237C anchor slot's +00 active word
ANCHOR_DEATH_COUNTER = 0x2384   # its +08 death countdown
DEFAULT_DEMO = "demo_play_tandy_player_death_20260618_233821"


def _vm_exit(mem):
    if mem.rw(GAME_DS, 0xA344) == 1:
        return GameplayExit.SCRIPTED
    if mem.rw(GAME_DS, 0xA342) == 1:
        return GameplayExit.GAME_OVER
    if mem.rw(GAME_DS, 0xA346) == 1:
        return GameplayExit.DEATH
    return None


def main(argv) -> int:
    demo = load_demo(argv[0] if argv else None, DEFAULT_DEMO)
    max_frames = int(argv[1]) if len(argv) > 1 else 1790
    st = {"entry": None, "checked": 0, "reached": 0, "fired": 0, "fails": []}

    def on_step(cpu):
        s = cpu.s
        if (s.cs & 0xFFFF) != CS:
            return
        ip = s.ip & 0xFFFF
        m = cpu.mem
        if ip == B2E_ENTRY:
            st["entry"] = dict(a95a=m.rw(GAME_DS, 0xA95A), a97a=m.rw(GAME_DS, 0xA97A),
                               v2326=m.rw(GAME_DS, 0x2326), counter=m.rw(GAME_DS, ANCHOR_DEATH_COUNTER))
        elif ip == DISPATCH_97CE and st["entry"] is not None:
            e, st["entry"] = st["entry"], None
            _check(e, m)

    def _check(e, m):
        step = step_death_tail_9aff(e["a95a"], e["a97a"], e["v2326"], e["counter"])
        st["checked"] += 1
        post_counter = m.rw(GAME_DS, ANCHOR_DEATH_COUNTER)
        vm_exit = _vm_exit(m)
        anchor_active = m.rw(GAME_DS, ANCHOR_ACTIVE)
        from overkill.recovered.systems.frame_loop import death_tail_reached_9aff
        if death_tail_reached_9aff(e["a95a"], e["a97a"]) and e["v2326"] == 3:
            st["reached"] += 1
        mine_exit = step.transition.exit if step.transition else None
        # the counter: A940/other code doesn't touch 2384 on these frames, so post == step.anchor_counter
        if step.anchor_counter != post_counter:
            st["fails"].append(("counter", e, step.anchor_counter, post_counter))
        # the exit verdict (only meaningful when the tail fires -> matches the 97B2 flags)
        if step.transition is not None:
            st["fired"] += 1
            if mine_exit is not vm_exit:
                st["fails"].append(("exit", mine_exit, vm_exit))
            if step.deactivate_anchor and anchor_active != 0:
                st["fails"].append(("anchor-not-deactivated", anchor_active))

    run_ref_step_probe(demo, max_frames, on_step)

    print(f"death-tail witness ({demo.snapshot_path().parent.name}): checked={st['checked']} "
          f"reached={st['reached']} fired={st['fired']} fails={len(st['fails'])}")
    for f in st["fails"][:8]:
        print("  FAIL", f)
    if st["checked"] == 0:
        print("RESULT: NO-WITNESS (9B2E never ran)")
        return 1
    ok = not st["fails"]
    tag = "" if st["fired"] else " (counter run-up only -- no fire in window)"
    print("RESULT:", f"PASS -- step_death_tail_9aff reproduces the live 9AFF counter/exit{tag}"
          if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
