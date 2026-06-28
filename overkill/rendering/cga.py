"""CGA byte-level masked sprite compositors recovered from ``overkill/hooks.py``.

The shift-based CGA siblings of the Tandy 2E6E masked-sprite family -- ``1010:3E12``
(two-shift) and ``1010:3EFB`` (six-shift) -- plus the shared 5-byte RCR/SHR
shift-chain helpers they use.  These are pure ``run_*(cpu)`` functions; the
address-facing ``@registry.replace`` wrappers (and 3EFB's overlay signature guard)
stay in ``hooks.py``.
"""
from __future__ import annotations

from dos_re.cpu import CF


def _rcr_stc_chain_5bytes(bl: int, bh: int, al: int, ah: int, dl: int, passes: int) -> tuple[int, int, int, int, int]:
    """Return the 5-byte result of repeated STC; RCR BL,BH,AL,AH,DL groups.

    Used by the CGA masked-sprite compositors.  The interpreted version updated
    CPU flags on every single rotate, but those flags are overwritten by the
    row-step ADD/DEC before control leaves the hook.
    """
    bl &= 0xFF; bh &= 0xFF; al &= 0xFF; ah &= 0xFF; dl &= 0xFF
    for _ in range(passes):
        cf = 1
        old = bl; bl = ((cf << 7) | (old >> 1)) & 0xFF; cf = old & 1
        old = bh; bh = ((cf << 7) | (old >> 1)) & 0xFF; cf = old & 1
        old = al; al = ((cf << 7) | (old >> 1)) & 0xFF; cf = old & 1
        old = ah; ah = ((cf << 7) | (old >> 1)) & 0xFF; cf = old & 1
        old = dl; dl = ((cf << 7) | (old >> 1)) & 0xFF
    return bl, bh, al, ah, dl


def _shr_rcr_chain_5bytes(bl: int, bh: int, al: int, ah: int, dl: int, passes: int) -> tuple[int, int, int, int, int]:
    """Return the 5-byte result of repeated SHR BL; RCR BH,AL,AH,DL groups."""
    bl &= 0xFF; bh &= 0xFF; al &= 0xFF; ah &= 0xFF; dl &= 0xFF
    for _ in range(passes):
        cf = bl & 1
        bl = (bl >> 1) & 0xFF
        old = bh; bh = ((cf << 7) | (old >> 1)) & 0xFF; cf = old & 1
        old = al; al = ((cf << 7) | (old >> 1)) & 0xFF; cf = old & 1
        old = ah; ah = ((cf << 7) | (old >> 1)) & 0xFF; cf = old & 1
        old = dl; dl = ((cf << 7) | (old >> 1)) & 0xFF
    return bl, bh, al, ah, dl


def run_masked_cga_composite_3e12(cpu) -> None:
    """Composite the CGA two-shift masked sprite/highlight row loop at 1010:3E12.

    Eight source bytes per row: shift mask and data bits through carry twice, then
    AND/OR-composite three destination bytes; ADD SI,8 / ADD DI,34h / DEC BP per row.
    Hot on the planet/difficulty selection redraw.  Ends at the 3E6A continuation
    (no DS restore).
    """
    s = cpu.s
    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    bp = s.bp & 0xFFFF
    rows = bp if bp != 0 else 0x10000
    initial_dh = s.dx & 0xFF00
    final_dl = s.dx & 0x00FF

    mem = cpu.mem
    for _ in range(rows):
        # Mask phase:
        #   mov bx,[si]; mov ax,[si+4]; mov dl,ff; stc;
        #   rcr bl,bh,al,ah,dl twice; and destination bytes.
        mask_bx = mem.rw(ds, si)
        mask_ax = mem.rw(ds, (si + 4) & 0xFFFF)
        bl = mask_bx & 0xFF
        bh = (mask_bx >> 8) & 0xFF
        al = mask_ax & 0xFF
        ah = (mask_ax >> 8) & 0xFF
        dl = 0xFF
        bl, bh, al, ah, dl = _rcr_stc_chain_5bytes(bl, bh, al, ah, dl, 2)
        mask_bx = ((bh << 8) | bl) & 0xFFFF
        mask_ax = ((ah << 8) | al) & 0xFFFF
        mem.ww(es, di, mem.rw(es, di) & mask_bx)
        mem.ww(es, (di + 2) & 0xFFFF, mem.rw(es, (di + 2) & 0xFFFF) & mask_ax)
        mem.wb(es, (di + 4) & 0xFFFF, mem.rb(es, (di + 4) & 0xFFFF) & dl)

        # Data phase:
        #   mov bx,[si+2]; mov ax,[si+6]; xor dl,dl;
        #   shr bl; rcr bh,al,ah,dl; repeat; or destination bytes.
        data_bx = mem.rw(ds, (si + 2) & 0xFFFF)
        data_ax = mem.rw(ds, (si + 6) & 0xFFFF)
        bl = data_bx & 0xFF
        bh = (data_bx >> 8) & 0xFF
        al = data_ax & 0xFF
        ah = (data_ax >> 8) & 0xFF
        dl = 0x00
        cpu.set_logic_flags(0, 8)        # XOR DL,DL clears CF/OF and sets ZF/PF.
        bl, bh, al, ah, dl = _shr_rcr_chain_5bytes(bl, bh, al, ah, dl, 2)
        data_bx = ((bh << 8) | bl) & 0xFFFF
        data_ax = ((ah << 8) | al) & 0xFFFF
        mem.ww(es, di, mem.rw(es, di) | data_bx)
        mem.ww(es, (di + 2) & 0xFFFF, mem.rw(es, (di + 2) & 0xFFFF) | data_ax)
        mem.wb(es, (di + 4) & 0xFFFF, mem.rb(es, (di + 4) & 0xFFFF) | dl)
        final_dl = dl

        # ADD SI,8; ADD DI,34h; DEC BP; JNZ 3E12.  Only the final DEC flags are
        # externally visible, with CF preserved from the immediately preceding
        # ADD DI because DEC does not modify CF.
        si = (si + 8) & 0xFFFF
        old_di = di
        di_sum = old_di + 0x34
        di = di_sum & 0xFFFF
        cpu.set_add_flags(old_di, 0x34, di_sum, 16)
        old_cf = cpu.get_flag(CF)
        old_bp = bp
        bp = (bp - 1) & 0xFFFF
        cpu.set_sub_flags(old_bp, 1, old_bp - 1, 16)
        cpu.set_flag(CF, old_cf)

    s.si = si
    s.di = di
    s.bp = bp
    s.dx = initial_dh | final_dl
    # BX and AX are left containing the last shifted data words; DL is already
    # reflected in DX, while DH is untouched by the ASM loop.
    s.bx = data_bx
    s.ax = data_ax
    s.ip = 0x3E6A


