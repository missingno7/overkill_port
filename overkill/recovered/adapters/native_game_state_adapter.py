"""Project the live VM memory into a :class:`NativeGameState` (the verify-mode reference).

This is the one place the native-runtime aggregate state meets VM memory.  It
composes the already-recovered per-state projections (``read_object_pool`` /
``read_camera_state`` / ``read_hud_layer``) into the single aggregate the verify
harness compares the standalone runtime's output against (§1.2).  The standalone
runtime produces the SAME :class:`NativeGameState` with no VM; the pure
:func:`native_game_state_mismatches` checks they agree.
"""
from __future__ import annotations

from overkill.recovered.adapters.frame_snapshot_adapter import (
    OVERKILL_CODE_SEGMENT,
    read_camera_state,
    read_hud_layer,
)
from overkill.recovered.domain.native_game_state import NativeGameState
from overkill.recovered.views.object_slots import (
    GAMEPLAY_OBJECT_TABLE_BASE,
    GAMEPLAY_OBJECT_TABLE_COUNT,
    read_object_pool,
)


def read_native_game_state(mem, ds: int, cs: int = OVERKILL_CODE_SEGMENT) -> NativeGameState:
    """Build the verify-mode reference :class:`NativeGameState` from live VM memory.

    Snapshots the gameplay object pool (DS:``GAMEPLAY_OBJECT_TABLE_BASE``), the
    camera view origin, and the HUD/score, each through its recovered byte-faithful
    reader.  ``cs`` is accepted for symmetry with the other native projections /
    future render state; the three states read here are all DS-relative.
    """
    ds &= 0xFFFF
    return NativeGameState(
        object_pool=read_object_pool(
            mem, ds, GAMEPLAY_OBJECT_TABLE_BASE, GAMEPLAY_OBJECT_TABLE_COUNT
        ),
        camera=read_camera_state(mem, ds),
        hud=read_hud_layer(mem, ds),
    )
