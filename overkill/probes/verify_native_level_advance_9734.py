"""Driven-oracle gate for ``1010:9734`` -- LEVEL COMPLETE: advance the planet, start the next level.

The A344 exit's continuation.  It is what stands between "L1 is byte-exact" and "you can finish L1
and see L2", so it is on the critical path to a fully playable game.

    9734  [2356] == 0 -> the 9844 story intro (planet 0 only; unrecovered, fails loud)
    9744  [2356]++ ; if [2356] >= 6 -> [2356] = 0        (planet 5 wraps to the mothership)
    9755  [98C0] -> [BEFF] = 4                           (the level-complete jingle)
    9761  call 5145 ; 5BCA ; 6176                        (video; 6176 zeroes 2368..2372)
    976A  call 0B3E                                      (the NEW planet's map + C3AA class table)
    976D  call 0E9C                                      (the NEW planet's tile + sprite banks)
    9770  call 60AC                                      (the scroll init + warm-up)
    9773  ...the shared setup tail (already gated via the 9908 respawn)

ONLY ONE recorded demo completes a level: ``demo_play_tandy_L5_ending`` (planet 5 -> the wrap to 0).
So this gate traps ``9734``'s entry, snapshots DGROUP, runs the VM to ``9773``, and diffs that segment
against the native ``_level_advance_9734`` head over the same pre-state.  The shared tail beyond 9773
is not re-verified here -- the respawn gate already owns it.

Usage:
    pypy -m overkill.probes.verify_native_level_advance_9734 [demo]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from overkill.probes._harness import load_demo, run_ref_step_probe  # noqa: E402
from overkill.probes.verify_native_lockstep import EXCLUDED_CELLS, level_assets_for  # noqa: E402

CS = 0x1010
DS = 0x25CC
ADVANCE_ENTRY = 0x9734
TAIL_ENTRY = 0x9773
DEFAULT_DEMO = "demo_play_tandy_L5_ending_20260618_225419"
VERIFIER_FRAMES = 3000
STACK_SLACK = 0x100


class _Done(Exception):
    pass


def _native_head(mem, level_assets) -> None:
    """The 9734..9773 head only -- everything up to (not including) the shared setup tail."""
    from overkill.native_frame import (
        LEVEL_COMPLETE_SOUND, PLANET_COUNT, _hud_reset_6176, _level_data_init_0b3e,
        _level_load_0e9c, _level_start_scroll_60ac,
    )
    from overkill.recovered.domain.gaps import RecoveryGap

    planet = mem.rw(DS, 0x2356)
    if planet == 0:
        raise RecoveryGap("the 9844 planet-0 story intro", "shown before the mothership level")
    planet = planet + 1
    if planet >= PLANET_COUNT:
        planet = 0
    mem.ww(DS, 0x2356, planet)
    if mem.rb(DS, 0x98C0):
        mem.wb(DS, 0xBEFF, LEVEL_COMPLETE_SOUND)
    _hud_reset_6176(mem)
    _level_data_init_0b3e(mem, level_assets)
    _level_load_0e9c(mem, level_assets)
    _level_start_scroll_60ac(mem)


def main(argv) -> int:
    from overkill.recovered.adapters.flat_memory import MutFlatMemory

    demo = load_demo(argv[0] if argv else None, DEFAULT_DEMO)
    base = DS * 16
    res: dict = {}

    def on_step(cpu) -> None:
        s = cpu.s
        cs, ip = s.cs & 0xFFFF, s.ip & 0xFFFF
        if cs != CS:
            return
        if ip == ADVANCE_ENTRY and "pre" not in res:
            res["pre"] = bytes(cpu.mem.data)
            res["sp"] = s.sp & 0xFFFF
            res["planet"] = cpu.mem.rw(DS, 0x2356)
        elif ip == TAIL_ENTRY and "pre" in res and "post" not in res:
            res["post"] = bytes(cpu.mem.data[base:base + 0x10000])
            raise _Done

    try:
        run_ref_step_probe(demo, VERIFIER_FRAMES, on_step,
                           trap=frozenset({(CS, ADVANCE_ENTRY), (CS, TAIL_ENTRY)}))
    except _Done:
        pass

    if "post" not in res:
        print("RESULT: FAIL -- 9734 never reached 9773 in this demo")
        return 1

    native = MutFlatMemory(bytearray(res["pre"]))
    _native_head(native, level_assets_for)
    nat = bytes(native.data[base:base + 0x10000])
    post = res["post"]
    sp = res["sp"]
    lo = (sp - STACK_SLACK) & 0xFFFF
    diff = [o for o in range(0x10000)
            if nat[o] != post[o] and o not in EXCLUDED_CELLS and not (lo <= o < sp)]

    pre_dg = res["pre"][base:base + 0x10000]
    changed = [o for o in range(0x10000)
               if pre_dg[o] != post[o] and o not in EXCLUDED_CELLS and not (lo <= o < sp)]
    print(f"planet {res['planet']} -> {post[0x2356] | (post[0x2357] << 8)}; "
          f"the VM's 9734 head changed {len(changed)} DGROUP cells")
    print(f"native vs VM: {len(diff)} diverging cells")
    for o in diff[:16]:
        print(f"  DS:{o:04X}  vm={post[o]:02X}  nat={nat[o]:02X}")
    if len(diff) > 16:
        print(f"  ... and {len(diff) - 16} more")
    ok = not diff and len(changed) > 0
    print("RESULT:", "PASS -- the native level advance reproduces 9734's DGROUP effect exactly"
          if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
