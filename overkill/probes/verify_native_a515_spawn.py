"""Verify the native A515 linked-anchor spawn (``native_a515``) vs the VM.

1010:A515 is the A067 counter-driven link weapon: gated by DS:A960 != 0 && DS:A97E != 1 it allocates a
free gameplay slot with the raw 7547 finder (advancing DS:95DA), anchors it (A571, source + 0xA), then
runs the B15A link scan over the effect pool (advancing DS:A43A).  On a found target it PARTIALLY stamps
the slot (9 word overrides over its stale prior contents) and bumps A97E/A960; on a miss the slot stays
inactive.  Step-hook A515 on the oracle side, snapshot both pools + both cursors + the firing object
(SS:BP +2/+4) + the counters, run ``native_a515``, and at A515's return assert the whole activated slot
record + DS:95DA + DS:A43A + DS:A97E + DS:A960 all match.

Usage:
    python -m overkill.probes.verify_native_a515_spawn [demo_name] [max_frames]
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
from overkill.recovered.systems.objects import native_a515  # noqa: E402

CS = 0x1010
A515_ENTRY = 0xA515
CURSOR_95DA, CURSOR_A43A = 0x95DA, 0xA43A
GATE_A960, GATE_A97E = 0xA960, 0xA97E
SRC_X_BP, SRC_Y_BP = 0x02, 0x04
GAMEPLAY_BASE, GAMEPLAY_COUNT = 0x2B5C, 0x22
EFFECT_BASE, EFFECT_COUNT = 0x23B4, 0x23
STRIDE = 0x38
STRIDE_WORDS = STRIDE >> 1


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

    res = {"calls": 0, "ok": 0, "fail": [], "spawned": 0, "no_target": 0}
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
            if ip == A515_ENTRY and key not in pending:
                pred = native_a515(
                    _snapshot_pool(mem, ds, GAMEPLAY_BASE, GAMEPLAY_COUNT), mem.rw(ds, CURSOR_95DA),
                    _snapshot_pool(mem, ds, EFFECT_BASE, EFFECT_COUNT), mem.rw(ds, CURSOR_A43A),
                    mem.rw(ss, (bp + SRC_X_BP) & 0xFFFF), mem.rw(ss, (bp + SRC_Y_BP) & 0xFFFF),
                    mem.rw(ds, GATE_A960), mem.rw(ds, GATE_A97E))
                if pred is not None:
                    ret_addr = mem.rw(ss, self.s.sp & 0xFFFF)
                    pending[key] = (ret_addr, (self.s.sp + 2) & 0xFFFF, pred)
            else:
                p = pending.get(key)
                if p is not None and ip == p[0] and (self.s.sp & 0xFFFF) == p[1]:
                    _ret, _sp, pred = pending.pop(key)
                    mismatches: list = []
                    if pred.slot_offset is not None:
                        res["spawned"] += 1
                        for j, expected in enumerate(pred.slot_words):
                            got = mem.rw(ds, (pred.slot_offset + 2 * j) & 0xFFFF)
                            if got != expected:
                                mismatches.append((f"slot[{2 * j:#04x}]", got, expected))
                    else:
                        res["no_target"] += 1
                    for name, off, exp in (("95da", CURSOR_95DA, pred.cursor_95da),
                                           ("a43a", CURSOR_A43A, pred.cursor_a43a),
                                           ("a97e", GATE_A97E, pred.a97e), ("a960", GATE_A960, pred.a960)):
                        got = mem.rw(ds, off)
                        if got != exp:
                            mismatches.append((name, got, exp))
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

    print(f"demo {demo_name} ({max_frames} frames): native native_a515 link spawn vs VM: "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])} "
          f"(spawned={res['spawned']} no_target={res['no_target']})")
    for mism in res["fail"][:5]:
        print(f"  FAIL {mism}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native A515 link spawn byte-exact vs the VM across the demo"
          if ok else "CHECK -- no A515 dispatches reached, or a divergence")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
