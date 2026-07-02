"""Produced-vs-VM verify: the pure ``1010:5145`` Tandy-mode gate vs the real VM.

``5145`` is a tiny helper reached only during the post-level-confirm new-game HUD/status-bar setup
(``971A`` -> ``5C9A`` -> ``5BEE`` -> ``5145``), never during regular gameplay (confirmed: 0 hits across
a 1500-frame gameplay demo, so this MUST run against a cold-start session).

Only the GATE itself is modelled/verified here (:func:`tandy_status_cache_reset_5145`): whether the
routine takes the immediate ``ret`` (mode != 1, a true no-op for this Tandy-only port) or falls through
into more work. The fall-through body does MORE than a first read suggested (a second write, DS:[95A4]
= 0xA000, then a non-standard jump exit rather than a plain ``ret`` back to the caller) -- that tail is
NOT modelled or claimed here; if a demo is ever found that takes it, extend this probe before trusting
it. Verified fact so far: the real cold-start session takes the immediate-ret branch every time.

Usage: python -m overkill.probes.verify_native_tandy_status_cache_reset_5145 [demo_name] [max_frames]
"""
from __future__ import annotations

import sys

from overkill.probes._harness import load_demo, run_ref_step_probe_cold_start
from overkill.recovered.systems.menu import tandy_status_cache_reset_5145

CS = 0x1010
IP_5145 = 0x5145
IP_IMMEDIATE_RET = 0x514D    # the ret at 5145+8, reached only when mode != 1 (JZ not taken)
IP_FALLTHROUGH = 0x514E      # the mov right after the ret, reached only when mode == 1 (JZ taken)
MODE_FLAG = 0x95BC


def main(argv) -> int:
    demo_name = argv[0] if argv else "demo_cold_start_20260701_191727"
    max_frames = int(argv[1]) if len(argv) > 1 else None
    demo = load_demo(demo_name, "demo_cold_start_20260701_191727")

    res = {"calls": 0, "ok": 0, "not_reset_gate": 0, "reset_gate_unverified": 0, "fail": []}
    pending: dict[int, tuple] = {}

    def on_ref_step(cpu):
        cs = cpu.s.cs & 0xFFFF
        ip = cpu.s.ip & 0xFFFF
        key = id(cpu)
        if cs != CS:
            return

        if ip == IP_5145 and key not in pending:
            mode = cpu.mem.rw(cs, MODE_FLAG)
            pending[key] = (mode, tandy_status_cache_reset_5145(mode))
            return

        p = pending.get(key)
        if p is None or ip not in (IP_IMMEDIATE_RET, IP_FALLTHROUGH):
            return
        mode, predicted_reset = pending.pop(key)
        actual_reset_gate = ip == IP_FALLTHROUGH

        res["calls"] += 1
        if predicted_reset != actual_reset_gate:
            res["fail"].append((mode, predicted_reset, actual_reset_gate))
            return
        if actual_reset_gate:
            res["reset_gate_unverified"] += 1  # gate matches; the tail body itself stays unverified
        else:
            res["not_reset_gate"] += 1
        res["ok"] += 1

    run_ref_step_probe_cold_start(demo, max_frames, on_ref_step)

    print(f"demo {demo_name}: native 5145 Tandy-status-cache-reset GATE vs VM: "
          f"calls={res['calls']} ok={res['ok']} not_reset_gate={res['not_reset_gate']} "
          f"reset_gate_unverified_tail={res['reset_gate_unverified']} fail={len(res['fail'])}")
    for f in res["fail"][:8]:
        print(f"  FAIL mode={f[0]:#06x} predicted_reset={f[1]} actual_reset_gate={f[2]}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS" if ok else ("NO-EVENTS" if res["calls"] == 0 else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
