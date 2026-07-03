"""Produced-vs-VM gate for the native starfield PLATE + the standalone playfield self-compose.

This closes the last VM dependency in the standalone playfield (Bucket B/C wiring): the
background *plate* is now built from the recovered :class:`StarfieldState` instead of captured
from the VM page.  For each frame it checks two things at the plate-capture point (the frame's
first masked-sprite block, exactly where ``verify_playfield_compose`` snapshots the plate):

1. **plate**: :func:`~overkill.native_video.starfield_plate.render_starfield_plate` (from the
   star state read where ``DS`` = the game segment) equals the VM's decoded playfield plate
   (:func:`~overkill.native_video.page_raster.render_present_page_indices` of the live page),
   byte-for-byte.
2. **self-compose** (informational): ``compose_playfield_indices(native_plate, sprite_blocks)``
   vs the VM's decoded ``[9598]`` playfield — the brief's Bucket-B gate, now with the plate
   produced natively.  Because the native plate is byte-identical to the VM plate (check 1), this
   number is *identical* to ``verify_playfield_compose``'s over the VM-captured plate (both model
   the masked + OR-inverted compositor leaves), so it tracks that probe's result.  PASS is gated
   on the plate proof (check 1), which is what this slice establishes.

Usage:
    python -m overkill.probes.verify_native_starfield_plate <demo_dir> [frames]
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


def _read_starfield(cpu):
    from overkill.recovered.domain.starfield import STAR_COUNT, Star, StarfieldState
    ds = cpu.s.ds & 0xFFFF
    stars = tuple(
        Star(cpu.mem.rw(ds, (0xC6C1 + i * 6) & 0xFFFF),
             cpu.mem.rw(ds, (0xC6C3 + i * 6) & 0xFFFF),
             cpu.mem.rw(ds, (0xC6C5 + i * 6) & 0xFFFF))
        for i in range(STAR_COUNT)
    )
    counters = (cpu.mem.rw(ds, 0xC812), cpu.mem.rw(ds, 0xC814), cpu.mem.rw(ds, 0xC816))
    enabled = cpu.mem.rw(ds, 0xA95A) != 0xFFFF
    return StarfieldState(stars, counters, enabled)


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    demo_dir = Path(argv[0])
    if not demo_dir.is_dir():
        demo_dir = ROOT / "artifacts" / "demos" / argv[0]
    frames_wanted = int(argv[1]) if len(argv) > 1 else 40

    from dos_re.cpu import DF
    from dos_re.input_demo import InputDemoPlayback
    import overkill.hooks  # noqa: F401
    from dos_re.hooks import registry
    from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier
    from overkill.native_video.frame import SnapshotSprite, SpriteBlock
    from overkill.native_video.page_raster import render_present_page_indices
    from overkill.native_video.playfield import compose_playfield_indices
    from overkill.native_video.starfield_plate import render_starfield_plate
    from overkill.recovered.adapters.sprite_draw_extractor import LAYER_DRAW_ROUTINES
    from overkill.recovered.systems.sprite_textures import (
        MASKED_COMPOSITORS,
        OR_INVERTED_COMPOSITORS,
        decode_masked_sprite,
        decode_or_inverted_delta,
    )

    demo = InputDemoPlayback.load(demo_dir)
    snapshot = demo.snapshot_path()
    video = str(demo.manifest.get("metadata", {}).get("video", "tandy"))

    st = {"cursor": None, "sf": None}
    frame = {"plate": None, "blocks": [], "cursor": None, "dirty": False}
    agg = {"frames": 0, "plate_ok": 0, "compose_ok": 0, "fail": 0, "skipped": 0}
    wrapped = []

    def reset():
        frame["plate"] = None
        frame["blocks"] = []
        frame["cursor"] = None
        frame["dirty"] = False

    for ip in LAYER_DRAW_ROUTINES:                # cursor + star state where DS = game segment
        rep = registry.replacements[(CS, ip)]
        orig = rep.handler

        def cap(cpu, _orig=orig):
            st["cursor"] = cpu.mem.rw(cpu.s.ds & 0xFFFF, P_CURSOR)
            st["sf"] = _read_starfield(cpu)
            _orig(cpu)
        object.__setattr__(rep, "handler", cap)
        wrapped.append((rep, orig))

    for ip, (wpr, _row_add, fixed_rows) in MASKED_COMPOSITORS.items():
        rep = registry.replacements[(CS, ip)]
        orig = rep.handler

        def hook(cpu, _orig=orig, _wpr=wpr, _fixed=fixed_rows):
            s = cpu.s
            if st["cursor"] is None or (s.flags & DF):
                frame["dirty"] = frame["dirty"] or st["cursor"] is None
                if s.flags & DF:
                    frame["dirty"] = True
                _orig(cpu)
                return
            mem_arr = np.frombuffer(cpu.mem.data, np.uint8)
            if frame["plate"] is None:
                # native plate (from recovered star state) + the VM plate for the direct check
                frame["plate"] = render_starfield_plate(st["sf"], st["cursor"])
                frame["vm_plate"] = render_present_page_indices(mem_arr, s.es & 0xFFFF, st["cursor"]).copy()
                frame["cursor"] = st["cursor"]
            rows = _fixed if _fixed is not None else (s.cx & 0xFFFF) or 0x10000
            ds, si, di = s.ds & 0xFFFF, s.si & 0xFFFF, s.di & 0xFFFF
            src = bytes(mem_arr[((ds << 4) + si):((ds << 4) + si) + _wpr * rows * 4])
            tex = decode_masked_sprite(src, _wpr, rows)
            frame["blocks"].append(SpriteBlock(di, tex.pixels, tex.opaque))
            _orig(cpu)
        object.__setattr__(rep, "handler", hook)
        wrapped.append((rep, orig))

    for ip, (wpr, _row_add) in OR_INVERTED_COMPOSITORS.items():
        rep = registry.replacements[(CS, ip)]
        orig = rep.handler

        def or_hook(cpu, _orig=orig, _wpr=wpr):
            s = cpu.s
            if st["cursor"] is None or (s.flags & DF):
                frame["dirty"] = True
                _orig(cpu)
                return
            mem_arr = np.frombuffer(cpu.mem.data, np.uint8)
            if frame["plate"] is None:
                frame["plate"] = render_starfield_plate(st["sf"], st["cursor"])
                frame["vm_plate"] = render_present_page_indices(mem_arr, s.es & 0xFFFF, st["cursor"]).copy()
                frame["cursor"] = st["cursor"]
            rows = (s.cx & 0xFFFF) or 0x10000
            ds, si, di = s.ds & 0xFFFF, s.si & 0xFFFF, s.di & 0xFFFF
            src = bytes(mem_arr[((ds << 4) + si):((ds << 4) + si) + _wpr * rows * 4])
            delta = decode_or_inverted_delta(src, _wpr, rows)
            frame["blocks"].append(SpriteBlock(di, delta, np.ones(delta.shape, bool), kind="or_inverted"))
            _orig(cpu)
        object.__setattr__(rep, "handler", or_hook)
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
        plate_ok = np.array_equal(frame["plate"], frame["vm_plate"])
        compose_ok = np.array_equal(native, vm)
        if plate_ok:
            agg["plate_ok"] += 1
        else:
            agg["fail"] += 1  # gate on the plate proof only (self-compose just echoes the baseline)
        if compose_ok:
            agg["compose_ok"] += 1
        reset()

    def pump_inputs(ref_rt, cand_rt):
        flush(cand_rt)
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

    print(f"demo {demo_dir.name}  frames={agg['frames']}  plate_exact={agg['plate_ok']}  "
          f"self_compose_exact={agg['compose_ok']}  fail={agg['fail']}  skipped(DF)={agg['skipped']}")
    ok = agg["frames"] > 0 and agg["fail"] == 0
    print("RESULT:", "PASS" if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
