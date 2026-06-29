"""Verify the native 1010:7476 formation child spawn template (``formation_spawn_seed_7476``)
is byte-exact vs the VM across a gameplay demo -- the produced-vs-VM gate for the shared
formation child spawn reached from B800/B73E.

Step-hook 7476 on the pure-VM (oracle/ref) side of the frame verifier.  At its entry capture
the parent slot's X/Y (SS:[BP+2]/[+4]), the final-boss flag (DS:A8C2), and the view globals
(DS:2380/237E), and predict the spawned child's fields via the native seed; at the routine's
return read the slot the real ASM allocated (BX) and assert every field matches.

An all-match run means the native formation spawn template reproduces the VM byte-exact on real
spawns.  (The per-routine oracle is the VM-free ``tests/test_formation_spawn_seed_7476.py``.)

Usage:
    python -m overkill.probes.verify_native_formation_spawn_seed_7476 [demo_name] [max_frames]
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
from overkill.recovered.systems.objects import formation_spawn_seed_7476  # noqa: E402
from overkill.recovered.views.object_slots import OFF_X, OFF_Y, ObjectSlotView  # noqa: E402

CS = 0x1010
SPAWN_7476 = 0x7476
A8C2 = 0xA8C2
VIEW_Y_2380 = 0x2380
VIEW_X_237E = 0x237E


def _read_slot(mem, ds, bx):
    v = ObjectSlotView(mem, ds, bx)
    return (
        v.y_word, v.x_word, v.active_word, v.scan_enable_or_solid, v.direction_or_step,
        v.sprite_or_state, v.gate_or_layer, v.scan_flag, v.hazard_class, v.logic_id,
        v.substate, v.move_delta_y, v.move_delta_x,
    )


def _seed_fields(s):
    return (
        s.y_word, s.x_word, s.active_word, s.scan_enable_or_solid, s.direction_or_step,
        s.sprite_or_state, s.gate_or_layer, s.scan_flag, s.hazard_class, s.logic_id,
        s.substate, s.move_delta_y, s.move_delta_x,
    )


def main(argv) -> int:
    demo_name = argv[0] if argv else "demo_play_tandy_L2_full_20260617_180221"
    max_frames = int(argv[1]) if len(argv) > 1 else 1200
    demo = InputDemoPlayback.load(ROOT / "artifacts" / "demos" / demo_name)
    snapshot = demo.snapshot_path()
    video = str(demo.manifest.get("metadata", {}).get("video", "tandy"))

    res = {"calls": 0, "ok": 0, "noslot": 0, "fail": []}
    pending: dict[int, tuple] = {}
    orig_step = CPU8086.step

    def step(self):
        if getattr(self, "_side", "") == "ref":
            cs = self.s.cs & 0xFFFF
            ip = self.s.ip & 0xFFFF
            key = id(self)
            if cs == CS and ip == SPAWN_7476 and key not in pending:
                ds = self.s.ds & 0xFFFF
                ss = self.s.ss & 0xFFFF
                bp = self.s.bp & 0xFFFF
                rw = self.mem.rw
                seed = formation_spawn_seed_7476(
                    rw(ss, (bp + OFF_X) & 0xFFFF), rw(ss, (bp + OFF_Y) & 0xFFFF),
                    rw(ds, A8C2) == 0x0001, rw(ds, VIEW_Y_2380), rw(ds, VIEW_X_237E),
                )
                ret_addr = rw(ss, self.s.sp & 0xFFFF)
                ret_sp = (self.s.sp + 2) & 0xFFFF
                pending[key] = (ret_addr, ret_sp, ds, _seed_fields(seed))
            elif key in pending:
                ret_addr, ret_sp, ds, predicted = pending[key]
                if ip == ret_addr and (self.s.sp & 0xFFFF) == ret_sp:
                    pending.pop(key)
                    bx = self.s.bx & 0xFFFF
                    if bx == 0xFFFF:
                        res["noslot"] += 1
                    else:
                        actual = _read_slot(self.mem, ds, bx)
                        res["calls"] += 1
                        if actual == predicted:
                            res["ok"] += 1
                        else:
                            res["fail"].append((predicted, actual))
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
                           snapshot=str(snapshot), command_tail=b"", config=cfg,
                           pump_inputs=pump_inputs)
    finally:
        fv._load_runtime = orig_load
        CPU8086.step = orig_step

    print(f"demo {demo_name} ({max_frames} frames): native formation_spawn_seed_7476 vs VM 7476: "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])} noslot={res['noslot']}")
    for predicted, actual in res["fail"][:10]:
        print(f"  FAIL predicted={predicted} actual={actual}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native 7476 formation spawn byte-exact vs the VM across the demo"
          if ok else "CHECK -- no formation spawns reached, or a divergence")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
