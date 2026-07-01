"""Verify the native A0E8 early-level muzzle pair tails (``native_a0e8_pair``) vs the VM.

A2F6 (A958==4) and A337 (A958==3) are the early-scroll counterparts of the A41A 3/4 pair: gated by
DS:A3A0 == 0 they spawn two A4EA-seed slots at the A1AE-projected muzzle, each stamped with the state's
logic_id (+18) / sprite (+08), the second slot's X = the first's + 8.  Step-hook A2F6/A337 on the oracle
side, project the gameplay pool (DS:2B5C) + cursor (DS:95DA) + the firing object (SS:BP +8/+2/+4) +
the gate (DS:A3A0), run ``native_a0e8_pair`` for that state, and at the return assert both spawned slots'
fields + the final cursor equal the prediction.

Usage:
    python -m overkill.probes.verify_native_a0e8_pair_spawn [demo_name] [max_frames]
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
from overkill.recovered.systems.objects import native_a0e8_pair  # noqa: E402
from overkill.recovered.views.object_slots import ObjectSlotView  # noqa: E402

CS = 0x1010
ENTRY_TO_STATE = {0xA2F6: 0x0004, 0xA337: 0x0003}   # A2F6 = A958 4, A337 = A958 3
CURSOR_95DA = 0x95DA
GATE_A3A0 = 0xA3A0
SRC_INDEX_BP, SRC_X_BP, SRC_Y_BP = 0x08, 0x02, 0x04   # the firing object's +8 / +2 / +4 (SS:BP)
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

    res = {"calls": 0, "ok": 0, "fail": [], "a2f6": 0, "a337": 0}
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
            if ip in ENTRY_TO_STATE and key not in pending:
                pool = ObjectPool(base=GAMEPLAY_BASE, stride=STRIDE, slots=tuple(
                    tuple(mem.rw(ds, (GAMEPLAY_BASE + i * STRIDE + 2 * j) & 0xFFFF)
                          for j in range(STRIDE_WORDS))
                    for i in range(GAMEPLAY_COUNT)))
                pred = native_a0e8_pair(
                    pool, mem.rw(ds, CURSOR_95DA), ENTRY_TO_STATE[ip],
                    mem.rw(ss, (bp + SRC_INDEX_BP) & 0xFFFF),
                    mem.rw(ss, (bp + SRC_X_BP) & 0xFFFF), mem.rw(ss, (bp + SRC_Y_BP) & 0xFFFF),
                    mem.rw(ds, GATE_A3A0), lambda off, _m=mem, _d=ds: _m.rw(_d, off & 0xFFFF))
                if pred is not None:
                    ret_addr = mem.rw(ss, self.s.sp & 0xFFFF)
                    pending[key] = (ret_addr, (self.s.sp + 2) & 0xFFFF, pred, ip)
            else:
                p = pending.get(key)
                if p is not None and ip == p[0] and (self.s.sp & 0xFFFF) == p[1]:
                    _ret, _sp, pred, entry_ip = pending.pop(key)
                    res["a2f6" if entry_ip == 0xA2F6 else "a337"] += 1
                    mismatches: list = []
                    for shot in pred:
                        slot = ObjectSlotView(mem, ds, shot.slot_offset & 0xFFFF)
                        mismatches += [(f, getattr(slot, f), getattr(shot, f))
                                       for f in _FIELDS if getattr(slot, f) != getattr(shot, f)]
                    bx = self.s.bx & 0xFFFF   # BX is the VM's LAST A4EA slot
                    cursor = mem.rw(ds, CURSOR_95DA)
                    # Normally BX is the last find_free slot -- where DS:95DA parks and which native predicts
                    # (pred[-1]).  On a full pool the last A4EA RECYCLES (7550, unmodelled) into a slot that
                    # does NOT move the cursor (bx != cursor); native returns only the committed find_free
                    # shots (a partial) and does not predict that recycle slot, so cross-check BX against
                    # pred[-1] only when no recycle happened.  The authoritative DS:95DA check always applies.
                    if bx == cursor and bx != pred[-1].slot_offset:
                        mismatches.append(("slot_offset", bx, pred[-1].slot_offset))
                    if cursor != pred[-1].new_cursor:
                        mismatches.append(("new_cursor", cursor, pred[-1].new_cursor))
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

    print(f"demo {demo_name} ({max_frames} frames): native native_a0e8_pair (A2F6/A337) vs VM: "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])} "
          f"(A2F6={res['a2f6']} A337={res['a337']})")
    for mism in res["fail"][:5]:
        print(f"  FAIL {mism}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native A2F6/A337 early-level pair byte-exact vs the VM across the demo"
          if ok else "CHECK -- no A2F6/A337 dispatches reached, or a divergence")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
