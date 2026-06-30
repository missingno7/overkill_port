"""Shared startup graphics assets (asset_codecs.load_shared_startup_assets) vs the live VM buffers.

The startup loads at 1010:0D42-0E0E decode + de-planarize eight shared assets (sprite/directory/block
modes) into CS:[959C..95B8].  This loads them cold and checks each against its live buffer in the
menu-state bundle image.
"""
from __future__ import annotations

import pathlib
import struct

import pytest

from overkill.asset_codecs import (
    SHARED_STARTUP_ASSETS,
    load_shared_asset,
    load_shared_startup_assets,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
OVERKILL = ROOT / "assets" / "OVERKILL"
BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"

CS = 0x1010
# Runtime dest-segment pointer (CS:[...]) for each shared asset -- from the 0D42-0E0E load sites.
DEST_VARS = {
    "1X1.BIC": 0x95A8,
    "2X2.BIC": 0x95AA,
    "2X2C.BIC": 0x95AC,
    "MANEXPL.BIC": 0x95A6,
    "THEND.BIC": 0x95B2,
    "PANEL.ENC": 0x95B4,
    "BLUEBITS.BIC": 0x95B8,
    "SHIP.BIC": 0x959C,
}


@pytest.mark.skipif(not OVERKILL.is_file(), reason="assets/OVERKILL not present")
def test_load_shared_startup_assets_nonempty():
    banks = load_shared_startup_assets(OVERKILL.read_bytes())
    assert set(banks) == {name for name, _ in SHARED_STARTUP_ASSETS}
    assert all(len(v) > 0 for v in banks.values())


@pytest.mark.skipif(not OVERKILL.is_file() or not BUNDLE.is_file(), reason="game data not present")
def test_shared_startup_assets_match_live_buffers():
    container = OVERKILL.read_bytes()
    img = BUNDLE.read_bytes()
    for name, mode in SHARED_STARTUP_ASSETS:
        seg = struct.unpack_from("<H", img, CS * 16 + DEST_VARS[name])[0]
        out = load_shared_asset(container, name, mode)
        assert img[seg * 16 : seg * 16 + len(out)] == out, name
