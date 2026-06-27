"""Verify the pure sprite-texture decoder byte-exact vs the live compositor.

Wraps OVERKILL's masked-sprite compositor leaves (1010:2E6E / 2F81 / 2FB6) over a
real demo. For every call it captures the source bytes (DS:SI), the destination
background words and the post-blit result words (along the real DI stride), then
checks that :func:`overkill.recovered.systems.sprite_textures.decode_masked_sprite`
reproduces the result two ways:

  * **faithful:** ``(bg & mask) | data`` from the decoded words == live result;
  * **render form:** the ``pixels``/``opaque`` texture composited over the bg ==
    live result (this also proves the masks are clean 0x0/0xF nibbles, so the
    background-independent texture is lossless).

Any mismatch (or a set direction flag we don't model yet) fails loud — no silent
fallback. This grounds the first semantic layer the native renderer consumes.

Usage:
    python -m overkill.probes.verify_sprite_decode <demo_dir> [frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
EXE = ROOT / "assets" / "OVERKILL"
ASSETS = ROOT / "assets"

CS = 0x1010


def _read_seg_bytes(mem, seg, off, n):
    base = ((seg & 0xFFFF) << 4) & 0xFFFFF
    return bytes(mem.data[base + off: base + off + n])


def _di_grid(di0, words_per_row, rows, row_add):
    """The (rows, words) DI offsets the compositor writes (forward, DF clear)."""
    grid = np.zeros((rows, words_per_row), dtype=np.int64)
    di = di0 & 0xFFFF
    for r in range(rows):
        for c in range(words_per_row):
            grid[r, c] = di
            di = (di + 2) & 0xFFFF
        di = (di + row_add) & 0xFFFF
    return grid


def _read_words(mem, seg, grid):
    base = ((seg & 0xFFFF) << 4) & 0xFFFFF
    out = np.zeros(grid.shape, dtype=np.uint16)
    data = mem.data
    for r in range(grid.shape[0]):
        for c in range(grid.shape[1]):
            a = base + int(grid[r, c])
            out[r, c] = data[a] | (data[a + 1] << 8)
    return out


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    demo_dir = Path(argv[0])
    frames_wanted = int(argv[1]) if len(argv) > 1 else 20

    from dos_re.cpu import DF
    from dos_re.input_demo import InputDemoPlayback
    import overkill.hooks  # noqa: F401
    from dos_re.hooks import registry
    from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier
    from overkill.recovered.systems.sprite_textures import (
        MASKED_COMPOSITORS, decode_masked_sprite, composite_words,
    )

    demo = InputDemoPlayback.load(demo_dir)
    snapshot = demo.snapshot_path()
    video = str(demo.manifest.get("metadata", {}).get("video", "tandy"))

    stats = {"calls": 0, "ok_words": 0, "ok_render": 0, "df_set": 0,
             "fail_words": 0, "fail_render": 0, "by_ip": {}}
    failures = []

    wrapped = []
    for ip, (wpr, row_add, fixed_rows) in MASKED_COMPOSITORS.items():
        rep = registry.replacements[(CS, ip)]
        orig = rep.handler

        def make(ip, wpr, row_add, fixed_rows, rep, orig):
            def hook(cpu):
                s = cpu.s
                rows = fixed_rows if fixed_rows is not None else (s.cx & 0xFFFF) or 0x10000
                ds, si, es, di = s.ds & 0xFFFF, s.si & 0xFFFF, s.es & 0xFFFF, s.di & 0xFFFF
                df_set = bool(s.flags & DF)
                src = _read_seg_bytes(cpu.mem, ds, si, wpr * rows * 4)
                grid = _di_grid(di, wpr, rows, row_add)
                bg = _read_words(cpu.mem, es, grid)
                orig(cpu)
                result = _read_words(cpu.mem, es, grid)
                _check(ip, wpr, rows, src, bg, result, df_set)
            return hook

        def _check(ip, wpr, rows, src, bg, result, df_set):
            stats["calls"] += 1
            stats["by_ip"][ip] = stats["by_ip"].get(ip, 0) + 1
            if df_set:
                stats["df_set"] += 1
                return
            tex = decode_masked_sprite(src, wpr, rows)
            # faithful: (bg & mask) | data == live result
            if np.array_equal(composite_words(tex, bg), result):
                stats["ok_words"] += 1
            else:
                stats["fail_words"] += 1
                if len(failures) < 6:
                    failures.append((ip, "words", rows, wpr))
                return
            # render form: pixels/opaque over the bg == live result (clean masks)
            from overkill.native_video.page_raster import decode_tandy_b800_indices  # noqa: F401
            if _render_form_matches(tex, bg, result):
                stats["ok_render"] += 1
            else:
                stats["fail_render"] += 1
                if len(failures) < 6:
                    failures.append((ip, "render", rows, wpr))

        object.__setattr__(rep, "handler", make(ip, wpr, row_add, fixed_rows, rep, orig))
        wrapped.append((rep, orig))

    boundary = {"n": 0}

    def pump_inputs(ref_rt, cand_rt):
        demo.apply_to_runtimes(boundary["n"], (ref_rt, cand_rt))
        boundary["n"] += 1

    def publish_candidate(rt, sample):
        boundary["frames"] = boundary.get("frames", 0) + 1

    config = FrameVerifyConfig(video=video, source="candidate", max_frames=frames_wanted,
                               semantic_state_check=False, stop_on_diff=False, log_every=0)
    try:
        run_frame_verifier(exe=EXE, assets=ASSETS, snapshot=str(snapshot), command_tail=b"",
                           config=config, pump_inputs=pump_inputs, publish_candidate=publish_candidate)
    finally:
        for rep, orig in wrapped:
            object.__setattr__(rep, "handler", orig)

    print(f"demo {demo_dir.name}  masked-compositor calls={stats['calls']}  "
          + " ".join(f"{ip:04X}={n}" for ip, n in sorted(stats['by_ip'].items())))
    print(f"  faithful (bg&mask)|data == live : {stats['ok_words']}/{stats['calls'] - stats['df_set']}  "
          f"fail={stats['fail_words']}")
    print(f"  render-form pixels/opaque == live: {stats['ok_render']}/{stats['calls'] - stats['df_set']}  "
          f"fail={stats['fail_render']}")
    if stats["df_set"]:
        print(f"  DF set (unmodelled, skipped): {stats['df_set']}")
    if failures:
        print(f"  first failures: {failures}")
    ok = stats["calls"] > 0 and stats["fail_words"] == 0 and stats["fail_render"] == 0 and stats["df_set"] == 0
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def _render_form_matches(tex, bg_words, result_words) -> bool:
    """Composite the pixels/opaque texture over the bg (as words) and compare."""
    from overkill.recovered.systems.sprite_textures import PX_PER_WORD
    rows, wpr = bg_words.shape
    # background pixels (rows, wpr*4) from the bg words
    blo = (bg_words & 0xFF).astype(np.uint8)
    bhi = (bg_words >> 8).astype(np.uint8)
    bg_px = np.stack([blo >> 4, blo & 0xF, bhi >> 4, bhi & 0xF], axis=-1).reshape(rows, wpr * PX_PER_WORD)
    out_px = np.where(tex.opaque, tex.pixels, bg_px).astype(np.uint8)
    # repack pixels -> words and compare to the live result words
    q = out_px.reshape(rows, wpr, PX_PER_WORD)
    lo = (q[:, :, 0] << 4) | q[:, :, 1]
    hi = (q[:, :, 2] << 4) | q[:, :, 3]
    out_words = (lo.astype(np.uint16) | (hi.astype(np.uint16) << 8))
    return np.array_equal(out_words, result_words)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
