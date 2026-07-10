"""Driven-oracle gate for ``1010:8546`` -- the APPLY-UPGRADE handler (the TAB key).

The apply-upgrade BIT (0x20) has two sources: the fixed key TAB (0x0F) and the CONFIGURABLE control
map's entry 2, which in this corpus is **Z (0x2C)**.  They are aliases for the same action.  The
demos press Z 40 times across the corpus -- but never in the L1 cold-start demo the lockstep gate
replays, and that demo never holds a powerup anyway (``[95FA]`` is FFFF on all 8292 frames).  So the
gate cannot reach this handler, and ``native_frame`` used to fail loud there.  The owner hit it in
play_native the moment they collected a powerup and tried to apply it.

Rather than lower the bar, this probe SYNTHESISES the missing coverage: it replays a demo whose
snapshot already holds a powerup marker (``[95FA] != FFFF``), writes the TAB scancode (0x0F -> input
bit 0x20) into the pure VM's own INT9 key table at a 9B2E boundary -- exactly what the keyboard IRQ
would have done -- lets the game's own ``0162`` decode it, then traps ``8546`` entry and its ``859D``
ret, runs the native ``_apply_upgrade_8546`` over the entry image, and diffs DGROUP.

Injecting input into the reference VM does not weaken the oracle: it CREATES an oracle for a code
path the corpus never covers.  Everything the handler writes is still compared, byte for byte.

Usage:
    pypy -m overkill.probes.verify_native_apply_upgrade_8546 [demo]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from overkill.probes._harness import load_demo, run_ref_step_probe  # noqa: E402

CS = 0x1010
DS = 0x25CC
FRAME_TOP = 0x9B2E
HANDLER_ENTRY = 0x8546
HANDLER_RET = 0x859D
TAB_SCANCODE = 0x0F
#: this demo's snapshot holds marker 0 with the level scrolled in ([2350] = 0x111 > 0xB6)
DEFAULT_DEMO = "demo_play_tandy_L6_different_weapons_20260618_225615"
INJECT_AT_FRAME = 6
VERIFIER_FRAMES = 80
STACK_SLACK = 0x100


class _Done(Exception):
    pass


def main(argv) -> int:
    from overkill.native_frame import _apply_upgrade_8546
    from overkill.recovered.adapters.flat_memory import MutFlatMemory

    demo = load_demo(argv[0] if argv else None, DEFAULT_DEMO)
    base = DS * 16
    st: dict = {"frame": 0}
    res: dict = {}

    def on_step(cpu) -> None:
        s = cpu.s
        cs, ip = s.cs & 0xFFFF, s.ip & 0xFFFF
        if cs != CS:
            return
        if ip == FRAME_TOP:
            st["frame"] += 1
            if st["frame"] >= INJECT_AT_FRAME:
                # the IRQ's own effect: mark TAB down in the game's key table
                cpu.mem.wb(DS, (0x98C4 + TAB_SCANCODE) & 0xFFFF, 1)
            if st["frame"] > INJECT_AT_FRAME + 2:
                raise _Done
            return
        if ip == HANDLER_ENTRY and "pre" not in res:
            res["pre"] = bytes(cpu.mem.data)
            res["sp"] = s.sp & 0xFFFF
            orig = cpu.__class__.step

            def step(_c=cpu):
                # cpu.step was the harness's trap observer; replacing it means catching the ret here
                if (_c.s.cs & 0xFFFF) == CS and (_c.s.ip & 0xFFFF) == HANDLER_RET \
                        and "post" not in res:
                    res["post"] = bytes(_c.mem.data[base:base + 0x10000])
                    raise _Done
                return orig(_c)

            cpu.step = step

    try:
        run_ref_step_probe(demo, VERIFIER_FRAMES, on_step,
                           trap=frozenset({(CS, FRAME_TOP), (CS, HANDLER_ENTRY)}))
    except _Done:
        pass

    if "post" not in res:
        print("RESULT: FAIL -- 8546 never ran; the TAB injection did not reach the handler "
              "(check [95FA] != FFFF and [2350] > 0xB6 in this demo's snapshot)")
        return 1

    native = MutFlatMemory(bytearray(res["pre"]))
    marker = native.rw(DS, 0x95FA)
    _apply_upgrade_8546(native)
    nat = bytes(native.data[base:base + 0x10000])
    post = res["post"]
    sp = res["sp"]
    lo = (sp - STACK_SLACK) & 0xFFFF
    diff = [o for o in range(0x10000) if nat[o] != post[o] and not (lo <= o < sp)]

    pre_dg = res["pre"][base:base + 0x10000]
    changed = [o for o in range(0x10000) if pre_dg[o] != post[o] and not (lo <= o < sp)]
    print(f"marker [95FA] = {marker:04X}; the VM's 8546 changed {len(changed)} DGROUP cells:")
    for o in changed:
        print(f"  DS:{o:04X} {pre_dg[o]:02X} -> {post[o]:02X}  (native {nat[o]:02X})")
    print(f"\nnative vs VM: {len(diff)} diverging cells")
    for o in diff[:12]:
        print(f"  DS:{o:04X} vm={post[o]:02X} nat={nat[o]:02X}")
    ok = not diff and len(changed) > 0
    print("RESULT:", "PASS -- the native apply-upgrade reproduces 8546's DGROUP effect exactly"
          if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
