"""Verify the sprite-draw extractor over a demo.

Installs :class:`SpriteDrawCollector` and, per frame, checks the positioned,
identified sprite list it produces:

  * **attribution** - every captured block lands at its object's screen_di
    (block[0].di == screen_di); no orphan/unmodeled blocks slip by silently;
  * **correlation** - the captured sprites match the verified object table
    (frame_snapshot_adapter): same (sprite id, screen_di) on-screen set;
  * **identity persistence** - the same object-record identity recurs across
    frames (so the renderer can interpolate a sprite between source ticks).

The per-block pixels are already proven byte-exact by verify_sprite_decode; this
grounds the *extraction* (grouping + identity + position) on top of it.

Usage:
    python -m overkill.probes.verify_sprite_extractor <demo_dir> [frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXE = ROOT / "assets" / "OVERKILL"
ASSETS = ROOT / "assets"


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    demo_dir = Path(argv[0])
    frames_wanted = int(argv[1]) if len(argv) > 1 else 18

    from dos_re.input_demo import InputDemoPlayback
    import overkill.hooks  # noqa: F401
    from dos_re.hooks import registry
    from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier
    from overkill.recovered.adapters.sprite_draw_extractor import SpriteDrawCollector
    from overkill.recovered.adapters.frame_snapshot_adapter import extract_frame_snapshot

    demo = InputDemoPlayback.load(demo_dir)
    snapshot = demo.snapshot_path()
    video = str(demo.manifest.get("metadata", {}).get("video", "tandy"))

    collector = SpriteDrawCollector(registry)
    collector.install()

    agg = {"frames_drawn": 0, "sprites": 0, "blocks": 0, "multi": 0,
           "bad_single": 0, "corr_ok": 0, "corr_miss": 0}
    identity_frames: dict[int, int] = {}   # identity -> how many frames seen
    boundary = {"n": 0}

    def pump_inputs(ref_rt, cand_rt):
        demo.apply_to_runtimes(boundary["n"], (ref_rt, cand_rt))
        boundary["n"] += 1

    def publish_candidate(rt, sample):
        sprites = collector.take_frame()
        if not sprites:
            return
        snap = extract_frame_snapshot(rt.cpu.mem, rt.cpu.s.ds & 0xFFFF)
        table = {(sd.sprite, sd.screen_di) for sd in snap.playfield.sprites}
        agg["frames_drawn"] += 1
        agg["sprites"] += len(sprites)
        for spr in sprites:
            agg["blocks"] += len(spr.blocks)
            if len(spr.blocks) > 1:
                agg["multi"] += 1            # 75A6 double-slot / 3657 tiled: blocks not at the anchor
            elif spr.blocks[0].di != spr.screen_di:
                agg["bad_single"] += 1       # a single-block sprite must land at its anchor
            if (spr.sprite_id, spr.screen_di) in table:
                agg["corr_ok"] += 1
            else:
                agg["corr_miss"] += 1
            identity_frames[spr.identity] = identity_frames.get(spr.identity, 0) + 1

    config = FrameVerifyConfig(video=video, source="candidate", max_frames=frames_wanted,
                               semantic_state_check=False, stop_on_diff=False, log_every=0)
    try:
        run_frame_verifier(exe=EXE, assets=ASSETS, snapshot=str(snapshot), command_tail=b"",
                           config=config, pump_inputs=pump_inputs, publish_candidate=publish_candidate)
    finally:
        collector.uninstall()

    s = collector.stats
    persistent = sum(1 for n in identity_frames.values() if n >= 2)
    print(f"demo {demo_dir.name}")
    print(f"  frames with draws={agg['frames_drawn']}  sprites={agg['sprites']}  blocks={agg['blocks']}  "
          f"(multi-block={agg['multi']})")
    print(f"  COMPLETENESS: high-calls={s.high_calls} masked-blocks={s.masked_blocks} "
          f"unmodeled={s.unmodeled_blocks} orphan={s.orphan_blocks}")
    print(f"  single-block anchor: {agg['sprites'] - agg['multi'] - agg['bad_single']}/"
          f"{agg['sprites'] - agg['multi']} land at screen_di (bad={agg['bad_single']})")
    print(f"  correlation vs object table (info): {agg['corr_ok']}/{agg['corr_ok'] + agg['corr_miss']}")
    print(f"  identity persistence: {persistent}/{len(identity_frames)} identities seen in >=2 frames")
    if s.orphan_dis:
        from overkill.recovered.systems.tandy_screen import di_to_screen, on_screen
        locs = [f"{di:04X}{'' if on_screen(di) else '*off'}->{di_to_screen(di) if on_screen(di) else '?'}"
                for di in s.orphan_dis[:12]]
        print(f"  orphan block DIs (sample): {locs}")
    # Gate on completeness (every masked block attributed) + single-block placement.
    ok = (agg["sprites"] > 0 and s.orphan_blocks == 0 and s.unmodeled_blocks == 0
          and agg["bad_single"] == 0)
    print("RESULT:", "PASS" if ok else "CHECK")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
