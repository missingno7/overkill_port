"""Verify the native 1010:7420 linked-effect spawn template (``object_spawn_seed_7420``) is
byte-exact vs the VM across a gameplay demo -- the §1.2 produced-vs-VM gate for the BFC7
death/spawn tail's effect spawn.

Step-hook 7420 on the pure-VM (oracle/ref) side of the frame verifier.  At its entry capture
the staged source globals it reads (DS:2376 Y / 2378 X / 237A type / A278 scroll offset) and
predict the spawned slot's fields via the native :func:`object_spawn_seed_7420`; at the
routine's return read the slot the real ASM allocated (BX) and assert every field matches.

NOTE: 7420 fires only when a linked-counter group's *last* member dies, which is a rare event
-- a generic demo may reach it zero times (the run then reports ``calls=0`` -> CHECK, not a
pass).  Use a linked-spawn-heavy demo to get coverage; the per-routine oracle is the VM-free
``tests/test_object_spawn_seed_7420.py``.

Usage:
    python -m overkill.probes.verify_native_object_spawn_seed_7420 [demo_name] [max_frames]
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
from overkill.recovered.systems.objects import object_spawn_seed_7420  # noqa: E402
from overkill.recovered.views.object_slots import ObjectSlotView  # noqa: E402

CS = 0x1010
SPAWN_7420 = 0x7420
SRC_Y_OFF = 0x2376
SRC_X_OFF = 0x2378
SRC_TYPE_OFF = 0x237A
SCROLL_OFF = 0xA278


def _read_slot_fields(mem, ds: int, bx: int):
    view = ObjectSlotView(mem, ds, bx)
    return (
        view.active_word, view.x_word, view.y_word, view.transition_latch,
        view.scan_flag, view.hazard_class, view.logic_id, view.linked_counter_index,
        view.variant, mem.rw(ds, (bx + 0x26) & 0xFFFF), view.sprite_or_state,
        view.gate_or_layer,
    )


def _seed_fields(seed):
    return (
        seed.active_word, seed.x_word, seed.y_word, seed.transition_latch,
        seed.scan_flag, seed.hazard_class, seed.logic_id, seed.linked_counter_index,
        seed.variant, seed.slot_field_26, seed.sprite_or_state, seed.gate_or_layer,
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
            if cs == CS and ip == SPAWN_7420 and key not in pending:
                ds = self.s.ds & 0xFFFF
                rw = self.mem.rw
                seed = object_spawn_seed_7420(
                    source_x=rw(ds, SRC_X_OFF), source_y=rw(ds, SRC_Y_OFF),
                    source_type=rw(ds, SRC_TYPE_OFF), x_offset=rw(ds, SCROLL_OFF),
                )
                ret_addr = rw(self.s.ss & 0xFFFF, self.s.sp & 0xFFFF)
                ret_sp = (self.s.sp + 2) & 0xFFFF
                pending[key] = (ret_addr, ret_sp, ds, _seed_fields(seed))
            elif key in pending:
                ret_addr, ret_sp, ds, predicted = pending[key]
                if ip == ret_addr and (self.s.sp & 0xFFFF) == ret_sp:
                    pending.pop(key)
                    bx = self.s.bx & 0xFFFF
                    if bx == 0xFFFF:  # 7524 found no free slot -> no spawn happened
                        res["noslot"] += 1
                    else:
                        actual = _read_slot_fields(self.mem, ds, bx)
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

    print(f"demo {demo_name} ({max_frames} frames): native object_spawn_seed_7420 vs VM 7420: "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])} noslot={res['noslot']}")
    for predicted, actual in res["fail"][:10]:
        print(f"  FAIL predicted={predicted} actual={actual}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native 7420 spawn template byte-exact vs the VM across the demo"
          if ok else "CHECK -- no linked-effect spawns reached, or a divergence")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
