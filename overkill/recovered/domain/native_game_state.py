"""The source-level aggregate game state the standalone native runtime owns (Bucket C).

``NativeGameState`` is the VM-free state the recovered systems read/write and the
standalone loop carries frame to frame.  In ``--mode verify`` the native state is
compared field-by-field against a VM-projected ``NativeGameState`` (built by the
adapter layer); zero mismatches at every checkpoint across every demo is the §1.2
done-condition.  This module owns the state *shape* and the *pure* comparison core;
the VM projection (the one place this meets VM memory) lives in
``adapters/native_game_state_adapter.py``.

Pure: no ``cpu``/``mem``/segment access.  It composes the already-recovered
sub-state structures (``ObjectPool`` + ``CameraState`` + ``HudLayer``) so the
comparison is the dual-mode rule's verify half — the standalone runtime produces
the same structures the VM projection does, and this checks they agree.
"""
from __future__ import annotations

from dataclasses import dataclass

from overkill.recovered.domain.frame_snapshot import CameraState, HudLayer
from overkill.recovered.domain.object_slots import ObjectPool


@dataclass(frozen=True, slots=True)
class NativeGameState:
    """The aggregate native game state, grown as more §1.2 states are recovered.

    Today it carries the states whose native mirrors are proven byte-faithful: the
    ``special_pool`` (the leading view-anchor slot) + the gameplay ``object_pool`` +
    the ``effect_pool`` (the 0x38-stride object tables the present scan walks, in the
    witnessed-exact special-then-gameplay-then-effect draw order), the ``camera`` view
    origin, and the ``hud`` (status counters + ``score_bcd`` = the §1.2 ScoreState).
    The standalone runtime produces this with no VM; verify mode compares it against
    the VM-projected state via :func:`native_game_state_mismatches`.
    """

    special_pool: ObjectPool
    object_pool: ObjectPool
    effect_pool: ObjectPool
    camera: CameraState
    hud: HudLayer


def _pool_mismatches(
    label: str, n_pool: ObjectPool, r_pool: ObjectPool, out: list
) -> None:
    """Append every ``(label, field, native, reference)`` where two native ObjectPools
    diverge -- layout first, then byte-faithful per-slot/per-word."""
    if (n_pool.base, n_pool.stride) != (r_pool.base, r_pool.stride):
        out.append((label, "layout", (n_pool.base, n_pool.stride), (r_pool.base, r_pool.stride)))
        return
    for i in range(max(len(n_pool.slots), len(r_pool.slots))):
        ns = n_pool.slots[i] if i < len(n_pool.slots) else ()
        rs = r_pool.slots[i] if i < len(r_pool.slots) else ()
        for w in range(max(len(ns), len(rs))):
            nv = ns[w] if w < len(ns) else None
            rv = rs[w] if w < len(rs) else None
            if nv != rv:
                out.append((label, f"slot[{i}].word[{w << 1:#x}]", nv, rv))


def native_game_state_mismatches(
    native: NativeGameState, reference: NativeGameState
) -> tuple[tuple[str, str, object, object], ...]:
    """Pure verify-mode comparison: every ``(state, field, native, reference)`` where
    ``native`` diverges from ``reference``.

    Both sides are native structures, so this is VM-free — the standalone runtime's
    output is compared against the VM-projected reference (built by the adapter)
    through this one core.  An empty result means the native state mirrors the
    reference at this checkpoint (the §1.2 invariant).  Comparison is byte-faithful
    for the object pool (every word of every slot, including still-unknown bytes).
    """
    out: list[tuple[str, str, object, object]] = []

    # CameraState (signed view origin).
    if native.camera.x != reference.camera.x:
        out.append(("camera", "x", native.camera.x, reference.camera.x))
    if native.camera.y != reference.camera.y:
        out.append(("camera", "y", native.camera.y, reference.camera.y))

    # HudLayer: the status counters + the packed-decimal score.
    n_counters, r_counters = native.hud.counters, reference.hud.counters
    for i in range(max(len(n_counters), len(r_counters))):
        nv = n_counters[i] if i < len(n_counters) else None
        rv = r_counters[i] if i < len(r_counters) else None
        if nv != rv:
            out.append(("hud", f"counter[{i}]", nv, rv))
    for j in range(2):
        nv = native.hud.score_bcd[j] if j < len(native.hud.score_bcd) else None
        rv = reference.hud.score_bcd[j] if j < len(reference.hud.score_bcd) else None
        if nv != rv:
            out.append(("hud", f"score_bcd[{j}]", nv, rv))

    # The object pools (special view-anchor, then gameplay, then effect -- draw order):
    # layout first, then byte-faithful per-slot/per-word.
    _pool_mismatches("special_pool", native.special_pool, reference.special_pool, out)
    _pool_mismatches("object_pool", native.object_pool, reference.object_pool, out)
    _pool_mismatches("effect_pool", native.effect_pool, reference.effect_pool, out)
    return tuple(out)
