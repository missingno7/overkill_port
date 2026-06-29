"""VM-free unit tests for the pure 1010:BEC5 collision-variant family classifier.

Pins the variant -> reaction-family routing (``bec5_collision_variant_family``): the BD0D-then-A8C2
family (05/06/07/08/0C), the A8C2-without-BD0D variant (09), the sprite-0033 variant-2 path (02),
and the owner-linked/no-op fallback (every other logic id).  The demo-level confirmation is the
fallback cross-check in the BEC5 handler hook, exercised by collision frame-replays.
"""
from __future__ import annotations

from overkill.recovered.domain.collision import CollisionVariantDispatchBEC5
from overkill.recovered.systems.collision import bec5_collision_variant_family


def test_bd0d_then_a8c2_family():
    for variant in (0x05, 0x06, 0x07, 0x08, 0x0C):
        assert bec5_collision_variant_family(variant) == CollisionVariantDispatchBEC5("bd0d_then_a8c2")


def test_singleton_families():
    assert bec5_collision_variant_family(0x09) == CollisionVariantDispatchBEC5("a8c2_no_bd0d")
    assert bec5_collision_variant_family(0x02) == CollisionVariantDispatchBEC5("sprite_variant_2")


def test_owner_linked_or_noop_fallback():
    # Every logic id outside the named families falls back to the owner-link/no-op path.
    for variant in (0x00, 0x01, 0x03, 0x04, 0x0A, 0x0B, 0x0D, 0x10, 0x33, 0x82):
        assert bec5_collision_variant_family(variant).kind == "owner_linked_or_noop"
