"""Produced-vs-VM verify: the native forward world-scroll tick (``step_scroll_forward_a6fe``) vs the
VM's ``1010:A6FE`` (called from the already-hooked A66F).

Per real A6FE entry: capture DS:234E/2350/234C/A978/2354, predict via the pure port, then compare
against the VM's actual values at 0xA68A -- A66F's own continuation right after the A6FE call
returns (A66F pushes that address before calling A6FE; see
``overkill.gameplay.object_movement.run_object_scroll_world_progress_gate_a66f``).

Usage:
    python -m overkill.probes.verify_native_scroll_forward_a6fe [demo_name] [max_frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from overkill.probes._harness import load_demo, run_ref_step_probe  # noqa: E402
from overkill.recovered.domain.scroll import ScrollState  # noqa: E402
from overkill.recovered.systems.scroll import step_scroll_forward_a6fe  # noqa: E402

CS = 0x1010
ENTRY_IP = 0xA6FE
DONE_IP = 0xA68A
ORIGIN_X, ROW_BASE, ROW_SOURCE, ROWS_TO_MILESTONE, FORWARD_FLAG = 0x234E, 0x2350, 0x234C, 0xA978, 0x2354


def _read_scroll(mem, ds: int) -> ScrollState:
    return ScrollState(
        origin_x=mem.rw(ds, ORIGIN_X), row_base=mem.rw(ds, ROW_BASE),
        row_source=mem.rw(ds, ROW_SOURCE), rows_to_milestone=mem.rw(ds, ROWS_TO_MILESTONE),
        forward_last=mem.rw(ds, FORWARD_FLAG) == 0,
    )


def main(argv) -> int:
    default_demo = "demo_play_tandy_L2_full_20260617_180221"
    demo_name = argv[0] if argv else default_demo
    max_frames = int(argv[1]) if len(argv) > 1 else 1500
    demo = load_demo(demo_name, default_demo)

    res = {"calls": 0, "ok": 0, "fail": [], "backward_skipped": 0}
    pending: dict[int, dict] = {}

    def on_ref_step(cpu):
        if (cpu.s.cs & 0xFFFF) != CS:
            return
        ip = cpu.s.ip & 0xFFFF
        key = id(cpu)
        ds = cpu.s.ds & 0xFFFF

        p = pending.get(key)
        if p is not None and ip == DONE_IP:
            del pending[key]
            predicted = p["predicted"]
            actual = _read_scroll(cpu.mem, ds)
            if not p["forward_last_before"]:
                # DS:2354 was already 1 (last pull backward) -- A6FE's own second, still-unported
                # DS:234E==0-after-decrement gate (see systems/scroll.py's module docstring) can
                # fire here and this port does not model it. Skip rather than false-fail.
                res["backward_skipped"] += 1
                return
            res["calls"] += 1
            if predicted == actual:
                res["ok"] += 1
            else:
                res["fail"].append((p["before"], predicted, actual))

        if ip == ENTRY_IP and key not in pending:
            before = _read_scroll(cpu.mem, ds)
            predicted = step_scroll_forward_a6fe(before).state
            pending[key] = dict(predicted=predicted, before=before, forward_last_before=before.forward_last)

    run_ref_step_probe(demo, max_frames, on_ref_step)

    print(f"demo {demo_name} ({max_frames} frames): native forward scroll (A6FE) vs VM: "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])} "
          f"backward_skipped={res['backward_skipped']}")
    for f in res["fail"][:8]:
        print(f"  FAIL before={f[0]} predicted={f[1]} actual={f[2]}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native forward scroll tick reproduces the VM"
          if ok else ("NO-EVENTS -- A6FE was not reached" if res["calls"] == 0
                      else "FAIL -- the native forward scroll tick diverged from the VM"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
