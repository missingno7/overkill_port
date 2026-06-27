"""End-to-end: VM memory -> RenderSnapshot -> native backend render == faithful.

Grounds the whole native pipeline against the recovered/faithful frame: the
extractor reads the composed page, the backend colorizes it, and the result must
equal the decoded on-screen B800 exactly (source-boundary parity). NumPy is
imported inside the test so the core runner skips when it is absent.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

DEMOS = Path(__file__).resolve().parents[1] / "artifacts" / "demos"


def _snapshots():
    if not DEMOS.is_dir():
        return []
    return sorted(
        d / "snapshot"
        for d in DEMOS.glob("demo_*")
        if (d / "snapshot" / "memory_1mb.bin").is_file()
    )


@pytest.mark.parametrize("snap", _snapshots(), ids=lambda p: p.parent.name)
def test_pipeline_matches_faithful_frame(snap):
    try:
        import numpy as np
    except Exception:  # pragma: no cover
        pytest.skip("numpy not installed")

    from dos_re.memory import Memory
    from overkill.native_video.backend import NativeOverkillVideoBackend
    from overkill.native_video.page_raster import decode_tandy_b800_rgb
    from overkill.recovered.adapters.render_snapshot_adapter import extract_render_snapshot

    mem = Memory()
    mem.data[:] = (snap / "memory_1mb.bin").read_bytes()
    cpu = json.loads((snap / "state.json").read_text(encoding="utf-8"))["cpu_snapshot"]
    ds = int(re.search(r"DS=([0-9A-Fa-f]{4})", cpu).group(1), 16)

    rsnap = extract_render_snapshot(mem, ds, frame_id=1, timestamp=0.0)

    # extractor produced complete, well-formed layers
    assert rsnap.composed_indices.shape == (200, 320)
    assert rsnap.playfield_indices is not None and rsnap.playfield_indices.shape == (200, 320)
    assert len(rsnap.palette) == 16

    be = NativeOverkillVideoBackend()
    be.submit_source_frame(rsnap)
    out = be.present(0.0)

    # source-boundary parity: the backend-rendered frame is exactly the faithful
    # decoded on-screen frame (the backend owns the colorize; no VM framebuffer
    # read on its side).
    mem_arr = np.frombuffer(mem.data, dtype=np.uint8)
    video_page = mem.rw(0x1010, 0x95A4)
    faithful = decode_tandy_b800_rgb(mem_arr, ((video_page & 0xFFFF) << 4) & 0xFFFFF)
    assert np.array_equal(out.rgb, faithful)
