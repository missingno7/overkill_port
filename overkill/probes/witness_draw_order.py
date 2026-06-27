"""Probe: witness the REAL per-frame draw order over a demo, vs the FrameSnapshot.

Runs a Tandy demo through the hybrid runtime and wraps the 5AC8 draw dispatch to
record every object actually drawn, in order, per frame. At each frame it also
extracts a FrameSnapshot and compares: does the witnessed draw SET match the
snapshot's sprites (culling), and does the witnessed ORDER match a layer sort of
the snapshot? This grounds the draw order/culling against live behaviour without
a renderer.

Usage:
    python -m overkill.probes.witness_draw_order <demo_dir> [frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXE = ROOT / "assets" / "OVERKILL"
ASSETS = ROOT / "assets"

OFF_SPRITE, OFF_DEST, OFF_TYPE, OFF_LAYER = 0x08, 0x0C, 0x14, 0x16


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    demo_dir = Path(argv[0])
    frames_wanted = int(argv[1]) if len(argv) > 1 else 30

    from dos_re.input_demo import InputDemoPlayback
    import overkill.hooks  # noqa: F401 - registers the hooks
    from dos_re.hooks import registry
    from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier
    from overkill.recovered.adapters.frame_snapshot_adapter import extract_frame_snapshot

    demo = InputDemoPlayback.load(demo_dir)
    snapshot = demo.snapshot_path()
    video = str(demo.manifest.get("metadata", {}).get("video", "tandy"))

    current: list[tuple[int, int, int, int]] = []  # (sprite, dest, layer, type) in draw order

    # The candidate runtime installs hooks from the registry, so witness there
    # (the per-draw 5AC8 dispatch fires once per drawn object).
    draw_rep = registry.replacements[(0x1010, 0x5AC8)]
    original_draw = draw_rep.handler

    def witnessed_draw(cpu):
        ss, bp = cpu.s.ss & 0xFFFF, cpu.s.bp & 0xFFFF
        current.append((
            cpu.mem.rw(ss, (bp + OFF_SPRITE) & 0xFFFF),
            cpu.mem.rw(ss, (bp + OFF_DEST) & 0xFFFF),
            cpu.mem.rw(ss, (bp + OFF_LAYER) & 0xFFFF),
            cpu.mem.rw(ss, (bp + OFF_TYPE) & 0xFFFF),
        ))
        original_draw(cpu)

    object.__setattr__(draw_rep, "handler", witnessed_draw)

    records: list[tuple[list, object]] = []
    boundary = {"n": 0}

    def pump_inputs(ref_rt, cand_rt) -> None:
        demo.apply_to_runtimes(boundary["n"], (ref_rt, cand_rt))
        boundary["n"] += 1

    def publish_candidate(rt, sample) -> None:
        if len(records) < frames_wanted:
            records.append((list(current), extract_frame_snapshot(rt.cpu.mem, rt.cpu.s.ds & 0xFFFF)))
        current.clear()

    config = FrameVerifyConfig(video=video, source="both", max_frames=frames_wanted + 2,
                               semantic_state_check=False, stop_on_diff=False, log_every=0)
    try:
        run_frame_verifier(exe=EXE, assets=ASSETS, snapshot=str(snapshot), command_tail=b"",
                           config=config, pump_inputs=pump_inputs, publish_candidate=publish_candidate)
    finally:
        object.__setattr__(draw_rep, "handler", original_draw)

    print(f"demo {demo_dir.name}  frames captured={len(records)}")
    for i, (drawn, snap) in enumerate(records):
        if not drawn and not snap.sprites:
            continue
        drawn_set = sorted((s, d) for s, d, _, _ in drawn)
        snap_set = sorted((sd.sprite, sd.screen_di) for sd in snap.sprites)
        match = "OK" if drawn_set == snap_set else "DIFF"
        print(f"\nframe {i}: drawn={len(drawn)} snapshot={len(snap.sprites)}  set-match={match}")
        print("  witnessed draw order (sprite,dest,layer):  "
              + " ".join(f"{s:04X}@{d:04X}/L{ly:X}" for s, d, ly, _ in drawn[:14]))
        print("  snapshot order        (sprite,dest,layer):  "
              + " ".join(f"{sd.sprite:04X}@{sd.screen_di:04X}/L{sd.layer:X}" for sd in snap.sprites[:14]))
        if match == "DIFF":
            print(f"    drawn_set ={drawn_set}")
            print(f"    snap_set  ={snap_set}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
