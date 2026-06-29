"""Verify the native effect-spawn template (object_spawn_seed_8209) is byte-exact vs the VM's
1010:8209 across a gameplay demo -- the §1.2 produced-vs-VM gate for object *creation* (a distinct
piece of the ObjectPool state).

Step-hook 8209 on the pure-VM (oracle) side; at entry capture the freshly allocated slot (BX) and
the caller's source position (SS:[BP+2]/[BP+4]) and predict the stamped record natively via
``object_spawn_seed_8209``; at the routine's return read the slot's stamped fields and assert they
match the prediction -- for every real in-game effect spawn.

An all-match run means the native spawn template reproduces the VM byte-exact on the real spawns
the game generates. (The synthetic oracle is ``test_object_spawn_seed_8209_matches_interpreted_asm``;
this is the demo-level confirmation, and grows the cross-demo native-producer gate.)

Usage:
    python -m overkill.probes.verify_native_spawn_seed [demo_name] [max_frames]
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
from overkill.gameplay.object_spawns import (  # noqa: E402
    OBJECT_SPAWN_SEED_8209_SOURCE_X_BP,
    OBJECT_SPAWN_SEED_8209_SOURCE_Y_BP,
)
from overkill.input_waits import pump_demo_frame  # noqa: E402
from overkill.recovered.systems.objects import object_spawn_seed_8209  # noqa: E402
from overkill.recovered.views.object_slots import ObjectSlotView  # noqa: E402

CS = 0x1010
SPAWN_IP = 0x8209
SPAWN_END = 0x8247  # the straight-line 8209..8247 stamp; return leaves this range

# Seed fields stamped by 8209, in (ObjectSlotView accessor) form.
_FIELDS = (
    "active_word", "gate_or_layer", "x_word", "y_word", "direction_or_step", "scan_flag",
    "hazard_class", "logic_id", "counter_20", "variant", "target_x_word", "target_y_word",
    "linked_counter_index",
)


def main(argv) -> int:
    demo_name = argv[0] if argv else "demo_play_tandy_L2_full_20260617_180221"
    max_frames = int(argv[1]) if len(argv) > 1 else 1200
    demo = InputDemoPlayback.load(ROOT / "artifacts" / "demos" / demo_name)
    snapshot = demo.snapshot_path()
    video = str(demo.manifest.get("metadata", {}).get("video", "tandy"))

    res = {"calls": 0, "ok": 0, "fail": []}
    pending: dict[int, tuple[int, object]] = {}
    orig_step = CPU8086.step

    def step(self):
        if getattr(self, "_side", "") == "ref":
            cs = self.s.cs & 0xFFFF
            ip = self.s.ip & 0xFFFF
            key = id(self)
            if cs == CS and ip == SPAWN_IP and key not in pending:
                ss = self.s.ss & 0xFFFF
                bp = self.s.bp & 0xFFFF
                sx = self.mem.rw(ss, (bp + OBJECT_SPAWN_SEED_8209_SOURCE_X_BP) & 0xFFFF)
                sy = self.mem.rw(ss, (bp + OBJECT_SPAWN_SEED_8209_SOURCE_Y_BP) & 0xFFFF)
                pending[key] = (self.s.bx & 0xFFFF, object_spawn_seed_8209(sx, sy))
            elif key in pending and not (cs == CS and SPAWN_IP <= ip <= SPAWN_END):
                slot_off, seed = pending.pop(key)
                slot = ObjectSlotView(self.mem, self.s.ds & 0xFFFF, slot_off)
                mismatches = [
                    (f, getattr(slot, f), getattr(seed, f)) for f in _FIELDS
                    if getattr(slot, f) != getattr(seed, f)
                ]
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

    print(f"demo {demo_name} ({max_frames} frames): native object_spawn_seed_8209 vs VM 8209: "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])}")
    for mismatches in res["fail"][:5]:
        print(f"  FAIL {mismatches}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native spawn template byte-exact vs the VM across the demo"
          if ok else "CHECK -- no spawns reached, or a divergence")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
