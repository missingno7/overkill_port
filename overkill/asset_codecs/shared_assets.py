"""Shared (non-per-level) startup assets -- the graphics loaded once at boot, not part of a `LEV{n}` set.

The startup sequence at 1010:0D42-0E0E loads eight shared graphics assets, each decoded from the
container and de-planarized to its runtime buffer (`CS:[959C..95B8]`).  The de-planarize *mode* depends
on the load entry used (the 0CC8/0CD8/0CB8 mode flags):

* **sprite**    (0CD8, bd6=1): mask-interleaved -- `1X1`, `2X2`, `2X2C`, `MANEXPL`;
* **directory** (0CB8, bd8=1): block pixels with per-item `{width,stride}` headers -- `THEND`,
  `PANEL` (an `.ENC`), `BLUEBITS`;
* **block**     (0CC8, bd6=0): opaque pixels -- `SHIP`.

Each loads VM-free, byte-for-byte identical to its live buffer (tests/test_shared_assets.py).
"""
from __future__ import annotations

from .container import load_container_asset
from .planar import deplanarize_tandy

SHARED_MODE_SPRITE = "sprite"
SHARED_MODE_BLOCK = "block"
SHARED_MODE_DIRECTORY = "directory"

#: The startup shared-asset loads (1010:0D42-0E0E), in order, each with its de-planarize mode.
SHARED_STARTUP_ASSETS = (
    ("1X1.BIC", SHARED_MODE_SPRITE),
    ("2X2.BIC", SHARED_MODE_SPRITE),
    ("2X2C.BIC", SHARED_MODE_SPRITE),
    ("MANEXPL.BIC", SHARED_MODE_SPRITE),
    ("THEND.BIC", SHARED_MODE_DIRECTORY),
    ("PANEL.ENC", SHARED_MODE_DIRECTORY),
    ("BLUEBITS.BIC", SHARED_MODE_DIRECTORY),
    ("SHIP.BIC", SHARED_MODE_BLOCK),
)


def load_shared_asset(container_data, name: str, mode: str) -> bytes:
    """Decode + de-planarize one shared startup asset in the given ``mode`` (sprite/block/directory)."""
    decoded = load_container_asset(container_data, name)
    if mode == SHARED_MODE_SPRITE:
        return deplanarize_tandy(decoded, sprite_mode=True)
    if mode == SHARED_MODE_DIRECTORY:
        return deplanarize_tandy(decoded, sprite_mode=False, emit_item_headers=True)
    if mode == SHARED_MODE_BLOCK:
        return deplanarize_tandy(decoded, sprite_mode=False)
    raise ValueError(f"unknown shared-asset mode {mode!r}")


def load_shared_startup_assets(container_data) -> dict[str, bytes]:
    """Load every startup shared graphics asset, decoded + de-planarized, keyed by asset name."""
    return {name: load_shared_asset(container_data, name, mode) for name, mode in SHARED_STARTUP_ASSETS}
