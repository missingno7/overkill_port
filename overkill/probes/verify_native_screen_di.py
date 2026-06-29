"""Verify the native object screen-di composition (project_object_screen_di) is byte-exact vs the
VM's slot ``+0C`` across a gameplay demo -- the §1.2 produced-vs-VM gate for the FULL render
placement (the value frame_snapshot_adapter reads as ``screen_di``).

The per-object draw handler 1010:35CC computes ``+0C`` as::

    35CC call 5A36          ; -> (Tandy) 30D2 returns AX = core di = (obj_y>>1) + DS:99C8[obj_x]
    35CF mov ss:[bp+0C],ax  ; +0C = core (or FFFFh when 30D2 culled via 25B2)
    35D2 cmp ax,FFFFh / jnz ; cull short-circuit
    35D7 ret                ;   culled: +0C stays FFFFh
    35D8 add ax,ds:[234C]   ; + present scroll cursor
    35DC mov ss:[bp+0C],ax  ; +0C = (core + DS:234C) & 0xFFFF  (final screen di)

So ``+0C = project_object_screen_di(obj_x, obj_y, DS:99C8[obj_x], DS:234C)`` for on-screen objects,
and ``None`` (left as the FFFFh sentinel) when culled.  Step-hook 35CC on the pure-VM (oracle) side:
at the final-write boundary 35DF assert the VM's ``+0C`` equals the native prediction; at the cull
return 35D7 assert the native prediction is ``None`` and the VM left ``+0C == FFFFh`` -- for every
real per-object draw.

An all-match run means the native sprite layer can place objects from NativeGameState's pool (x/y +
the column table + the DS:234C scroll) instead of reading the VM's ``+0C``.

Usage:
    python -m overkill.probes.verify_native_screen_di [demo_name] [max_frames]
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
from overkill.native_video.projection import project_object_screen_di  # noqa: E402

CS = 0x1010
DRAW_IP = 0x35CC          # the per-object draw handler entry
FINAL_WRITE_IP = 0x35DF   # after `35DC mov ss:[bp+0C],ax` -- +0C holds the final di
CULL_RET_IP = 0x35D7      # the cull return -- +0C left as FFFFh
COLUMN_TABLE = 0x99C8     # DS:99C8 per-column base table (word per X)
SCROLL_CURSOR = 0x234C    # DS:234C present source cursor
OFF_PLUS_0C = 0x0C        # slot +0C (draw_scratch_or_di / screen_di)


def main(argv) -> int:
    demo_name = argv[0] if argv else "demo_play_tandy_L2_full_20260617_180221"
    max_frames = int(argv[1]) if len(argv) > 1 else 1200
    demo = InputDemoPlayback.load(ROOT / "artifacts" / "demos" / demo_name)
    snapshot = demo.snapshot_path()
    video = str(demo.manifest.get("metadata", {}).get("video", "tandy"))

    res = {"calls": 0, "ok": 0, "fail": []}
    orig_step = CPU8086.step

    def _read_inputs(self):
        ss = self.s.ss & 0xFFFF
        ds = self.s.ds & 0xFFFF
        bp = self.s.bp & 0xFFFF
        x = self.mem.rw(ss, (bp + 2) & 0xFFFF)
        y = self.mem.rw(ss, (bp + 4) & 0xFFFF)
        col = self.mem.rw(ds, (COLUMN_TABLE + ((x * 2) & 0xFFFF)) & 0xFFFF)
        scroll = self.mem.rw(ds, SCROLL_CURSOR)
        vm_di = self.mem.rw(ss, (bp + OFF_PLUS_0C) & 0xFFFF)
        return project_object_screen_di(x, y, col, scroll), vm_di

    def step(self):
        if getattr(self, "_side", "") == "ref":
            cs = self.s.cs & 0xFFFF
            ip = self.s.ip & 0xFFFF
            if cs == CS and ip == FINAL_WRITE_IP:
                predicted, vm_di = _read_inputs(self)
                res["calls"] += 1
                if predicted is not None and predicted == vm_di:
                    res["ok"] += 1
                else:
                    res["fail"].append(("draw", predicted, vm_di))
            elif cs == CS and ip == CULL_RET_IP:
                predicted, vm_di = _read_inputs(self)
                res["calls"] += 1
                if predicted is None and vm_di == 0xFFFF:
                    res["ok"] += 1
                else:
                    res["fail"].append(("cull", predicted, vm_di))
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

    print(f"demo {demo_name} ({max_frames} frames): native project_object_screen_di vs VM slot +0C: "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])}")
    for kind, predicted, actual in res["fail"][:8]:
        print(f"  FAIL [{kind}] predicted={predicted} actual={actual:#06x}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native screen-di byte-exact vs the VM +0C across the demo"
          if ok else "CHECK -- no draws reached, or a divergence")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
