"""Verify the native A0E8 subroutine (``native_a0e8_subroutine``) vs the VM.

A0E8 is the A067 FULL fan-out's early-table dispatch: it runs the A114 pre-call (when DS:A96E != FFFFh)
then jumps to the A958 tail (0->A19F, 1->A18A, 2->A1C8, 3->A337, 4->A2F6).  Step-hook A0E8 (1010:A0E8) on
the oracle side, project the gameplay pool (DS:2B5C) + cursor (DS:95DA) + the dispatch words
(DS:A958/A96E/A3A6/A3A0) + the firing object (SS:BP +8/+2/+4) + the input (DS:98BE), run
``native_a0e8_subroutine``, and at A0E8's return (A0E7) assert every combined spawned slot + the final
cursor equal the prediction.  a958 >= 5 (the A2A0 pre-call / dead 44AF/3E83 tails) returns None and is
skipped (VM-owned).

Usage:
    python -m overkill.probes.verify_native_a0e8_subroutine [demo_name] [max_frames]
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
from overkill.recovered.systems.objects import native_a0e8_subroutine  # noqa: E402
from overkill.recovered.views.object_slots import ObjectSlotView  # noqa: E402

CS = 0x1010
A0E8_ENTRY = 0xA0E8
CURSOR_95DA = 0x95DA
FIRE_STATE_A958, SCHEDULE_A96E, GATE_A3A6, GATE_A3A0 = 0xA958, 0xA96E, 0xA3A6, 0xA3A0
INPUT_98BE = 0x98BE
SRC_INDEX_BP, SRC_X_BP, SRC_Y_BP = 0x08, 0x02, 0x04
GAMEPLAY_BASE, GAMEPLAY_COUNT, STRIDE = 0x2B5C, 0x22, 0x38
STRIDE_WORDS = STRIDE >> 1

_FIELDS = (
    "active_word", "scan_enable_or_solid", "direction_or_step", "sprite_or_state",
    "scan_flag", "hazard_class", "logic_id", "substate", "x_word", "y_word",
)


def main(argv) -> int:
    demo_name = argv[0] if argv else "demo_play_tandy_L6_different_weapons_20260618_225615"
    max_frames = int(argv[1]) if len(argv) > 1 else 1500
    demo = InputDemoPlayback.load(ROOT / "artifacts" / "demos" / demo_name)
    snapshot = demo.snapshot_path()
    video = str(demo.manifest.get("metadata", {}).get("video", "tandy"))

    res = {"calls": 0, "ok": 0, "fail": []}
    pending: dict[int, tuple] = {}
    orig_step = CPU8086.step

    def step(self):
        if getattr(self, "_side", "") == "ref" and (self.s.cs & 0xFFFF) == CS:
            ip = self.s.ip & 0xFFFF
            mem = self.mem
            ds = self.s.ds & 0xFFFF
            ss = self.s.ss & 0xFFFF
            bp = self.s.bp & 0xFFFF
            key = id(self)
            if ip == A0E8_ENTRY and key not in pending:
                pool = ObjectPool(base=GAMEPLAY_BASE, stride=STRIDE, slots=tuple(
                    tuple(mem.rw(ds, (GAMEPLAY_BASE + i * STRIDE + 2 * j) & 0xFFFF)
                          for j in range(STRIDE_WORDS))
                    for i in range(GAMEPLAY_COUNT)))
                pred = native_a0e8_subroutine(
                    pool, mem.rw(ds, CURSOR_95DA),
                    a958=mem.rw(ds, FIRE_STATE_A958), a96e=mem.rw(ds, SCHEDULE_A96E),
                    a3a6=mem.rw(ds, GATE_A3A6), a3a0=mem.rw(ds, GATE_A3A0),
                    source_index=mem.rw(ss, (bp + SRC_INDEX_BP) & 0xFFFF),
                    source_x=mem.rw(ss, (bp + SRC_X_BP) & 0xFFFF),
                    source_y=mem.rw(ss, (bp + SRC_Y_BP) & 0xFFFF),
                    input_98be=mem.rb(ds, INPUT_98BE),
                    read_ds_word=lambda off, _m=mem, _d=ds: _m.rw(_d, off & 0xFFFF))
                if pred is not None:
                    ret_addr = mem.rw(ss, self.s.sp & 0xFFFF)
                    pending[key] = (ret_addr, (self.s.sp + 2) & 0xFFFF, pred)
            else:
                p = pending.get(key)
                if p is not None and ip == p[0] and (self.s.sp & 0xFFFF) == p[1]:
                    _ret, _sp, pred = pending.pop(key)
                    # Verify the authoritative spawn state: every spawned slot's fields + the allocator
                    # cursor (DS:95DA).  BX at A0E7 is a dead scratch register (A067 rets straight after the
                    # A0E8 call, discarding it) and the a958 tail is reached by JMP, so unlike the single-
                    # child probes it is not a reliable "last slot" witness -- the cursor is.
                    mismatches: list = []
                    for shot in pred.spawns:
                        slot = ObjectSlotView(mem, ds, shot.slot_offset & 0xFFFF)
                        mismatches += [(f, getattr(slot, f), getattr(shot, f))
                                       for f in _FIELDS if getattr(slot, f) != getattr(shot, f)]
                    if mem.rw(ds, CURSOR_95DA) != pred.final_cursor:
                        mismatches.append(("cursor", mem.rw(ds, CURSOR_95DA), pred.final_cursor))
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

    print(f"demo {demo_name} ({max_frames} frames): native native_a0e8_subroutine vs VM: "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])}")
    for mism in res["fail"][:5]:
        print(f"  FAIL {mism}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native A0E8 subroutine byte-exact vs the VM across the demo"
          if ok else "CHECK -- no A0E8 dispatches reached, or a divergence")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
