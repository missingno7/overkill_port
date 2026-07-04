"""Pure domain records for the AFD8 contact-step worker (enemy locomotion)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContactProbeResult:
    """The full AFD8 worker outcome: the record's stepped position, the DS:A43x cell writes and
    the blocked/contact verdict (the original returns it as ZF from ``cmp [A430],0``)."""

    x_word: int          # the record's final +0x02 (un-biased)
    y_word: int          # the record's final +0x04
    blocked: bool        # DS:A430 != 0 (terrain refusal, contact hit, or off-map probe)
    snap_x: int          # DS:A432 -- the pre-step X snapshot
    snap_y: int          # DS:A434 -- the pre-step Y snapshot
    mirror_x: int        # DS:A438 -- snapshot + step delta (== the final X)
    mirror_y: int        # DS:A436 -- snapshot + step delta (== the final Y)
    sample_215a: int     # DS:215A after the probe + handler adjustments
    tile_offset: int     # the handler-adjusted 5073 offset (0xFFFF on the off-map early-out)


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
