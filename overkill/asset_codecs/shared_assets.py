"""Shared (non-per-level) startup assets -- loaded once, not part of a level's `LEV{n}` set.

The startup sequence at 1010:0D42-0D87 loads the shared graphics banks via 0CD8 (sprite-mode
de-planarize, the same transform as the per-level `G{n}` graphics): the small/large tile banks and the
man-explosion sprite sheet.  Each decodes from the container and de-planarizes to its runtime buffer
(`CS:[95A6..95AC]`).  This loads them VM-free, byte-for-byte identical to those live buffers.

The two further startup loads at 0D8A/0DA3 -- `THEND.BIC` and `PANEL.ENC` -- use the 0CB8 ``bd8``
directory mode (block-mode de-planarize with each item's ``{width, stride}`` written ahead of its data).
"""
from __future__ import annotations

from .container import load_container_asset
from .planar import deplanarize_tandy

#: The shared graphics banks loaded at startup via the sprite-mode de-planarize (1010:0D42-0D87).
SHARED_SPRITE_BANKS = ("1X1.BIC", "2X2.BIC", "2X2C.BIC", "MANEXPL.BIC")

#: The shared directory-mode assets loaded at startup via the 0CB8 bd8 path (1010:0D8A-0DA3).
SHARED_DIRECTORY_ASSETS = ("THEND.BIC", "PANEL.ENC")


def load_shared_sprite_bank(container_data, name: str) -> bytes:
    """Decode + sprite-de-planarize one shared graphics bank (``name`` from :data:`SHARED_SPRITE_BANKS``)."""
    return deplanarize_tandy(load_container_asset(container_data, name), sprite_mode=True)


def load_shared_sprite_banks(container_data) -> dict[str, bytes]:
    """Load every shared startup graphics bank, decoded + de-planarized, keyed by asset name."""
    return {name: load_shared_sprite_bank(container_data, name) for name in SHARED_SPRITE_BANKS}


def load_shared_directory_asset(container_data, name: str) -> bytes:
    """Decode + de-planarize one directory-mode startup asset (block mode, item headers emitted)."""
    return deplanarize_tandy(load_container_asset(container_data, name), sprite_mode=False, emit_item_headers=True)
