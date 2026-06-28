"""EGA (mode-1) planar renderer — lifted source-like logic.

These are the EGA composite/expand/copy/present routines that used to live
inline in ``overkill/hooks.py``.  They are pure ``run_*(cpu)`` functions plus
their private bit-spread helpers; the address-bound ``@registry.replace``
wrappers stay in ``hooks.py`` and delegate here, matching the
``rendering/tandy.py`` pattern.  Bodies were relocated verbatim.
"""
from __future__ import annotations

from dos_re.cpu import CF, DF, SF, ZF
from dos_re.memory import EGA_APERTURE, EGA_PLANE_STRIDE, EGA_PLANE_WINDOW
from ..asm import (
    _add_mem_word, _add_reg16, _cmp_word, _dec_reg16_preserve_cf,
    _ega_aperture_overlap, _ega_next_scanline_di,
    _inc_reg16_preserve_cf, _inc_reg8_preserve_cf, _out_dx_al, _out_dx_ax,
    _rep_movsb, _rep_movsw, _rep_stosb, _sub_mem_word, _sub_reg16,
    _test_word, _xor_al_al,
)
from ..hook_wrappers.common import (
    call_hook_like_near_call as _call_hook_like_near_call,
    call_installed_hook_like_near_call as _call_installed_hook_like_near_call,
    jump_installed_hook_boundary as _jump_installed_hook_boundary,
    self_disable_if_patched as _self_disable_if_patched,
)
from ..hook_wrappers.runtime_signatures import *  # noqa: F401,F403 - _SIG_* live-byte signatures
from .coordinates import object_row_address_mode1_2580



def _ega_spread_word_two_bits_mask(word: int) -> tuple[int, int]:
    """Spread a 16-bit source word through the 409D two-bit mask chain."""
    al = word & 0xFF
    ah = (word >> 8) & 0xFF
    dl = 0xFF
    for _ in range(2):
        cf = 1
        new_al = ((cf << 7) | (al >> 1)) & 0xFF; cf = al & 1; al = new_al
        new_ah = ((cf << 7) | (ah >> 1)) & 0xFF; cf = ah & 1; ah = new_ah
        new_dl = ((cf << 7) | (dl >> 1)) & 0xFF; cf = dl & 1; dl = new_dl
    return ((ah << 8) | al) & 0xFFFF, dl & 0xFF


def _ega_spread_word_two_bits_data(word: int) -> tuple[int, int]:
    """Spread a 16-bit source word through the 409D two-bit data chain."""
    al = word & 0xFF
    ah = (word >> 8) & 0xFF
    dl = 0
    for _ in range(2):
        cf = al & 1
        al = (al >> 1) & 0xFF
        new_ah = ((cf << 7) | (ah >> 1)) & 0xFF; cf = ah & 1; ah = new_ah
        new_dl = ((cf << 7) | (dl >> 1)) & 0xFF; cf = dl & 1; dl = new_dl
    return ((ah << 8) | al) & 0xFFFF, dl & 0xFF


def _ega_spread_word_bits_mask(word: int, bits: int) -> tuple[int, int]:
    al = word & 0xFF
    ah = (word >> 8) & 0xFF
    dl = 0xFF
    for _ in range(bits):
        cf = 1
        new_al = ((cf << 7) | (al >> 1)) & 0xFF; cf = al & 1; al = new_al
        new_ah = ((cf << 7) | (ah >> 1)) & 0xFF; cf = ah & 1; ah = new_ah
        new_dl = ((cf << 7) | (dl >> 1)) & 0xFF; cf = dl & 1; dl = new_dl
    return ((ah << 8) | al) & 0xFFFF, dl & 0xFF


def _ega_spread_word_bits_data(word: int, bits: int) -> tuple[int, int]:
    al = word & 0xFF
    ah = (word >> 8) & 0xFF
    dl = 0
    for _ in range(bits):
        cf = al & 1
        al = (al >> 1) & 0xFF
        new_ah = ((cf << 7) | (ah >> 1)) & 0xFF; cf = ah & 1; ah = new_ah
        new_dl = ((cf << 7) | (dl >> 1)) & 0xFF; cf = dl & 1; dl = new_dl
    return ((ah << 8) | al) & 0xFFFF, dl & 0xFF


def _run_ega_compact_spread_composite_bits(cpu, *, bits: int) -> None:
    s = cpu.s
    mem = cpu.mem
    rows = s.bp & 0xFFFF
    if rows == 0:
        rows = 0x10000

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    dh = (s.dx >> 8) & 0xFF
    ax = s.ax & 0xFFFF
    dl = s.dx & 0xFF
    sd = -2 if cpu.get_flag(DF) else 2

    for _ in range(rows):
        mask_word = mem.rw(ds, si)
        si = (si + sd) & 0xFFFF
        mask_ax, mask_dl = _ega_spread_word_bits_mask(mask_word, bits)
        mem.ww(es, di, mem.rw(es, di) & mask_ax)
        mem.wb(es, (di + 0x02) & 0xFFFF, mem.rb(es, (di + 0x02) & 0xFFFF) & mask_dl)

        data_word = mem.rw(ds, si)
        si = (si + sd) & 0xFFFF
        ax, dl = _ega_spread_word_bits_data(data_word, bits)
        mem.ww(es, di, mem.rw(es, di) | ax)
        mem.wb(es, (di + 0x02) & 0xFFFF, mem.rb(es, (di + 0x02) & 0xFFFF) | dl)

        old_di = di
        di = (di + 0x34) & 0xFFFF
        cpu.set_add_flags(old_di, 0x34, old_di + 0x34, 16)

        old_bp = s.bp & 0xFFFF
        s.bp = (old_bp - 1) & 0xFFFF
        cpu.set_sub_flags(old_bp, 1, old_bp - 1, 16)

    s.ax = ax & 0xFFFF
    s.dx = ((dh << 8) | (dl & 0xFF)) & 0xFFFF
    s.si = si
    s.di = di
    s.ds = mem.rw(s.cs & 0xFFFF, 0x9596)
    s.ip = cpu.pop()


def _ega_spread_byte_rcr_mask(byte: int, bits: int) -> int:
    al = byte & 0xFF
    ah = 0xFF
    for _ in range(bits):
        cf = 1
        new_al = ((cf << 7) | (al >> 1)) & 0xFF; cf = al & 1; al = new_al
        new_ah = ((cf << 7) | (ah >> 1)) & 0xFF; cf = ah & 1; ah = new_ah
    return ((ah << 8) | al) & 0xFFFF


def _ega_spread_byte_rcr_data(byte: int, bits: int) -> int:
    al = byte & 0xFF
    ah = 0
    for _ in range(bits):
        cf = al & 1
        al = (al >> 1) & 0xFF
        new_ah = ((cf << 7) | (ah >> 1)) & 0xFF; cf = ah & 1; ah = new_ah
    return ((ah << 8) | al) & 0xFFFF


def _run_ega_compact_byte_spread_composite_bits(cpu, *, bits: int) -> None:
    s = cpu.s
    mem = cpu.mem
    rows = s.cx & 0xFFFF
    if rows == 0:
        rows = 0x10000

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    sd = -1 if cpu.get_flag(DF) else 1
    ax = s.ax & 0xFFFF
    old_di = di

    for _ in range(rows):
        mask = _ega_spread_byte_rcr_mask(mem.rb(ds, si), bits)
        si = (si + sd) & 0xFFFF
        for k in (0x00, 0x1A, 0x34, 0x4E):
            mem.ww(es, (di + k) & 0xFFFF, mem.rw(es, (di + k) & 0xFFFF) & mask)
        for k in (0x00, 0x1A, 0x34, 0x4E):
            ax = _ega_spread_byte_rcr_data(mem.rb(ds, si), bits)
            si = (si + sd) & 0xFFFF
            mem.ww(es, (di + k) & 0xFFFF, mem.rw(es, (di + k) & 0xFFFF) | ax)
        old_di = di
        di = (di + 0x68) & 0xFFFF
        cpu.set_add_flags(old_di, 0x68, old_di + 0x68, 16)

    s.ax = ax & 0xFFFF
    s.si = si
    s.di = di
    s.cx = 0
    s.ds = mem.rw(s.cs & 0xFFFF, 0x9596)
    s.ip = cpu.pop()


def _ega_spread_byte_rcl_mask(byte: int, bits: int) -> int:
    ah = byte & 0xFF
    al = 0xFF
    for _ in range(bits):
        cf = 1
        new_ah = ((ah << 1) | cf) & 0xFF; cf = (ah >> 7) & 1; ah = new_ah
        new_al = ((al << 1) | cf) & 0xFF; cf = (al >> 7) & 1; al = new_al
    return ((ah << 8) | al) & 0xFFFF


