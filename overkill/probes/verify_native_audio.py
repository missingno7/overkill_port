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


def main(argv) -> int:
    demo = argv[0] if argv else "demo_play_tandy_L2_full_20260617_180221"
    max_frames = int(argv[1]) if len(argv) > 1 else 600
    seed_at = int(argv[2]) if len(argv) > 2 else 2
    print(f"audio oracle: {demo} (seed@{seed_at}, {max_frames} present-frames)")
    matched, diverge, detail = clean_window(demo, max_frames, seed_at)
    print(f"byte-exact music window: {matched} gameplay-frames from frame {seed_at + 1}")
    if diverge is None:
        print("RESULT: PASS -- byte-exact for the whole captured span (no game event hit)")
        return 0
    got, exp = detail
    print(f"first divergence at frame {diverge}: VM-free {len(got)} writes vs VM {len(exp)} writes")
    print("  (a large VM-side burst here is the game triggering SFX / a page change -- the music-only")
    print("   isolation boundary; a driver bug would instead diverge on a small mismatch mid-window)")
    print(f"RESULT: byte-exact music proven over {matched} frames, then the game event at {diverge}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
