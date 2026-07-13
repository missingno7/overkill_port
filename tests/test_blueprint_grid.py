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


#: the full blueprint compose (grid + all 15 recipe cells) -- grid + cells == the VM's blueprint with
#: ZERO under-draw (verified 2026-07-13; the recipe is now READ from the game's own DS:BD54 table, not a
#: hardcoded 10-cell guess, so all 3 ship schematics + text render).
_BLUEPRINT_SHA = "677230f6f380b888"
_BLUEPRINT_NZ = 22368


@pytest.mark.skipif(not _BUNDLE.is_file(), reason="needs the static_runtime_bundle (BLUEBITS bank)")
def test_ce97_grid_matches_verified_reference():
    from overkill.native_video.blueprint import compose_ce97_grid
    from overkill.recovered.adapters.flat_memory import MutFlatMemory

    grid = compose_ce97_grid(MutFlatMemory(_BUNDLE.read_bytes()))
    assert grid.shape == (200, 320)
    assert int(np.count_nonzero(grid)) == _GRID_NZ
    assert hashlib.sha256(grid.tobytes()).hexdigest()[:16] == _GRID_SHA


@pytest.mark.skipif(not _BUNDLE.is_file(), reason="needs the static_runtime_bundle (BLUEBITS bank)")
def test_full_blueprint_compose_is_stable():
    from overkill.native_video.blueprint import compose_blueprint
    from overkill.recovered.adapters.flat_memory import MutFlatMemory

    bp = compose_blueprint(MutFlatMemory(_BUNDLE.read_bytes()))
    assert bp.shape == (200, 320)
    assert int(np.count_nonzero(bp)) == _BLUEPRINT_NZ
    assert hashlib.sha256(bp.tobytes()).hexdigest()[:16] == _BLUEPRINT_SHA


@pytest.mark.skipif(not _BUNDLE.is_file(), reason="needs the static_runtime_bundle (BLUEBITS bank)")
def test_blueprint_recipe_is_read_from_the_game_table_and_reveals_by_beat():
    """The overlay recipe is READ from DS:BD54 (15 entries, the source CE5F walks), and the reveal
    builds 5 cells per beat -- the three animation steps are grid, +5, +10, +15."""
    import numpy as np
    from overkill.native_video.blueprint import (
        BLUEPRINT_RECIPE_ENTRIES, compose_blueprint, read_blueprint_recipe)
    from overkill.recovered.adapters.flat_memory import MutFlatMemory

    mem = MutFlatMemory(_BUNDLE.read_bytes())
    recipe = read_blueprint_recipe(mem)
    assert len(recipe) == BLUEPRINT_RECIPE_ENTRIES == 15
    assert [cid for cid, _, _ in recipe] == list(range(15))[::3] + list(range(15))[1::3] \
                                            + list(range(15))[2::3]   # beats interleave 0,3,6,9,C / 1,4,.. / 2,5,..
    # each beat reveals 5 more cells; nz strictly grows grid < +5 < +10 < +15
    nzs = [int(np.count_nonzero(compose_blueprint(mem, n))) for n in (0, 5, 10, 15)]
    assert nzs[0] < nzs[1] < nzs[2] < nzs[3]
    assert nzs[1] == 16827        # +5 cells == the VM's early blueprint frame (measured)
