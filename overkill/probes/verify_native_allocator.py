"""Verify the native object-slot allocator (object_pool_find_free) is byte-exact vs the VM's
1010:7573 across a gameplay demo -- the §1.2 produced-vs-VM gate for the object pool (the core
game state).

Step-hook 7573 on the pure-VM (oracle) side; at entry snapshot the gameplay object pool
(``read_object_pool``) plus the allocator cursor (DS:95DA) and predict the allocation natively via
``object_pool_find_free``; at the routine's return read the VM's result (BX = the allocated slot
offset, or FFFF when full) and the updated cursor (DS:95DA), and assert they match -- for every
real in-game allocation.

An all-match run means the native allocator reproduces the VM byte-exact on the real allocation
sequence the game generates (the synthetic equivalence test is
``test_object_pool_find_free_matches_vm_allocator``; this is the demo-level confirmation).

Usage:
    python -m overkill.probes.verify_native_allocator [demo_name] [max_frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import overkill.frame_verify as fv  # noqa: E402
from dos_re.cpu import CPU8086  # noqa: E402
from dos_re.input_demo import InputDemoPlayback  # noqa: E402
from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier  # noqa: E402
from overkill.input_waits import pump_demo_frame  # noqa: E402
from overkill.recovered.systems.objects import object_pool_find_free  # noqa: E402
from overkill.recovered.views.object_slots import (  # noqa: E402
    GAMEPLAY_OBJECT_TABLE_BASE,
    GAMEPLAY_OBJECT_TABLE_COUNT,
    read_object_pool,
)

CS = 0x1010
ALLOC_IP = 0x7573
ALLOC_END = 0x75A0  # the straight-line 7573 allocator body (no sub-calls); return leaves this range
CURSOR_OFF = 0x95DA


def main(argv) -> int:
    demo_name = argv[0] if argv else "demo_play_tandy_L2_full_20260617_180221"
    max_frames = int(argv[1]) if len(argv) > 1 else 1200
    demo = InputDemoPlayback.load(ROOT / "artifacts" / "demos" / demo_name)
    snapshot = demo.snapshot_path()
    video = str(demo.manifest.get("metadata", {}).get("video", "tandy"))

    res = {"calls": 0, "ok": 0, "fail": []}
    pending: dict[int, tuple[int, int]] = {}
    orig_step = CPU8086.step

    def step(self):
        if getattr(self, "_side", "") == "ref":
            cs = self.s.cs & 0xFFFF
            ip = self.s.ip & 0xFFFF
            key = id(self)
            if cs == CS and ip == ALLOC_IP and key not in pending:
                ds = self.s.ds & 0xFFFF
                cursor = self.mem.rw(ds, CURSOR_OFF)
                pool = read_object_pool(self.mem, ds, GAMEPLAY_OBJECT_TABLE_BASE, GAMEPLAY_OBJECT_TABLE_COUNT)
                alloc = object_pool_find_free(pool, cursor)
                pred_offset = alloc.offset if alloc.offset is not None else 0xFFFF
                pending[key] = (pred_offset, alloc.cursor)
            elif key in pending and not (cs == CS and ALLOC_IP <= ip <= ALLOC_END):
                pred_offset, pred_cursor = pending.pop(key)
                ds = self.s.ds & 0xFFFF
                actual = (self.s.bx & 0xFFFF, self.mem.rw(ds, CURSOR_OFF))
                res["calls"] += 1
                if actual == (pred_offset, pred_cursor):
                    res["ok"] += 1
                else:
                    res["fail"].append(((pred_offset, pred_cursor), actual))
        return orig_step(self)

    CPU8086.step = step
    orig_load = fv._load_runtime
    sides = iter(("ref", "cand"))

    def patched_load(exe, assets, snap, tail):
        rt = orig_load(exe, assets, snap, tail)
        rt.cpu._side = next(sides)
        return rt

    fv._load_runtime = patched_load
    boundary = {"n": 0}

    def pump_inputs(ref_rt, cand_rt):
        boundary["n"], _ = pump_demo_frame(demo, boundary["n"], (ref_rt, cand_rt), ref_rt.cpu)
        boundary["n"] += 1

    cfg = FrameVerifyConfig(video=video, source="candidate", max_frames=max_frames,
                            semantic_state_check=False, stop_on_diff=False, log_every=0)
    try:
        run_frame_verifier(exe=ROOT / "assets" / "OVERKILL", assets=ROOT / "assets",
                           snapshot=str(snapshot), command_tail=b"", config=cfg, pump_inputs=pump_inputs)
    finally:
        fv._load_runtime = orig_load
        CPU8086.step = orig_step

    print(f"demo {demo_name} ({max_frames} frames): native object_pool_find_free vs VM 7573: "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])}")
    for predicted, actual in res["fail"][:10]:
        print(f"  FAIL predicted={predicted} actual={actual}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native allocator byte-exact vs the VM across the demo"
          if ok else "CHECK -- no allocations reached, or a divergence")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
