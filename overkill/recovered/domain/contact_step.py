"""Pure domain records for the AFD8 contact-step worker (enemy locomotion)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContactStepState:
    """The mutable state one ``B022`` step handler threads: the (biased) object position, the
    ``5073`` tile offset ``dx`` and the ``DS:215A`` X sub-tile sample counter."""

    x_word: int          # ss:[bp+2] -- the A278-biased X during the probe window
    y_word: int          # ss:[bp+4]
    tile_offset: int     # dx -- the 5073 coordinate->tile offset, handler-adjusted (+/-0xD, +/-1)
    sample_215a: int     # DS:215A -- the X sub-tile sample counter (low nibble)
    blocked: bool = False        # DS:A430 != 0 -- terrain block or contact hit
    mirror_dx_x: int = 0         # net +/- applied to DS:A438 (the X mirror snapshot)
    mirror_dx_y: int = 0         # net +/- applied to DS:A436 (the Y mirror snapshot)
