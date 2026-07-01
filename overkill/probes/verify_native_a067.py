"""Verify the composed A067 entry gate + EARLY spawn dispatch (``native_a067``) vs the VM.

This is the whole-A067 first layer coming together: instead of hooking an individual child, step-hook A067
itself, project every input the entry decision reads (the gameplay pool DS:2B5C + cursor DS:95DA, the gate
words DS:98BE/A980/9790/232A, the path words DS:2350/BDAC/A958/BE06, and the firing object SS:BP +8/+2/+4),
run ``native_a067``, and at A067's return assert the whole outcome -- DS:A980's write-back, every spawned
slot, and the final DS:95DA cursor.  ``native_a067`` returns None for the FULL fan-out (not composed yet)
and full-pool frames, which the probe skips (they stay VM-owned); the gate-only (not firing / held) and
EARLY (A1C8 / A19F) frames are verified end-to-end.

Usage:
    python -m overkill.probes.verify_native_a067 [demo_name] [max_frames]
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
from overkill.recovered.systems.action_spawns import native_a067  # noqa: E402
from overkill.recovered.views.object_slots import ObjectSlotView  # noqa: E402

CS = 0x1010
A067_ENTRY = 0xA067
CURSOR_95DA, LATCH_A980 = 0x95DA, 0xA980
INPUT_98BE, REPEAT_9790, STATE_232A = 0x98BE, 0x9790, 0x232A
SCROLL_2350, BDAC, FIRE_STATE_A958, BE06 = 0x2350, 0xBDAC, 0xA958, 0xBE06
SRC_INDEX_BP, SRC_X_BP, SRC_Y_BP = 0x08, 0x02, 0x04
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

    res = {"calls": 0, "ok": 0, "fail": [], "gate_only": 0, "spawned": 0}
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
            if ip == A067_ENTRY and key not in pending:
                pool = ObjectPool(base=GAMEPLAY_BASE, stride=STRIDE, slots=tuple(
                    tuple(mem.rw(ds, (GAMEPLAY_BASE + i * STRIDE + 2 * j) & 0xFFFF)
                          for j in range(STRIDE_WORDS))
                    for i in range(GAMEPLAY_COUNT)))
                pred = native_a067(
                    pool, mem.rw(ds, CURSOR_95DA),
                    input_98be=mem.rb(ds, INPUT_98BE), latch_a980=mem.rw(ds, LATCH_A980),
                    repeat_9790=mem.rb(ds, REPEAT_9790), state_232a=mem.rw(ds, STATE_232A),
                    scroll_2350=mem.rw(ds, SCROLL_2350), bdac=mem.rw(ds, BDAC),
                    a958=mem.rw(ds, FIRE_STATE_A958), be06=mem.rw(ds, BE06),
                    source_index=mem.rw(ss, (bp + SRC_INDEX_BP) & 0xFFFF),
                    source_x=mem.rw(ss, (bp + SRC_X_BP) & 0xFFFF),
                    source_y=mem.rw(ss, (bp + SRC_Y_BP) & 0xFFFF),
                    read_ds_word=lambda off, _m=mem, _d=ds: _m.rw(_d, off & 0xFFFF))
                if pred is not None:
                    ret_addr = mem.rw(ss, self.s.sp & 0xFFFF)
                    pending[key] = (ret_addr, (self.s.sp + 2) & 0xFFFF, pred)
            else:
                p = pending.get(key)
                if p is not None and ip == p[0] and (self.s.sp & 0xFFFF) == p[1]:
                    _ret, _sp, pred = pending.pop(key)
                    mismatches: list = []
                    if mem.rw(ds, LATCH_A980) != pred.new_a980:
                        mismatches.append(("a980", mem.rw(ds, LATCH_A980), pred.new_a980))
                    for shot in pred.spawns:
                        slot = ObjectSlotView(mem, ds, shot.slot_offset & 0xFFFF)
                        mismatches += [(f, getattr(slot, f), getattr(shot, f))
                                       for f in _FIELDS if getattr(slot, f) != getattr(shot, f)]
                    if mem.rw(ds, CURSOR_95DA) != pred.final_cursor:
                        mismatches.append(("cursor", mem.rw(ds, CURSOR_95DA), pred.final_cursor))
                    res["calls"] += 1
                    res["spawned" if pred.ran_fanout else "gate_only"] += 1
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

    print(f"demo {demo_name} ({max_frames} frames): native native_a067 (gate + EARLY) vs VM: "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])} "
          f"(gate_only={res['gate_only']} spawned={res['spawned']})")
    for mism in res["fail"][:5]:
        print(f"  FAIL {mism}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native A067 gate+EARLY decision byte-exact vs the VM across the demo"
          if ok else "CHECK -- no A067 entries reached, or a divergence")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
