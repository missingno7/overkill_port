"""Byte-exact gate: the native A846 hit-flash decay vs the ORIGINAL, for EVERY drawn record.

The recorded demos never set an enemy hit-flash (+0x24), so the lockstep gate never exercised the
per-record flash decay -- and an earlier native frame decayed ONLY the player anchor, leaving every
hit enemy stuck white.  This drives the pure reference VM over a gameplay demo and, at each 1010:9B2E
frame boundary, INJECTS +0x24 = K into all 70 object records on BOTH sides, runs one VM frame and one
native frame (``advance_gameplay_frame_97b2``) over the same pre-state, and compares every record's
+0x24 the next boundary.  Zero divergence means the native decay ticks exactly the records the VM's
draw scan draws, by exactly the slot count -- the fix for the "enemies stay white" bug.

Usage:
    python -m overkill.probes.verify_native_flash_decay [demo_name] [max_frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from overkill.native_frame import advance_gameplay_frame_97b2  # noqa: E402
from overkill.probes._harness import load_demo, run_ref_step_probe  # noqa: E402
from overkill.recovered.adapters.flat_memory import MutFlatMemory  # noqa: E402
from overkill.recovered.domain.gaps import RecoveryGap  # noqa: E402

CS = 0x1010
FRAME_TOP = 0x9B2E
INT8_VECTOR = (0x0000, 0x0020)
DGROUP = 0x25CC
STRIDE = 0x38
OFFV = 0x24
INJECT = 6
# every object record A846 can draw: the anchor, the 8D12 gameplay pool, the 32CA effect pool.
RECORDS = ([0x237C]
           + [0x2B5C + i * STRIDE for i in range(0x22)]
           + [0x23B4 + i * STRIDE for i in range(0x23)])


def _level_assets_for(planet, _cache={}):
    if planet not in _cache:
        sys.path.insert(0, str(ROOT / "scripts"))
        from play_native import make_level_assets
        container = (ROOT / "assets" / "OVERKILL").read_bytes()
        bundle = (ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin").read_bytes()
        _cache[planet] = make_level_assets(container, bundle)
    return _cache[planet]


def main(argv) -> int:
    demo = load_demo(argv[0] if argv else None, "demo_play_tandy_20260710_144212")
    max_frames = int(argv[1]) if len(argv) > 1 else 400

    st = {"n": 0, "ticks": 0, "pending": None, "checked": 0, "diverged": 0, "gaps": 0,
          "first": []}
    base = DGROUP * 16

    def read_flashes(m):
        ds = DGROUP
        return {r: m.rw(ds, (r + OFFV) & 0xFFFF) if hasattr(m, "rw")
                else (m.data[base + r + OFFV] | (m.data[base + r + OFFV + 1] << 8))
                for r in RECORDS}

    def on_step(cpu):
        s = cpu.s
        if (s.cs & 0xFFFF, s.ip & 0xFFFF) == INT8_VECTOR:
            st["ticks"] += 1
            return
        if (s.cs & 0xFFFF) != CS or (s.ip & 0xFFFF) != FRAME_TOP:
            return
        m = cpu.mem
        ds = s.ds & 0xFFFF

        # 1) settle the previous frame: the VM's +0x24 now == its decay of the injected pre-state.
        if st["pending"] is not None:
            native_post = st["pending"]
            for r in RECORDS:
                vm_v = m.data[base + r + OFFV] | (m.data[base + r + OFFV + 1] << 8)
                st["checked"] += 1
                if vm_v != native_post[r]:
                    st["diverged"] += 1
                    if len(st["first"]) < 8:
                        st["first"].append(f"frame {st['n']} rec {r:#06x}: VM +24={vm_v} "
                                            f"native={native_post[r]}")
            st["pending"] = None

        st["n"] += 1
        if st["n"] > max_frames:
            raise StopIteration

        # 2) inject K into every record on BOTH sides, then run one native frame over the VM pre-state.
        pre = bytearray(m.data)
        for r in RECORDS:
            off = base + r + OFFV
            pre[off] = INJECT & 0xFF
            pre[off + 1] = (INJECT >> 8) & 0xFF
            m.ww(ds, (r + OFFV) & 0xFFFF, INJECT)          # the live VM decays these this frame

        planet = m.rw(ds, 0x2356)
        native = MutFlatMemory(bytes(pre))
        try:
            advance_gameplay_frame_97b2(native, isr_ticks=max(1, st["ticks"]),
                                        level_assets=_level_assets_for(planet))
            st["pending"] = read_flashes(native)
        except RecoveryGap:
            st["gaps"] += 1
            st["pending"] = None
        st["ticks"] = 0

    try:
        run_ref_step_probe(demo, max_frames + 5, on_step,
                           trap=frozenset({(CS, FRAME_TOP), INT8_VECTOR}))
    except StopIteration:
        pass

    print(f"demo {demo_name(demo)}: frames driven {st['n']}, record-compares {st['checked']}, "
          f"native gaps skipped {st['gaps']}, DIVERGED {st['diverged']}")
    for line in st["first"]:
        print(f"  DIVERGENCE {line}")
    ok = st["checked"] > 0 and st["diverged"] == 0
    print("RESULT:", "PASS -- the native A846 hit-flash decay matches the VM for every drawn record "
          "(enemies flash then clear, not stick white)" if ok else "FAIL")
    return 0 if ok else 1


def demo_name(demo):
    try:
        return Path(demo.snapshot_path()).parents[0].name
    except Exception:  # noqa: BLE001
        return "demo"


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
