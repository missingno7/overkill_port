"""Probe: witness the REAL text/glyph draws over a demo (the scene render path).

The non-gameplay scenes (title/menu/intro/tally) and the in-game HUD score draw
through OVERKILL's text path: 518C (string loop) -> 519A (dispatch) -> 3153
(Tandy glyph renderer). Unlike the object table, glyphs are *transient* imperative
draws, so we witness them live: wrap the 3153 dispatch and record, per glyph, the
character + the cursor cell (DS:215E x, DS:2160 y-offset) + colour (DS:215C).

This grounds *which* scenes draw text and *what* the glyph stream is, so the text
layer of the semantic model can be modelled and checked against it.

Usage:
    python -m overkill.probes.witness_text_draw <demo_dir> [frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXE = ROOT / "assets" / "OVERKILL"
ASSETS = ROOT / "assets"

CURSOR_X_OFF = 0x215E   # DS:215E  glyph cursor column (Tandy byte units)
CURSOR_Y_OFF = 0x2160   # DS:2160  glyph cursor row offset into the work plane
COLOUR_OFF = 0x215C     # DS:215C  current text colour nibble


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    demo_dir = Path(argv[0])
    frames_wanted = int(argv[1]) if len(argv) > 1 else 60

    from dos_re.input_demo import InputDemoPlayback
    import overkill.hooks  # noqa: F401 - registers the hooks
    from dos_re.hooks import registry
    from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier

    demo = InputDemoPlayback.load(demo_dir)
    snapshot = demo.snapshot_path()
    video = str(demo.manifest.get("metadata", {}).get("video", "tandy"))

    glyphs: list[tuple[int, int, int, int]] = []  # (char, x, y, colour)

    glyph_rep = registry.replacements[(0x1010, 0x3153)]
    original = glyph_rep.handler

    def witnessed_glyph(cpu):
        al = cpu.s.ax & 0xFF
        ds = cpu.s.ds & 0xFFFF
        if al >= 0x12:  # 0x10/0x11 are colour/cursor control bytes, not glyphs
            glyphs.append((
                al,
                cpu.mem.rb(ds, CURSOR_X_OFF),
                cpu.mem.rw(ds, CURSOR_Y_OFF),
                cpu.mem.rb(ds, COLOUR_OFF),
            ))
        original(cpu)

    object.__setattr__(glyph_rep, "handler", witnessed_glyph)

    boundary = {"n": 0}
    frame_count = {"n": 0}

    def pump_inputs(ref_rt, cand_rt) -> None:
        demo.apply_to_runtimes(boundary["n"], (ref_rt, cand_rt))
        boundary["n"] += 1

    def publish_candidate(rt, sample) -> None:
        frame_count["n"] += 1

    config = FrameVerifyConfig(video=video, source="both", max_frames=frames_wanted + 2,
                               semantic_state_check=False, stop_on_diff=False, log_every=0)
    try:
        run_frame_verifier(exe=EXE, assets=ASSETS, snapshot=str(snapshot), command_tail=b"",
                           config=config, pump_inputs=pump_inputs, publish_candidate=publish_candidate)
    finally:
        object.__setattr__(glyph_rep, "handler", original)

    print(f"demo {demo_dir.name}: frames={frame_count['n']}  glyphs_drawn={len(glyphs)}")
    if glyphs:
        # Reconstruct the drawn strings (printable runs), grouped by cursor row.
        printable = "".join(chr(c) if 0x20 <= c < 0x7F else "." for c, _, _, _ in glyphs)
        print(f"  glyph chars: {printable[:200]}")
        colours = sorted({col for _, _, _, col in glyphs})
        rows = sorted({y for _, _, y, _ in glyphs})
        print(f"  distinct colours={[hex(c) for c in colours]}  distinct rows={len(rows)}")
        print("  first 12 (char,x,y,colour): "
              + " ".join(f"{c:02X}@{x:02X},{y:04X}/{col:X}" for c, x, y, col in glyphs[:12]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
