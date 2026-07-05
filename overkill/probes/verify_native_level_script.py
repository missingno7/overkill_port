"""Driven-oracle: the level object-script walker vs the ORIGINAL 1010:4A65.

For each planet's static script, picks upcoming entries, sets ``DS:A978`` to their trigger row,
clears the pools, and drives the original walker; then runs
``adapters/level_object_script.run_level_object_script_4a65`` on a pre-state copy and diffs the
ENTIRE DGROUP (the completeness-diff pattern: only the live stack window excluded).  This proves
the spawn stamps, the 2078 counter registration, the controller 0209 init, the cursor advance and
the multi-entry-per-row iteration byte-exact.

Ground-object entries (scan == 1, gate != 1) currently fail loud in the native walker; the case
list reports which triggers exercised them so the 4B4A snap decode can close the gap.

Usage:
    python -m overkill.probes.verify_native_level_script [snapshot_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CS = 0x1010
ENTRY = 0x4A65
SENTINEL_IP = 0xFFFE
SCRATCH_SP = 0xFF40
DGROUP = 0x25CC
DEFAULT_SNAP = "artifacts/demos/demo_play_tandy_L1_start_20260618_143947/snapshot"
SCRIPT_HEADS = {0: 0xC85C, 1: 0xC8DE, 2: 0xCA02, 3: 0xCC36, 4: 0xCC80, 5: 0xCCAA}


def main(argv) -> int:
    from overkill.runtime import load_overkill_snapshot
    from overkill.recovered.adapters.flat_memory import MutFlatMemory
    from overkill.recovered.adapters.level_object_script import run_level_object_script_4a65
    from overkill.recovered.domain.gaps import RecoveryGap

    snap = Path(argv[0]) if argv else ROOT / DEFAULT_SNAP
    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None
    s = cpu.s
    ds = s.ds & 0xFFFF
    m = cpu.mem
    base = DGROUP * 16

    def run_vm() -> None:
        m.ww(ds, SCRATCH_SP, SENTINEL_IP)
        s.sp = SCRATCH_SP
        s.cs, s.ip = CS, ENTRY
        for _ in range(200_000):
            if (s.ip & 0xFFFF) == SENTINEL_IP:
                return
            cpu.step()
        raise RuntimeError("4A65 did not return")

    def clear_pools() -> None:
        for cx in range(1, 0x24):
            rec = m.rw(ds, (0x32CA + cx * 2) & 0xFFFF)
            if rec:
                m.ww(ds, rec, 0)
        for i in range(0x10):
            m.ww(ds, 0x2078 + i * 2, 0)      # free every completion-counter slot

    fails = cases = gaps = 0
    for planet, head in SCRIPT_HEADS.items():
        # walk the static script structurally to enumerate the first few triggers
        triggers = []
        si = head
        for _ in range(6):
            trig = m.rw(ds, si)
            if trig == 0xFFFF:
                break
            step = 8
            if m.rw(ds, si + 2) == 0xFFFF:
                step = 10
            triggers.append((trig, si))
            si += step
            if len(triggers) >= 3:
                break
        for trig, entry_at in triggers:
            cases += 1
            clear_pools()
            m.ww(ds, 0x2356, planet)
            m.ww(ds, m.rw(ds, (0xC5E9 + planet * 2) & 0xFFFF), entry_at)   # cursor -> this entry
            m.ww(ds, 0xA978, trig)
            pre = bytes(m.data)
            run_vm()
            sp_entry = SCRATCH_SP
            vm_bytes = bytes(m.data[base:base + 0x10000])
            native = MutFlatMemory(pre)
            try:
                run_level_object_script_4a65(native)
            except RecoveryGap as gap:
                gaps += 1
                print(f"  planet {planet} trig {trig:04X}: NATIVE GAP ({gap.args[0]}) -- skipped")
                continue
            nat_bytes = bytes(native.data[base:base + 0x10000])
            # the stack window includes the sentinel word AT sp_entry (the probe writes it after
            # taking the pre-state copy)
            diffs = [o for o in range(0x10000)
                     if vm_bytes[o] != nat_bytes[o] and not (sp_entry - 0x60 <= o < sp_entry + 2)]
            ok = not diffs
            fails += not ok
            print(f"  planet {planet} trig {trig:04X}: "
                  + ("ok" if ok else f"FAIL {len(diffs)} bytes, first DS:{diffs[0]:04X} "
                                     f"(vm={vm_bytes[diffs[0]]:02X} native={nat_bytes[diffs[0]]:02X})"))

    print(f"level object script: {cases} cases, fails={fails}, native-gap skips={gaps}")
    print("RESULT:", "PASS -- the native 4A65 walker matches the original for every non-gap entry"
          if fails == 0 and cases > gaps else "CHECK")
    return 0 if fails == 0 and cases > gaps else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
