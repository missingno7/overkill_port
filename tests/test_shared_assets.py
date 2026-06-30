"""Shared startup graphics banks (asset_codecs.load_shared_sprite_banks) vs the live VM buffers.

The startup loads at 1010:0D42-0D87 sprite-de-planarize 1X1/2X2/2X2C/MANEXPL.BIC into CS:[95A8/95AA/
95AC/95A6].  This loads them cold and checks each against the live buffer in the menu-state bundle image.
"""
from __future__ import annotations

import pathlib
import struct

import pytest

from overkill.asset_codecs import (
    SHARED_SPRITE_BANKS,
    load_shared_sprite_bank,
    load_shared_sprite_banks,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
OVERKILL = ROOT / "assets" / "OVERKILL"
BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"

CS = 0x1010
# Runtime dest-segment pointer for each shared bank (CS:[...]) -- from the 0D42-0D87 load sites.
DEST_VARS = {"1X1.BIC": 0x95A8, "2X2.BIC": 0x95AA, "2X2C.BIC": 0x95AC, "MANEXPL.BIC": 0x95A6}


@pytest.mark.skipif(not OVERKILL.is_file(), reason="assets/OVERKILL not present")
def test_load_shared_sprite_banks_nonempty():
    banks = load_shared_sprite_banks(OVERKILL.read_bytes())
    assert set(banks) == set(SHARED_SPRITE_BANKS)
    assert all(len(v) > 0 for v in banks.values())


@pytest.mark.skipif(not OVERKILL.is_file() or not BUNDLE.is_file(), reason="game data not present")
def test_shared_sprite_banks_match_live_buffers():
    container = OVERKILL.read_bytes()
    img = BUNDLE.read_bytes()
    for name in SHARED_SPRITE_BANKS:
        seg = struct.unpack_from("<H", img, CS * 16 + DEST_VARS[name])[0]
        out = load_shared_sprite_bank(container, name)
        assert img[seg * 16 : seg * 16 + len(out)] == out, name
