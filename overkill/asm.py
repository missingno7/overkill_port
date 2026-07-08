"""Re-export of ``dos_re.asm`` under the historical ``overkill.asm`` import path.

These 8086-style arithmetic/string helpers were originally written here, then
promoted verbatim into ``dos_re.asm`` when the framework was extracted (they
turned out to be genuinely game-agnostic, not OVERKILL-specific). This module
is kept only so existing ``from overkill.asm import ...`` call sites don't
need to change; the implementation lives in ``dos_re.asm``.
"""
from __future__ import annotations

from dos_re.asm import (
    _add_mem_byte,
    _add_mem_word,
    _add_reg16,
    _and_mem_byte,
    _and_mem_word,
    _cmp_byte,
    _cmp_word,
    _dec_mem_byte_preserve_cf,
    _dec_mem_word_preserve_cf,
    _dec_reg16_preserve_cf,
    _ega_aperture_overlap,
    _ega_next_scanline_di,
    _inc_mem_byte_preserve_cf,
    _inc_mem_word_preserve_cf,
    _inc_reg16_preserve_cf,
    _inc_reg8_preserve_cf,
    _out_dx_al,
    _out_dx_ax,
    _rep_movsb,
    _rep_movsw,
    _rep_stosb,
    _rep_stosw_preserve_flags,
    _stosw,
    _sub_mem_word,
    _sub_reg16,
    _test_word,
    _xor_al_al,
    loop_count,
)

__all__ = [
    "_add_mem_byte", "_add_mem_word", "_add_reg16", "_and_mem_byte", "_and_mem_word",
    "_cmp_byte", "_cmp_word", "_dec_mem_byte_preserve_cf", "_dec_mem_word_preserve_cf",
    "_dec_reg16_preserve_cf", "_ega_aperture_overlap", "_ega_next_scanline_di",
    "_inc_mem_byte_preserve_cf", "_inc_mem_word_preserve_cf", "_inc_reg16_preserve_cf",
    "_inc_reg8_preserve_cf", "_out_dx_al", "_out_dx_ax", "_rep_movsb", "_rep_movsw",
    "_rep_stosb", "_rep_stosw_preserve_flags", "_stosw", "_sub_mem_word", "_sub_reg16",
    "_test_word", "_xor_al_al", "loop_count",
]