def _ega_spread_byte_rcl_data(byte: int, bits: int) -> int:
    ah = byte & 0xFF
    al = 0
    for _ in range(bits):
        cf = (ah >> 7) & 1
        ah = ((ah << 1) & 0xFF)
        new_al = ((al << 1) | cf) & 0xFF; cf = (al >> 7) & 1; al = new_al
    return ((ah << 8) | al) & 0xFFFF


def _run_ega_compact_byte_spread_left_composite_bits(cpu, *, bits: int) -> None:
    s = cpu.s
    mem = cpu.mem
    rows = s.cx & 0xFFFF
    if rows == 0:
        rows = 0x10000

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    ax = s.ax & 0xFFFF
    old_si = si

    for _ in range(rows):
        row_si = si
        mask = _ega_spread_byte_rcl_mask(mem.rb(ds, row_si), bits)
        for k in (0x00, 0x1A, 0x34, 0x4E):
            mem.ww(es, (di + k) & 0xFFFF, mem.rw(es, (di + k) & 0xFFFF) & mask)
        for source_off, k in ((1, 0x00), (2, 0x1A), (3, 0x34), (4, 0x4E)):
            ax = _ega_spread_byte_rcl_data(mem.rb(ds, (row_si + source_off) & 0xFFFF), bits)
            mem.ww(es, (di + k) & 0xFFFF, mem.rw(es, (di + k) & 0xFFFF) | ax)
        old_di = di
        di = (di + 0x68) & 0xFFFF
        cpu.set_add_flags(old_di, 0x68, old_di + 0x68, 16)
        old_si = si
        si = (si + 0x05) & 0xFFFF
        cpu.set_add_flags(old_si, 0x05, old_si + 0x05, 16)

    s.ax = ax & 0xFFFF
    s.si = si
    s.di = di
    s.cx = 0
    s.ds = mem.rw(s.cs & 0xFFFF, 0x9596)
    s.ip = cpu.pop()


def run_ega_compact_spread_composite_40d7(cpu):
    """Replace compact EGA four-bit spread compositor at 1010:40D7."""
    _run_ega_compact_spread_composite_bits(cpu, bits=4)


def run_ega_compact_spread_composite_412b(cpu):
    """Replace compact EGA six-bit spread compositor at 1010:412B."""
    _run_ega_compact_spread_composite_bits(cpu, bits=6)


def run_ega_compact_spread_composite_409d(cpu):
    """Replace compact EGA two-bit spread compositor at 1010:409D.

    Reached from the 7746 compact layer helper in EGA-ish dispatch tables.  BP is
    the row counter (normally 8).  Each row consumes one mask word and one data
    word, spreads them through the original two-step RCR/SHR chains, updates a
    word plus byte at ES:DI/ES:DI+2, advances DI by 34h, and decrements BP.
    """
    s = cpu.s
    mem = cpu.mem
    rows = s.bp & 0xFFFF
    if rows == 0:
        rows = 0x10000

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    dh = (s.dx >> 8) & 0xFF
    ax = s.ax & 0xFFFF
    dl = s.dx & 0xFF

    for _ in range(rows):
        mask_word = mem.rw(ds, si)            # LODSW
        si = (si + (-2 if cpu.get_flag(DF) else 2)) & 0xFFFF
        mask_ax, mask_dl = _ega_spread_word_two_bits_mask(mask_word)
        mem.ww(es, di, mem.rw(es, di) & mask_ax)
        mem.wb(es, (di + 0x02) & 0xFFFF, mem.rb(es, (di + 0x02) & 0xFFFF) & mask_dl)

        data_word = mem.rw(ds, si)            # LODSW
        si = (si + (-2 if cpu.get_flag(DF) else 2)) & 0xFFFF
        ax, dl = _ega_spread_word_two_bits_data(data_word)
        mem.ww(es, di, mem.rw(es, di) | ax)
        mem.wb(es, (di + 0x02) & 0xFFFF, mem.rb(es, (di + 0x02) & 0xFFFF) | dl)

        old_di = di
        di = (di + 0x34) & 0xFFFF
        cpu.set_add_flags(old_di, 0x34, old_di + 0x34, 16)

        old_bp = s.bp & 0xFFFF
        s.bp = (old_bp - 1) & 0xFFFF
        cpu.set_sub_flags(old_bp, 1, old_bp - 1, 16)

    s.ax = ax & 0xFFFF
    s.dx = ((dh << 8) | (dl & 0xFF)) & 0xFFFF
    s.si = si
    s.di = di
    # CX is intentionally preserved; this routine loops on BP, not LOOP/CX.
    s.ds = mem.rw(s.cs & 0xFFFF, 0x9596)
    s.ip = cpu.pop()


def run_ega_compact_byte_masked_composite_2193(cpu):
    """Replace EGA compact byte masked compositor at 1010:2193."""
    s = cpu.s
    mem = cpu.mem
    rows = s.cx & 0xFFFF
    if rows == 0:
        rows = 0x10000

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    ah = (s.ax >> 8) & 0xFF
    al = s.ax & 0xFF
    old_si = si

    for _ in range(rows):
        row_si = si
        mask = mem.rb(ds, row_si)
        for source_off in (1, 2, 3, 4):
            al = (mem.rb(es, di) & mask) | mem.rb(ds, (row_si + source_off) & 0xFFFF)
            mem.wb(es, di, al & 0xFF)
            old_di = di
            di = (di + 0x1A) & 0xFFFF
            cpu.set_add_flags(old_di, 0x1A, old_di + 0x1A, 16)
        old_si = si
        si = (si + 0x05) & 0xFFFF
        cpu.set_add_flags(old_si, 0x05, old_si + 0x05, 16)

    s.ax = ((ah << 8) | (al & 0xFF)) & 0xFFFF
    s.si = si
    s.di = di
    s.cx = 0
    s.ds = mem.rw(s.cs & 0xFFFF, 0x9596)
    s.ip = cpu.pop()


def run_ega_compact_byte_spread_left_composite_238d(cpu):
    """Replace left-shift EGA byte-spread compact compositor at 1010:238D."""
    _run_ega_compact_byte_spread_left_composite_bits(cpu, bits=3)


def run_ega_compact_byte_spread_left_composite_2410(cpu):
    """Replace left-shift EGA byte-spread compact compositor at 1010:2410."""
    _run_ega_compact_byte_spread_left_composite_bits(cpu, bits=2)


def run_ega_compact_byte_spread_left_composite_247e(cpu):
    """Replace left-shift EGA byte-spread compact compositor at 1010:247E."""
    _run_ega_compact_byte_spread_left_composite_bits(cpu, bits=1)


def run_ega_compact_byte_spread_composite_21d6(cpu):
    """Replace EGA byte-spread compact compositor at 1010:21D6."""
    _run_ega_compact_byte_spread_composite_bits(cpu, bits=1)


def run_ega_compact_byte_spread_composite_2223(cpu):
    """Replace EGA byte-spread compact compositor at 1010:2223."""
    _run_ega_compact_byte_spread_composite_bits(cpu, bits=2)


def run_ega_compact_byte_spread_composite_2285(cpu):
    """Replace EGA byte-spread compact compositor at 1010:2285."""
    _run_ega_compact_byte_spread_composite_bits(cpu, bits=3)


def run_ega_compact_byte_spread_composite_22fc(cpu):
    """Replace EGA byte-spread compact compositor at 1010:22FC.

    The compact layer helper 7746 reaches this mode-1 target for an 8-row sprite
    phase.  Each row consumes one mask byte and four data bytes, spreads each byte
    through four RCR/SHR steps into a 16-bit word, updates four EGA chunks spaced
    by 1Ah, advances DI by 68h, and LOOPs on CX.
    """
    s = cpu.s
    mem = cpu.mem
    rows = s.cx & 0xFFFF
    if rows == 0:
        rows = 0x10000

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    sd = -1 if cpu.get_flag(DF) else 1
    ax = s.ax & 0xFFFF
    old_di = di

    for _ in range(rows):
        mask = _ega_spread_byte_rcr_mask(mem.rb(ds, si), 4)  # LODSB + mask chain
        si = (si + sd) & 0xFFFF
        for k in (0x00, 0x1A, 0x34, 0x4E):
            mem.ww(es, (di + k) & 0xFFFF, mem.rw(es, (di + k) & 0xFFFF) & mask)
        for k in (0x00, 0x1A, 0x34, 0x4E):
            ax = _ega_spread_byte_rcr_data(mem.rb(ds, si), 4)
            si = (si + sd) & 0xFFFF
            mem.ww(es, (di + k) & 0xFFFF, mem.rw(es, (di + k) & 0xFFFF) | ax)
        old_di = di
        di = (di + 0x68) & 0xFFFF
        cpu.set_add_flags(old_di, 0x68, old_di + 0x68, 16)

    s.ax = ax & 0xFFFF
    s.si = si
    s.di = di
    s.cx = 0
    s.ds = mem.rw(s.cs & 0xFFFF, 0x9596)
    s.ip = cpu.pop()


