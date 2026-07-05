"""The per-frame counter cascade (frame_loop.advance_frame_counters_5f61)."""
from __future__ import annotations

import pytest

from overkill.recovered.systems.frame_loop import (
    FRAME_COUNTER_CELLS,
    advance_frame_counters_5f61,
)


def _zero():
    return {off: 0 for off in FRAME_COUNTER_CELLS}


def test_every_frame_counters_advance_with_their_moduli():
    c = advance_frame_counters_5f61(_zero())
    assert c[0x2324] == 1                 # parity xor
    assert (c[0x2326], c[0x2328], c[0x232A], c[0x232C], c[0x232E], c[0x2330]) == (1, 1, 1, 1, 1, 1)
    # masks: 2326 mod4, 2328 mod8, 232A mod16, 232C mod32, 232E mod64, 2330 mod128
    for off, mask, n in ((0x2326, 3, 8), (0x2328, 7, 16), (0x232E, 0x3F, 0x80)):
        v = _zero()
        for _ in range(n):
            v = advance_frame_counters_5f61(v)
        assert v[off] == (n & mask)


def test_the_a7a0_sub_bank_ticks_only_every_fourth_frame():
    c = _zero()
    a7a0 = []
    for _ in range(16):
        c = advance_frame_counters_5f61(c)
        a7a0.append(c[0xA7A0])
    # 2332 gates: A7A0 advances once per 4 frames -> 4 increments over 16 frames
    assert c[0xA7A0] == 4
    assert a7a0 == [0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4]
    # the mod-5 233A also lives in the /4 sub-bank (an earlier inline hardcoded it to 0)
    assert c[0x233A] == 4


def test_the_wave_oscillator_is_gated_on_2328_and_flips_2342():
    # drive to just before 2328 wraps to 7, with 2342 = 1 and 2344 poised to flip
    c = _zero()
    c[0x2342] = 1
    c[0x2344] = 1          # inc branch: 2344 -> 2 triggers the neg
    c[0x2328] = 7          # the oscillator gate
    out = advance_frame_counters_5f61(c)
    assert out[0x2344] == 2 and out[0x2342] == 0xFFFF     # flipped +1 -> -1
    assert out[0x2348] == 1
    # when 2328 != 7 the oscillator is untouched
    c2 = _zero()
    c2[0x2342] = 1
    c2[0x2328] = 3
    assert advance_frame_counters_5f61(c2)[0x2342] == 1


def test_the_wave_cleared_branch_is_rejected():
    with pytest.raises(ValueError):
        advance_frame_counters_5f61(_zero(), enemies_alive=False)
