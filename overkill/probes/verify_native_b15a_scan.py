"""Verify the native B15A rotating target-candidate scan (``native_b15a_scan``) vs the VM.

1010:B15A scans the effect/contact table (DS:23B4, 0x23 slots) from the rotating cursor DS:A43A for the
first player-chase candidate, returning BX = the found slot offset (or FFFFh) and advancing DS:A43A.  It
is shared by the B1B0 chase behaviour (called every frame a B1B0 object is active) and the A515 link
spawn.  Step-hook B15A on the oracle side, snapshot the effect pool + the cursor at entry, run
``native_b15a_scan``, and at B15A's return assert BX (found | FFFFh) and the advanced DS:A43A both match.

Usage:
    python -m overkill.probes.verify_native_b15a_scan [demo_name] [max_frames]
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
from overkill.recovered.systems.objects import native_b15a_scan  # noqa: E402

CS = 0x1010
B15A_ENTRY = 0xB15A
CURSOR_A43A = 0xA43A
EFFECT_BASE, EFFECT_COUNT, STRIDE = 0x23B4, 0x23, 0x38
STRIDE_WORDS = STRIDE >> 1


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
            key = id(self)
            if ip == B15A_ENTRY and key not in pending:
                effect_pool = ObjectPool(base=EFFECT_BASE, stride=STRIDE, slots=tuple(
                    tuple(mem.rw(ds, (EFFECT_BASE + i * STRIDE + 2 * j) & 0xFFFF)
                          for j in range(STRIDE_WORDS))
                    for i in range(EFFECT_COUNT)))
                found, new_cursor = native_b15a_scan(effect_pool, mem.rw(ds, CURSOR_A43A))
                ret_addr = mem.rw(ss, self.s.sp & 0xFFFF)
                bx_expected = 0xFFFF if found is None else (found & 0xFFFF)
                pending[key] = (ret_addr, (self.s.sp + 2) & 0xFFFF, bx_expected, new_cursor & 0xFFFF)
            else:
                p = pending.get(key)
                if p is not None and ip == p[0] and (self.s.sp & 0xFFFF) == p[1]:
                    _ret, _sp, bx_expected, cursor_expected = pending.pop(key)
                    mismatches: list = []
                    bx = self.s.bx & 0xFFFF
                    if bx != bx_expected:
                        mismatches.append(("bx", bx, bx_expected))
                    a43a = mem.rw(ds, CURSOR_A43A)
                    if a43a != cursor_expected:
                        mismatches.append(("a43a", a43a, cursor_expected))
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

    print(f"demo {demo_name} ({max_frames} frames): native native_b15a_scan vs VM: "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])}")
    for mism in res["fail"][:5]:
        print(f"  FAIL {mism}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native B15A target-candidate scan byte-exact vs the VM across the demo"
          if ok else "CHECK -- no B15A scans reached, or a divergence")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