def run_ega_layer_or_inverted_composite_10b7(cpu):
    """Replace EGA layer inverted-mask OR compositor at 1010:10B7."""
    s = cpu.s
    mem = cpu.mem
    rows = s.cx & 0xFFFF
    if rows == 0:
        rows = 0x10000

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    ax = s.ax & 0xFFFF
    old_si = si

    for _ in range(rows):
        row_si = si
        ax = (~mem.rw(ds, row_si)) & 0xFFFF
        for k in (0x00, 0x1A, 0x34, 0x4E):
            mem.ww(es, (di + k) & 0xFFFF, mem.rw(es, (di + k) & 0xFFFF) | ax)
        ax = (~mem.rw(ds, (row_si + 0x02) & 0xFFFF)) & 0xFFFF
        for k in (0x02, 0x1C, 0x36, 0x50):
            mem.ww(es, (di + k) & 0xFFFF, mem.rw(es, (di + k) & 0xFFFF) | ax)
        old_di = di
        di = (di + 0x68) & 0xFFFF
        cpu.set_add_flags(old_di, 0x68, old_di + 0x68, 16)
        old_si = si
        si = (si + 0x14) & 0xFFFF
        cpu.set_add_flags(old_si, 0x14, old_si + 0x14, 16)

    s.ax = ax & 0xFFFF
    s.si = si
    s.di = di
    s.cx = 0
    s.ds = mem.rw(s.cs & 0xFFFF, 0x9596)
    s.ip = cpu.pop()


def run_ega_layer_masked_composite_103c(cpu):
    """Replace the EGA layer masked compositor at 1010:103C.

    This is reached from the shared 75F5 layer-sprite dispatch in mode 1
    (EGA). Per row it updates four destination chunks spaced by 1Ah bytes.
    Each chunk has two destination words: the first word uses source mask
    [SI+00] and data words [SI+04/08/0C/10]; the second uses source mask
    [SI+02] and data words [SI+06/0A/0E/12].  The row then advances SI by
    14h and LOOPs.  The original restores DS from CS:[9596] and returns near.
    """
    s = cpu.s
    mem = cpu.mem
    rows = s.cx & 0xFFFF
    if rows == 0:
        rows = 0x10000

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    ax = s.ax & 0xFFFF
    old_si = si

    for _ in range(rows):
        row_si = si
        row_di = di
        mask0 = mem.rw(ds, row_si)
        mask1 = mem.rw(ds, (row_si + 0x02) & 0xFFFF)
        for data0, data1 in ((0x04, 0x06), (0x08, 0x0A), (0x0C, 0x0E), (0x10, 0x12)):
            ax = (mem.rw(es, row_di) & mask0) | mem.rw(ds, (row_si + data0) & 0xFFFF)
            mem.ww(es, row_di, ax & 0xFFFF)
            ax = (mem.rw(es, (row_di + 0x02) & 0xFFFF) & mask1) | mem.rw(ds, (row_si + data1) & 0xFFFF)
            mem.ww(es, (row_di + 0x02) & 0xFFFF, ax & 0xFFFF)
            row_di = (row_di + 0x1A) & 0xFFFF
        di = row_di
        old_si = si
        si = (si + 0x14) & 0xFFFF

    # Live flags come from the final ADD SI,14h before the last LOOP.
    cpu.set_add_flags(old_si, 0x14, old_si + 0x14, 16)
    s.ax = ax & 0xFFFF
    s.si = si
    s.di = di
    s.cx = 0
    s.ds = mem.rw(s.cs & 0xFFFF, 0x9596)
    s.ip = cpu.pop()


def run_ega_spaced_word_composite_1aeb(cpu):
    """Replace the hot EGA spaced-word composite loop at 1010:1AEB.

    Each row updates four words separated by 1Ah bytes in ES.  Source words are
    laid out as one mask word followed by four data words.  The original
    restores DS from CS:[9596] and returns near after the loop.
    """
    s = cpu.s
    mem = cpu.mem
    rows = s.cx & 0xFFFF
    if rows == 0:
        rows = 0x10000

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    ax = s.ax & 0xFFFF
    old_si = si

    for _ in range(rows):
        row_si = si
        mask = mem.rw(ds, row_si)
        for data_off in (2, 4, 6, 8):
            ax = (mem.rw(es, di) & mask) | mem.rw(ds, (row_si + data_off) & 0xFFFF)
            mem.ww(es, di, ax)
            di = (di + 0x1A) & 0xFFFF
        old_si = si
        si = (si + 0x0A) & 0xFFFF

    cpu.set_add_flags(old_si, 0x0A, old_si + 0x0A, 16)
    s.ax = ax & 0xFFFF
    s.si = si
    s.di = di
    s.cx = 0
    s.ds = mem.rw(s.cs & 0xFFFF, 0x9596)
    s.ip = cpu.pop()


def run_ega_spread_masked_composite_1d1b(cpu):
    """Replace the hot EGA bit-spread masked composite loop at 1010:1D1B.

    This is the sibling of the 1AEB jump-table sprite variant (both are reached
    through the ``jmp cs:[bx]`` dispatcher at 1010:76E2 and return near to the
    object-scan caller after restoring DS from CS:[9596]).  Per row it writes
    four 3-byte chunks (a word at DI plus a byte at DI+2) spaced 1Ah bytes apart,
    advancing DI by 68h between rows.

    The source layout is one mask word followed by four data words (SI += 0Ah per
    row).  Unlike 1AEB, each word is first spread through the original RCR/SHR bit
    chains before it is combined with the destination:

      * mask word: ``DL=FF`` then 4x {STC; RCR AL; RCR AH; RCR DL}; the resulting
        AX (word) and DL (byte) are AND-ed into all four chunks of the row,
        clearing the pixels the sprite will overwrite;
      * each of the four data words: ``DL=0`` then 4x {SHR AL; RCR AH; RCR DL};
        the resulting AX/DL are OR-ed into that chunk, painting the pixels.

    The chains are replicated exactly (same primitives, same order) so registers,
    flags and written memory match the interpreted ASM; only the per-instruction
    fetch/decode/dispatch overhead is removed.  Verified bit-identical at runtime
    by the differential hook verifier (see ``DEFAULT_STOPS`` 1D1B near_ret) and by
    ``test_ega_spread_masked_composite_1d1b_hook_matches_interpreted_asm``.
    """
    s = cpu.s
    mem = cpu.mem
    rows = s.cx & 0xFFFF
    if rows == 0:
        rows = 0x10000

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    dh = (s.dx >> 8) & 0xFF

    rw, ww, rb, wb = mem.rw, mem.ww, mem.rb, mem.wb

    ax = s.ax & 0xFFFF
    dl = 0
    old_di = di
    # Destination chunk offsets within a row: word at +k, byte at +k+2.
    chunk = (0x00, 0x1A, 0x34, 0x4E)

    for _ in range(rows):
        # Mask word: STC-seeded RCR chain, then AND into all four chunks.
        al = rw(ds, si) & 0xFF
        ah = (rw(ds, si) >> 8) & 0xFF
        si = (si + 2) & 0xFFFF
        dl = 0xFF
        for _ in range(4):
            cf = 1
            nal = ((cf << 7) | (al >> 1)) & 0xFF; cf = al & 1; al = nal
            nah = ((cf << 7) | (ah >> 1)) & 0xFF; cf = ah & 1; ah = nah
            ndl = ((cf << 7) | (dl >> 1)) & 0xFF; cf = dl & 1; dl = ndl
        mask_ax = ((ah << 8) | al) & 0xFFFF
        mask_dl = dl
        for k in chunk:
            ww(es, (di + k) & 0xFFFF, rw(es, (di + k) & 0xFFFF) & mask_ax)
            wb(es, (di + k + 2) & 0xFFFF, rb(es, (di + k + 2) & 0xFFFF) & mask_dl)

        # Four data words: SHR-seeded RCR chain, then OR into the matching chunk.
        for k in chunk:
            al = rw(ds, si) & 0xFF
            ah = (rw(ds, si) >> 8) & 0xFF
            si = (si + 2) & 0xFFFF
            dl = 0
            for _ in range(4):
                cf = al & 1; al = (al >> 1) & 0xFF
                nah = ((cf << 7) | (ah >> 1)) & 0xFF; cf = ah & 1; ah = nah
                ndl = ((cf << 7) | (dl >> 1)) & 0xFF; cf = dl & 1; dl = ndl
            ax = ((ah << 8) | al) & 0xFFFF
            ww(es, (di + k) & 0xFFFF, rw(es, (di + k) & 0xFFFF) | ax)
            wb(es, (di + k + 2) & 0xFFFF, rb(es, (di + k + 2) & 0xFFFF) | dl)

        old_di = di
        di = (di + 0x68) & 0xFFFF

    # Live flags at the near return come from the final ADD DI,68h.
    cpu.set_add_flags(old_di, 0x68, old_di + 0x68, 16)
    s.ax = ax & 0xFFFF
    s.dx = ((dh << 8) | (dl & 0xFF)) & 0xFFFF
    s.si = si
    s.di = di
    s.cx = 0
    s.ds = mem.rw(s.cs & 0xFFFF, 0x9596)
    s.ip = cpu.pop()


