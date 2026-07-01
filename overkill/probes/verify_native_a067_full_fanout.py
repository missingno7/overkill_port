"""Verify the whole A067 FULL fan-out capstone (``native_a067_full_fanout``) vs the VM.

The FULL_FANOUT path runs the counter copy + A515 -> A584 -> A3FF -> A3CA -> A0E8 in sequence.  Step-hook
A067 on the oracle side; when the entry gate fires and the path is FULL_FANOUT, project every input the
sequence reads -- the gameplay pool (DS:2B5C) + the effect pool (DS:23B4, for A515's B15A scan), the two
allocator cursors (DS:95DA / DS:A43A), the held-action counters (DS:A970/A972/A976/A974), the A515/A584
gates (DS:A95E/A960/A97E), the dispatch words (DS:A958/A96E/98BE), the firing object (SS:BP +8/+2/+4), and
the mirror/side schedules (DS:A962/A964 and DS:A966/A968/A96A/A96C) -- run ``native_a067_full_fanout``, and
at A067's return assert every spawned slot + the final cursor + the copied counters (A3A0..A3A6) + the
A515 link-scan state (A43A/A960/A97E) all equal the prediction.  a958 >= 5 (the dead tail) is skipped.

Usage:
    python -m overkill.probes.verify_native_a067_full_fanout [demo_name] [max_frames]
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
from overkill.recovered.systems.action_spawns import (  # noqa: E402
    A067FirePath,
    a067_fire_path,
    action_fanout_gate,
)
from overkill.recovered.systems.objects import native_a067_full_fanout  # noqa: E402
from overkill.recovered.views.object_slots import ObjectSlotView  # noqa: E402

CS = 0x1010
A067_ENTRY = 0xA067
CURSOR_95DA, CURSOR_A43A = 0x95DA, 0xA43A
LATCH_A980, INPUT_98BE, REPEAT_9790, STATE_232A = 0xA980, 0x98BE, 0x9790, 0x232A
SCROLL_2350, BDAC, FIRE_STATE_A958, BE06, SCHED_A96E = 0x2350, 0xBDAC, 0xA958, 0xBE06, 0xA96E
A970, A972, A976, A974, A95E, A960, A97E = 0xA970, 0xA972, 0xA976, 0xA974, 0xA95E, 0xA960, 0xA97E
MIRROR_SCHED = (0xA962, 0xA964)
SIDE_SCHED = (0xA966, 0xA968, 0xA96A, 0xA96C)
SRC_INDEX_BP, SRC_X_BP, SRC_Y_BP = 0x08, 0x02, 0x04
GAMEPLAY_BASE, GAMEPLAY_COUNT = 0x2B5C, 0x22
EFFECT_BASE, EFFECT_COUNT = 0x23B4, 0x23
STRIDE = 0x38
STRIDE_WORDS = STRIDE >> 1

_FIELDS = (
    "active_word", "scan_enable_or_solid", "direction_or_step", "sprite_or_state",
    "scan_flag", "hazard_class", "logic_id", "substate", "x_word", "y_word",
)


def _snapshot_pool(mem, ds, base, count):
    return ObjectPool(base=base, stride=STRIDE, slots=tuple(
        tuple(mem.rw(ds, (base + i * STRIDE + 2 * j) & 0xFFFF) for j in range(STRIDE_WORDS))
        for i in range(count)))


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
            if ip == A067_ENTRY and key not in pending:
                gate = action_fanout_gate(mem.rb(ds, INPUT_98BE), mem.rw(ds, LATCH_A980),
                                          mem.rb(ds, REPEAT_9790), mem.rw(ds, STATE_232A))
                if not gate.runs:
                    return orig_step(self)
                path = a067_fire_path(mem.rw(ds, SCROLL_2350), mem.rw(ds, BDAC),
                                      mem.rw(ds, FIRE_STATE_A958), mem.rw(ds, BE06))
                if path is not A067FirePath.FULL_FANOUT:
                    return orig_step(self)

                def read_ds_word(off, _m=mem, _d=ds):
                    return _m.rw(_d, off & 0xFFFF)
                pred = native_a067_full_fanout(
                    _snapshot_pool(mem, ds, GAMEPLAY_BASE, GAMEPLAY_COUNT),
                    _snapshot_pool(mem, ds, EFFECT_BASE, EFFECT_COUNT),
                    mem.rw(ds, CURSOR_95DA), mem.rw(ds, CURSOR_A43A),
                    a970=mem.rw(ds, A970), a972=mem.rw(ds, A972), a976=mem.rw(ds, A976),
                    a974=mem.rw(ds, A974), a95e=mem.rw(ds, A95E), a960=mem.rw(ds, A960),
                    a97e=mem.rw(ds, A97E), a958=mem.rw(ds, FIRE_STATE_A958), a96e=mem.rw(ds, SCHED_A96E),
                    input_98be=mem.rb(ds, INPUT_98BE),
                    source_index=mem.rw(ss, (bp + SRC_INDEX_BP) & 0xFFFF),
                    source_x=mem.rw(ss, (bp + SRC_X_BP) & 0xFFFF),
                    source_y=mem.rw(ss, (bp + SRC_Y_BP) & 0xFFFF),
                    mirror_schedule=tuple(mem.rw(ds, a) for a in MIRROR_SCHED),
                    side_schedule=tuple(mem.rw(ds, a) for a in SIDE_SCHED),
                    read_ds_word=read_ds_word)
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
                    for name, off, want in (("cursor", CURSOR_95DA, pred.final_cursor),
                                            ("a3a0", 0xA3A0, pred.a3a0), ("a3a2", 0xA3A2, pred.a3a2),
                                            ("a3a4", 0xA3A4, pred.a3a4), ("a3a6", 0xA3A6, pred.a3a6),
                                            ("a43a", CURSOR_A43A, pred.cursor_a43a),
                                            ("a960", A960, pred.a960), ("a97e", A97E, pred.a97e)):
                        if mem.rw(ds, off) != want:
                            mismatches.append((name, mem.rw(ds, off), want))
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

    print(f"demo {demo_name} ({max_frames} frames): native native_a067_full_fanout vs VM: "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])}")
    for mism in res["fail"][:5]:
        print(f"  FAIL {mism}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native A067 FULL fan-out byte-exact vs the VM across the demo"
          if ok else "CHECK -- no FULL_FANOUT A067 frames reached, or a divergence")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
