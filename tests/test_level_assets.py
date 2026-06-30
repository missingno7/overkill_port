"""Per-level asset mapping (asset_codecs.overkill_level_assets) -- shape + real-container validation.

The mapping comes from the level-init data tables (DS:14C0 MAP pointers, DS:14E8 {graphics, blocks}
list walked by 1010:0E9C).  The real-file test is the proof: every per-level asset name for all six
levels must resolve to a container asset that decodes -- a wrong pattern would miss the container.
"""
from __future__ import annotations

import pathlib

import pytest

from overkill.asset_codecs import (
    LEVEL_COUNT,
    load_container_asset,
    overkill_level_assets,
    parse_overkill_container,
)
from overkill.asset_codecs.level_assets import ROLE_BLOCKS, ROLE_GRAPHICS, ROLE_MAP

OVERKILL = pathlib.Path(__file__).resolve().parent.parent / "assets" / "OVERKILL"


def test_level_assets_shape():
    assets = overkill_level_assets(0)
    assert [a.role for a in assets] == [ROLE_MAP, ROLE_BLOCKS, ROLE_GRAPHICS]
    assert [a.name for a in assets] == ["LEV0MAP.BIC", "LEV0BLX.BIC", "G0.BIC"]
    assert [a.name for a in overkill_level_assets(5)] == ["LEV5MAP.BIC", "LEV5BLX.BIC", "G5.BIC"]


def test_level_out_of_range_raises():
    with pytest.raises(ValueError):
        overkill_level_assets(-1)
    with pytest.raises(ValueError):
        overkill_level_assets(LEVEL_COUNT)


@pytest.mark.skipif(not OVERKILL.is_file(), reason="assets/OVERKILL not present")
def test_every_level_asset_is_in_the_container_and_decodes():
    data = OVERKILL.read_bytes()
    names = {e.name for e in parse_overkill_container(data)}
    for level in range(LEVEL_COUNT):
        for asset in overkill_level_assets(level):
            assert asset.name in names, asset.name
            assert len(load_container_asset(data, asset.name)) > 0, asset.name