def run_ega_spread_masked_composite_wide_13e7(cpu):
    """Replace the hot wide EGA bit-spread masked composite loop at 1010:13E7.

    This is the five-byte-wide sibling of the 1D1B variant: another target of the
    ``jmp cs:[bx]`` sprite dispatcher (here at 1010:7620) that returns near to the
    object-scan caller after restoring DS from CS:[9596].  Where 1D1B writes a
    word+byte (3-byte) chunk, 1D1B's wide sibling writes a word+word+byte (5-byte)
    chunk: a word at DI, a word at DI+2, and a byte at DI+4.  Four chunks per row
    are spaced 1Ah bytes apart (DI += 68h between rows).

    Per row the source is read with explicit ``MOV r,DS:[SI+disp]`` (not LODSW), as
    one mask pair followed by four data pairs, so SI advances by 14h per row:

      * mask: AX=[SI], BX=[SI+2], ``DL=FF`` then 4x {STC; RCR AL; RCR AH; RCR BL;
        RCR BH; RCR DL}; AX/BX/DL are AND-ed into all four chunks of the row;
      * data k (k=0..3): AX=[SI+4+4k], BX=[SI+6+4k], ``DL=0`` then 4x {SHR AL;
        RCR AH; RCR BL; RCR BH; RCR DL}; AX/BX/DL are OR-ed into chunk k.

    The RCR/SHR chains are replicated exactly (same primitives/order over the
    AL/AH/BL/BH/DL register chain) so registers, flags and written memory match the
    interpreted ASM; only the per-instruction fetch/decode/dispatch overhead is
    removed.  The live flags at the near return come from the final ``ADD SI,14h``
    (textually the last arithmetic before LOOP).  Verified bit-identical by the
    differential hook verifier (``DEFAULT_STOPS`` 13E7 near_ret) and by
    ``test_ega_spread_masked_composite_wide_13e7_hook_matches_interpreted_asm``.
    """
    s = cpu.s
    mem = cpu.mem
    rows = s.cx & 0xFFFF
    if rows == 0:
        rows = 0x10000

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    dh = (s.dx >> 8) & 0xFF

    rw, ww, rb, wb = mem.rw, mem.ww, mem.rb, mem.wb

    ax = s.ax & 0xFFFF
    bx = s.bx & 0xFFFF
    dl = 0
    old_si = si
    # Destination chunk offsets within a row: word at +k, word at +k+2, byte +k+4.
    chunk = (0x00, 0x1A, 0x34, 0x4E)

    for _ in range(rows):
        # Mask pair: STC-seeded RCR chain over AL/AH/BL/BH/DL, AND into all chunks.
        word = rw(ds, si)
        al = word & 0xFF; ah = (word >> 8) & 0xFF
        word = rw(ds, (si + 2) & 0xFFFF)
        bl = word & 0xFF; bh = (word >> 8) & 0xFF
        dl = 0xFF
        for _ in range(4):
            cf = 1
            n = ((cf << 7) | (al >> 1)) & 0xFF; cf = al & 1; al = n
            n = ((cf << 7) | (ah >> 1)) & 0xFF; cf = ah & 1; ah = n
            n = ((cf << 7) | (bl >> 1)) & 0xFF; cf = bl & 1; bl = n
            n = ((cf << 7) | (bh >> 1)) & 0xFF; cf = bh & 1; bh = n
            n = ((cf << 7) | (dl >> 1)) & 0xFF; cf = dl & 1; dl = n
        mask_ax = ((ah << 8) | al) & 0xFFFF
        mask_bx = ((bh << 8) | bl) & 0xFFFF
        mask_dl = dl
        for k in chunk:
            ww(es, (di + k) & 0xFFFF, rw(es, (di + k) & 0xFFFF) & mask_ax)
            ww(es, (di + k + 2) & 0xFFFF, rw(es, (di + k + 2) & 0xFFFF) & mask_bx)
            wb(es, (di + k + 4) & 0xFFFF, rb(es, (di + k + 4) & 0xFFFF) & mask_dl)

        # Four data pairs: SHR-seeded RCR chain, then OR into the matching chunk.
        for j, k in enumerate(chunk):
            so = 4 + j * 4
            word = rw(ds, (si + so) & 0xFFFF)
            al = word & 0xFF; ah = (word >> 8) & 0xFF
            word = rw(ds, (si + so + 2) & 0xFFFF)
            bl = word & 0xFF; bh = (word >> 8) & 0xFF
            dl = 0
            for _ in range(4):
                cf = al & 1; al = (al >> 1) & 0xFF
                n = ((cf << 7) | (ah >> 1)) & 0xFF; cf = ah & 1; ah = n
                n = ((cf << 7) | (bl >> 1)) & 0xFF; cf = bl & 1; bl = n
                n = ((cf << 7) | (bh >> 1)) & 0xFF; cf = bh & 1; bh = n
                n = ((cf << 7) | (dl >> 1)) & 0xFF; cf = dl & 1; dl = n
            ax = ((ah << 8) | al) & 0xFFFF
            bx = ((bh << 8) | bl) & 0xFFFF
            ww(es, (di + k) & 0xFFFF, rw(es, (di + k) & 0xFFFF) | ax)
            ww(es, (di + k + 2) & 0xFFFF, rw(es, (di + k + 2) & 0xFFFF) | bx)
            wb(es, (di + k + 4) & 0xFFFF, rb(es, (di + k + 4) & 0xFFFF) | dl)

        di = (di + 0x68) & 0xFFFF
        old_si = si
        si = (si + 0x14) & 0xFFFF

    # Live flags at the near return come from the final ADD SI,14h.
    cpu.set_add_flags(old_si, 0x14, old_si + 0x14, 16)
    s.ax = ax & 0xFFFF
    s.bx = bx & 0xFFFF
    s.dx = ((dh << 8) | (dl & 0xFF)) & 0xFFFF
    s.si = si
    s.di = di
    s.cx = 0
    s.ds = mem.rw(s.cs & 0xFFFF, 0x9596)
    s.ip = cpu.pop()


def run_ega_spaced_copy_29c6(cpu):
    """Replace the hot EGA 16-row spaced copy routine at 1010:29C6.

    If DI is FFFFh the original returns immediately.  Otherwise it copies four
    3-byte chunks per row for 16 rows, spacing destination chunks by 1Ah bytes.
    """
    s = cpu.s
    mem = cpu.mem
    _cmp_word(cpu, s.di & 0xFFFF, 0xFFFF)
    if (s.di & 0xFFFF) == 0xFFFF:
        s.ip = cpu.pop()
        return

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    s.bx = 0x0017
    old_di = di

    for _row in range(16):
        for _col in range(4):
            mem.ww(es, di, mem.rw(ds, si))
            si = (si + 2) & 0xFFFF
            di = (di + 2) & 0xFFFF
            mem.wb(es, di, mem.rb(ds, si))
            si = (si + 1) & 0xFFFF
            di = (di + 1) & 0xFFFF
            old_di = di
            di = (di + 0x0017) & 0xFFFF

    cpu.set_add_flags(old_di, 0x0017, old_di + 0x0017, 16)
    s.si = si
    s.di = di
    s.cx = 0
    s.ip = cpu.pop()


