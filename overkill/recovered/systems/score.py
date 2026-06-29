"""Pure recovered score system.

The packed-decimal (BCD) score add at 1010:5F0D adds the 16-bit BCD delta in BX
(BL -> byte 0, BH -> byte 1) into the 4-byte score at 2314..2317 with a DAA carry
chain, dropping the carry out of the top byte (it writes only those 4 bytes).

Pure: no ``cpu``/``mem``/segment.  The hook/adapter owns the DOS pointer; this owns
the arithmetic.  This is the byte-exact faithful add (oracle-verified vs the real
5F0D), the score producer the native runtime advances ``NativeGameState``'s score
with.  (The death-tail helper ``object_deactivation._run_score_add_5f0d_observed``
is a witness-poor single-byte-delta approximation; converging it onto this is a
follow-up that needs the death-tail demo re-verified.)
"""
from __future__ import annotations

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
