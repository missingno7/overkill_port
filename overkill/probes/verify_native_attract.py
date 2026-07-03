"""Demo witness: the pure attract scene-machine rules vs the ORIGINAL 1010:D007/D04D loop.

Replays a cold-start demo on the ref (hooks-stripped) side and, at the two in-loop anchors, samples
the scene cells:

* ``1010:D016`` (the per-frame D04D call site) -> the PRE state (BE06 scene, BE08 countdown, BE0A
  auto-fire tick);
* ``1010:D0CA`` (just past the auto-fire block) -> the MID state (BE0A after the block, the injected
  98BE input).

For every (pre -> mid -> next-frame pre) triple it asserts ``systems.attract.attract_frame_step``
reproduces the auto-fire gate/cycle, the injected input, and the countdown/advance -- the whole
D04D state machine.  Coverage is reported explicitly (scene range, auto-fire-active frames) so a PASS
cannot silently claim more than the demo exercised.  Scene-0 frames and scene advances are skipped
exactly where the pure rules fail loud by design (D160 / next-scene entry actions are declared gaps).

Usage:
    python -m overkill.probes.verify_native_attract [cold_start_demo_name]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from overkill.probes._harness import load_demo, run_ref_step_probe_cold_start  # noqa: E402
from overkill.recovered.domain.attract import AttractSceneState  # noqa: E402
from overkill.recovered.domain.gaps import RecoveryGap  # noqa: E402
from overkill.recovered.systems.attract import attract_autofire_runs, attract_frame_step  # noqa: E402

CS = 0x1010
D016, D0CA = 0xD016, 0xD0CA
GAME_DS = 0x25CC
DEFAULT_DEMO = "demo_cold_start_attract_interrupt_synthetic"


def main(argv) -> int:
    demo = load_demo(argv[0] if argv else None, DEFAULT_DEMO)
    st = {"pre": None, "mid": None, "frames": 0, "checked": 0, "autofire_checked": 0,
          "scenes": set(), "fails": []}

    def on_step(cpu):
        s = cpu.s
        if (s.cs & 0xFFFF) != CS:
            return
        ip = s.ip & 0xFFFF
        if ip == D016:
            m = cpu.mem
            pre = (m.rw(GAME_DS, 0xBE06), m.rw(GAME_DS, 0xBE08), m.rw(GAME_DS, 0xBE0A))
            if st["pre"] is not None and st["mid"] is not None:
                _check(st["pre"], st["mid"], pre)
            st["pre"], st["mid"] = pre, None
            st["frames"] += 1
            st["scenes"].add(pre[0])
        elif ip == D0CA:
            m = cpu.mem
            st["mid"] = (m.rw(GAME_DS, 0xBE0A), m.rb(GAME_DS, 0x98BE))

    def _check(pre, mid, next_pre):
        be06, be08, be0a = pre
        if be06 == 0:
            return  # D160 special branch -- a declared gap, not witnessable by these rules
        try:
            step = attract_frame_step(AttractSceneState(scene=be06, countdown=be08, autofire_tick=be0a))
        except RecoveryGap:
            return
        st["checked"] += 1
        ok = True
        if step.run_fanout:
            st["autofire_checked"] += 1
            ok &= mid[0] == step.state.autofire_tick and mid[1] == (step.injected_input or 0)
        else:
            ok &= mid[0] == be0a
        if not step.scene_advanced:
            ok &= next_pre[0] == step.state.scene and next_pre[1] == step.state.countdown
        if not ok:
            st["fails"].append((st["frames"], pre, mid, next_pre))

    run_ref_step_probe_cold_start(demo, None, on_step)

    scenes = sorted(st["scenes"])
    autofire_scenes = sorted(x for x in scenes if x and attract_autofire_runs(x, 0x64))
    print(f"attract witness: frames={st['frames']} checked={st['checked']} fails={len(st['fails'])}")
    print(f"  coverage: scenes={[hex(x) for x in scenes]} "
          f"auto-fire-eligible scenes seen={[hex(x) for x in autofire_scenes]} "
          f"auto-fire transitions checked={st['autofire_checked']}")
    for f in st["fails"][:5]:
        print("  FAIL", f)
    if st["checked"] == 0:
        print("RESULT: NO-WITNESS (the demo never entered the D007 scene loop)")
        return 1
    if st["fails"]:
        print("RESULT: CHECK")
        return 1
    caveat = "" if st["autofire_checked"] else " (auto-fire window NOT exercised by this demo)"
    print(f"RESULT: PASS -- the pure attract scene-machine matches the live D04D{caveat}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
