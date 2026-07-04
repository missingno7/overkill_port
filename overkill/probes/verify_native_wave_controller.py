"""Driven-oracle: the 0x1F wave controller vs the ORIGINAL 1F8F:027A (whole, per phase).

Drives the far handler with ``bp`` = a synthetic controller record (behavior 0x1F so the family
dispatch takes the 0x1F tail), across flying and waypoint-arrival cases on the live L1 runtime, and
compares against ``systems/enemy_behaviors.step_wave_controller_1f`` composed with the recovered
5DB2 seek:

* the record's ``+02/+04/+06/+08`` after the frame (seek step + the 0448 sprite = direction+0x3B),
* the seek-target globals ``2304/2306/2308`` (mode 3), the schedule cursor ``A482``, the ring
  cursor ``A842`` (+4 per spawn attempt, NO wrap) and the enemy count ``A47E``,
* on arrival: the FIVE spawned records' stamps (8209 base with leader-context = the controller's
  position, ``+34/+32`` from consecutive ring slots, behavior 0x20, substate FFFF).

Both pools are cleared so the burst allocates deterministically and nothing collides mid-seek; the
player anchor is parked away from the flight path (the seek path's touch-death lesson).

Usage:
    python -m overkill.probes.verify_native_wave_controller [snapshot_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

OVERLAY = 0x1F8F
ENTRY = 0x027A
SENTINEL_CS, SENTINEL_IP = 0x1010, 0xFFFE
SCRATCH_SP = 0xFEC0
RECORD = 0x23EC
DEFAULT_SNAP = "artifacts/demos/demo_play_tandy_L1_start_20260618_143947/snapshot"
SPAWN_OFFSETS = (0x00, 0x02, 0x04, 0x06, 0x0A, 0x14, 0x16, 0x18, 0x1C, 0x20, 0x24, 0x28,
                 0x32, 0x34)


def main(argv) -> int:
    from overkill.runtime import load_overkill_snapshot
    from overkill.recovered.systems.enemy_behaviors import step_wave_controller_1f

    snap = Path(argv[0]) if argv else ROOT / DEFAULT_SNAP
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None
    s = cpu.s
    ds = s.ds & 0xFFFF
    m = cpu.mem

    # the schedule pairs are read from LIVE memory: the A82A region is NOT a flat static pair list
    # (a cold==live pin caught runtime-written words embedded past the flown prefix -- the
    # structure decode is its own future slice); the controller only ever consumes [A482]'s pair.
    def schedule_pair(a482: int) -> tuple[int, int]:
        return m.rw(ds, a482 & 0xFFFF), m.rw(ds, (a482 + 2) & 0xFFFF)

    direction_table = tuple(m.rb(ds, (0xA348 + i) & 0xFFFF) for i in range(16))

    def ring_slot_at(cursor: int):
        return m.rw(ds, cursor & 0xFFFF), m.rw(ds, (cursor + 2) & 0xFFFF)

    def clear_pools():
        for cx in range(1, 0x23):
            rec = m.rw(ds, (0x8D12 + cx * 2) & 0xFFFF)
            if rec:
                m.ww(ds, rec, 0)
        for cx in range(1, 0x24):
            rec = m.rw(ds, (0x32CA + cx * 2) & 0xFFFF)
            if rec and rec != RECORD:
                m.ww(ds, rec, 0)

    def run_far() -> None:
        m.ww(ds, SCRATCH_SP, SENTINEL_IP)
        m.ww(ds, SCRATCH_SP + 2, SENTINEL_CS)
        s.sp = SCRATCH_SP
        s.cs, s.ip, s.bp = OVERLAY, ENTRY, RECORD
        for _ in range(20000):
            if (s.cs & 0xFFFF) == SENTINEL_CS and (s.ip & 0xFFFF) == SENTINEL_IP:
                return
            cpu.step()
        raise RuntimeError("1F8F:027A did not return")

    # cases: mid-flight toward waypoint 0 (two spots), exactly AT waypoint 0 (the burst), and
    # mid-flight toward a later waypoint (cursor advanced)
    wp0_raw = schedule_pair(0xA82A)
    wp1_raw = schedule_pair(0xA82E)
    wp0_x, wp0_y = (wp0_raw[0] + 0x20) & 0xFFFF, wp0_raw[1]
    wp1_x, wp1_y = (wp1_raw[0] + 0x20) & 0xFFFF, wp1_raw[1]
    cases = [
        ("fly far", 0xA82A, 0x30, 0x20, 6),
        ("fly near", 0xA82A, (wp0_x - 8) & 0xFFFF, wp0_y, 2),
        ("ARRIVE burst", 0xA82A, wp0_x, wp0_y, 6),
        ("fly wp1", 0xA82E, (wp1_x + 0x10) & 0xFFFF, (wp1_y + 0x18) & 0xFFFF, 0),
    ]
    fails = 0
    for name, a482, x, y, direction in cases:
        clear_pools()
        m.ww(ds, RECORD + 0x00, 1)
        m.ww(ds, RECORD + 0x02, x)
        m.ww(ds, RECORD + 0x04, y)
        m.ww(ds, RECORD + 0x06, direction)
        m.ww(ds, RECORD + 0x08, 0x1111)
        m.ww(ds, RECORD + 0x16, 4)
        m.ww(ds, RECORD + 0x18, 0x001F)
        for off, val in ((0xA482, a482), (0xA842, 0xA844), (0xA47E, 1),
                         (0x2380, 0xB8), (0x237E, 0x08),
                         (0x2304, 0), (0x2306, 0), (0x2308, 0), (0x230A, 0)):
            m.ww(ds, off, val)
        sched_x_raw, sched_y = schedule_pair(a482)
        run_far()
        vm_rec = tuple(m.rw(ds, RECORD + o) for o in (0x02, 0x04, 0x06, 0x08))
        vm_glob = tuple(m.rw(ds, o) for o in (0x2304, 0x2306, 0x2308, 0xA482, 0xA842, 0xA47E))
        spawned = [m.rw(ds, (0x32CA + cx * 2) & 0xFFFF) for cx in range(1, 0x24)
                   if (rec := m.rw(ds, (0x32CA + cx * 2) & 0xFFFF)) != RECORD
                   and m.rw(ds, rec) != 0]

        r = step_wave_controller_1f(
            x_word=x, y_word=y, direction=direction,
            schedule_x_raw=sched_x_raw, schedule_y=sched_y,
            ring_cursor_a842=0xA844, ring_slot_at=ring_slot_at,
            direction_table=direction_table)
        mine_rec = (r.x_word, r.y_word, r.direction, r.sprite)
        mine_glob = (r.seek_globals[0x2304], r.seek_globals[0x2306], r.seek_globals[0x2308],
                     (a482 + r.schedule_advance) & 0xFFFF, r.ring_cursor_after,
                     1 + len(r.spawn_stamps))
        spawn_ok = len(spawned) == len(r.spawn_stamps)
        if spawn_ok and r.spawn_stamps:
            for rec, stamp in zip(sorted(spawned), r.spawn_stamps):
                got = {o: m.rw(ds, (rec + o) & 0xFFFF) for o in SPAWN_OFFSETS}
                want = {o: stamp.get(o, got[o]) & 0xFFFF for o in SPAWN_OFFSETS}
                if got != want:
                    spawn_ok = False
                    print(f"    spawn diff at {rec:04X}: "
                          f"{ {o: (got[o], want[o]) for o in SPAWN_OFFSETS if got[o] != want[o]} }")
        ok = vm_rec == mine_rec and vm_glob == mine_glob and spawn_ok
        fails += not ok
        print(f"  {name:14s} {'ok' if ok else 'FAIL'}"
              + ("" if ok else f"  vm_rec={vm_rec} mine={mine_rec} vm_glob={vm_glob} "
                               f"mine={mine_glob} spawns vm={len(spawned)} mine={len(r.spawn_stamps)}"))

    print(f"wave controller 0x1F: {len(cases)} cases, fails={fails}")
    print("RESULT:", "PASS -- step_wave_controller_1f (+ the recovered seek) matches the original"
          " 1F8F:027A whole" if not fails else "CHECK")
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
