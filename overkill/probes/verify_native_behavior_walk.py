"""The WHOLE-WALK SHADOW: the native behavior-registry walk vs the VM's A9D3..AA25, per frame.

For each fast-forwarded frame from the L1_start snapshot (raw original bytes, the real IRQ0 ISR
delivered at the game's own wait points -- the timing_fastforward semantics, never a CS:066B poke):

1. trap the walk-stage entry ``1010:A9D3``; copy the machine state;
2. run the NATIVE walk (``adapters/behavior_walk.run_behavior_walk_a9d3`` -- the registry of
   recovered pure systems) over the copy;
3. let the VM run its own walk to ``1010:AA25`` (the stage end, before the 1F8F:0922 far call);
4. diff the ENTIRE 64K DGROUP between the VM and the native copy, excluding only the live stack
   window (SS == DS; the VM's walk pushes/pops there, the native walk has no stack) and the
   documented out-of-model steer scratch cells (DS:A954 direction-bits + DS:230A blocked flag --
   the 5DB2 island's contract keeps them separate).

Zero differing bytes over >= 200 frames = the registry stage IS the walk.

Usage:
    python -m overkill.probes.verify_native_behavior_walk [snapshot_dir] [frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CS = 0x1010
WALK_ENTRY = 0xA9D3
WALK_END = 0xAA25
DGROUP = 0x25CC
DEFAULT_SNAP = "artifacts/demos/demo_play_tandy_L1_start_20260618_143947/snapshot"
# out-of-model scratch (documented): the 5DB2/5E42 steer globals live OUTSIDE the pure islands
# (A954 direction bits, 230A blocked flag, 230C/230E/2310 the 5E42 delta-steer scratch triple --
# "not slot state" per domain/movement.DeltaSteerStep; the attract wave only toggles 230E/2310).
# DS:215A is promiscuous IRQ/sound/menu scratch, not object-behavior state -- see
# verify_native_walk_demo.EXCLUDED_CELLS for the trace evidence.
EXCLUDED_CELLS = {0xA954, 0xA955, 0x230A, 0x230B, 0x230C, 0x230D,
                  0x230E, 0x230F, 0x2310, 0x2311, 0x215A, 0x215B}


def main(argv) -> int:
    from overkill.runtime import load_overkill_snapshot
    from overkill.recovered.adapters.behavior_walk import run_behavior_walk_a9d3
    from overkill.recovered.adapters.flat_memory import MutFlatMemory
    from overkill.recovered.domain.tilemap import LevelTileContext
    from overkill.sounds.timing import deliver_overkill_timer_irq0

    snap = Path(argv[0]) if argv else ROOT / DEFAULT_SNAP
    want_frames = int(argv[1]) if len(argv) > 1 else 200
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None
    s = cpu.s
    ds = s.ds & 0xFFFF
    m = cpu.mem
    base = DGROUP * 16
    plane_seg = m.rw(CS, 0x9592)
    class_table = tuple(m.rb(ds, (0xC3AA + i) & 0xFFFF) for i in range(256))
    plane = bytes(m.data[plane_seg * 16:plane_seg * 16 + 0x4000])

    def step_with_isr() -> None:
        csr, ip = s.cs & 0xFFFF, s.ip & 0xFFFF
        if csr == CS and ip in (0x0679, 0x067F) and m.rb(CS, 0x066B) == 0:
            if not deliver_overkill_timer_irq0(cpu):
                raise RuntimeError("no installed INT 08h")
            return
        if csr == CS and ip in (0x9921, 0x9926) and m.rb(ds, 0xBEFE) != 0:
            if not deliver_overkill_timer_irq0(cpu):
                raise RuntimeError("no installed INT 08h")
            return
        cpu.step()

    frames = 0
    diverged = 0
    first_diffs: list[str] = []
    budget = 60_000_000
    while frames < want_frames and budget > 0:
        budget -= 1
        if (s.cs & 0xFFFF) == CS and (s.ip & 0xFFFF) == WALK_ENTRY:
            # ---- the shadow ----
            native = MutFlatMemory(bytes(m.data))
            tiles = LevelTileContext(origin_x_word=m.rw(ds, 0x234E), row_base_word=m.rw(ds, 0x2350),
                                     tile_plane=plane, class_table=class_table)
            run_behavior_walk_a9d3(native, tiles)
            sp_entry = s.sp & 0xFFFF
            while not ((s.cs & 0xFFFF) == CS and (s.ip & 0xFFFF) == WALK_END):
                cpu.step()
                budget -= 1
                if budget <= 0:
                    raise RuntimeError("walk did not reach AA25")
            frames += 1
            vm_bytes = bytes(m.data[base:base + 0x10000])
            nat_bytes = bytes(native.data[base:base + 0x10000])
            if vm_bytes != nat_bytes:
                diffs = [o for o in range(0x10000)
                         if vm_bytes[o] != nat_bytes[o]
                         and o not in EXCLUDED_CELLS
                         and not (sp_entry - 0x60 <= o < sp_entry)]
                if diffs:
                    diverged += 1
                    if len(first_diffs) < 12:
                        first_diffs.append(
                            f"frame {frames}: {len(diffs)} bytes, first at DS:{diffs[0]:04X} "
                            f"(vm={vm_bytes[diffs[0]]:02X} native={nat_bytes[diffs[0]]:02X})")
            continue
        step_with_isr()

    for line in first_diffs:
        print("  " + line)
    print(f"whole-walk shadow: {frames} frames, diverged={diverged}")
    print("RESULT:", f"PASS -- the native behavior-registry walk matches the VM's A9D3..AA25 with "
          f"zero divergence over {frames} fast-forwarded frames"
          if frames >= want_frames and diverged == 0 else "CHECK")
    return 0 if frames >= want_frames and diverged == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
