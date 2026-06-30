"""Verify the native A41A single-slot player-shot spawn (``native_a41a_shot``) is byte-exact vs the VM.

A067 (the fire-button weapon fanout) walks the equipped weapon's shot schedules and dispatches each shot
through A41A's ``[A958]`` state table (``cs:0xA42C`` -> A4D7/A490/A499/A464/A438).  This gates the
single-slot states (0/1/2 -> A4D7/A490/A499): step-hook A41A's entry on the pure-VM (oracle) side, project
the gameplay pool (DS:2B5C) + allocator cursor (DS:95DA) + the schedule entry (SI) + state (A958) +
direction stamp (A3EC), run ``native_a41a_shot``, and at A41A's return address read the VM's freshly
spawned slot (BX) + cursor and assert they equal the native prediction, for every real single-slot shot.
Multi-slot states (3/4), state 5 (44AF), SI==FFFF, and a full pool are skipped (native returns None).

Usage:
    python -m overkill.probes.verify_native_player_shot_spawn [demo_name] [max_frames]
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
from overkill.recovered.domain.object_slots import ObjectPool  # noqa: E402
from overkill.recovered.systems.objects import native_a41a_shot  # noqa: E402
from overkill.recovered.views.object_slots import ObjectSlotView  # noqa: E402

CS = 0x1010
A41A_ENTRY = 0xA41A
A958_STATE = 0xA958
A3EC_DIR = 0xA3EC
ALLOC_CURSOR_95DA = 0x95DA
GAMEPLAY_BASE, GAMEPLAY_COUNT, STRIDE = 0x2B5C, 0x22, 0x38
STRIDE_WORDS = STRIDE >> 1
OFF_X, OFF_Y = 0x02, 0x04

_FIELDS = (
    "active_word", "scan_enable_or_solid", "direction_or_step", "sprite_or_state",
    "scan_flag", "hazard_class", "logic_id", "substate", "x_word", "y_word",
)


def main(argv) -> int:
    demo_name = argv[0] if argv else "demo_play_tandy_L2_full_20260617_180221"
    max_frames = int(argv[1]) if len(argv) > 1 else 1200
    demo = InputDemoPlayback.load(ROOT / "artifacts" / "demos" / demo_name)
    snapshot = demo.snapshot_path()
    video = str(demo.manifest.get("metadata", {}).get("video", "tandy"))

    res = {"calls": 0, "ok": 0, "skip": 0, "fail": []}
    pending: dict[int, tuple] = {}
    orig_step = CPU8086.step

    def step(self):
        if getattr(self, "_side", "") == "ref" and (self.s.cs & 0xFFFF) == CS:
            ip = self.s.ip & 0xFFFF
            mem = self.mem
            ds = self.s.ds & 0xFFFF
            ss = self.s.ss & 0xFFFF
            key = id(self)
            if ip == A41A_ENTRY and key not in pending:
                si = self.s.si & 0xFFFF
                if si != 0xFFFF:
                    pool = ObjectPool(base=GAMEPLAY_BASE, stride=STRIDE, slots=tuple(
                        tuple(mem.rw(ds, (GAMEPLAY_BASE + i * STRIDE + 2 * j) & 0xFFFF)
                              for j in range(STRIDE_WORDS))
                        for i in range(GAMEPLAY_COUNT)))
                    pred = native_a41a_shot(
                        pool, mem.rw(ds, ALLOC_CURSOR_95DA), mem.rw(ds, A958_STATE),
                        mem.rw(ds, (si + OFF_X) & 0xFFFF), mem.rw(ds, (si + OFF_Y) & 0xFFFF),
                        mem.rw(ds, A3EC_DIR),
                    )
                    if pred is not None:
                        ret_addr = mem.rw(ss, self.s.sp & 0xFFFF)
                        pending[key] = (ret_addr, (self.s.sp + 2) & 0xFFFF, pred)
            else:
                p = pending.get(key)
                if p is not None and ip == p[0] and (self.s.sp & 0xFFFF) == p[1]:
                    _ret, _sp, pred = pending.pop(key)
                    bx = self.s.bx & 0xFFFF
                    slot = ObjectSlotView(mem, ds, bx)
                    cursor = mem.rw(ds, ALLOC_CURSOR_95DA)
                    mismatches = [(f, getattr(slot, f), getattr(pred, f))
                                  for f in _FIELDS if getattr(slot, f) != getattr(pred, f)]
                    if bx != pred.slot_offset:
                        mismatches.append(("slot_offset", bx, pred.slot_offset))
                    if cursor != pred.new_cursor:
                        mismatches.append(("new_cursor", cursor, pred.new_cursor))
                    res["calls"] += 1
                    if not mismatches:
                        res["ok"] += 1
                    else:
                        res["fail"].append(mismatches)
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

    print(f"demo {demo_name} ({max_frames} frames): native native_a41a_shot vs VM A41A single-slot spawn: "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])}")
    for mismatches in res["fail"][:5]:
        print(f"  FAIL {mismatches}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native A41A single-slot shot spawn byte-exact vs the VM across the demo"
          if ok else "CHECK -- no single-slot shots reached, or a divergence")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
