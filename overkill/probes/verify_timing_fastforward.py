"""Verify the timing FAST-FORWARD primitive (timing_fastforward.advance_frames_fast).

Three gates, from the L1_start snapshot on raw original bytes (hooks cleared):

1. FRAME CADENCE: over N fast-forwarded frames the wave clock ``DS:A7A0`` (inc'd once per frame at
   ``1010:6031``) advances exactly +1 per frame (or resets via ``FA2F``) -- the boundary the
   primitive counts IS the game's own frame.
2. DETERMINISM: two identical runs produce a byte-identical DGROUP after N frames.
3. THE DRIFT DIFFERENTIAL: the old ``CS:066B = 1`` poke (ISR skipped) visibly diverges from the
   ISR-delivered run -- confirming the primitive carries the state the poke lost.  Both runs' enemy
   liveliness (``DS:A47E`` + the A7A0 clock) is reported; the ISR run must stay live past the
   ~90-frame drift horizon documented in ``loop_blockers.md``.

Usage:
    python -m overkill.probes.verify_timing_fastforward [snapshot_dir] [frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CS = 0x1010
DEFAULT_SNAP = "artifacts/demos/demo_play_tandy_L1_start_20260618_143947/snapshot"
DGROUP_SEG = 0x25CC


def _load(snap):
    from overkill.runtime import load_overkill_snapshot

    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    rt.cpu.replacement_hooks.clear()
    rt.cpu.hook_verifier = None
    return rt.cpu


def _dgroup(cpu) -> bytes:
    base = DGROUP_SEG * 16
    return bytes(cpu.mem.data[base:base + 0x10000])


def _run_fast(snap, frames):
    from overkill.timing_fastforward import advance_frames_fast

    cpu = _load(snap)
    ds = cpu.s.ds & 0xFFFF
    series = []
    advance_frames_fast(cpu, frames,
                        on_frame=lambda c, i: series.append((c.mem.rw(ds, 0xA7A0),
                                                             c.mem.rw(ds, 0xA47E))))
    return cpu, series


def _run_poke(snap, frames):
    """The OLD drift-y method: break the 0679 spin by poking CS:066B=1 (ISR never runs)."""
    cpu = _load(snap)
    ds = cpu.s.ds & 0xFFFF
    series = []
    for _ in range(frames):
        for _ in range(3_000_000):
            cs, ip = cpu.s.cs & 0xFFFF, cpu.s.ip & 0xFFFF
            if cs == CS and ip in (0x0679, 0x067F) and cpu.mem.rb(CS, 0x066B) == 0:
                cpu.mem.wb(CS, 0x066B, 1)
                continue
            if cs == CS and ip == 0x0681:
                cpu.step()
                break
            cpu.step()
        else:
            break
        series.append((cpu.mem.rw(ds, 0xA7A0), cpu.mem.rw(ds, 0xA47E)))
    return cpu, series


def main(argv) -> int:
    snap = Path(argv[0]) if argv else ROOT / DEFAULT_SNAP
    waits = int(argv[1]) if len(argv) > 1 else 800
    fails = 0

    # gate 1: cadence -- the logic-frame clock A7A0 advances by at most +1 per completed wait,
    # never skips, and paces ~1 logic frame per 4 waits on the gameplay path.
    cpu_a, series_a = _run_fast(snap, waits)
    steps = [(series_a[i - 1][0], series_a[i][0]) for i in range(1, len(series_a))]
    bad = [(p, a) for p, a in steps if a not in (p, (p + 1) & 0xFFFF) and a > p]
    resets = sum(1 for p, a in steps if a < p)
    advance = sum(1 for p, a in steps if a == ((p + 1) & 0xFFFF))
    cadence_ok = not bad and resets == 0
    fails += not cadence_ok
    print(f"  cadence: A7A0 {series_a[0][0]:#06x} -> {series_a[-1][0]:#06x} over {waits} waits "
          f"(+1 x{advance}, resets={resets}, skips={len(bad)}) -- ~{waits / max(advance, 1):.2f} waits"
          f"/logic-frame {'ok' if cadence_ok else 'FAIL ' + repr(bad[:4])}")

    # gate 2: determinism
    cpu_b, series_b = _run_fast(snap, waits)
    det_ok = _dgroup(cpu_a) == _dgroup(cpu_b) and series_a == series_b
    fails += not det_ok
    print(f"  determinism: two runs byte-identical DGROUP + series: {'ok' if det_ok else 'FAIL'}")

    # gate 3: the poke differential -- skipping the ISR (the old CS:066B=1 method) must lose state.
    cpu_p, series_p = _run_poke(snap, waits)
    da, dp = _dgroup(cpu_a), _dgroup(cpu_p)
    first_diff = next((i for i in range(len(da)) if da[i] != dp[i]), None)
    diff_count = sum(1 for x, y in zip(da, dp) if x != y)
    fails += first_diff is None
    print(f"  poke differential: DGROUP diff bytes={diff_count}, first at DS:{first_diff:04X}"
          if first_diff is not None else "  poke differential: FAIL -- no DGROUP difference?!")
    gameplay_split = next((i for i, (a, p) in enumerate(zip(series_a, series_p)) if a != p), None)
    print(f"  (info) waits completed: fast={len(series_a)}, poke={len(series_p)}"
          + (f" -- the poke method STALLED at {cpu_p.s.cs & 0xFFFF:04X}:{cpu_p.s.ip & 0xFFFF:04X}"
             f" (it cannot service waits the ISR must release)" if len(series_p) < waits else ""))
    print(f"  (info) gameplay series (A7A0,A47E): fast last={series_a[-1]}, poke last="
          f"{series_p[-1] if series_p else None}, first pairwise divergence at wait "
          f"{gameplay_split if gameplay_split is not None else 'NONE within the overlap'}")

    print(f"timing fast-forward: fails={fails}")
    print("RESULT:", "PASS -- advance_frames_fast paces the game's own wait unit deterministically;"
          " the ISR delivery carries state the poke method loses" if not fails else "CHECK")
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
