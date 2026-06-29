"""Bucket C: native_sprite_draws composes the FrameSnapshot sprite list from a NativeGameState's
object pools, VM-free.  The per-object screen_di is separately gated byte-exact vs the VM by
overkill/probes/verify_native_screen_di.py (35CC +0C, ~17k draws) and the present scan ORDER
(gameplay then effect) is the witnessed-exact order proven in frame_snapshot_adapter; this locks
the walk/active-filter/order/cull composition in a VM-free unit test."""
from __future__ import annotations

from types import SimpleNamespace

from overkill.native_video.projection import PROJECTION_CULL_ENTRY
from overkill.native_video.sprite_compose import native_sprite_draws
from overkill.recovered.domain.object_slots import ObjectPool
from overkill.recovered.views.object_slots import (
    EFFECT_OBJECT_TABLE_BASE,
    GAMEPLAY_OBJECT_TABLE_BASE,
    OBJECT_SLOT_STRIDE,
)


def _slot(active: int, x: int, y: int, sprite: int) -> tuple[int, ...]:
    # active=+00 (word0), x=+02 (word1), y=+04 (word2), sprite_or_state=+08 (word4).
    w = [0] * 5
    w[0], w[1], w[2], w[4] = active, x, y, sprite
    return tuple(w)


def _pool(base: int, slots: tuple) -> ObjectPool:
    return ObjectPool(base=base, stride=OBJECT_SLOT_STRIDE, slots=slots)


def test_native_sprite_draws_walks_both_pools_in_present_order():
    # cols 0x00-0x0F -> 0x1000 (on screen), 0x10-0x1F -> FFFF (cull).  scroll adds to every di.
    column_table = [0x1000] * 0x10 + [PROJECTION_CULL_ENTRY] * 0x10
    scroll = 0x0100
    gameplay = _pool(GAMEPLAY_OBJECT_TABLE_BASE, (
        _slot(1, 0x05, 0x10, 0x0041),   # active -> (0x10>>1)+0x1000+scroll = 0x1108
        _slot(0, 0x06, 0x20, 0x0099),   # inactive -> skipped
        _slot(1, 0x14, 0x30, 0x0077),   # x=0x14 -> col FFFF -> culled
    ))
    effect = _pool(EFFECT_OBJECT_TABLE_BASE, (
        _slot(1, 0x07, 0x40, 0x0042),   # active effect -> (0x40>>1)+0x1000+scroll = 0x1120
    ))
    state = SimpleNamespace(object_pool=gameplay, effect_pool=effect)
    # Gameplay slots first (witnessed present order), then effect; inactive + culled dropped.
    assert native_sprite_draws(state, column_table, scroll) == (
        (0x0041, 0x1108),
        (0x0042, 0x1120),
    )


def test_native_sprite_draws_empty_when_no_active_slots():
    column_table = [0x1000] * 0x20
    gameplay = _pool(GAMEPLAY_OBJECT_TABLE_BASE, (_slot(0, 0x01, 0x02, 0x03),))
    effect = _pool(EFFECT_OBJECT_TABLE_BASE, ())
    state = SimpleNamespace(object_pool=gameplay, effect_pool=effect)
    assert native_sprite_draws(state, column_table, 0x0000) == ()
