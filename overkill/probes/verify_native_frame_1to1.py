"""THE OWNER'S BAR: the native frame compose vs the PURE VM's page, 1:1, across a played demo.

The earlier cache-based form of this probe was INVALID as a render oracle: the walk-shadow cache
records the HYBRID runtime, whose presentation path is hooked out -- its pages are empty.  This
form runs the demo through the frame verifier's PURE reference VM (hooks cleared, the ORIGINAL
A846/5BDC presentation executing) and step-hooks ``1010:5BDC``'s RETURN -- the present-complete
boundary, where the page was drawn with exactly the projection cells the state still carries
(perfect phase).  At each sampled present it copies the machine state, composes the native frame
(live star records + object sprite blocks), and pixel-diffs the playfield region
``x in [0,208), y in [4,196)`` against the VM's ``CS:[95A4]`` page.

REPORT mode: the diff count is the render TODO list; the goal criterion is 0, then this flips to
a hard gate.

Usage:
    python -m overkill.probes.verify_native_frame_1to1 [demo_name] [max_frames] [stride]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import overkill.frame_verify as fv  # noqa: E402
from dos_re.cpu import CPU8086  # noqa: E402
from dos_re.input_demo import InputDemoPlayback  # noqa: E402
from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier  # noqa: E402
from overkill.input_waits import pump_demo_frame  # noqa: E402

CS = 0x1010
DS = 0x25CC
PRESENT_5BDC = 0x5BDC
PAGE_SEG_PTR = 0x95A4
PLAYFIELD = np.s_[4:196, 0:208]


def main(argv) -> int:
    from overkill.native_game import NativeGame
    from overkill.native_video.frame import SnapshotSprite
    from overkill.native_video.page_raster import decode_tandy_b800_indices
    from overkill.native_video.playfield import compose_playfield_indices
    from overkill.native_video.object_sprites import object_sprite_blocks
    from overkill.native_video.starfield_plate import render_starfield_plate
    from overkill.native_walk_frame import project_state
    from overkill.recovered.adapters.cold_level_start import build_cold_level_start
    from overkill.recovered.adapters.flat_memory import MutFlatMemory
    from overkill.recovered.adapters.starfield_adapter import load_starfield_state
    import scripts.play_native as pn

    demo_name = argv[0] if argv and argv[0] else "demo_cold_start_full_20260705_123645"
    max_frames = int(argv[1]) if len(argv) > 1 else 1200
    stride = int(argv[2]) if len(argv) > 2 else 50

    demo = InputDemoPlayback.load(ROOT / "artifacts" / "demos" / demo_name)
    snapshot = demo.snapshot_path()
    video = str(demo.manifest.get("metadata", {}).get("video", "tandy"))

    bundle_data = (ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin").read_bytes()
    container_data = (ROOT / "assets" / "OVERKILL").read_bytes()
    game0 = NativeGame.load_level(bundle_data, container_data, 0,
                                  build_cold_level_start(bundle_data, 0)[0],
                                  origin_x=0, row_base=0x9C)

    res = {"presents": 0, "sampled": 0, "diff_total": 0, "worst": (0, -1), "lines": []}
    pending: dict[int, tuple] = {}
    orig_step = CPU8086.step

    def _compose_and_diff(cpu) -> None:
        image = MutFlatMemory(bytes(cpu.mem.data))
        cursor = image.rw(DS, 0x234C)
        mem_np = np.frombuffer(bytes(image.data), dtype=np.uint8)
        page_seg = image.rw(CS, PAGE_SEG_PTR)
        vm = decode_tandy_b800_indices(mem_np[page_seg * 16: page_seg * 16 + 0x10000])
        ctx = pn._build_sprite_context(bundle_data, container_data, game0,
                                       (image.rw(DS, 0x1028) >> 1) & 0xFFFF)
        state = project_state(image)
        plate = render_starfield_plate(load_starfield_state(bytes(image.data)), cursor)
        blocks = []
        for pool in (state.special_pool, state.effect_pool, state.object_pool):
            blocks.extend(object_sprite_blocks(pool, ctx))
        if blocks:
            native = compose_playfield_indices(
                plate, [SnapshotSprite(0, 0, 0, 0, tuple(blocks))], cursor)
        else:
            native = plate
        d = int((native[PLAYFIELD] != vm[PLAYFIELD]).sum())
        res["sampled"] += 1
        res["diff_total"] += d
        if d > res["worst"][0]:
            res["worst"] = (d, res["presents"])
        res["lines"].append(f"  present {res['presents']:5d}: playfield diff px = {d} "
                            f"(vm nonzero {int((vm[PLAYFIELD] > 0).sum())})")

    def step(self):
        if getattr(self, "_side", "") == "ref":
            cs = self.s.cs & 0xFFFF
            ip = self.s.ip & 0xFFFF
            key = id(self)
            if cs == CS and ip == PRESENT_5BDC and key not in pending:
                ss = self.s.ss & 0xFFFF
                ret_addr = self.mem.rw(ss, self.s.sp & 0xFFFF)
                pending[key] = (ret_addr, (self.s.sp + 2) & 0xFFFF)
            elif key in pending:
                ret_addr, ret_sp = pending[key]
                if cs == CS and ip == ret_addr and (self.s.sp & 0xFFFF) == ret_sp:
                    pending.pop(key)
                    if res["presents"] % stride == 0:
                        _compose_and_diff(self)
                    res["presents"] += 1
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

    for line in res["lines"]:
        print(line)
    print(f"presents: {res['presents']}; sampled: {res['sampled']}; "
          f"mean diff px: {res['diff_total'] // max(1, res['sampled'])} of {192 * 208}; "
          f"worst: {res['worst'][0]} at present {res['worst'][1]}")
    print("RESULT:", "PASS -- 1:1 with the pure VM page" if res["diff_total"] == 0 else
          "REPORT -- the diff is the render TODO list; the goal criterion is 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
