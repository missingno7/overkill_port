"""Driven-oracle: behavior 0x20 (the planet-1 wave enemy) vs the ORIGINAL 1010:B73E, whole.

Drives ``B73E`` per phase with a synthetic record + synthetic clocks/globals on the live L1 runtime,
and compares EVERY modeled outcome against the PURE composition:
``systems/enemy_behaviors.step_enemy_behavior_20`` (the decision) + the recovered
``object_target_seek_step_5db2`` (the B85C/B729 move tail, mode 2 over the DS:A348 direction table)
+ ``enemy_shot_stamp_7476`` (the shot) + ``canned_random_next_4d95`` (the shoot gate).

Compared per case: the record fields (+02/+04/+06/+08/+1C/+32/+34), the globals the behavior owns
(2340 reset, the A842 ring cursor, the 20A6 random cursor, and the B729 move-tail writes
2304/2306/2308), and the allocated shot slot's full stamp when shooting.  Excluded (separate,
unmodeled state, per the 5DB2 island's contract): DS:A954 and DS:230A.  Phases covered: both
approach sprite ramps, the arrival idle vs hold boundary (A7A0 0x22 vs 0x23 -- pinning the >=
polarity), the shoot window with even AND odd ring words, the dive (parity 0/1 + the 2340<5 ungated
entry), the re-shuffle (fresh + skip-same), and substates 0 (both branches) / 1 / 2 (both edges).

Usage:
    python -m overkill.probes.verify_native_behavior_20 [snapshot_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CS = 0x1010
SENTINEL_IP = 0xFFFE
SCRATCH_SP = 0xFE80
RECORD = 0x23EC
DEFAULT_SNAP = "artifacts/demos/demo_play_tandy_L1_start_20260618_143947/snapshot"
SHOT_OFFSETS = (0x00, 0x02, 0x04, 0x06, 0x08, 0x0A, 0x14, 0x16, 0x18, 0x1C, 0x1E, 0x2A, 0x2C)


def main(argv) -> int:
    from overkill.runtime import load_overkill_snapshot
    from overkill.recovered.adapters.canned_random_adapter import load_canned_random_ring
    from overkill.recovered.adapters.enemy_slot_ring_adapter import load_enemy_slot_ring
    from overkill.recovered.domain.movement import MovementTarget
    from overkill.recovered.systems.enemy_behaviors import step_enemy_behavior_20
    from overkill.recovered.systems.frame_loop import (
        canned_random_next_4d95,
        enemy_shot_stamp_7476,
    )
    from overkill.recovered.systems.movement import object_target_seek_step_5db2

    snap = Path(argv[0]) if argv else ROOT / DEFAULT_SNAP
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None
    s = cpu.s
    ds = s.ds & 0xFFFF
    m = cpu.mem

    image = bytes(m.data)
    rand_ring = load_canned_random_ring(image)
    slot_ring = load_enemy_slot_ring(image)
    direction_table = tuple(m.rb(ds, (0xA348 + i) & 0xFFFF) for i in range(16))

    def run_b73e() -> None:
        m.ww(ds, SCRATCH_SP, SENTINEL_IP)
        s.sp = SCRATCH_SP
        s.cs, s.ip, s.bp = CS, 0xB73E, RECORD
        for _ in range(8000):
            if (s.ip & 0xFFFF) == SENTINEL_IP:
                return
            cpu.step()
        raise RuntimeError("B73E did not return")

    def clear_gameplay_pool():
        for cx in range(1, 0x23):
            rec = m.rw(ds, (0x8D12 + cx * 2) & 0xFFFF)
            if rec:
                m.ww(ds, rec, 0)
        # also clear every OTHER effect-pool record: live leftover objects otherwise collide with
        # the synthetic record mid-seek (the C037 death family zeroes its sprite -- caught by the
        # write-trap when a case at (0x40,0x50) overlapped live L1 state)
        for cx in range(1, 0x24):
            rec = m.rw(ds, (0x32CA + cx * 2) & 0xFFFF)
            if rec and rec != RECORD:
                m.ww(ds, rec, 0)

    # pick 20A6 cursors whose NEXT ring word is even / odd (for the shoot-gate cases)
    def cursor_for_parity(par: int) -> int:
        for cur in range(0x20A6, 0x20C6, 2):
            if canned_random_next_4d95(cur, rand_ring)[0] & 1 == par:
                return cur
        raise RuntimeError(f"no ring word with parity {par}")

    even_cur, odd_cur = cursor_for_parity(0), cursor_for_parity(1)

    # the player anchor sits far from every case position: the REAL seek path includes the
    # player-touch check, and an enemy stepping onto the anchor runs the C037 death transition
    # (found the hard way -- a case at (0x40,0x50) with the anchor at (0x40,0x58) died mid-move)
    base = dict(x=0x60, y=0x50, sub=0xFFFF, tx=0x60, ty=0x50, a7a0=0x30, c2338=2, c2340=0x100,
                c232e=0, par=0, a47e=10, ax_2380=0xA8, px_237e=0x18, a842=0xA844, a20a6=0x20A6)
    cases = [
        ("approach lo-ramp", dict(x=0x40, a7a0=0)),
        ("approach hi-ramp", dict(x=0x40, y=0x70, ty=0x70)),
        ("idle pre-gate", dict(a7a0=0x22)),
        ("hold at gate", dict(a7a0=0x23)),
        ("shoot even", dict(c2340=0x2BC, a20a6=even_cur)),
        ("shoot odd", dict(c2340=0x2D0, a20a6=odd_cur)),
        ("dive parity0", dict(a47e=3, par=0)),
        ("dive parity1", dict(a47e=3, par=1, ty=0x53, y=0x53)),
        ("dive ungated", dict(c2340=4, par=1)),
        ("reshuffle", dict(c232e=0x3F)),
        ("reshuffle skip-same", dict(c232e=0x3F,
                                     x=(slot_ring[0][0] + 0x20) & 0xFFFF, y=slot_ring[0][1],
                                     tx=(slot_ring[0][0] + 0x20) & 0xFFFF, ty=slot_ring[0][1])),
        ("substate0 move", dict(sub=0, x=0x20)),
        ("substate0 arrive", dict(sub=0)),
        ("substate1", dict(sub=1)),
        ("substate2 fly", dict(sub=2, x=0x90)),
        ("substate2 edge", dict(sub=2, x=0x9C)),
    ]

    fails = 0
    for name, over in cases:
        c = dict(base)
        c.update(over)
        clear_gameplay_pool()
        m.ww(ds, RECORD + 0x00, 1)
        m.ww(ds, RECORD + 0x02, c["x"])
        m.ww(ds, RECORD + 0x04, c["y"])
        m.ww(ds, RECORD + 0x06, 0)
        m.ww(ds, RECORD + 0x08, 0x0011)
        m.ww(ds, RECORD + 0x1C, c["sub"])
        m.ww(ds, RECORD + 0x32, c["ty"])
        m.ww(ds, RECORD + 0x34, c["tx"])
        for off, val in ((0x2338, c["c2338"]), (0x2340, c["c2340"]), (0x232E, c["c232e"]),
                         (0x2324, c["par"]), (0xA7A0, c["a7a0"]), (0xA47E, c["a47e"]),
                         (0x2380, c["ax_2380"]), (0x237E, c["px_237e"]), (0xA842, c["a842"]),
                         (0x20A6, c["a20a6"]), (0xA8C2, 0), (0x2304, 0), (0x2306, 0), (0x2308, 0)):
            m.ww(ds, off, val)
        m.wb(ds, 0x98C0, 0)
        run_b73e()
        vm_rec = tuple(m.rw(ds, RECORD + o) for o in (0x02, 0x04, 0x06, 0x08, 0x1C, 0x32, 0x34))
        vm_glob = tuple(m.rw(ds, o) for o in (0x2340, 0xA842, 0x20A6, 0x2304, 0x2306, 0x2308))
        vm_shot_slot = next((m.rw(ds, (0x8D12 + cx * 2) & 0xFFFF) for cx in range(1, 0x23)
                             if m.rw(ds, m.rw(ds, (0x8D12 + cx * 2) & 0xFFFF)) != 0), None)

        # ---- the pure composition ----
        rand_val, rand_next = canned_random_next_4d95(c["a20a6"], rand_ring)
        r = step_enemy_behavior_20(
            x_word=c["x"], y_word=c["y"], substate_1c=c["sub"],
            target_x_34=c["tx"], target_y_32=c["ty"],
            a7a0=c["a7a0"], clock_2338=c["c2338"], clock_2340=c["c2340"], clock_232e=c["c232e"],
            parity_2324=c["par"], active_enemies_a47e=c["a47e"], anchor_y_2380=c["ax_2380"],
            ring_cursor_a842=c["a842"], slot_ring=slot_ring, random_value=rand_val)
        x, y, direction = c["x"], c["y"], 0
        g2304 = g2306 = g2308 = 0
        if r.move_to_target:
            seek = object_target_seek_step_5db2(x, y, direction,
                                                MovementTarget(y_word=c["ty"], x_word=c["tx"]),
                                                2, direction_table)
            x, y, direction = seek.x_word, seek.y_word, seek.direction_or_step
            g2304, g2306, g2308 = c["ty"], c["tx"], 2
        rec = {0x02: x, 0x04: y, 0x06: direction, 0x08: 0x0011,
               0x1C: c["sub"], 0x32: c["ty"], 0x34: c["tx"]}
        for off, val in r.record_writes.items():
            rec[off] = val & 0xFFFF
        glob = {0x2340: c["c2340"], 0xA842: c["a842"],
                0x20A6: rand_next if r.random_stepped else c["a20a6"],
                0x2304: g2304, 0x2306: g2306, 0x2308: g2308}
        for off, val in r.global_writes.items():
            glob[off] = val & 0xFFFF
        mine_rec = tuple(rec[o] for o in (0x02, 0x04, 0x06, 0x08, 0x1C, 0x32, 0x34))
        mine_glob = tuple(glob[o] for o in (0x2340, 0xA842, 0x20A6, 0x2304, 0x2306, 0x2308))

        shot_ok = True
        if r.shoot:
            if vm_shot_slot is None:
                shot_ok = False
            else:
                stamp = enemy_shot_stamp_7476(c["x"], c["y"], False, c["px_237e"], c["ax_2380"])
                got = {o: m.rw(ds, (vm_shot_slot + o) & 0xFFFF) for o in SHOT_OFFSETS}
                shot_ok = got == {o: stamp[o] & 0xFFFF for o in SHOT_OFFSETS}
        else:
            shot_ok = vm_shot_slot is None

        ok = vm_rec == mine_rec and vm_glob == mine_glob and shot_ok
        fails += not ok
        print(f"  {name:20s} {'ok' if ok else 'FAIL'}"
              + ("" if ok else f"  vm_rec={vm_rec} mine={mine_rec} vm_glob={vm_glob} "
                               f"mine={mine_glob} shot_ok={shot_ok}"))

    print(f"behavior 0x20: {len(cases)} cases, fails={fails}")
    print("RESULT:", "PASS -- step_enemy_behavior_20 (+ the recovered seek/shot/random) matches the"
          " original B73E whole" if not fails else "CHECK")
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
