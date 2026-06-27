"""Corpus grounding: the FrameSnapshot extractor runs on real gameplay memory.

Loads every demo start snapshot and asserts the reconstructed draw list is
well-formed — every drawn sprite is on-screen (culling held) and the list stays
within the object-table bounds. This is robustness/consistency over real memory
(no renderer needed); the full pixel round-trip is enhanced_renderer_plan.md R3.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from dos_re.memory import Memory
from overkill.recovered.adapters.frame_snapshot_adapter import extract_frame_snapshot
from overkill.recovered.domain.frame_snapshot import CameraState
from overkill.recovered.views.object_slots import (
    EFFECT_OBJECT_TABLE_COUNT,
    GAMEPLAY_OBJECT_TABLE_COUNT,
)

DEMOS = Path(__file__).resolve().parents[1] / "artifacts" / "demos"
_MAX_SPRITES = EFFECT_OBJECT_TABLE_COUNT + GAMEPLAY_OBJECT_TABLE_COUNT + 1  # +1 special slot


def _snapshots() -> list[Path]:
    if not DEMOS.is_dir():
        return []
    return sorted(
        d / "snapshot"
        for d in DEMOS.glob("demo_*")
        if (d / "snapshot" / "memory_1mb.bin").is_file()
    )


@pytest.mark.parametrize("snap", _snapshots(), ids=lambda p: p.parent.name)
def test_extractor_is_well_formed_on_corpus_snapshot(snap: Path):
    mem = Memory()
    mem.data[:] = (snap / "memory_1mb.bin").read_bytes()
    cpu_snap = json.loads((snap / "state.json").read_text(encoding="utf-8"))["cpu_snapshot"]
    ds = int(re.search(r"DS=([0-9A-Fa-f]{4})", cpu_snap).group(1), 16)

    fs = extract_frame_snapshot(mem, ds)

    assert isinstance(fs.playfield.camera, CameraState)
    assert len(fs.hud.counters) == 6
    sprites = fs.playfield.sprites
    assert len(sprites) <= _MAX_SPRITES
    # culling held: nothing off-screen survives into the draw list
    assert all(sd.screen_di != 0xFFFF for sd in sprites)
    # coordinates are plausible signed words
    assert all(-0x8000 <= sd.x < 0x8000 and -0x8000 <= sd.y < 0x8000 for sd in sprites)
    # present composition is well-formed: the Tandy demos blit to the B800
    # aperture from a real (non-zero) composited source page.
    assert fs.present.video_page == 0xB800
    assert fs.present.source_page not in (0x0000, 0xFFFF)
