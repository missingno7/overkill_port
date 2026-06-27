"""Verify the native sprite layer places + composites blocks like the live game.

The full-frame composition (bg + all sprites) depends on the not-yet-recovered
background layer to know the clean per-present plate under the double buffer, so
this validates the sprite layer **per block** against each block's own captured
page (no timing assumption): for every masked compositor write it snapshots the
destination page before/after, decodes the present window of both, composites the
decoded block via ``composite_sprites`` at ``block_screen_origin`` onto the before
image, and asserts it equals the after image. Byte-exact proves the data path
CapturedSprite -> SnapshotSprite -> composite_sprites reconstructs the game's draw,
positioning included.

The present cursor ``[234C]`` is read at the draw routine (where DS is the game
data segment), not at the compositor (where DS is the sprite source segment).

Usage:
    python -m overkill.probes.verify_sprite_layer <demo_dir> [frames]
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


def _decode_seg(seg_bytes, cursor):
    from overkill.native_video.page_raster import render_present_page_indices
    return render_present_page_indices(seg_bytes, 0, cursor)


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    demo_dir = Path(argv[0])
    frames_wanted = int(argv[1]) if len(argv) > 1 else 8

    from dos_re.cpu import DF
    from dos_re.input_demo import InputDemoPlayback
    import overkill.hooks  # noqa: F401
    from dos_re.hooks import registry
    from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier
    from overkill.native_video.frame import SnapshotSprite, SpriteBlock
    from overkill.native_video.sprite_layer import composite_sprites
    from overkill.recovered.adapters.sprite_draw_extractor import LAYER_DRAW_ROUTINES
    from overkill.recovered.systems.sprite_textures import MASKED_COMPOSITORS, decode_masked_sprite

    demo = InputDemoPlayback.load(demo_dir)
    snapshot = demo.snapshot_path()
    video = str(demo.manifest.get("metadata", {}).get("video", "tandy"))

    st = {"cursor": None}      # the present cursor, read at the draw routine (game DS)
    agg = {"blocks": 0, "exact": 0, "fail": 0, "skip_df": 0}
    wrapped = []

    def seg_copy(cpu, seg):
        base = ((seg & 0xFFFF) << 4) & 0xFFFFF
        return np.frombuffer(cpu.mem.data, dtype=np.uint8)[base:base + 0x15000].copy()

    for ip in LAYER_DRAW_ROUTINES:           # capture the cursor where DS is the game segment
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
            if (s.flags & DF) or st["cursor"] is None:
                _orig(cpu)
                agg["skip_df"] += int(bool(s.flags & DF))
                return
            rows = _fixed if _fixed is not None else (s.cx & 0xFFFF) or 0x10000
            cursor = st["cursor"]
            es, di, ds, si = s.es & 0xFFFF, s.di & 0xFFFF, s.ds & 0xFFFF, s.si & 0xFFFF
            src = bytes(np.frombuffer(cpu.mem.data, np.uint8)[((ds << 4) + si):((ds << 4) + si) + _wpr * rows * 4])
            before = seg_copy(cpu, es)
            _orig(cpu)
            after = seg_copy(cpu, es)
            tex = decode_masked_sprite(src, _wpr, rows)
            spr = SnapshotSprite(0, 0, 0, di, (SpriteBlock(di, tex.pixels, tex.opaque),))
            native = composite_sprites(_decode_seg(before, cursor), [spr], cursor)
            agg["blocks"] += 1
            if np.array_equal(native, _decode_seg(after, cursor)):
                agg["exact"] += 1
            else:
                agg["fail"] += 1
        object.__setattr__(rep, "handler", hook)
        wrapped.append((rep, orig))

    boundary = {"n": 0}

    def pump_inputs(ref_rt, cand_rt):
        demo.apply_to_runtimes(boundary["n"], (ref_rt, cand_rt))
        boundary["n"] += 1

    def publish_candidate(rt, sample):
        pass

    config = FrameVerifyConfig(video=video, source="candidate", max_frames=frames_wanted,
                               semantic_state_check=False, stop_on_diff=False, log_every=0)
    try:
        run_frame_verifier(exe=EXE, assets=ASSETS, snapshot=str(snapshot), command_tail=b"",
                           config=config, pump_inputs=pump_inputs, publish_candidate=publish_candidate)
    finally:
        for rep, orig in wrapped:
            object.__setattr__(rep, "handler", orig)

    print(f"demo {demo_dir.name}  blocks checked={agg['blocks']}  byte-exact={agg['exact']}  "
          f"fail={agg['fail']}  df-skipped={agg['skip_df']}")
    ok = agg["blocks"] > 0 and agg["fail"] == 0
    print("RESULT:", "PASS" if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
