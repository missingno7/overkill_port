"""CONVERGENCE slice A gate: the VM-less engine's code-segment dependency is exactly `native_rom`.

If a cold image whose CS code segment has been ZEROED except the native_rom ranges plays byte-exact
(DGROUP game state) against the full bundle-seeded image, then those ~580 bytes are the entire
code-segment dependency -- the 1 MB exe-derived bundle's code is droppable, replaced by this extract.
"""
from __future__ import annotations

import pathlib

import pytest

from overkill.native_frame import advance_gameplay_frame_97b2
from overkill.recovered.adapters.cold_level_start import build_cold_level_start_image
from overkill.recovered.adapters.native_rom import (
    NATIVE_ROM_SIZE,
    apply_native_rom,
    extract_native_rom,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"
CONTAINER = ROOT / "assets" / "OVERKILL"
DS_BASE = 0x25CC * 16
_HAVE = BUNDLE.is_file() and CONTAINER.exists()


def test_native_rom_is_small():
    assert NATIVE_ROM_SIZE < 700           # ~580 bytes -- the whole code-segment footprint


@pytest.mark.skipif(not _HAVE, reason="bundle / container not present")
def test_reduced_code_segment_plays_byte_exact():
    bundle = BUNDLE.read_bytes()
    container = CONTAINER.read_bytes()
    from scripts.play_native import make_level_assets
    level_assets = make_level_assets(container, bundle)
    frames = 120

    def run(reduce_code: bool):
        img = build_cold_level_start_image(bundle, 0, container)
        if reduce_code:
            apply_native_rom(img, extract_native_rom(bundle))   # zero CS, keep only native_rom
        for _ in range(frames):
            advance_gameplay_frame_97b2(img, isr_ticks=2, level_assets=level_assets, menu_pick=0)
        return bytes(img.data[DS_BASE:DS_BASE + 0x10000])

    full = run(False)
    reduced = run(True)
    diff = [o for o in range(0x10000) if full[o] != reduced[o]]
    assert not diff, (f"DGROUP diverged at {len(diff)} cells with the code segment reduced to "
                      f"native_rom ({NATIVE_ROM_SIZE} bytes): first "
                      + ", ".join(f"{o:04X}" for o in diff[:8]))