def run_masked_cga_composite_3efb(cpu) -> None:
    """Composite the CGA six-shift overlaid masked sprite loop at 1010:3EFB.

    The dominant interpreted loop on the planet/difficulty selection redraw after
    3E12 is hooked; identical to 3E12 but shifting six times per phase and falling
    into the shared 38D0 tail (MOV DS,CS:[9596]; RET).  The overlay signature guard
    stays in the wrapper.
    """
    s = cpu.s
    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    cs = s.cs & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    bp = s.bp & 0xFFFF
    rows = bp if bp != 0 else 0x10000
    initial_dh = s.dx & 0xFF00
    final_dl = s.dx & 0x00FF
    mem = cpu.mem

    for _ in range(rows):
        mask_bx = mem.rw(ds, si)
        mask_ax = mem.rw(ds, (si + 4) & 0xFFFF)
        bl = mask_bx & 0xFF
        bh = (mask_bx >> 8) & 0xFF
        al = mask_ax & 0xFF
        ah = (mask_ax >> 8) & 0xFF
        dl = 0xFF
        bl, bh, al, ah, dl = _rcr_stc_chain_5bytes(bl, bh, al, ah, dl, 6)
        mask_bx = ((bh << 8) | bl) & 0xFFFF
        mask_ax = ((ah << 8) | al) & 0xFFFF
        mem.ww(es, di, mem.rw(es, di) & mask_bx)
        mem.ww(es, (di + 2) & 0xFFFF, mem.rw(es, (di + 2) & 0xFFFF) & mask_ax)
        mem.wb(es, (di + 4) & 0xFFFF, mem.rb(es, (di + 4) & 0xFFFF) & dl)

        data_bx = mem.rw(ds, (si + 2) & 0xFFFF)
        data_ax = mem.rw(ds, (si + 6) & 0xFFFF)
        bl = data_bx & 0xFF
        bh = (data_bx >> 8) & 0xFF
        al = data_ax & 0xFF
        ah = (data_ax >> 8) & 0xFF
        dl = 0x00
        cpu.set_logic_flags(0, 8)        # XOR DL,DL
        bl, bh, al, ah, dl = _shr_rcr_chain_5bytes(bl, bh, al, ah, dl, 6)
        data_bx = ((bh << 8) | bl) & 0xFFFF
        data_ax = ((ah << 8) | al) & 0xFFFF
        mem.ww(es, di, mem.rw(es, di) | data_bx)
        mem.ww(es, (di + 2) & 0xFFFF, mem.rw(es, (di + 2) & 0xFFFF) | data_ax)
        mem.wb(es, (di + 4) & 0xFFFF, mem.rb(es, (di + 4) & 0xFFFF) | dl)
        final_dl = dl

        si = (si + 8) & 0xFFFF
        old_di = di
        di_sum = old_di + 0x34
        di = di_sum & 0xFFFF
        cpu.set_add_flags(old_di, 0x34, di_sum, 16)
        old_cf = cpu.get_flag(CF)
        old_bp = bp
        bp = (bp - 1) & 0xFFFF
        cpu.set_sub_flags(old_bp, 1, old_bp - 1, 16)
        cpu.set_flag(CF, old_cf)         # DEC preserves CF.

    s.si = si
    s.di = di
    s.bp = bp
    s.dx = initial_dh | final_dl
    s.bx = data_bx
    s.ax = data_ax
    s.ds = mem.rw(cs, 0x9596)            # MOV DS,CS:[9596] before RET.
    s.ip = cpu.pop()
