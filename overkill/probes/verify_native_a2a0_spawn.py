"""Verify the native A2A0 listed two-slot spawn (``native_a2a0``) vs the VM.

A2A0 is the A067 A958==5 fanout child: gated by DS:A3A2 == 0 it clears the 26-word anchor list (DS:A3B4)
to FFFFh, resets the list pointer (DS:A3EA), then runs the A2D6 body twice -- two A4EA-seed logic-9 slots
at the A1AE muzzle (Y snapped to (y&~7)+8, sprite 6Ch), each appending its DS offset to the list; slot 1 is
post-stamped to sprite 6Ah / Y-=8.  Step-hook A2A0 on the oracle side, project the gameplay pool (DS:2B5C)
+ cursor (DS:95DA) + the firing object (SS:BP +8/+2/+4) + the gate (DS:A3A2), run ``native_a2a0``, and at
A2A0's return assert both spawned slots' fields + the whole 26-word list + the advanced DS:A3EA + the final
cursor equal the prediction.

Usage:
    python -m overkill.probes.verify_native_a2a0_spawn [demo_name] [max_frames]
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
from overkill.recovered.systems.objects import native_a2a0  # noqa: E402
from overkill.recovered.views.object_slots import ObjectSlotView  # noqa: E402

CS = 0x1010
A2A0_ENTRY = 0xA2A0
CURSOR_95DA = 0x95DA
GATE_A3A2 = 0xA3A2
LIST_BASE, LIST_PTR, LIST_LEN = 0xA3B4, 0xA3EA, 26   # the DS anchor list + its pointer (adapter knowledge)
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
            if ip == A2A0_ENTRY and key not in pending:
                pool = ObjectPool(base=GAMEPLAY_BASE, stride=STRIDE, slots=tuple(
                    tuple(mem.rw(ds, (GAMEPLAY_BASE + i * STRIDE + 2 * j) & 0xFFFF)
                          for j in range(STRIDE_WORDS))
                    for i in range(GAMEPLAY_COUNT)))
                pred = native_a2a0(
                    pool, mem.rw(ds, CURSOR_95DA),
                    mem.rw(ss, (bp + SRC_INDEX_BP) & 0xFFFF),
                    mem.rw(ss, (bp + SRC_X_BP) & 0xFFFF), mem.rw(ss, (bp + SRC_Y_BP) & 0xFFFF),
                    mem.rw(ds, GATE_A3A2), lambda off, _m=mem, _d=ds: _m.rw(_d, off & 0xFFFF))
                if pred is not None:
                    ret_addr = mem.rw(ss, self.s.sp & 0xFFFF)
                    pending[key] = (ret_addr, (self.s.sp + 2) & 0xFFFF, pred)
            else:
                p = pending.get(key)
                if p is not None and ip == p[0] and (self.s.sp & 0xFFFF) == p[1]:
                    _ret, _sp, pred = pending.pop(key)
                    mismatches: list = []
                    for shot in pred.spawns:
                        slot = ObjectSlotView(mem, ds, shot.slot_offset & 0xFFFF)
                        mismatches += [(f, getattr(slot, f), getattr(shot, f))
                                       for f in _FIELDS if getattr(slot, f) != getattr(shot, f)]
                    vm_list = tuple(mem.rw(ds, (LIST_BASE + 2 * k) & 0xFFFF) for k in range(LIST_LEN))
                    if vm_list != pred.list_words:
                        first = next(k for k in range(LIST_LEN) if vm_list[k] != pred.list_words[k])
                        mismatches.append(("list", (first, vm_list[first]), pred.list_words[first]))
                    a3ea = mem.rw(ds, LIST_PTR)
                    if a3ea != ((LIST_BASE + pred.list_advance) & 0xFFFF):
                        mismatches.append(("a3ea", a3ea, (LIST_BASE + pred.list_advance) & 0xFFFF))
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

    print(f"demo {demo_name} ({max_frames} frames): native native_a2a0 listed spawn vs VM: "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])}")
    for mism in res["fail"][:5]:
        print(f"  FAIL {mism}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native A2A0 listed spawn byte-exact vs the VM across the demo"
          if ok else "CHECK -- no A2A0 dispatches reached, or a divergence")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
