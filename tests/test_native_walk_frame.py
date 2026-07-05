"""The image-is-the-state seam (native_walk_frame): the fired-shot sync (the dual-state fix)."""
from __future__ import annotations

import pathlib

import pytest

from overkill.recovered.adapters.flat_memory import MutFlatMemory
from overkill.native_walk_frame import (
    DS,
    GAMEPLAY_POOL_BASE,
    RECORD_STRIDE,
    sync_new_gameplay_records,
)
from overkill.recovered.domain.object_slots import ObjectPool

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"


def _pool_with(records: dict[int, dict[int, int]]) -> ObjectPool:
    slots = []
    for i in range(0x22):
        words = [0] * (RECORD_STRIDE // 2)
        for off, val in records.get(i, {}).items():
            words[off // 2] = val
        slots.append(tuple(words))
    return ObjectPool(base=GAMEPLAY_POOL_BASE, stride=RECORD_STRIDE, slots=tuple(slots))


@pytest.mark.skipif(not BUNDLE.is_file(), reason="static runtime bundle not present")
def test_new_dataclass_records_flow_into_the_image():
    image = MutFlatMemory(BUNDLE.read_bytes())
    # a freshly fired shot in dataclass slot 3 (the image slot is inactive)
    shot = {0x00: 1, 0x02: 0x60, 0x04: 0x40, 0x16: 4, 0x18: 0x0002, 0x1C: 0x10}
    pool = _pool_with({3: shot})
    rec = GAMEPLAY_POOL_BASE + 3 * RECORD_STRIDE
    assert image.rw(DS, rec) == 0
    assert sync_new_gameplay_records(image, pool) == 1
    for off, val in shot.items():
        assert image.rw(DS, rec + off) == val


@pytest.mark.skipif(not BUNDLE.is_file(), reason="static runtime bundle not present")
def test_image_owned_records_are_never_clobbered():
    image = MutFlatMemory(BUNDLE.read_bytes())
    rec = GAMEPLAY_POOL_BASE + 5 * RECORD_STRIDE
    image.ww(DS, rec + 0x00, 1)          # the image already owns slot 5 (a walked enemy shot)
    image.ww(DS, rec + 0x02, 0x1234)
    # the dataclass side has a STALE copy at the same slot -- must NOT overwrite the image's
    pool = _pool_with({5: {0x00: 1, 0x02: 0x9999 & 0xFFFF}})
    assert sync_new_gameplay_records(image, pool) == 0
    assert image.rw(DS, rec + 0x02) == 0x1234
