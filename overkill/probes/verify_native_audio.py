"""THE AUDIO ORACLE GATE: is the VM-free AdLib driver's OPL stream byte-exact against the VM?

`render_demo_music` proves the *VM's* OPL stream sounds right; `render_native_music` renders the
recovered VM-free driver (`overkill.native_audio.adlib.AdlibDriver`) but with a GUESSED tempo and no
byte-exact proof.  This gate closes that: it seeds the VM-free driver from the VM's own seg-2032 image
and runs it FORWARD in lockstep with the reference VM, diffing the YM3812 register writes frame by
frame.  A match proves the recovered `tick_2032_0063` spine (the 0409 page gate, the nine 00CD channel
ticks, 024F note/frequency, 0181 instrument select, the 02C9/02F6 modulation) is byte-exact -- and it
reads the music TEMPO (driver ISR ticks per present-frame) directly from the VM instead of by ear.

Method (the same seed-and-replay discipline as the gameplay 9B2E lockstep, for audio):

* Replay a snapshot demo through the pure ref VM; TRAP the tick entry (2032:0063), the OPL write leaf
  (2032:0557, AL=reg/AH=val) and the 1010:9B2E frame tail so each present-frame's (tick-count, writes)
  are captured, plus the seg-2032 image at a chosen seed frame.
* Seed `AdlibDriver` from that image; for each later frame tick it the VM's captured tick-count and
  diff its writes against the VM's.

The music driver plays MUSIC channels only; the game separately triggers SFX and page changes by
writing driver cells mid-frame, which a forward-from-seed sim cannot see.  So a run stays byte-exact
across a steady single-page MUSIC window and then diverges at the first such game event -- `clean_window`
reports that span, and it IS the proof surface (a real driver bug would diverge INSIDE the window).

Usage:
    python -m overkill.probes.verify_native_audio <demo_name> [max_frames] [seed_at]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))

from overkill.native_audio.adlib import AdlibDriver  # noqa: E402
from overkill.probes._harness import load_demo, run_ref_step_probe  # noqa: E402

SEG_2032 = 0x2032
FRAME_BOUNDARY = (0x1010, 0x9B2E)   # the 97B2 gameplay frame tail -- fires once per gameplay frame
DRIVER_TICK = (SEG_2032, 0x0063)    # one timer-ISR driver tick
OPL_WRITE = (SEG_2032, 0x0557)      # AL=reg -> 388h, AH=val -> 389h


def capture(demo_name: str, max_frames: int, seed_at: "int | None" = None):
    """Replay the demo through the ref VM; per gameplay-frame record ``{f, ticks, writes, req, active}``
    (the driver activity DURING that frame) and, if ``seed_at`` is set, the seg-2032 image at that
    frame's tail.  The ref VM runs the driver in the pure interpreter, so ticks/writes are counted by
    TRAPPING the tick entry / write leaf (the fast ``run_ref_step_probe`` trap path)."""
    demo = load_demo(demo_name, demo_name)
    rows: "list[dict]" = []
    st = {"ticks": 0, "writes": [], "seed": None}

    def on_ref(cpu):
        s = cpu.s
        addr = (s.cs & 0xFFFF, s.ip & 0xFFFF)
        if addr == DRIVER_TICK:
            st["ticks"] += 1
        elif addr == OPL_WRITE:
            ax = s.ax & 0xFFFF
            st["writes"].append((ax & 0xFF, (ax >> 8) & 0xFF))
        else:  # FRAME_BOUNDARY: close the frame that just ran, open the next
            f = len(rows)
            if f == seed_at and st["seed"] is None:
                st["seed"] = bytes(cpu.mem.rb(SEG_2032, o) for o in range(0x10000))
            rows.append({
                "f": f, "ticks": st["ticks"], "writes": st["writes"],
                "req": cpu.mem.rb(SEG_2032, 0x0008), "active": cpu.mem.rb(SEG_2032, 0x0009),
            })
            st["ticks"] = 0
            st["writes"] = []

    run_ref_step_probe(demo, max_frames, on_ref,
                       trap=frozenset({FRAME_BOUNDARY, DRIVER_TICK, OPL_WRITE}))
    return rows, st["seed"]


def clean_window(demo_name: str, max_frames: int, seed_at: int = 2):
    """FORWARD lockstep: seed the VM-free driver from the VM's seg-2032 at ``seed_at``, then per frame
    tick it the VM's captured tick-count and diff the OPL writes.  Returns
    ``(matched_frames, diverge_frame, detail)``: how many frames stayed byte-exact, the frame the first
    game event (or a driver bug) broke the match (or ``None`` if the whole span matched), and a
    ``(got, exp)`` sample at that frame."""
    rows, seed = capture(demo_name, max_frames, seed_at=seed_at)
    if seed is None:
        raise RuntimeError(f"no seg-2032 snapshot captured at frame {seed_at} (frames={len(rows)})")
    drv = AdlibDriver(seed)
    drv.drain()
    matched = 0
    for r in rows:
        if r["f"] <= seed_at:      # seg[seed_at] is snapshot AFTER frame seed_at's ticks -> start next
            continue
        for _ in range(r["ticks"]):
            drv.tick_2032_0063()
        got = drv.drain()
        if got != r["writes"]:
            return matched, r["f"], (got, r["writes"])
        matched += 1
    return matched, None, None


def per_tick(demo_name: str, max_frames: int):
    """The STRONGEST form: at every 2032:0063 tick entry snapshot seg-2032, run ONE VM-free tick from
    that exact image, and diff its writes against the VM's writes for that tick.  Because each tick is
    seeded independently from the true pre-tick state, this verifies the driver over the WHOLE demo --
    music AND SFX AND page changes (all of which reach the driver as seg-2032 cells the snapshot
    captures) -- with no forward drift.  Returns ``(ticks_checked, first_bad)`` where ``first_bad`` is
    ``(tick_index, vm_writes, predicted_writes)`` or ``None`` if every tick matched."""
    demo = load_demo(demo_name, demo_name)
    base = SEG_2032 << 4
    st = {"pred": None, "vm": [], "tick": 0, "bad": None}

    def on_ref(cpu):
        s = cpu.s
        addr = (s.cs & 0xFFFF, s.ip & 0xFFFF)
        if addr == OPL_WRITE:
            ax = s.ax & 0xFFFF
            st["vm"].append((ax & 0xFF, (ax >> 8) & 0xFF))
            return
        # DRIVER_TICK entry: close the previous tick, then predict this one from the live image.
        if st["pred"] is not None and st["bad"] is None and st["vm"] != st["pred"]:
            st["bad"] = (st["tick"] - 1, list(st["vm"]), st["pred"])
        st["vm"] = []
        st["tick"] += 1
        drv = AdlibDriver(bytes(cpu.mem.data[base:base + 0x10000]))
        drv.tick_2032_0063()
        st["pred"] = drv.drain()

    run_ref_step_probe(demo, max_frames, on_ref, trap=frozenset({DRIVER_TICK, OPL_WRITE}))
    # the final tick's writes trail the last entry with no next entry to close it -> left unchecked.
    return max(0, st["tick"] - 1), st["bad"]


def main(argv) -> int:
    demo = argv[0] if argv else "demo_play_tandy_L2_full_20260617_180221"
    max_frames = int(argv[1]) if len(argv) > 1 else 600
    seed_at = int(argv[2]) if len(argv) > 2 else 2
    print(f"audio oracle: {demo} ({max_frames} present-frames)")

    # 1) FORWARD from a seed -- proves the music tick + reads the tempo, until the first game event.
    matched, diverge, detail = clean_window(demo, max_frames, seed_at)
    print(f"\n[forward]  byte-exact music window: {matched} gameplay-frames from frame {seed_at + 1}"
          + ("  (whole span, no game event hit)" if diverge is None
             else f"  -> game SFX/page event at frame {diverge}"))

    # 2) PER-TICK -- seeds each tick from the true image, so it proves the driver over the WHOLE demo.
    ticks, bad = per_tick(demo, max_frames)
    if bad is None:
        print(f"[per-tick] {ticks} ticks byte-exact (music + SFX + page changes)")
        print("\nRESULT: PASS -- the VM-free AdLib driver reproduces the VM's OPL stream byte-exact")
        return 0
    idx, vm, pred = bad
    print(f"[per-tick] DIVERGE at tick {idx}: VM {vm[:8]} ({len(vm)}) vs VM-free {pred[:8]} ({len(pred)})")
    print("\nRESULT: FAIL -- a per-tick mismatch is a real driver-recovery frontier")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
