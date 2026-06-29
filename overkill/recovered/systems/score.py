"""Pure recovered score system.

The packed-decimal (BCD) score add at 1010:5F0D adds the 16-bit BCD delta in BX
(BL -> byte 0, BH -> byte 1) into the 4-byte score at 2314..2317 with a DAA carry
chain, dropping the carry out of the top byte (it writes only those 4 bytes).

Pure: no ``cpu``/``mem``/segment.  The hook/adapter owns the DOS pointer; this owns
the arithmetic.  This is the byte-exact faithful add (oracle-verified vs the real
5F0D), the score producer the native runtime advances ``NativeGameState``'s score
with.  The death-tail helper ``object_deactivation._run_score_add_5f0d_observed``
now composes this same function (converged 2026-06-29 -- it was a witness-poor
hand-rolled approximation), re-verified byte-exact against the assembled 5F0D and
across a full kill-heavy demo, so there is one verified score producer.
"""
from __future__ import annotations

from overkill.recovered.domain.frame_snapshot import HudLayer

SCORE_BCD_BYTES = 4  # 1010:5F0D writes the four bytes 2314..2317


def bcd_add_score(score_bytes: tuple[int, ...], delta: int) -> tuple[int, ...]:
    """Add the 16-bit BCD ``delta`` (BL->byte0, BH->byte1) into the 4-byte BCD
    ``score_bytes`` with carry, matching 1010:5F0D's ADD/ADC + DAA chain.

    Nibble-wise BCD addition — equivalent to the 8086 ADD+DAA for valid BCD operands,
    which the score and its deltas always are — propagating the carry through bytes
    2 and 3 and dropping the carry out of the top byte (exactly as 5F0D, which writes
    only 4 bytes).  Returns the new four bytes.
    """
    out = list(score_bytes[:SCORE_BCD_BYTES])
    while len(out) < SCORE_BCD_BYTES:
        out.append(0)
    addends = (delta & 0xFF, (delta >> 8) & 0xFF, 0, 0)
    carry = 0
    for i in range(SCORE_BCD_BYTES):
        lo = (out[i] & 0x0F) + (addends[i] & 0x0F) + carry
        hi = (out[i] >> 4) + (addends[i] >> 4)
        carry = 0
        if lo > 9:
            lo -= 10
            hi += 1
        if hi > 9:
            hi -= 10
            carry = 1
        out[i] = ((hi << 4) | lo) & 0xFF
    return tuple(out)


def advance_hud_score(hud: HudLayer, delta: int) -> HudLayer:
    """Native score producer: return the :class:`HudLayer` with its packed-decimal
    score advanced by the BCD ``delta`` (via the 5F0D add :func:`bcd_add_score`),
    counters unchanged.

    ``HudLayer.score_bcd`` is two words (DS:2314 low / 2316 high) = the four 5F0D
    bytes; this packs/unpacks them around the byte-level add.  Pure: the standalone
    runtime advances ``NativeGameState``'s score through this with no VM (the
    dual-mode rule), and verify mode checks the result against the VM-projected HUD.
    """
    low, high = hud.score_bcd
    b0, b1, b2, b3 = bcd_add_score(
        (low & 0xFF, (low >> 8) & 0xFF, high & 0xFF, (high >> 8) & 0xFF), delta
    )
    return HudLayer(counters=hud.counters, score_bcd=(b0 | (b1 << 8), b2 | (b3 << 8)))