def run_ega_source_spaced_copy_2ab9(cpu):
    """Replace EGA object draw copy routine at 1010:2AB9.

    The original calls the mode-specific 5A36 row-address helper, then copies
    four 3-byte chunks per row for 16 rows, spacing source chunks by 1Ah bytes.
    """
    s = cpu.s
    mem = cpu.mem
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF
    cs = s.cs & 0xFFFF

    _call_hook_like_near_call(cpu, object_row_address_mode1_2580, 0x2ABC)
    if s.ip != 0x2ABC:
        return
    # The near-call push already left 0x2ABC in the scratch slot below SP, so the
    # stack image matches a real CALL/RET without an extra fixup write here.

    mem.ww(ss, (bp + 0x0C) & 0xFFFF, s.ax)
    _cmp_word(cpu, s.ax, 0xFFFF)
    if (s.ax & 0xFFFF) == 0xFFFF:
        s.ip = cpu.pop()
        return

    _add_reg16(cpu, 0, mem.rw(s.ds & 0xFFFF, 0x234C))
    mem.ww(ss, (bp + 0x0C) & 0xFFFF, s.ax)
    s.si = s.ax & 0xFFFF
    s.di = mem.rw(ss, (bp + 0x0E) & 0xFFFF)
    s.es = mem.rw(cs, 0x9596)
    s.ds = mem.rw(cs, 0x9598)
    s.bx = 0x0017

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    old_si = si

    for _row in range(16):
        for _col in range(4):
            mem.ww(es, di, mem.rw(ds, si))
            si = (si + 2) & 0xFFFF
            di = (di + 2) & 0xFFFF
            mem.wb(es, di, mem.rb(ds, si))
            si = (si + 1) & 0xFFFF
            di = (di + 1) & 0xFFFF
            old_si = si
            si = (si + 0x0017) & 0xFFFF

    cpu.set_add_flags(old_si, 0x0017, old_si + 0x0017, 16)
    s.si = si
    s.di = di
    s.cx = 0
    s.ds = mem.rw(cs, 0x9596)
    s.ip = cpu.pop()


def run_ega_row_driver_27eb(cpu):
    if _self_disable_if_patched(cpu, 0x27EB, _SIG_27EB, "overkill_ega_row_driver_27eb"):
        return
    """Fuse the hot EGA mode-1 row driver at 1010:27EB.

    This is the interpreted outer loop that used to call the already-hooked
    helpers thousands of times during EGA startup/menu asset expansion:

        27EB  push cx                  ; remaining source rows
        27EC  cmp  cs:[0BD6],0
        27F4  push si / call 2932 ...  ; optional transparency-mask row
        2802  mov  cs:[5BA6],di
        2807  mov  di,5AF4h
        280A  mov  bp,0004h
        280D  ... temp-row load
        2824  ... temp expansion/copy, LOOP back to 27EB or JMP 27D9

    The narrow 280D/2824/2932 hooks are still the source of truth.  This driver
    removes the repeated interpreter dispatch and hook-boundary crossings around
    them without inventing new renderer semantics.
    """
    cs = cpu.s.cs & 0xFFFF
    mem = cpu.mem

    while True:
        outer_cx = cpu.s.cx & 0xFFFF
        # 27EB PUSH CX.  The 2824 block consumes this with its final POP CX.
        cpu.push(outer_cx)

        _cmp_word(cpu, mem.rw(cs, 0x0BD6), 0)
        if not cpu.get_flag(ZF):
            # 27F4 PUSH SI; 27F5 MOV CX,CS:[5B9C]
            saved_si = cpu.s.si & 0xFFFF
            cpu.push(saved_si)
            width = mem.rw(cs, 0x5B9C)
            loop_count = width if width != 0 else 0x10000
            cpu.s.cx = width & 0xFFFF

            while loop_count:
                # 27FA PUSH CX; 27FB CALL 2932; 27FE POP CX; 27FF LOOP 27FA.
                cpu.push(cpu.s.cx)
                _call_installed_hook_like_near_call(cpu, (0x1010, 0x2932), run_ega_transparency_mask_2932, 0x27FE)
                if (cpu.s.ip & 0xFFFF) != 0x27FE:
                    raise RuntimeError(f"2932 returned to unexpected IP {cpu.s.ip:04X} inside 27EB row driver")
                cpu.s.cx = cpu.pop()
                cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF
                loop_count -= 1

            cpu.s.si = cpu.pop()

        # 2802 MOV CS:[5BA6],DI; 2807 MOV DI,5AF4h; 280A MOV BP,4.
        mem.ww(cs, 0x5BA6, cpu.s.di & 0xFFFF)
        cpu.s.di = 0x5AF4
        cpu.s.bp = 0x0004

        _jump_installed_hook_boundary(cpu, (0x1010, 0x280D), run_ega_load_temp_rows_280d)
        if (cpu.s.ip & 0xFFFF) != 0x2824:
            raise RuntimeError(f"280D fell through to unexpected IP {cpu.s.ip:04X} inside 27EB row driver")
        _jump_installed_hook_boundary(cpu, (0x1010, 0x2824), run_ega_expand_temp_rows_2824)
        if cpu.s.ip != 0x27EB:
            return


def run_ega_load_temp_rows_280d(cpu):
    if _self_disable_if_patched(cpu, 0x280D, _SIG_280D, "overkill_ega_load_temp_rows_280d"):
        return
    """Replace the hot four-row temp loader at 1010:280D.

    The block copies four ``CS:5B9C``-byte rows from DS:SI into the temporary
    EGA row buffer starting at CS:5AF4, with a fixed 40-byte stride between
    rows.  It is the setup immediately before the 2824 expansion block.
    """
    cs = cpu.s.cs & 0xFFFF
    width = cpu.mem.rw(cs, 0x5B9C)
    if width == 0:
        width = 0x10000
    data = cpu.mem.data
    src_base = (cpu.s.ds & 0xFFFF) << 4
    dst_base = cs << 4
    di = cpu.s.di & 0xFFFF
    si = cpu.s.si & 0xFFFF
    bp = cpu.s.bp & 0xFFFF

    while bp != 0:
        # Final PUSH-less LOOP leaves flags from DEC BP / the last arithmetic
        # instruction that matters.  We still use the helper flag operations for
        # the row-step instructions so oracle tests can compare exact FLAGS.
        row_di = di
        for _ in range(width):
            cpu.set_reg8(0, data[(src_base + si) & 0xFFFFF])  # LODSB
            si = (si + 1) & 0xFFFF
            data[(dst_base + row_di) & 0xFFFFF] = cpu.get_reg8(0)
            row_di = (row_di + 1) & 0xFFFF
        cpu.s.di = row_di
        _sub_reg16(cpu, 7, width)
        _add_reg16(cpu, 7, 0x0028)
        di = cpu.s.di & 0xFFFF
        cpu.s.bp = bp
        _dec_reg16_preserve_cf(cpu, 5)
        bp = cpu.s.bp & 0xFFFF

    cpu.s.si = si
    cpu.s.cx = 0
    cpu.s.ip = 0x2824


