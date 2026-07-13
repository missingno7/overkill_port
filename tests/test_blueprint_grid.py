"""The CE97 blueprint-grid compose is byte-exact + stable.

`overkill.native_video.blueprint.compose_ce97_grid` reproduces the VM's `1010:CE97` output (the cold-
boot blueprint screen's grid background) from the BLUEBITS bank -- proven byte-exact vs the VM directly
(diff 0/64000, see the campaign doc).  This locks the composed grid to that verified reference so the
recovery can't silently regress.
"""
import hashlib
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"

#: sha256 of the byte-exact grid (verified diff 0/64000 vs the VM's CE97 output).
_GRID_SHA = "895a49ce2cb42f18"
_GRID_NZ = 13953


@pytest.mark.skipif(not _BUNDLE.is_file(), reason="needs the static_runtime_bundle (BLUEBITS bank)")
def test_ce97_grid_matches_verified_reference():
    from overkill.native_video.blueprint import compose_ce97_grid
    from overkill.recovered.adapters.flat_memory import MutFlatMemory

    grid = compose_ce97_grid(MutFlatMemory(_BUNDLE.read_bytes()))
    assert grid.shape == (200, 320)
    assert int(np.count_nonzero(grid)) == _GRID_NZ
    assert hashlib.sha256(grid.tobytes()).hexdigest()[:16] == _GRID_SHA
