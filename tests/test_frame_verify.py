from __future__ import annotations

import tempfile
from pathlib import Path

from dos_re.frame_verify import (
    FrameSample,
    FrameVerifyConfig,
    compose_compare_rgb,
    diff_rgb_frame,
    dump_divergence,
)
from overkill.frame_verify import HEIGHT, WIDTH


def _rgb_frame(fill: bytes) -> bytes:
    return fill * (WIDTH * HEIGHT)


def _sample(*, side: str, frame_no: int, rgb: bytes) -> FrameSample:
    return FrameSample(
        side=side,
        frame_no=frame_no,
        kind="present",
        hook=(0x1010, 0x447B),
        cs=0x1010,
        ip=0x447B,
        steps_since_start=123,
        boundary_steps=45,
        display_start=0,
        raw_crc=0x12345678,
        rgb_crc=0x9ABCDEF0,
        raw=b"\x00" * 0x4000,
        rgb=rgb,
        recent_hooks=("1010:447B frame_verify_candidate_present enter=1010:447B",),
        width=WIDTH,
        height=HEIGHT,
        context="tandy",
    )


def test_compose_compare_rgb_keeps_all_three_panels():
    ref = _rgb_frame(b"\x10\x20\x30")
    cand = _rgb_frame(b"\x40\x50\x60")
    diff = diff_rgb_frame(ref, cand)

    compare = compose_compare_rgb(ref, cand, diff, width=WIDTH, height=HEIGHT)
    row_bytes = (WIDTH * 3 + 8) * 3

    assert len(compare) == row_bytes * HEIGHT
    assert compare[:9] == b"\x10\x20\x30" * 3
    assert compare[WIDTH * 3 : WIDTH * 3 + 12] == b"\x20" * 12
    assert compare[WIDTH * 3 + 12 : WIDTH * 3 + 21] == b"\x40\x50\x60" * 3


def test_dump_divergence_writes_compare_png():
    ref_rgb = _rgb_frame(b"\x01\x02\x03")
    cand_rgb = _rgb_frame(b"\x04\x05\x06")
    ref = _sample(side="reference", frame_no=7, rgb=ref_rgb)
    cand = _sample(side="candidate", frame_no=7, rgb=cand_rgb)
    report = "FRAME VERIFY DIVERGENCE\nframe: 7"
    with tempfile.TemporaryDirectory() as tmp:
        dump_dir = Path(tmp)
        config = FrameVerifyConfig(dump_dir=dump_dir, preview_on_diff=False)

        dump_divergence(ref, cand, report, config)

        stem = dump_dir / "frame_00007_tandy"
        assert stem.with_name("frame_00007_tandy_ref.png").exists()
        assert stem.with_name("frame_00007_tandy_hook.png").exists()
        assert stem.with_name("frame_00007_tandy_diff.png").exists()
        assert stem.with_name("frame_00007_tandy_compare.png").exists()
        assert stem.with_name("frame_00007_tandy_compare.png").stat().st_size > 0