def run_ega_expand_temp_rows_2824(cpu):
    if _self_disable_if_patched(cpu, 0x2824, _SIG_2824, "overkill_ega_expand_temp_rows_2824"):
        return
    """Replace the hot EGA temp-row expansion/copy block at 1010:2824.

    This block converts four temporary 1bpp-ish rows at CS:5AF4/5B1C/5B44/5B6C
    into four EGA output-plane rows, applies OVERKILL's transparent-colour rule,
    then copies the four rows to the destination cursor tracked in CS:5BA6.  It
    is an internal block of the mode-1 renderer, not a subroutine: the hook ends
    at the same control-flow targets as the original ``LOOP/JMP`` tail
    (``27EB`` for another source row, ``27D9`` for the next object/list entry).

    The first lift mirrored the rotate/shift chain through ``CPU.shift``.  This
    version keeps the same byte/flag/stack results but performs the per-pixel
    plane packing as integer bit operations, which matters when the new 27EB
    driver fuses hundreds of rows into one hook call.
    """
    cs = cpu.s.cs & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    es = cpu.s.es & 0xFFFF
    mem = cpu.mem
    data = mem.data
    cs_base = cs << 4
    es_base = es << 4
    width_word = mem.rw(cs, 0x5B9C)
    width = width_word if width_word != 0 else 0x10000

    di = 0x5AF4
    transparent_enabled = mem.rw(cs, 0x0BD6) != 0
    transparent_colour = mem.rb(cs, 0x0000) & 0xFF
    marker_enabled = mem.rb(cs, 0xC5B0) == 1
    marker_base = mem.rw(cs, 0x5BAA)
    marker_add = mem.rw(cs, 0x5BA8)

    for col in range(width):
        # Final column PUSH CX scratch.  The column loop's push/pop pair leaves
        # the last pushed count in the word below SP.
        mem.ww(ss, (cpu.s.sp - 2) & 0xFFFF, (width - col) & 0xFFFF)

        al = data[(cs_base + di) & 0xFFFFF]
        ah = data[(cs_base + ((di + 0x28) & 0xFFFF)) & 0xFFFFF]
        dl = data[(cs_base + ((di + 0x50) & 0xFFFF)) & 0xFFFFF]
        dh = data[(cs_base + ((di + 0x78) & 0xFFFF)) & 0xFFFFF]
        p0 = mem.rb(cs, 0x5BA2)
        p1 = mem.rb(cs, 0x5BA3)
        p2 = mem.rb(cs, 0x5BA4)
        p3 = mem.rb(cs, 0x5BA5)
        bl = cpu.get_reg8(3)
        final_rcl_value = p3

        for _ in range(8):
            # ROL DH/DL/AH/AL + RCL BL gathers one 4-bit pixel.  The carry
            # emitted by RCL BL is overwritten by the next ROL, so only the
            # incoming plane bit matters for the low nibble that survives AND.
            bit = (dh >> 7) & 1; dh = ((dh << 1) | bit) & 0xFF; bl = ((bl << 1) | bit) & 0xFF
            bit = (dl >> 7) & 1; dl = ((dl << 1) | bit) & 0xFF; bl = ((bl << 1) | bit) & 0xFF
            bit = (ah >> 7) & 1; ah = ((ah << 1) | bit) & 0xFF; bl = ((bl << 1) | bit) & 0xFF
            bit = (al >> 7) & 1; al = ((al << 1) | bit) & 0xFF; bl = ((bl << 1) | bit) & 0xFF
            bl &= 0x0F

            if transparent_enabled and bl == transparent_colour:
                bl = 0

            if marker_enabled:
                cpu.s.bp = marker_base
                if cpu.s.bp != 0xFFFF:
                    cpu.s.bp = (cpu.s.bp + marker_add) & 0xFFFF
                    marker = mem.rb(ss, cpu.s.bp)
                    # The ASM branches are slightly counter-intuitive here:
                    # marker == 1 enters the 06h/0Ch swap block, while
                    # marker == 2 (and all other values) skip it.
                    if marker == 1:
                        if bl == 0x06:
                            bl = 0x0C
                        elif bl == 0x0C:
                            bl = 0x06

            cf = bl & 1; bl >>= 1
            old = p0; p0 = ((p0 << 1) | cf) & 0xFF; cf = (old >> 7) & 1
            cf = bl & 1; bl >>= 1
            old = p1; p1 = ((p1 << 1) | cf) & 0xFF; cf = (old >> 7) & 1
            cf = bl & 1; bl >>= 1
            old = p2; p2 = ((p2 << 1) | cf) & 0xFF; cf = (old >> 7) & 1
            cf = bl & 1; bl >>= 1
            old = p3; p3 = ((p3 << 1) | cf) & 0xFF; cf = (old >> 7) & 1
            final_rcl_value = p3

        data[(cs_base + di) & 0xFFFFF] = p0
        data[(cs_base + ((di + 0x28) & 0xFFFF)) & 0xFFFFF] = p1
        data[(cs_base + ((di + 0x50) & 0xFFFF)) & 0xFFFFF] = p2
        data[(cs_base + ((di + 0x78) & 0xFFFF)) & 0xFFFFF] = p3
        mem.wb(cs, 0x5BA2, p0)
        mem.wb(cs, 0x5BA3, p1)
        mem.wb(cs, 0x5BA4, p2)
        mem.wb(cs, 0x5BA5, p3)
        di = (di + 1) & 0xFFFF
        bl = 0

    cpu.set_reg8(0, al if width else cpu.get_reg8(0))
    cpu.set_reg8(4, ah if width else cpu.get_reg8(4))
    cpu.set_reg8(2, dl if width else cpu.get_reg8(2))
    cpu.set_reg8(6, dh if width else cpu.get_reg8(6))
    cpu.set_reg8(3, bl)
    cpu.s.di = di
    cpu.s.cx = 0
    # These flags are normally overwritten by the row-copy INC below; keep the
    # RCL result here for completeness before the copy phase runs.
    cpu.set_logic_flags(final_rcl_value, 8)
    cpu.set_flag(CF, bool(cf))

    def copy_temp_row(start: int, return_ip: int) -> None:
        count_word = mem.rw(cs, 0x5B9C)
        count = count_word if count_word != 0 else 0x10000
        src_di = start & 0xFFFF
        out_di = mem.rw(cs, 0x5BA6)

        # Mirror CALL 291C plus the helper's final PUSH CX/PUSH DI scratches.
        mem.ww(ss, (cpu.s.sp - 2) & 0xFFFF, return_ip & 0xFFFF)
        mem.ww(ss, (cpu.s.sp - 4) & 0xFFFF, 0x0001)
        mem.ww(ss, (cpu.s.sp - 6) & 0xFFFF, (src_di + count) & 0xFFFF)

        if count and src_di + count <= 0x10000 and out_di + count <= 0x10000 \
                and not (mem.ega_planar and _ega_aperture_overlap(es, out_di, count)):
            src = (cs_base + src_di) & 0xFFFFF
            dst = (es_base + out_di) & 0xFFFFF
            data[dst:dst + count] = data[src:src + count]
            al_last = data[src + count - 1]
            src_di = (src_di + count) & 0xFFFF
            out_di = (out_di + count) & 0xFFFF
        else:
            al_last = cpu.get_reg8(0)
            for _ in range(count):
                al_last = mem.rb(cs, src_di)
                src_di = (src_di + 1) & 0xFFFF
                mem.wb(es, out_di, al_last)
                out_di = (out_di + 1) & 0xFFFF

        mem.ww(cs, 0x5BA6, out_di)
        cpu.s.di = src_di
        cpu.s.cx = 0
        cpu.set_reg8(0, al_last)
        old_cf = cpu.get_flag(CF)
        old = (src_di - 1) & 0xFFFF
        cpu.set_add_flags(old, 1, old + 1, 16)
        cpu.set_flag(CF, old_cf)

    copy_temp_row(0x5AF4, 0x28EB)
    copy_temp_row(0x5B1C, 0x28F6)
    copy_temp_row(0x5B44, 0x2901)
    copy_temp_row(0x5B6C, 0x290C)

    cpu.s.di = mem.rw(cs, 0x5BA6)
    outer = cpu.pop()
    cpu.s.cx = (outer - 1) & 0xFFFF
    cpu.s.ip = 0x27EB if cpu.s.cx != 0 else 0x27D9


def run_ega_temp_row_copy_291c(cpu):
    if _self_disable_if_patched(cpu, 0x291C, _SIG_291C, "overkill_ega_temp_row_copy_291c"):
        return
    """Replace the hot EGA temp-row copy helper at 1010:291C.

    Original shape::

        push cx
    loop:
        mov  al,cs:[di]
        inc  di
        push di
        mov  di,cs:[5BA6]
        stosb
        mov  cs:[5BA6],di
        pop  di
        pop  cx
        loop loop
        ret

    It copies ``CX`` bytes from a temporary CS row to the current ES output
    cursor stored at ``CS:5BA6``.  The helper is called four times for each EGA
    converted row, so collapsing the interpreted push/pop/stos loop noticeably
    speeds up EGA startup and menu rendering without changing renderer logic.
    """
    cs = cpu.s.cs & 0xFFFF
    mem = cpu.mem
    count = cpu.s.cx & 0xFFFF
    if count == 0:
        count = 0x10000

    source_di = cpu.s.di & 0xFFFF
    out_di = mem.rw(cs, 0x5BA6)
    ah = cpu.get_reg8(4)
    last_source_di = source_di

    # Preserve the stack scratch left by the final PUSH CX / PUSH DI pair.  The
    # words are popped again, but full-memory oracle tests can still observe the
    # overwritten stack slots.
    final_pushed_cx = 1
    final_pushed_di = (source_di + count) & 0xFFFF
    mem.ww(cpu.s.ss, (cpu.s.sp - 2) & 0xFFFF, final_pushed_cx)
    mem.ww(cpu.s.ss, (cpu.s.sp - 4) & 0xFFFF, final_pushed_di)

    src_base = (cs << 4)
    es = cpu.s.es & 0xFFFF
    dst_base = es << 4
    data = mem.data
    planar_destination = mem.ega_planar and _ega_aperture_overlap(es, out_di, count)
    for i in range(count):
        al = data[(src_base + source_di) & 0xFFFFF]
        source_di = (source_di + 1) & 0xFFFF
        last_source_di = source_di
        if planar_destination:
            # STOSB into A000h must go through the EGA map-mask router.  The
            # previous lift wrote the flat A000 byte directly, which only changed
            # shadow plane 0 and could leave stale bits in the other planes.
            mem.wb(es, out_di, al)
        else:
            data[(dst_base + out_di) & 0xFFFFF] = al
        out_di = (out_di + 1) & 0xFFFF
        cpu.set_reg8(0, al)

    mem.ww(cs, 0x5BA6, out_di)
    cpu.s.di = last_source_di
    cpu.s.cx = 0
    # Final flags are from the last INC DI.  INC preserves CF.
    old_cf = cpu.get_flag(CF)
    old = (last_source_di - 1) & 0xFFFF
    cpu.set_add_flags(old, 1, old + 1, 16)
    cpu.set_flag(CF, old_cf)
    cpu.set_reg8(4, ah)
    cpu.s.ip = cpu.pop()


