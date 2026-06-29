"""VM-free unit tests for the pure 1010:AA2B first-level object-logic dispatch.

Pins the recovered draw-layer -> handler routing (``object_logic_dispatch_aa2b``): the eight
defined draw layers (0-7), the shared EFAE second-level dispatcher on layers 2 and 4, and the
fail-loud out-of-range guard.  Also checks the adapter's kind -> CS:AA36 IP map covers every
recovered kind (the demo-level table match is ``verify_native_object_logic_dispatch_aa2b``).
"""
from __future__ import annotations

import pytest

from overkill.gameplay.object_behaviors import _AA2B_HANDLER_IP_BY_KIND
from overkill.recovered.domain.object_behaviors import ObjectLogicDispatchAA2B
from overkill.recovered.systems.objects import (
    OBJECT_LOGIC_DISPATCH_AA2B_BY_LAYER,
    object_logic_dispatch_aa2b,
)


def test_aa2b_routes_each_draw_layer():
    expected = (
        "postmove_prelude_bc45", "tracked_logic_ad04", "family_dispatch_efae", "action_44af",
        "family_dispatch_efae", "collision_tail_aac2", "logic_ab10", "handler_c3f8",
    )
    for layer, kind in enumerate(expected):
        assert object_logic_dispatch_aa2b(layer) == ObjectLogicDispatchAA2B(kind)


def test_aa2b_layers_2_and_4_share_family_dispatch():
    assert object_logic_dispatch_aa2b(2).kind == object_logic_dispatch_aa2b(4).kind == "family_dispatch_efae"


def test_aa2b_out_of_range_draw_layer_fails_loud():
    assert len(OBJECT_LOGIC_DISPATCH_AA2B_BY_LAYER) == 8
    with pytest.raises(ValueError):
        object_logic_dispatch_aa2b(8)
    with pytest.raises(ValueError):
        object_logic_dispatch_aa2b(0x0F)


def test_aa2b_ip_map_covers_every_recovered_kind():
    # Every routing kind must have an adapter IP so the hook cross-check never KeyErrors.
    for kind in set(OBJECT_LOGIC_DISPATCH_AA2B_BY_LAYER):
        assert kind in _AA2B_HANDLER_IP_BY_KIND
