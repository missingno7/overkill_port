"""Unit tests for the sprite-draw collector's VM-independent logic.

The full byte-exact / completeness check runs against the live game in
``overkill/probes/verify_sprite_extractor.py``; these cover the lifecycle and the
frame-assembly logic headlessly.
"""
from __future__ import annotations

import numpy as np

from overkill.recovered.adapters.sprite_draw_extractor import (
    CapturedSprite,
    SpriteBlock,
    SpriteDrawCollector,
)
from overkill.recovered.systems.sprite_textures import decode_masked_sprite


class _FakeRep:
    def __init__(self, handler):
        self.handler = handler


class _FakeRegistry:
    def __init__(self, ips=()):
        self.replacements = {(0x1010, ip): _FakeRep(lambda cpu: None) for ip in ips}


def _tex():
    return decode_masked_sprite(b"\x00" * 16, words_per_row=4, rows=1)


def test_take_frame_drops_empty_sprites():
    c = SpriteDrawCollector(_FakeRegistry())
    empty = CapturedSprite(1, 5, 0, 0x100, (0x100,), 0x768E)
    drawn = CapturedSprite(2, 6, 0, 0x100, (0x100,), 0x768E)
    drawn.blocks.append(SpriteBlock(di=0x100, compositor_ip=0x2F81, texture=_tex()))
    c._sprites = [empty, drawn]
    out = c.take_frame()
    assert [s.identity for s in out] == [2]
    assert c._sprites == []  # reset for the next frame


def test_take_frame_derives_offscreen_anchor_from_blocks():
    # A tiled object whose +0C anchor is off the top: screen_di becomes the topmost block.
    c = SpriteDrawCollector(_FakeRegistry())
    spr = CapturedSprite(3, 0x73, 0, 0xFFFF, (), 0x3657)
    spr.blocks += [SpriteBlock(0x2050, 0x2FB6, _tex()), SpriteBlock(0x2030, 0x2FB6, _tex())]
    c._sprites = [spr]
    out = c.take_frame()
    assert out[0].screen_di == 0x2030


def test_install_wraps_and_uninstall_restores_handlers():
    reg = _FakeRegistry(ips=(0x768E, 0x2F81))
    originals = {k: rep.handler for k, rep in reg.replacements.items()}
    c = SpriteDrawCollector(reg)
    c.install()
    assert all(reg.replacements[k].handler is not originals[k] for k in originals)
    c.uninstall()
    assert all(reg.replacements[k].handler is originals[k] for k in originals)


def test_missing_registry_entries_are_skipped_not_fatal():
    c = SpriteDrawCollector(_FakeRegistry())  # no entries at all
    c.install()  # must not raise
    c.uninstall()


def test_captured_texture_is_background_independent():
    # The block carries a decoded texture (pixels/opaque), not raw page bytes.
    tex = _tex()
    assert tex.pixels.shape == (1, 16)
    assert tex.opaque.dtype == np.bool_
