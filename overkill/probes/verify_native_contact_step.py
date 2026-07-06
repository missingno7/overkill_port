"""Driven-oracle: the pure B022 contact-step handlers vs the ORIGINAL 1010:B00D dispatch.

Drives ``B00D`` (the 5073 probe + the B022 direction dispatch AFD8 calls) on the live L1 tile plane
with a synthetic record, across a matrix of positions x all 8 directions x sample-counter seeds, and
compares EVERY outcome to ``systems.contact_step.contact_step_b022``:

* the record's stepped ``+0x02``/``+0x04`` position,
* the blocked/contact flag ``DS:A430`` and the mirror deltas ``DS:A438``/``A436``,
* the ``DS:215A`` sample counter, and the handler-adjusted tile offset (register ``dx`` at return).

Isolation: the initial tile offset comes from the VM's own (already-verified) ``5073``; the pure
side's ``tile_class_at`` callback drives the VM's (already-verified) ``505B`` -- so THIS gate tests
exactly the new handler logic.  Both object pools are CLEARED so the BDD0 contact scan misses
deterministically (the contact-undo path stays a unit-tested pure branch; BDD0's predicate is a
separate leaf).  Off-map (5073 -> FFFF) blocked cases are included.

Usage:
    python -m overkill.probes.verify_native_contact_step [snapshot_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CS = 0x1010
ENTRY_B00D = 0xB00D
ENTRY_5073 = 0x5073
ENTRY_505B = 0x505B
SENTINEL_IP = 0xFFFE
SCRATCH_RECORD = 0x23EC          # effect slot 1 -- the synthetic record bp points at
SCRATCH_SP = 0xFE00              # a high DGROUP scratch stack (SS == DS)
DEFAULT_SNAP = "artifacts/demos/demo_play_tandy_L1_start_20260618_143947/snapshot"


def main(argv) -> int:
    from overkill.runtime import load_overkill_snapshot
    from overkill.recovered.domain.contact_step import ContactStepState
    from overkill.recovered.systems.contact_step import contact_step_b022

    snap = Path(argv[0]) if argv else ROOT / DEFAULT_SNAP
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None
    s = cpu.s
    ds = s.ds & 0xFFFF
    m = cpu.mem

    # clear BOTH pools so the BDD0 contact scan misses deterministically
    for cx in range(1, 0x24):
        rec = m.rw(ds, (0x32CA + cx * 2) & 0xFFFF)
        if rec:
            m.ww(ds, rec, 0)
    for cx in range(1, 0x23):
        rec = m.rw(ds, (0x8D12 + cx * 2) & 0xFFFF)
        if rec:
            m.ww(ds, rec, 0)

    def run_to_sentinel(entry: int, max_steps: int = 4000) -> None:
        m.ww(ds, SCRATCH_SP, SENTINEL_IP)
        s.sp = SCRATCH_SP
        s.cs, s.ip, s.bp = CS, entry, SCRATCH_RECORD
        for _ in range(max_steps):
            if (s.ip & 0xFFFF) == SENTINEL_IP:
                return
            cpu.step()
        raise RuntimeError(f"drive of {entry:04X} did not return")

    def tile_offset_5073() -> int:
        run_to_sentinel(ENTRY_5073)
        return s.bx & 0xFFFF

    def tile_class(offset: int) -> int:
        # 505B: bx = tile offset -> class; ZF set on class 0.  bx is preserved input; class in al.
        save = (s.ip, s.sp, s.bp, s.bx, s.ax)
        m.ww(ds, SCRATCH_SP - 0x40, SENTINEL_IP)
        s.sp = SCRATCH_SP - 0x40
        s.cs, s.ip, s.bx = CS, ENTRY_505B, offset & 0xFFFF
        for _ in range(2000):
            if (s.ip & 0xFFFF) == SENTINEL_IP:
                break
            cpu.step()
        else:
            raise RuntimeError("505B did not return")
        cls = s.ax & 0xFF
        s.ip, s.sp, s.bp, s.bx, s.ax = save
        return cls

    fails = 0
    cases = 0
    blocked_n = offmap_n = stepped_n = 0
    xs = (0x08, 0x30, 0x51, 0x70, 0x8F, 0xB0, 0xF8)
    ys = (0x02, 0x18, 0x33, 0x40, 0x58, 0x7F, 0xA4, 0xC0)
    for x in xs:
        for y in ys:
            for direction in range(8):
                    cases += 1
                    # --- VM side ------------------------------------------------------------
                    # NOTE: DS:215A is NOT an input -- 5073 DERIVES it from x (writes it, unmasked)
                    # on every probe; B00D's own 5073 call recomputes it.  Capture the derived
                    # value after the isolation probe and feed THAT to the pure side.
                    m.ww(ds, SCRATCH_RECORD + 0x00, 1)
                    m.ww(ds, SCRATCH_RECORD + 0x02, x)
                    m.ww(ds, SCRATCH_RECORD + 0x04, y)
                    m.ww(ds, SCRATCH_RECORD + 0x06, direction)
                    m.ww(ds, 0xA430, 0)
                    m.ww(ds, 0xA436, 0x1111)
                    m.ww(ds, 0xA438, 0x2222)
                    off0 = tile_offset_5073()
                    sample = m.rw(ds, 0x215A)
                    run_to_sentinel(ENTRY_B00D)
                    vm = (m.rw(ds, SCRATCH_RECORD + 0x02), m.rw(ds, SCRATCH_RECORD + 0x04),
                          m.rw(ds, 0xA430) != 0, m.rw(ds, 0x215A),
                          (m.rw(ds, 0xA438) - 0x2222) & 0xFFFF, (m.rw(ds, 0xA436) - 0x1111) & 0xFFFF)
                    vm_dx = s.dx & 0xFFFF
                    # --- pure side ----------------------------------------------------------
                    if off0 == 0xFFFF:
                        mine = (x, y, True, sample, 0, 0)
                        mine_dx = None                      # B032 leaves dx unconstrained here
                    else:
                        st = contact_step_b022(
                            direction,
                            ContactStepState(x, y, off0, sample),
                            tile_class,
                            lambda *_: False,
                        )
                        mine = (st.x_word, st.y_word, st.blocked, st.sample_215a,
                                st.mirror_dx_x & 0xFFFF, st.mirror_dx_y & 0xFFFF)
                        mine_dx = st.tile_offset & 0xFFFF
                    ok = vm == mine and (mine_dx is None or vm_dx == mine_dx)
                    fails += not ok
                    blocked_n += vm[2]
                    offmap_n += off0 == 0xFFFF
                    stepped_n += (vm[0], vm[1]) != (x, y)
                    if not ok and fails <= 8:
                        print(f"  FAIL x={x:02X} y={y:02X} dir={direction} 215A={sample:X} "
                              f"off0={off0:04X}: vm={vm} dx={vm_dx:04X} mine={mine} dx={mine_dx}")

    print(f"contact-step handlers: {cases} cases, fails={fails} "
          f"(coverage: stepped={stepped_n}, blocked={blocked_n}, off-map={offmap_n})")
    if not (stepped_n and blocked_n):
        fails += 1
        print("  COVERAGE FAIL: the matrix must exercise both stepped and blocked outcomes")

    # -- gate 2: the FULL AFD8 worker vs the pure composition (PURE tile context, no VM callbacks)
    from overkill.recovered.domain.tilemap import LevelTileContext
    from overkill.recovered.systems.contact_step import contact_probe_afd8

    plane_seg = m.rw(CS, 0x9592)
    tiles = LevelTileContext(
        origin_x_word=m.rw(ds, 0x234E), row_base_word=m.rw(ds, 0x2350),
        tile_plane=bytes(m.mem.data[plane_seg * 16:plane_seg * 16 + 0x4000])
        if hasattr(m, "mem") else bytes(m.data[plane_seg * 16:plane_seg * 16 + 0x4000]),
        class_table=tuple(m.rb(ds, (0xC3AA + i) & 0xFFFF) for i in range(256)),
    )
    cases2 = fails2 = blocked2 = 0
    for x in (0x30, 0x70, 0xB0, 0x9000):
        for y in (0x18, 0x40, 0x7F):
            for direction in range(8):
                for a278 in (0x0000, 0x0020):
                    cases2 += 1
                    m.ww(ds, SCRATCH_RECORD + 0x00, 1)
                    m.ww(ds, SCRATCH_RECORD + 0x02, x)
                    m.ww(ds, SCRATCH_RECORD + 0x04, y)
                    m.ww(ds, SCRATCH_RECORD + 0x06, direction)
                    m.ww(ds, 0xA278, a278)
                    m.ww(ds, 0xA430, 0xBEEF)
                    for cell in (0xA432, 0xA434, 0xA436, 0xA438):
                        m.ww(ds, cell, 0x5555)
                    run_to_sentinel(0xAFD8)
                    vm = (m.rw(ds, SCRATCH_RECORD + 0x02), m.rw(ds, SCRATCH_RECORD + 0x04),
                          m.rw(ds, 0xA430) != 0, m.rw(ds, 0xA432), m.rw(ds, 0xA434),
                          m.rw(ds, 0xA438), m.rw(ds, 0xA436), m.rw(ds, 0x215A))
                    r = contact_probe_afd8(x, y, direction, a278, tiles, lambda *_: False)
                    mine = (r.x_word, r.y_word, r.blocked, r.snap_x, r.snap_y,
                            r.mirror_x, r.mirror_y, r.sample_215a)
                    ok = vm == mine
                    fails2 += not ok
                    blocked2 += vm[2]
                    if not ok and fails2 <= 6:
                        print(f"  FAIL(full) x={x:04X} y={y:02X} dir={direction} a278={a278:04X}: "
                              f"vm={vm} mine={mine}")
    print(f"full AFD8 composition: {cases2} cases, fails={fails2} (blocked={blocked2})")
    fails += fails2
    print("RESULT:", "PASS -- contact_step_b022 matches the original B00D/B022 dispatch on live L1"
          " tiles" if not fails else "CHECK")
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
