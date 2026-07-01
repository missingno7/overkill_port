"""Verify the native A067 EARLY fire tails (``native_a19f_tail`` / ``native_a1c8_tail``) vs the VM.

The A067 EARLY path (DS:2350 <= B6h, BDAC == 0) reaches one of two tails by the fire state DS:A958:
A19F (A958 != 2) spawns ONE A4EA-seed shot; A1C8 (A958 == 2) spawns TWO (slot1 sprite 18h; slot2's
direction/sprite picked from the input DS:98BE -- bit1 -> 7/1Fh, elif bit0 -> 1/19h, else 0/18h).  Both
place each shot at the A1AE-projected muzzle (the A3A8 offset table indexed by the firing object's +8
field, plus the firing object's {X,Y}).  Step-hook the tail on the oracle side, project the gameplay pool
(DS:2B5C) + cursor (DS:95DA) + the firing object (SS:BP +8/+2/+4) + the input (DS:98BE), run the native
tail, and at the return assert every freshly spawned slot's fields + the final cursor equal the prediction.

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
from overkill.input_waits import pump_demo_frame  # noqa: E402
from overkill.recovered.domain.object_slots import ObjectPool  # noqa: E402
from overkill.recovered.systems.objects import (  # noqa: E402
    native_a18a,
    native_a19f_tail,
    native_a1c8_tail,
)
from overkill.recovered.views.object_slots import ObjectSlotView  # noqa: E402

CS = 0x1010
A19F_ENTRY, A1C8_ENTRY, A18A_ENTRY = 0xA19F, 0xA1C8, 0xA18A
CURSOR_95DA = 0x95DA
INPUT_98BE = 0x98BE
SRC_INDEX_BP, SRC_X_BP, SRC_Y_BP = 0x08, 0x02, 0x04   # the firing object's +8 / +2 / +4 (SS:BP)
GAMEPLAY_BASE, GAMEPLAY_COUNT, STRIDE = 0x2B5C, 0x22, 0x38
STRIDE_WORDS = STRIDE >> 1

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

    res = {"calls": 0, "ok": 0, "fail": [], "a19f": 0, "a1c8": 0, "a18a": 0}
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
            if ip in (A19F_ENTRY, A1C8_ENTRY, A18A_ENTRY) and key not in pending:
                pool = ObjectPool(base=GAMEPLAY_BASE, stride=STRIDE, slots=tuple(
                    tuple(mem.rw(ds, (GAMEPLAY_BASE + i * STRIDE + 2 * j) & 0xFFFF)
                          for j in range(STRIDE_WORDS))
                    for i in range(GAMEPLAY_COUNT)))
                cursor = mem.rw(ds, CURSOR_95DA)
                idx = mem.rw(ss, (bp + SRC_INDEX_BP) & 0xFFFF)
                src_x = mem.rw(ss, (bp + SRC_X_BP) & 0xFFFF)
                src_y = mem.rw(ss, (bp + SRC_Y_BP) & 0xFFFF)

                def read_ds_word(off, _m=mem, _d=ds):
                    return _m.rw(_d, off & 0xFFFF)
                if ip == A19F_ENTRY:
                    pred = native_a19f_tail(pool, cursor, idx, src_x, src_y, read_ds_word)
                elif ip == A18A_ENTRY:
                    pred = native_a18a(pool, cursor, idx, src_x, src_y, read_ds_word)
                else:
                    pred = native_a1c8_tail(pool, cursor, idx, src_x, src_y, mem.rb(ds, INPUT_98BE), read_ds_word)
                if pred is not None:
                    ret_addr = mem.rw(ss, self.s.sp & 0xFFFF)
                    pending[key] = (ret_addr, (self.s.sp + 2) & 0xFFFF, pred, ip)
            else:
                p = pending.get(key)
                if p is not None and ip == p[0] and (self.s.sp & 0xFFFF) == p[1]:
                    _ret, _sp, pred, entry_ip = pending.pop(key)
                    res[{A1C8_ENTRY: "a1c8", A18A_ENTRY: "a18a"}.get(entry_ip, "a19f")] += 1
                    shots = pred if isinstance(pred, tuple) else (pred,)
                    mismatches: list = []
                    for shot in shots:
                        slot = ObjectSlotView(mem, ds, shot.slot_offset & 0xFFFF)
                        mismatches += [(f, getattr(slot, f), getattr(shot, f))
                                       for f in _FIELDS if getattr(slot, f) != getattr(shot, f)]
                    bx = self.s.bx & 0xFFFF   # BX is the VM's LAST A4EA slot
                    cursor = mem.rw(ds, CURSOR_95DA)
                    # Normally BX is the last find_free slot -- where DS:95DA parks and which native predicts
                    # (shots[-1]).  On a full pool the last A4EA RECYCLES (7550, unmodelled) into a slot that
                    # does NOT move the cursor (bx != cursor); native returns only the committed find_free
                    # shots (a partial, e.g. the A1C8 pair's first shot) and does not predict that recycle
                    # slot, so cross-check BX only when no recycle happened.  DS:95DA is the authoritative check.
                    if bx == cursor and bx != shots[-1].slot_offset:
                        mismatches.append(("slot_offset", bx, shots[-1].slot_offset))
                    if cursor != shots[-1].new_cursor:
                        mismatches.append(("new_cursor", cursor, shots[-1].new_cursor))
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

    print(f"demo {demo_name} ({max_frames} frames): native A19F/A1C8/A18A tails vs VM: "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])} "
          f"(A19F={res['a19f']} A1C8={res['a1c8']} A18A={res['a18a']})")
    for mism in res["fail"][:5]:
        print(f"  FAIL {mism}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native A19F/A1C8/A18A tail shots byte-exact vs the VM across the demo"
          if ok else "CHECK -- no tail dispatches reached, or a divergence")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