def run_ega_transparency_mask_2932(cpu):
    if _self_disable_if_patched(cpu, 0x2932, _SIG_2932, "overkill_ega_transparency_mask_2932"):
        return
    """Replace the hot EGA transparency-mask builder at 1010:2932.

    This is the same routine as the previous transliterated hook, but it now
    computes the eight transparency bits directly instead of executing the
    original RCL chain through CPU.shift for every bit of every plane byte.
    The helper is called thousands of times by the EGA startup/menu asset path,
    so avoiding per-bit flag/register helper traffic is much more valuable than
    adding another tiny leaf hook.
    """
    s = cpu.s
    cs = s.cs & 0xFFFF
    ds = s.ds & 0xFFFF
    mem = cpu.mem

    width = mem.rw(cs, 0x5B9C)
    si = s.si & 0xFFFF
    bx = (width * 3) & 0xFFFF

    al_src = mem.rb(ds, si)
    ah_src = mem.rb(ds, (si + width) & 0xFFFF)
    dl_src = mem.rb(ds, (si + ((width << 1) & 0xFFFF)) & 0xFFFF)
    dh_src = mem.rb(ds, (si + bx) & 0xFFFF)
    transparent = mem.rb(cs, 0x0000) & 0x0F

    def rcl8(value: int, carry: int) -> tuple[int, int]:
        value &= 0xFF
        return (((value << 1) | carry) & 0xFF), ((value >> 7) & 1)

    # Keep the exact carry interactions through CS:[5BA1] and CS:[5BA0], but
    # run them as simple integer operations rather than CPU.shift calls.
    al = al_src
    ah = ah_src
    dl = dl_src
    dh = dh_src
    scratch = mem.rb(cs, 0x5BA1)
    mask = 0
    # The loop's incoming CF is not the caller's CF: the original setup
    # executes SHL BX,1 and then ADD BX,CS:[5B9C], so the first RCL sees the
    # carry produced by that ADD.
    bx2 = (width << 1) & 0xFFFF
    cf = 1 if (bx2 + width) > 0xFFFF else 0
    for _ in range(8):
        dh, cf = rcl8(dh, cf)
        scratch, cf = rcl8(scratch, cf)
        dl, cf = rcl8(dl, cf)
        scratch, cf = rcl8(scratch, cf)
        ah, cf = rcl8(ah, cf)
        scratch, cf = rcl8(scratch, cf)
        al, cf = rcl8(al, cf)
        scratch, cf = rcl8(scratch, cf)
        scratch &= 0x0F
        cf = 1 if scratch == transparent else 0
        mask, cf = rcl8(mask, cf)

    mem.wb(cs, 0x5BA0, mask)
    mem.wb(cs, 0x5BA1, scratch)
    mem.ww(s.ss & 0xFFFF, (s.sp - 2) & 0xFFFF, 0x0001)  # final PUSH CX scratch

    s.bx = bx
    s.cx = 0
    s.ax = ((ah & 0xFF) << 8) | (mask & 0xFF)  # MOV AL,[5BA0] after the loop.
    s.dx = ((dh & 0xFF) << 8) | (dl & 0xFF)

    mem.wb(s.es & 0xFFFF, s.di & 0xFFFF, mask)
    s.di = (s.di + ( -1 if cpu.get_flag(DF) else 1)) & 0xFFFF

    old_cf = bool(cf)
    old_si = s.si & 0xFFFF
    s.si = (old_si + 1) & 0xFFFF
    cpu.set_add_flags(old_si, 1, old_si + 1, 16)
    cpu.set_flag(CF, old_cf)
    s.ip = cpu.pop()


def run_ega_planar_to_linear_copy_5827(cpu):
    """Replace the hot 1010:5827 EGA row-copy loop only.

    This deliberately stops at 58A4 and lets the original setup/render driver run
    after the copied 200-row screen/work-buffer transfer.  It is a narrow hook:
    it collapses the repeated row copy selected by CS:95BCh, but does not infer
    higher-level video semantics.
    """
    cs = cpu.s.cs & 0xFFFF
    iterations = cpu.s.cx & 0xFFFF
    if iterations == 0:
        iterations = 0x10000

    for _ in range(iterations):
        cpu.push(cpu.s.cx)

        # 5828..582F: BX = CS:[95BC] << 1; JMP CS:[5834+BX]
        mode_word = cpu.mem.rw(cs, 0x95BC)
        cpu.s.bx = mode_word & 0xFFFF
        cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)
        mode = (cpu.s.bx >> 1) & 0xFFFF

        if mode == 0:
            # 583A: packed/linear 80-byte row, planar source stride.
            cpu.s.cx = 0x0050
            _rep_movsb(cpu, cpu.s.cx)
            _sub_reg16(cpu, 6, 0x0050)   # SI -= 80
            _add_reg16(cpu, 6, 0x2000)   # next EGA plane/scanline block
            _test_word(cpu, cpu.s.si, 0x4000)
            if not cpu.get_flag(ZF):
                _add_reg16(cpu, 6, 0xC050)
        elif mode == 1:
            # 5852: four 40-byte plane reads selected through GC index writes.
            # A real EGA returns bytes from the GC read-map-selected plane while
            # SI stays at the same CPU offset.  Copy directly from our shadow
            # plane when the geometry is simple; otherwise fall back through
            # mem.rb/mem.wb so the selected-read-plane emulation still applies.
            cpu.s.ax = 0x0004
            _out_dx_ax(cpu)
            for plane in range(4):
                count = 0x0028
                si = cpu.s.si & 0xFFFF
                di = cpu.s.di & 0xFFFF
                if (cpu.mem.ega_planar
                        and (cpu.s.ds & 0xFFFF) == 0xA000
                        and si + count <= EGA_PLANE_WINDOW
                        and di + count <= 0x10000
                        and not _ega_aperture_overlap(cpu.s.es, di, count)):
                    read_plane = cpu.mem.ega_read_plane & 0x03
                    src = EGA_APERTURE + read_plane * EGA_PLANE_STRIDE + si
                    dst = (((cpu.s.es & 0xFFFF) << 4) + di) & 0xFFFFF
                    cpu.mem.data[dst:dst + count] = cpu.mem.data[src:src + count]
                    cpu.s.si = (si + count) & 0xFFFF
                    cpu.s.di = (di + count) & 0xFFFF
                    cpu.s.cx = 0
                else:
                    cpu.s.cx = count
                    _rep_movsb(cpu, cpu.s.cx)
                if plane != 3:
                    _sub_reg16(cpu, 6, count)
                    _inc_reg8_preserve_cf(cpu, 4)  # INC AH
                    _out_dx_ax(cpu)
        elif mode == 2:
            # 587E: 80 word copies (=160 bytes), different EGA row wrap rule.
            cpu.s.cx = 0x0050
            _rep_movsw(cpu, cpu.s.cx)
            _sub_reg16(cpu, 6, 0x00A0)
            _add_reg16(cpu, 6, 0x2000)
            _test_word(cpu, cpu.s.si, 0x8000)
            if not cpu.get_flag(ZF):
                _add_reg16(cpu, 6, 0x80A0)
        else:
            raise RuntimeError(f"unsupported OVERKILL 5827 video mode selector {mode_word:04X}")

        cpu.s.cx = cpu.pop()
        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF  # LOOP, flags unchanged

    # 5898..58A3: optional final graphics-controller write for mode 1.
    _cmp_word(cpu, cpu.mem.rw(cs, 0x95BC), 0x0001)
    if cpu.get_flag(ZF):
        cpu.s.ax = 0x0004
        _out_dx_ax(cpu)
    cpu.s.ip = 0x58A4


