"""CONVERGENCE slice B: the two object-pool seed slot tables (DS:0x32CA, DS:0x8D12) are computable,
not exe-derived data.

Both were believed to need extraction like the level/plane ROMs; measurement showed each is exactly a
compiler-emitted literal for a simple arithmetic sequence.  These tests lock the formulas against the
bundle's actual stored tables -- the byte-exact proof that zero exe bytes are needed for either.
"""
from __future__ import annotations

import pathlib
import struct

import pytest

from overkill.recovered.systems.frame_loop import (
    GAMEPLAY_SEED_COUNT,
    GAMEPLAY_SEED_SLOT_TABLE_8D12,
    OBJECT_SEED_COUNT,
    OBJECT_SEED_SLOT_TABLE_32CA,
    gameplay_seed_slot_table_8d12,
    object_seed_slot_table_32ca,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"
DS = 0x25CC

_HAVE = BUNDLE.is_file()


def _read_table(bundle: bytes, base: int, count: int) -> dict:
    linear = DS * 16
    return {cx: struct.unpack_from("<H", bundle, linear + base + cx * 2)[0]
            for cx in range(1, count + 1)}


@pytest.mark.skipif(not _HAVE, reason="bundle not present")
def test_object_seed_slot_table_32ca_matches_the_stored_table():
    bundle = BUNDLE.read_bytes()
    assert object_seed_slot_table_32ca() == _read_table(bundle, OBJECT_SEED_SLOT_TABLE_32CA,
                                                         OBJECT_SEED_COUNT)


@pytest.mark.skipif(not _HAVE, reason="bundle not present")
def test_gameplay_seed_slot_table_8d12_matches_the_stored_table():
    bundle = BUNDLE.read_bytes()
    assert gameplay_seed_slot_table_8d12() == _read_table(bundle, GAMEPLAY_SEED_SLOT_TABLE_8D12,
                                                           GAMEPLAY_SEED_COUNT)
