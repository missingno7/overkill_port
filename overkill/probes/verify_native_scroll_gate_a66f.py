"""Produced-vs-VM verify: the native world-scroll gate (``step_scroll_world_progress_gate_a66f``)
vs the VM's ``1010:A66F`` (called every 9B2E tick, right before A067; see
``overkill.gameplay.frame_orchestration``'s ``call(0xA66F, 0x9BAC, ...)``).

Per real A66F entry: capture DS:A47C/A47E/A480 + the scroll fields, predict via the pure gate, then
compare against the VM's actual values at 0x9BAC (A66F's caller's continuation right after the call
returns). A ``None`` prediction (the boss-materialize or unknown-milestone branch) is skipped rather
than compared -- see the function's own docstring for why those two are still declined.

Usage:
    python -m overkill.probes.verify_native_scroll_gate_a66f [demo_name] [max_frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from overkill.probes._harness import load_demo, run_ref_step_probe  # noqa: E402
from overkill.recovered.domain.scroll import ScrollState  # noqa: E402
from overkill.recovered.systems.scroll import step_scroll_world_progress_gate_a66f  # noqa: E402

CS = 0x1010
ENTRY_IP = 0xA66F
DONE_IP = 0x9BAC
A47C, A47E, A480 = 0xA47C, 0xA47E, 0xA480
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

    res = {"calls": 0, "ok": 0, "fail": [], "declined": 0, "backward_skipped": 0}
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
            if predicted is None:
                res["declined"] += 1
                return
            if not p["forward_last_before"]:
                res["backward_skipped"] += 1
                return
            actual = _read_scroll(cpu.mem, ds)
            res["calls"] += 1
            if predicted == actual:
                res["ok"] += 1
            else:
                res["fail"].append((p["before"], predicted, actual))

        if ip == ENTRY_IP and key not in pending:
            before = _read_scroll(cpu.mem, ds)
            predicted = step_scroll_world_progress_gate_a66f(
                before, a47c=cpu.mem.rw(ds, A47C), a47e=cpu.mem.rw(ds, A47E), a480=cpu.mem.rw(ds, A480),
            )
            predicted_state = predicted.state if predicted is not None else None
            pending[key] = dict(predicted=predicted_state, before=before, forward_last_before=before.forward_last)

    run_ref_step_probe(demo, max_frames, on_ref_step)

    print(f"demo {demo_name} ({max_frames} frames): native world-scroll gate (A66F) vs VM: "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])} "
          f"declined={res['declined']} backward_skipped={res['backward_skipped']}")
    for f in res["fail"][:8]:
        print(f"  FAIL before={f[0]} predicted={f[1]} actual={f[2]}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native world-scroll gate reproduces the VM"
          if ok else ("NO-EVENTS -- A66F was not reached" if res["calls"] == 0
                      else "FAIL -- the native world-scroll gate diverged from the VM"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