def run_present_ega_frame_2750(cpu):
    if _self_disable_if_patched(cpu, 0x2750, _SIG_2750, "overkill_present_ega_frame_2750"):
        return
    """Replace the EGA mode-1 frame-present blit at 1010:2750.

    The real routine writes the same A000h offsets four times while changing the
    EGA sequencer map-mask register (03C4h index 02h / 03C5h data 1,2,4,8).
    The memory model routes those CPU-visible A000h writes into the selected
    shadow plane.  The common A000 case copies directly into that selected
    shadow plane; unusual geometry falls back through ``Memory.ww``.  The copied
    source bytes and register flow mirror the original routine; this is
    deliberately only the final presenter, not a broad VGA/EGA hardware
    emulator.
    """
    cs = cpu.s.cs & 0xFFFF
    mem = cpu.mem

    # 2750..275D setup.
    cpu.s.si = mem.rw(cpu.s.ds, 0x234C)
    cpu.s.es = mem.rw(cs, 0x95A4)
    cpu.s.ds = mem.rw(cs, 0x9598)
    cpu.s.bx = 0x000D
    cpu.s.di = 0x00A0
    cpu.s.dx = 0x03C4
    cpu.set_reg8(0, 0x02)
    _out_dx_al(cpu)                 # OUT 03C4h,02h: sequencer map mask index.
    _inc_reg16_preserve_cf(cpu, 2)  # INC DX -> 03C5h.
    cpu.s.bp = 0x00C0

    es_seg = cpu.s.es & 0xFFFF
    width = 0x001A
    words = width // 2
    data = mem.data

    def set_present_map_mask() -> None:
        # Runtime executions update this via DOSMachine.port_write.  Synthetic
        # hook tests often have no port writer attached, so mirror this routine's
        # known 03C5h map-mask writes locally too.
        mem.ega_planar = True
        mem.ega_map_mask = cpu.get_reg8(0) & 0x0F

    def fast_copy_selected_plane(src: int, dst: int) -> bool:
        mask = cpu.get_reg8(0) & 0x0F
        if (not mem.ega_planar
                or es_seg != 0xA000
                or mask not in (0x01, 0x02, 0x04, 0x08)
                or src + width > 0x10000
                or dst + width > EGA_PLANE_WINDOW
                or _ega_aperture_overlap(cpu.s.ds, src, width)):
            return False
        plane = (mask.bit_length() - 1) & 0x03
        src_base = (((cpu.s.ds & 0xFFFF) << 4) + src) & 0xFFFFF
        dst_base = EGA_APERTURE + plane * EGA_PLANE_STRIDE + dst
        data[dst_base:dst_base + width] = data[src_base:src_base + width]
        return True

    while True:
        cpu.set_reg8(0, 0x01)
        _out_dx_al(cpu)
        set_present_map_mask()
        for plane in range(4):
            # Original plane copy is REP MOVSW with BX=000Dh: 26 bytes.
            # MOVS changes SI/DI/CX but not flags.
            src = cpu.s.si & 0xFFFF
            dst = cpu.s.di & 0xFFFF
            if fast_copy_selected_plane(src, dst):
                src = (src + width) & 0xFFFF
                dst = (dst + width) & 0xFFFF
            else:
                for _ in range(words):
                    mem.ww(es_seg, dst, mem.rw(cpu.s.ds, src))
                    src = (src + 2) & 0xFFFF
                    dst = (dst + 2) & 0xFFFF
            cpu.s.si = src
            cpu.s.di = dst
            cpu.s.cx = 0
            if plane != 3:
                _sub_reg16(cpu, 7, width)
                cpu.set_reg8(0, cpu.shift(4, cpu.get_reg8(0), 1, 8))
                _out_dx_al(cpu)
                set_present_map_mask()
        _add_reg16(cpu, 7, 0x000E)  # Net row stride: 26 copied bytes + 14 = 40.
        _dec_reg16_preserve_cf(cpu, 5)
        if cpu.get_flag(ZF):
            break

    cpu.set_reg8(0, 0x0F)
    _out_dx_al(cpu)
    set_present_map_mask()
    cpu.s.ds = mem.rw(cs, 0x9596)
    cpu.s.ip = cpu.pop()


def run_ega_display_start_wait_5160(cpu):
    """Lift the mode-1-only display-start wait stub; Tandy/CGA return immediately."""
    if _self_disable_if_patched(cpu, 0x5160, _SIG_5160, "overkill_ega_display_start_wait_5160"):
        return
    cs = cpu.s.cs & 0xFFFF
    mode = cpu.mem.rw(cs, 0x95BC)
    _cmp_word(cpu, mode, 1)
    if mode != 1:
        cpu.s.ip = cpu.pop()
        return
    cpu.s.ip = 0x5169


def run_ega_blit_scaled_column_block_497a(cpu) -> None:
    """Blit/clear the scaled column block at 1010:497A (renderer dispatch via CS:95BC).

    Copies rows DS:SI -> ES:DI (decoded asset buffer -> B800 planar video memory),
    skipping or duplicating source rows according to the CS:58FD/5901/5903/5905 scale
    accumulator and using the same planar address step as the original inner loops.
    Direct transliteration of 497A..4A40 preserving the observed register/flag/stack
    state via the shared arithmetic-flag helpers.
    """
    cs = cpu.s.cs & 0xFFFF
    mem = cpu.mem

    # 497A: mov cs:[5903],0000h
    mem.ww(cs, 0x5903, 0)
    # 4981..4995: load local state and double BP (source bytes per row)
    cpu.s.di = mem.rw(cs, 0x58F9)
    cpu.s.si = mem.rw(cs, 0x58FB)
    cpu.s.cx = mem.rw(cs, 0x58FD)
    cpu.s.bp = mem.rw(cs, 0x58FF)
    cpu.s.bp = cpu.shift(4, cpu.s.bp, 1, 16)  # SHL BP,1

    # Optional bottom-up source positioning.
    _cmp_word(cpu, mem.rw(cs, 0x5905), 0)
    if not cpu.get_flag(ZF):
        cpu.s.ax = cpu.s.bp & 0xFFFF
        _dec_reg16_preserve_cf(cpu, 1)  # DEC CX
        # MUL CX, matching CPU8086 group-F7 behavior: AX*CX -> DX:AX, CF/OF only.
        result = (cpu.s.ax & 0xFFFF) * (cpu.s.cx & 0xFFFF)
        cpu.s.ax = result & 0xFFFF
        cpu.s.dx = (result >> 16) & 0xFFFF
        carry = cpu.s.dx != 0
        cpu.set_flag(CF, carry)
        cpu.set_flag(0x0800, carry)  # OF
        _inc_reg16_preserve_cf(cpu, 1)  # INC CX
        _add_reg16(cpu, 6, cpu.s.ax)    # ADD SI,AX

    # Initial clear/skip region before the first copied row.
    cpu.push(cpu.s.cx)
    cpu.s.cx = mem.rw(cs, 0x58FD)
    _sub_reg16(cpu, 1, mem.rw(cs, 0x5901))
    _test_word(cpu, cpu.s.cx, cpu.s.cx)  # OR CX,CX
    if not cpu.get_flag(SF):
        cpu.s.cx = cpu.shift(5, cpu.s.cx, 1, 16)  # SHR CX,1
        if cpu.s.cx != 0:
            _dec_reg16_preserve_cf(cpu, 1)
            if cpu.s.cx != 0:
                # 49BD..49CB: advance DI by CX-1 planar rows.
                while cpu.s.cx != 0:
                    _ega_next_scanline_di(cpu)
                    cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF  # LOOP, no flags
            # 49CD..49E3: clear one row and advance to next row.
            _xor_al_al(cpu)
            cpu.s.cx = cpu.s.bp & 0xFFFF
            _rep_stosb(cpu, cpu.s.cx)
            _sub_reg16(cpu, 7, cpu.s.bp)
            _ega_next_scanline_di(cpu)
    cpu.s.cx = cpu.pop()

    # 49E4..4A38: copy/skip rows according to CS:5901 accumulator.
    while True:
        cpu.s.ax = mem.rw(cs, 0x5901)
        _cmp_word(cpu, cpu.s.ax, mem.rw(cs, 0x58FD))
        if cpu.get_flag(ZF):
            copy_this_row = True
        else:
            _add_mem_word(cpu, cs, 0x5903, cpu.s.ax)
            cpu.s.ax = mem.rw(cs, 0x58FD)
            _cmp_word(cpu, cpu.s.ax, mem.rw(cs, 0x5903))
            # JA 4A11: jump if AX > CS:5903, unsigned.
            if (not cpu.get_flag(CF)) and (not cpu.get_flag(ZF)):
                _sub_mem_word(cpu, cs, 0x5903, cpu.s.ax)
                copy_this_row = True
            else:
                _cmp_word(cpu, mem.rw(cs, 0x5905), 0)
                if cpu.get_flag(ZF):
                    _add_reg16(cpu, 6, cpu.s.bp)
                else:
                    _sub_reg16(cpu, 6, cpu.s.bp)
                cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF  # LOOP 49E4, no flags
                if cpu.s.cx != 0:
                    continue
                break

        # 4A16..4A38: copy one BP-byte row, advance planar DI, optionally step SI back.
        cpu.push(cpu.s.cx)
        cpu.s.cx = cpu.s.bp & 0xFFFF
        _rep_movsb(cpu, cpu.s.cx)
        _sub_reg16(cpu, 7, cpu.s.bp)
        _ega_next_scanline_di(cpu)
        _cmp_word(cpu, mem.rw(cs, 0x5905), 0)
        if not cpu.get_flag(ZF):
            _sub_reg16(cpu, 6, cpu.s.bp)
            _sub_reg16(cpu, 6, cpu.s.bp)
        cpu.s.cx = cpu.pop()
        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF  # LOOP 49E4, no flags
        if cpu.s.cx != 0:
            continue
        break

    # 4A3A..4A40: final clear row and RET.
    _xor_al_al(cpu)
    cpu.s.cx = cpu.s.bp & 0xFFFF
    _rep_stosb(cpu, cpu.s.cx)
    cpu.s.ip = cpu.pop()
