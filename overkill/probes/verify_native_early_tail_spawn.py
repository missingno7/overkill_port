"""Verify the native A19F early-default fire tail (``native_a19f_tail``) vs the VM.

The A067 EARLY path (DS:2350 <= B6h, BDAC == 0, fire state DS:A958 != 2) reaches A19F, which spawns one
A4EA-seed shot at the A1AE-projected muzzle position (the A3A8 offset table indexed by the firing object's
+8 field, plus the firing object's {X,Y}).  Step-hook A19F on the oracle side, project the gameplay pool
(DS:2B5C) + cursor (DS:95DA) + the firing object (SS:BP +8/+2/+4), run ``native_a19f_tail``, and at A19F's
return assert the freshly spawned slot's fields + the cursor equal the prediction.

Usage:
    python -m overkill.probes.verify_native_early_tail_spawn [demo_name] [max_frames]
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
from overkill.gameplay.player_shot_spawn_gap import set_raise_on_encounter  # noqa: E402
from overkill.input_waits import pump_demo_frame  # noqa: E402
from overkill.recovered.domain.object_slots import ObjectPool  # noqa: E402
from overkill.recovered.systems.objects import native_a19f_tail  # noqa: E402
from overkill.recovered.views.object_slots import ObjectSlotView  # noqa: E402

CS = 0x1010
A19F_ENTRY = 0xA19F
CURSOR_95DA = 0x95DA
SRC_INDEX_BP, SRC_X_BP, SRC_Y_BP = 0x08, 0x02, 0x04   # the firing object's +8 / +2 / +4 (SS:BP)
GAMEPLAY_BASE, GAMEPLAY_COUNT, STRIDE = 0x2B5C, 0x22, 0x38
STRIDE_WORDS = STRIDE >> 1

_FIELDS = (
    "active_word", "scan_enable_or_solid", "direction_or_step", "sprite_or_state",
    "scan_flag", "hazard_class", "logic_id", "substate", "x_word", "y_word",
)


def main(argv) -> int:
    set_raise_on_encounter(False)
    demo_name = argv[0] if argv else "demo_play_tandy_L2_full_20260617_180221"
    max_frames = int(argv[1]) if len(argv) > 1 else 1200
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
            if ip == A19F_ENTRY and key not in pending:
                pool = ObjectPool(base=GAMEPLAY_BASE, stride=STRIDE, slots=tuple(
                    tuple(mem.rw(ds, (GAMEPLAY_BASE + i * STRIDE + 2 * j) & 0xFFFF)
                          for j in range(STRIDE_WORDS))
                    for i in range(GAMEPLAY_COUNT)))
                pred = native_a19f_tail(
                    pool, mem.rw(ds, CURSOR_95DA),
                    mem.rw(ss, (bp + SRC_INDEX_BP) & 0xFFFF),
                    mem.rw(ss, (bp + SRC_X_BP) & 0xFFFF), mem.rw(ss, (bp + SRC_Y_BP) & 0xFFFF),
                    lambda off, _m=mem, _d=ds: _m.rw(_d, off & 0xFFFF))
                if pred is not None:
                    ret_addr = mem.rw(ss, self.s.sp & 0xFFFF)
                    pending[key] = (ret_addr, (self.s.sp + 2) & 0xFFFF, pred)
            else:
                p = pending.get(key)
                if p is not None and ip == p[0] and (self.s.sp & 0xFFFF) == p[1]:
                    _ret, _sp, pred = pending.pop(key)
                    bx = self.s.bx & 0xFFFF
                    slot = ObjectSlotView(mem, ds, bx)
                    mismatches = [(f, getattr(slot, f), getattr(pred, f))
                                  for f in _FIELDS if getattr(slot, f) != getattr(pred, f)]
                    if bx != pred.slot_offset:
                        mismatches.append(("slot_offset", bx, pred.slot_offset))
                    if mem.rw(ds, CURSOR_95DA) != pred.new_cursor:
                        mismatches.append(("new_cursor", mem.rw(ds, CURSOR_95DA), pred.new_cursor))
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

    print(f"demo {demo_name} ({max_frames} frames): native native_a19f_tail vs VM A19F spawn: "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])}")
    for mism in res["fail"][:5]:
        print(f"  FAIL {mism}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native A19F early-tail shot byte-exact vs the VM across the demo"
          if ok else "CHECK -- no A19F dispatches reached, or a divergence")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
