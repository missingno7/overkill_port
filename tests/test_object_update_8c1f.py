"""Unit tests for object_update_8c1f (logic_id 0x8A -- the stateless animated sprite).

Byte-exact correctness is covered by verify_native_object_update (L2 304/312, the 8 skips being the
DS:232C == 1Fh BAE1 side-effect path); these lock the one-field animation formula.
"""
from __future__ import annotations

from overkill.recovered.systems.objects import OBJECT_8C1F_SPRITE_BIAS, object_update_8c1f


def test_sprite_is_frame_counter_plus_9d():
    assert object_update_8c1f(0x0000) == 0x009D
    assert object_update_8c1f(0x0010) == 0x00AD
    assert OBJECT_8C1F_SPRITE_BIAS == 0x009D


def test_sprite_wraps_16_bit():
    assert object_update_8c1f(0xFFFF) == (0xFFFF + 0x9D) & 0xFFFF
    assert object_update_8c1f(0xFF70) == 0x000D          # 0xFF70 + 0x9D = 0x1000D -> 0x000D
