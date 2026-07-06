"""Verify the native FULL-PANEL compose is byte-exact vs the VM's own B800 panel region.

Uses the L1 (cold_start_full) walk-shadow cache frame 0 as the oracle: its pre-state holds the
whole machine -- the VM-composed B800 page AND every DGROUP/CS state cell the panel draws from.
The native side decodes PANEL.ENC from the container (proven byte-equal to the VM's decoded
panel segment), assembles the compose inputs through the SAME adapter play_native uses
(``compose_hud_panel_from_image``), and byte-compares the panel byte columns (0x6C..0xA0 of
every row) against the oracle page.

Usage:
    python -m overkill.probes.verify_native_hud_panel [demo_name]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DEMO = "demo_cold_start_full_20260705_123645"
DEFAULT_BUDGET = 20000        # the cache key the L1 gate records under
B800_BASE = 0xB8000
PANEL_BYTE_COL = 0x6C         # pixel col 216
ROW_BYTES = 0xA0
BANKS = 4
BANK_STRIDE = 0x2000
ROWS_PER_BANK = 50


def _panel_bytes(page: np.ndarray) -> np.ndarray:
    """Every panel byte (cols 0x6C..0x9F of each of the 200 interleaved rows)."""
    out = []
    for bank in range(BANKS):
        for row in range(ROWS_PER_BANK):
            base = bank * BANK_STRIDE + row * ROW_BYTES
            out.append(page[base + PANEL_BYTE_COL: base + ROW_BYTES])
    return np.concatenate(out)


def main(argv) -> int:
    demo_name = argv[0] if argv else DEFAULT_DEMO
    from overkill.probes._shadow_cache import (cache_path_for, demo_key, iter_cached_frames,
                                               load_cache)
    from overkill.asset_codecs.container import load_container_asset
    from overkill.asset_codecs.planar import deplanarize_tandy
    from overkill.recovered.adapters.flat_memory import MutFlatMemory
    from overkill.recovered.adapters.hud_panel_state import (compose_hud_panel_from_image,
                                                             read_hud_dir_table, read_hud_font)

    class _Demo:
        demo_dir = str(ROOT / "artifacts" / "demos" / demo_name)

    cached = load_cache(cache_path_for(_Demo()), demo_key(_Demo()), DEFAULT_BUDGET)
    if cached is None:
        print(f"RESULT: SKIP -- no walk-shadow cache for {demo_name} (run the walk gate once)")
        return 0
    panel_source = np.frombuffer(
        deplanarize_tandy(load_container_asset((ROOT / "assets" / "OVERKILL").read_bytes(),
                                               "PANEL.ENC"),
                          sprite_mode=False, emit_item_headers=True), dtype=np.uint8)
    for pre, post, sp in iter_cached_frames(cached):
        image = MutFlatMemory(pre)
        # the native decode must byte-equal the VM's decoded panel segment -- assert, don't assume
        seg = image.rw(0x1010, 0x95B4)
        buf = np.frombuffer(bytes(image.data), dtype=np.uint8)
        vm_panel = buf[seg * 16: seg * 16 + len(panel_source)]
        if not np.array_equal(vm_panel, panel_source):
            print("RESULT: FAIL -- decoded PANEL.ENC differs from the VM panel segment")
            return 1
        native_page = compose_hud_panel_from_image(
            image, panel_source=panel_source,
            dir_table=read_hud_dir_table(image), font=read_hud_font(image))
        vm_page = buf[B800_BASE:B800_BASE + 0x10000]
        nat_b, vm_b = _panel_bytes(native_page), _panel_bytes(vm_page)
        diff = int(np.count_nonzero(nat_b != vm_b))
        print(f"panel bytes compared: {nat_b.size}  diff: {diff}")
        if diff:
            bad = np.where(nat_b != vm_b)[0][:10]
            print("  first diffs at panel-byte idx:", bad.tolist())
            print("RESULT: FAIL -- the native panel compose diverges from the VM page")
            return 1
        print("RESULT: PASS -- the native FULL-PANEL compose is byte-exact vs the VM page "
              "(frame 0, natively-decoded PANEL.ENC)")
        return 0
    print("RESULT: FAIL -- empty cache")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
