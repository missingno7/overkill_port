"""Produced-vs-VM: the native 1010:A940 game-state update stage vs the live A940, on a gameplay demo.

Replays a gameplay demo on the ref (hooks-stripped) side and, for every A940 call, captures the DS
cells A940 touches at its ENTRY (``1010:A940``) and at its EXIT (``A9E0``/``A9DA``), then asserts
``systems.frame_loop.frame_state_update_a940`` (fed the entry cells) reproduces the exit cells exactly.
Only the GAMEPLAY path is in scope: frames with ``DS:2356 == 5`` (attract-mode middle) are skipped and
counted separately (the composer fails loud on them by design).  This also settles the A8C8-reset
question empirically -- it checks the exit A8C8 is unchanged from entry (A940 does not reset it).

Usage:
    python -m overkill.probes.verify_native_a940 [demo_name] [max_frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from overkill.probes._harness import load_demo, run_ref_step_probe  # noqa: E402
from overkill.recovered.systems.frame_loop import frame_state_update_a940  # noqa: E402

CS = 0x1010
A940_ENTRY = 0xA940
A940_EXITS = {0xA9E0, 0xA9DA}
GAME_DS = 0x25CC
DEFAULT_DEMO = "demo_play_tandy_L3_full_20260617_202520"

# the cells A940's gameplay path reads/writes (offset -> name).  98A8/98A9 are BYTES (A940 rb/wb them);
# the rest are words.
CELLS_WORD = {0xA8CE: "A8CE", 0xA8C8: "A8C8", 0xA8CC: "A8CC", 0xA8C6: "A8C6", 0xA8CA: "A8CA",
              0x2356: "2356", 0xA8C2: "A8C2"}
CELLS_BYTE = {0x98A8: "98A8", 0x98A9: "98A9"}


def _snap(mem):
    snap = {name: mem.rw(GAME_DS, off) & 0xFFFF for off, name in CELLS_WORD.items()}
    snap.update({name: mem.rb(GAME_DS, off) & 0xFF for off, name in CELLS_BYTE.items()})
    return snap


def main(argv) -> int:
    demo = load_demo(argv[0] if argv else None, DEFAULT_DEMO)
    max_frames = int(argv[1]) if len(argv) > 1 else 1500
    st = {"pending_entry": None, "checked": 0, "attract_skipped": 0, "fails": []}

    def on_step(cpu):
        s = cpu.s
        if (s.cs & 0xFFFF) != CS:
            return
        ip = s.ip & 0xFFFF
        if ip == A940_ENTRY:
            st["pending_entry"] = _snap(cpu.mem)
        elif ip in A940_EXITS and st["pending_entry"] is not None:
            entry, st["pending_entry"] = st["pending_entry"], None
            _check(entry, _snap(cpu.mem))

    def _check(entry, exit_):
        if entry["2356"] == 0x0005:
            st["attract_skipped"] += 1
            return
        st["checked"] += 1
        got = frame_state_update_a940(
            counter_a8ce=entry["A8CE"], a8c8=entry["A8C8"], a8cc=entry["A8CC"],
            mode_2356=entry["2356"], flag_98a8=entry["98A8"], boss_pending_a8c2=entry["A8C2"],
        )
        want = {
            "A8CE": exit_["A8CE"], "A8C6": exit_["A8C6"], "A8CA": exit_["A8CA"],
            "A8CC": exit_["A8CC"], "98A8": exit_["98A8"], "98A9": exit_["98A9"],
        }
        mine = {
            "A8CE": got.counter_a8ce, "A8C6": got.prev_a8c6, "A8CA": got.prev_a8ca,
            "A8CC": got.a8cc_reset, "98A8": got.flag_98a8, "98A9": got.flag_98a9,
        }
        # A940 must NOT change A8C8 (the composer relies on this; settle it empirically)
        if exit_["A8C8"] != entry["A8C8"]:
            st["fails"].append(("A8C8-mutated", entry["A8C8"], exit_["A8C8"]))
        if mine != want:
            st["fails"].append(("cells", {k: (mine[k], want[k]) for k in want if mine[k] != want[k]}))

    run_ref_step_probe(demo, max_frames, on_step)

    print(f"A940 witness ({demo.snapshot_path().parent.name}): checked={st['checked']} "
          f"attract_skipped={st['attract_skipped']} fails={len(st['fails'])}")
    for f in st["fails"][:8]:
        print("  FAIL", f)
    if st["checked"] == 0:
        print("RESULT: NO-WITNESS (A940 gameplay path never ran)")
        return 1
    ok = not st["fails"]
    print("RESULT:", "PASS -- native frame_state_update_a940 reproduces the live A940 (gameplay path)"
          if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
