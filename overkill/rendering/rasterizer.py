"""Source-like Tandy/EGA rasterizer operations.

This is the recovered, VM-independent reconstruction of OVERKILL's inner blit
loops.  Each operation reads source words from ``DS:SI`` and writes destination
words to ``ES:DI`` of a *memory* object (anything exposing the ``rw``/``ww``/
``rb``/``wb`` word/byte accessors -- the live VM memory in the game, or a plain
buffer in tests) and returns the advanced cursors.  They are deliberately free
of the CPU register file and x86 flags: the address-bound leaves in
``tandy.py`` / ``ega.py`` are thin adapters that read the registers, call one of
these operations, store the returned cursors, and reconstruct the single
``ADD``-flag the original leaf leaves behind (always the strided cursor plus a
known immediate -- see ``_apply_strided_add_flag``).

Keeping the blit semantics here -- as ordinary loops over named coordinates --
is what turns the renderer into readable native code instead of a transliterated
register dance.
"""
from __future__ import annotations


def copy_word_rows(mem, *, ds: int, es: int, si: int, di: int, rows: int,
                   words_per_row: int, row_stride: int, stride_on: str,
                   step: int) -> tuple[int, int]:
    """Copy ``words_per_row`` 16-bit words per row for ``rows`` rows, advancing
    SI/DI by ``step`` each word and the ``stride_on`` cursor (``"di"`` dest or
    ``"si"`` source) by ``row_stride`` after each row.  Returns ``(si, di)``.

    This is the body shared by the 34C5/35AA strided-copy leaves and the
    34D8/3657 fixed-row object blocks.
    """
    for _ in range(rows):
        for _ in range(words_per_row):
            mem.ww(es, di, mem.rw(ds, si))
            si = (si + step) & 0xFFFF
            di = (di + step) & 0xFFFF
        if stride_on == "di":
            di = (di + row_stride) & 0xFFFF
        else:
            si = (si + row_stride) & 0xFFFF
    return si, di


def composite_masked_row(mem, *, ds: int, es: int, si: int, di: int,
                         words_per_row: int, step: int) -> tuple[int, int, int]:
    """Composite one row of ``words_per_row`` destination words from source
    ``[mask, data]`` pairs: ``dest = (mask & dest) | data``.  Advances SI past
    each pair (LODSW + ``ADD SI,2``) and DI past each written word.  Returns
    ``(si, di, ax)`` where ``ax`` is the last word written.
    """
    ax = 0
    for _ in range(words_per_row):
        ax = mem.rw(ds, si)
        si = (si + step) & 0xFFFF
        ax = (ax & mem.rw(es, di)) & 0xFFFF
        ax = (ax | mem.rw(ds, si)) & 0xFFFF
        si = (si + 2) & 0xFFFF
        mem.ww(es, di, ax)
        di = (di + step) & 0xFFFF
    return si, di, ax


def composite_masked_rows(mem, *, ds: int, es: int, si: int, di: int, rows: int,
                          words_per_row: int, row_stride: int,
                          step: int) -> tuple[int, int, int]:
    """``rows`` rows of :func:`composite_masked_row`, advancing DI by
    ``row_stride`` after each row.  Shared by the 2E6E/2F81 LOOP leaves, the
    2FB6 unrolled block, and the 38B7/3849 immediate-add siblings (which differ
    only in their CPU epilogue, applied by the adapter).  Returns ``(si, di, ax)``.
    """
    ax = 0
    for _ in range(rows):
        si, di, ax = composite_masked_row(
            mem, ds=ds, es=es, si=si, di=di, words_per_row=words_per_row, step=step)
        di = (di + row_stride) & 0xFFFF
    return si, di, ax


def or_inverted_word_rows(mem, *, ds: int, es: int, si: int, di: int, rows: int,
                          words_per_row: int, row_stride: int) -> tuple[int, int, int]:
    """For each of ``rows`` rows, OR the bitwise-NOT of each source word into the
    destination word, advancing SI by 4 and DI by 2 per word, then DI by
    ``row_stride`` after the row.  Returns ``(si, di, ax)`` where ``ax`` is the
    last NOTed source word.  (The 2F40/2ECB inverted-mask OR leaves.)
    """
    ax = 0
    for _ in range(rows):
        for _ in range(words_per_row):
            ax = (~mem.rw(ds, si)) & 0xFFFF
            mem.ww(es, di, (mem.rw(es, di) | ax) & 0xFFFF)
            si = (si + 4) & 0xFFFF
            di = (di + 2) & 0xFFFF
        di = (di + row_stride) & 0xFFFF
    return si, di, ax
