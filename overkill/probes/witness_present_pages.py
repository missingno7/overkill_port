"""Probe: witness the Tandy present-composition page relationships (B1).

The present blit 1010:3354 copies the composed *work/source* page into the
*visible* aperture. OVERKILL keeps several Tandy page pointers in the code
segment:

  CS:[9592]  background work plane (pre-rendered level, scrolled)
  CS:[9596]  display segment   (compositor target / DS restore)
  CS:[9598]  source segment    (the page 3354 reads from)
  CS:[95A4]  video segment      (the visible B800 aperture)
  DS:[234C]  work-buffer cursor (present source start offset)

To model "how the frame composes into the visible page" we need to know how
these relate every frame (e.g. is display==source, i.e. single work page, or is
there a double buffer?). This wraps 3354 and dumps the live pointers.

Usage:
    python -m overkill.probes.witness_present_pages <demo_dir> [frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXE = ROOT / "assets" / "OVERKILL"
ASSETS = ROOT / "assets"

BG_PLANE_OFF = 0x9592
DISPLAY_SEG_OFF = 0x9596
SOURCE_SEG_OFF = 0x9598
VIDEO_SEG_OFF = 0x95A4
WORK_CURSOR_OFF = 0x234C


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    demo_dir = Path(argv[0])
    frames_wanted = int(argv[1]) if len(argv) > 1 else 8

    from dos_re.input_demo import InputDemoPlayback
    import overkill.hooks  # noqa: F401 - registers the hooks
    from dos_re.hooks import registry
    from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier

    demo = InputDemoPlayback.load(demo_dir)
    snapshot = demo.snapshot_path()
    video = str(demo.manifest.get("metadata", {}).get("video", "tandy"))

    rows: list[tuple] = []
    present_rep = registry.replacements[(0x1010, 0x3354)]
    original = present_rep.handler

    def witnessed_present(cpu):
        cs = cpu.s.cs & 0xFFFF
        ds = cpu.s.ds & 0xFFFF
        if len(rows) < frames_wanted:
            rows.append((
                cpu.mem.rw(cs, BG_PLANE_OFF),
                cpu.mem.rw(cs, DISPLAY_SEG_OFF),
                cpu.mem.rw(cs, SOURCE_SEG_OFF),
                cpu.mem.rw(cs, VIDEO_SEG_OFF),
                cpu.mem.rw(ds, WORK_CURSOR_OFF),
            ))
        original(cpu)

    object.__setattr__(present_rep, "handler", witnessed_present)

    boundary = {"n": 0}

    def pump_inputs(ref_rt, cand_rt) -> None:
        demo.apply_to_runtimes(boundary["n"], (ref_rt, cand_rt))
        boundary["n"] += 1

    def publish_candidate(rt, sample) -> None:
        pass

    config = FrameVerifyConfig(video=video, source="both", max_frames=frames_wanted + 4,
                               semantic_state_check=False, stop_on_diff=False, log_every=0)
    try:
        run_frame_verifier(exe=EXE, assets=ASSETS, snapshot=str(snapshot), command_tail=b"",
                           config=config, pump_inputs=pump_inputs, publish_candidate=publish_candidate)
    finally:
        object.__setattr__(present_rep, "handler", original)

    print(f"demo {demo_dir.name}: present calls captured={len(rows)}")
    print("  bg[9592] display[9596] source[9598] video[95A4] cursor[234C]")
    for bg, disp, src, vid, cur in rows:
        rel = []
        if disp == src:
            rel.append("display==source")
        if bg == src:
            rel.append("bg==source")
        if bg == disp:
            rel.append("bg==display")
        print(f"  {bg:04X}      {disp:04X}     {src:04X}     {vid:04X}     {cur:04X}   {' '.join(rel)}")
    if rows:
        # Does the source/video pair alternate (double buffer) across frames?
        srcs = [r[2] for r in rows]
        vids = [r[3] for r in rows]
        print(f"  distinct source segs={sorted(set(srcs))}  distinct video segs={sorted(set(vids))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
