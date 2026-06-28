"""Verify the native backend SELF-COMPOSES the playfield, byte-exact vs the VM.

`verify_sprite_layer` proves each masked-sprite block reconstructs onto its own
captured page. This goes one level up: it proves the whole **playfield** is

    playfield = starfield plate  +  composite_sprites(all sprite blocks)

where the *starfield plate* is the persistent background (the 35FF page decoded just
before the frame's first sprite composite -- a sparse ~40-pixel starfield, scrolled
by the present cursor) and the blocks are the per-frame masked-compositor draws. For
each frame it accumulates every block, snapshots the plate at the first block, then
composites the blocks onto the decoded plate and asserts the result equals the VM's
decoded 35FF playfield (`render_present_page_indices`). Byte-exact over a gameplay
run demonstrates the playfield needs no per-frame VM page read -- only the (static)
plate + the semantic sprite blocks.

Usage:
    python -m overkill.probes.verify_playfield_compose <demo_dir> [frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
EXE = ROOT / "assets" / "OVERKILL"
ASSETS = ROOT / "assets"
CS = 0x1010
P_CURSOR = 0x234C
SOURCE_PAGE_PTR = 0x9598


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    demo_dir = Path(argv[0])
    frames_wanted = int(argv[1]) if len(argv) > 1 else 40

    from dos_re.cpu import DF
    from dos_re.input_demo import InputDemoPlayback
    import overkill.hooks  # noqa: F401
    from dos_re.hooks import registry
    from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier
    from overkill.native_video.frame import SnapshotSprite, SpriteBlock
    from overkill.native_video.playfield import compose_playfield_indices
    from overkill.native_video.page_raster import render_present_page_indices
    from overkill.recovered.adapters.sprite_draw_extractor import LAYER_DRAW_ROUTINES
    from overkill.recovered.systems.sprite_textures import MASKED_COMPOSITORS, decode_masked_sprite

    demo = InputDemoPlayback.load(demo_dir)
    snapshot = demo.snapshot_path()
    video = str(demo.manifest.get("metadata", {}).get("video", "tandy"))

    st = {"cursor": None}
    frame = {"plate": None, "blocks": [], "cursor": None, "dirty": False}
    agg = {"frames": 0, "exact": 0, "fail": 0, "skipped": 0}
    wrapped = []

    def reset():
        frame["plate"] = None
        frame["blocks"] = []
        frame["cursor"] = None
        frame["dirty"] = False

    for ip in LAYER_DRAW_ROUTINES:                # cursor read where DS = game segment
        rep = registry.replacements[(CS, ip)]
        orig = rep.handler

        def cap(cpu, _orig=orig):
            st["cursor"] = cpu.mem.rw(cpu.s.ds & 0xFFFF, P_CURSOR)
            _orig(cpu)
        object.__setattr__(rep, "handler", cap)
        wrapped.append((rep, orig))

    for ip, (wpr, _row_add, fixed_rows) in MASKED_COMPOSITORS.items():
        rep = registry.replacements[(CS, ip)]
        orig = rep.handler

        def hook(cpu, _orig=orig, _wpr=wpr, _fixed=fixed_rows):
            s = cpu.s
            if st["cursor"] is None or (s.flags & DF):
                frame["dirty"] = frame["dirty"] or st["cursor"] is None  # can't place without a cursor
                if s.flags & DF:
                    frame["dirty"] = True
                _orig(cpu)
                return
            mem_arr = np.frombuffer(cpu.mem.data, np.uint8)
            if frame["plate"] is None:
                frame["plate"] = render_present_page_indices(mem_arr, s.es & 0xFFFF, st["cursor"]).copy()
                frame["cursor"] = st["cursor"]
            rows = _fixed if _fixed is not None else (s.cx & 0xFFFF) or 0x10000
            ds, si, di = s.ds & 0xFFFF, s.si & 0xFFFF, s.di & 0xFFFF
            src = bytes(mem_arr[((ds << 4) + si):((ds << 4) + si) + _wpr * rows * 4])
            tex = decode_masked_sprite(src, _wpr, rows)
            frame["blocks"].append(SpriteBlock(di, tex.pixels, tex.opaque))
            _orig(cpu)
        object.__setattr__(rep, "handler", hook)
        wrapped.append((rep, orig))

    boundary = {"n": 0}

    def flush(cand_rt):
        if not frame["blocks"] or frame["plate"] is None:
            reset()
            return
        if frame["dirty"]:
            agg["skipped"] += 1
            reset()
            return
        cpu = cand_rt.cpu
        mem_arr = np.frombuffer(cand_rt.program.memory.data, np.uint8)
        src = cpu.mem.rw(CS, SOURCE_PAGE_PTR) & 0xFFFF
        cur = frame["cursor"]
        spr = SnapshotSprite(0, 0, 0, 0, tuple(frame["blocks"]))
        native = compose_playfield_indices(frame["plate"], [spr], cur)
        vm = render_present_page_indices(mem_arr, src, cur)
        agg["frames"] += 1
        if np.array_equal(native, vm):
            agg["exact"] += 1
        else:
            agg["fail"] += 1
        reset()

    def pump_inputs(ref_rt, cand_rt):
        flush(cand_rt)                         # compare the frame that just completed
        demo.apply_to_runtimes(boundary["n"], (ref_rt, cand_rt))
        boundary["n"] += 1

    config = FrameVerifyConfig(video=video, source="candidate", max_frames=frames_wanted,
                               semantic_state_check=False, stop_on_diff=False, log_every=0)
    try:
        run_frame_verifier(exe=EXE, assets=ASSETS, snapshot=str(snapshot), command_tail=b"",
                           config=config, pump_inputs=pump_inputs)
    finally:
        for rep, orig in wrapped:
            object.__setattr__(rep, "handler", orig)

    print(f"demo {demo_dir.name}  playfield frames checked={agg['frames']}  "
          f"byte-exact={agg['exact']}  fail={agg['fail']}  skipped(DF)={agg['skipped']}")
    ok = agg["frames"] > 0 and agg["fail"] == 0
    print("RESULT:", "PASS" if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
