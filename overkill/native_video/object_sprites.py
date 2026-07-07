"""Native (VM-free) object -> sprite-block bridge: turn each object slot into its drawable sprite(s).

An object is drawn by ONE of three shared layer-sprite routines, selected by its draw-type word
``obj[+14]`` through the dispatch table ``cs:[75A0]`` (``{0: 7746, 1: 768E, 2: 75A6}``).  The three
routines differ in sprite bank, frame table, id threshold, compositor and slot layout -- all recovered
here VM-free (banks from :mod:`overkill.asset_codecs.shared_assets` + the level graphics; the masked
decode from :mod:`overkill.recovered.systems.sprite_textures`):

* **75A6** (``dtype 2``): frame table ``cs:[9392]``; id ``< 0x1C`` -> the common bank ``cs:[95A6]`` =
  ``MANEXPL.BIC``, else the LEVEL bank ``cs:[95AE]`` = ``NativeLevel.graphics`` (index ``id-0x1C``).
  Compositor ``2E6E`` (8 words = 32 px, 16 rows).  It draws TWO slots: ``obj[+0C]`` at source ``off``,
  then ``obj[+10]`` at source ``off + (ds:[1028] >> 1)`` (the sprite cell's second half).
* **768E** (``dtype 1``): frame table ``cs:[9192]``; id ``< 0xFA`` -> ``cs:[95AA]`` = ``2X2.BIC``, else
  ``cs:[95AC]`` = ``2X2C.BIC`` (index ``id-0xFA``).  Compositor ``2F81`` (4 words = 16 px, 16 rows).
  ONE slot at ``obj[+0C]``.
* **7746** (``dtype 0``): frame table ``cs:[8F92]``; bank ``cs:[95A8]`` = ``1X1.BIC`` (no threshold).
  Compositor ``2FB6`` (2 words = 8 px, fixed 8 rows).  ONE slot at ``obj[+0C]``.

Verified byte-exact vs the VM by ``overkill/probes/verify_native_object_sprites.py``, which drives the
REAL draw-type dispatch ``1010:7596`` per object and matches every compositor blit's (routine, di,
source offset).  SCOPE (fail loud, no faking): only the Tandy masked base case is handled -- objects
with ``anim (+12) != 0`` or the ``obj[+24]`` OR-inverted variant flag set select a different compositor
and are SKIPPED, not faked (documented follow-ups); unknown draw-types (``dtype`` not 0/1/2) are skipped.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from overkill.native_video.frame import SpriteBlock
from overkill.recovered.systems.sprite_textures import decode_masked_sprite

# Draw-type dispatch: obj[+14] -> routine entry (the constant cs:[75A0] table, entries 0..2).
ROUTINE_7746 = 0x7746
ROUTINE_768E = 0x768E
ROUTINE_75A6 = 0x75A6
DRAW_TYPE_ROUTINES = (ROUTINE_7746, ROUTINE_768E, ROUTINE_75A6)

# Per-routine bank id thresholds (sprite_id below -> primary bank, at/above -> secondary bank).
THRESHOLD_75A6 = 0x1C   # < : common (MANEXPL);  >= : level (G{n}), index id-0x1C
THRESHOLD_768E = 0xFA   # < : 2X2;               >= : 2X2C,          index id-0xFA

OFFSCREEN = 0xFFFF
_OFF_SPRITE_ID = 0x08
_OFF_SLOT_0C = 0x0C
_OFF_SLOT_10 = 0x10
_OFF_ANIM = 0x12
_OFF_DRAW_TYPE = 0x14
_OFF_VARIANT = 0x24

# Compositor geometry per routine (masked Tandy base case, anim 0): (comp_ip, words_per_row, rows).
_COMP_75A6 = (0x2E6E, 8, 16)
_COMP_768E = (0x2F81, 4, 16)
_COMP_7746 = (0x2FB6, 2, 8)


@dataclass(frozen=True)
class SpriteSlot:
    """One compositor blit the VM's draw routine issues for an object: source + destination + shape.

    ``comp_ip`` is the Tandy masked-compositor leaf (2E6E/2F81/2FB6); ``di`` the page destination;
    ``bank`` + ``src_off`` locate the sprite pixels; ``words_per_row``/``rows`` its geometry.  This is
    the byte-exact unit the verify probe checks against the live 7596 dispatch.
    """

    comp_ip: int
    di: int
    bank: bytes
    src_off: int
    words_per_row: int
    rows: int


@dataclass(frozen=True)
class SpriteDrawContext:
    """The VM-free inputs the object draw needs: the sprite banks, frame tables and the cell half-stride.

    Banks are the de-planarized buffers the VM keeps at the matching ``cs:[95xx]`` segment; the frame
    tables are the ``cs:[9392]/[9192]/[8F92]`` word tables (sprite index -> byte offset into the bank);
    ``half_stride`` is ``ds:[1028] >> 1`` -- the source advance to 75A6's second (``obj[+10]``) slot.
    """

    common_bank: bytes    # cs:[95A6] = MANEXPL.BIC   (75A6, id < 0x1C)
    level_bank: bytes     # cs:[95AE] = NativeLevel.graphics (75A6, id >= 0x1C)
    wide_bank: bytes      # cs:[95AA] = 2X2.BIC       (768E, id < 0xFA)
    wide_bank_hi: bytes   # cs:[95AC] = 2X2C.BIC      (768E, id >= 0xFA)
    compact_bank: bytes   # cs:[95A8] = 1X1.BIC       (7746)
    table_75a6: Sequence[int]   # cs:[9392]
    table_768e: Sequence[int]   # cs:[9192]
    table_7746: Sequence[int]   # cs:[8F92]
    half_stride: int            # ds:[1028] >> 1


def _table_get(table: Sequence[int], index: int) -> int | None:
    if 0 <= index < len(table):
        return table[index] & 0xFFFF
    return None


def object_slots(sprite_id: int, draw_type: int, slot_0c: int, slot_10: int,
                 ctx: SpriteDrawContext) -> list[SpriteSlot]:
    """The compositor slots the VM would draw for one (already anim-0, non-variant) object.

    Empty if the draw-type is not a sprite routine (0/1/2) or the frame-table index is out of range.
    A slot whose destination is off-screen (``0xFFFF``) is omitted, exactly as the VM's per-slot check.
    """
    if draw_type >= len(DRAW_TYPE_ROUTINES):
        return []
    routine = DRAW_TYPE_ROUTINES[draw_type]

    if routine == ROUTINE_75A6:
        if sprite_id < THRESHOLD_75A6:
            bank, index = ctx.common_bank, sprite_id
        else:
            bank, index = ctx.level_bank, sprite_id - THRESHOLD_75A6
        off = _table_get(ctx.table_75a6, index)
        if off is None:
            return []
        comp, words, rows = _COMP_75A6
        slots: list[SpriteSlot] = []
        if slot_0c != OFFSCREEN:
            slots.append(SpriteSlot(comp, slot_0c, bank, off, words, rows))
        if slot_10 != OFFSCREEN:
            slots.append(SpriteSlot(comp, slot_10, bank, (off + ctx.half_stride) & 0xFFFF, words, rows))
        return slots

    if routine == ROUTINE_768E:
        if slot_0c == OFFSCREEN:
            return []
        if sprite_id < THRESHOLD_768E:
            bank, index = ctx.wide_bank, sprite_id
        else:
            bank, index = ctx.wide_bank_hi, sprite_id - THRESHOLD_768E
        off = _table_get(ctx.table_768e, index)
        if off is None:
            return []
        comp, words, rows = _COMP_768E
        return [SpriteSlot(comp, slot_0c, bank, off, words, rows)]

    # ROUTINE_7746
    if slot_0c == OFFSCREEN:
        return []
    off = _table_get(ctx.table_7746, sprite_id)
    if off is None:
        return []
    comp, words, rows = _COMP_7746
    return [SpriteSlot(comp, slot_0c, ctx.compact_bank, off, words, rows)]


def _slot_block(slot: SpriteSlot, variant: bool = False) -> SpriteBlock | None:
    need = slot.words_per_row * slot.rows * 4
    src = slot.bank[slot.src_off:slot.src_off + need]
    if len(src) < need:
        return None
    tex = decode_masked_sprite(src, slot.words_per_row, slot.rows)
    if variant:
        # the 2ECB/2F40 OR-INVERTED compositors (the 7658/7716 variant tables, anim 0):
        # ``dest |= ~mask`` per word -- the sprite's opaque area saturates to colour 0xF
        # (the hit-flash whiteout); transparent pixels keep the destination.
        white = tex.pixels.copy()
        white[...] = 0x0F
        return SpriteBlock(slot.di, white, tex.opaque)
    return SpriteBlock(slot.di, tex.pixels, tex.opaque)


def object_sprite_blocks(pool, ctx: SpriteDrawContext) -> list[SpriteBlock]:
    """The drawable sprite blocks for a pool's active, anim-0 objects.

    The (anim x variant) sub-dispatch, decoded from the 7628/7658 (75A6) and 76E6/7716 (768E)
    tables: ``anim (+12) != 0`` routes to the ``7688`` NO-DRAW stub in EVERY table (the skip is
    byte-faithful, not a gap); ``variant (+24) != 0`` (anim 0) draws through the OR-inverted
    compositors (2ECB/2F40) -- the opaque silhouette saturated to 0xF.
    """
    blocks: list[SpriteBlock] = []
    for i in range(len(pool)):
        if pool.active_word(i) == 0:
            continue
        if pool.word_at(i, _OFF_ANIM) != 0:
            continue          # 7688: the no-draw stub for every anim 1..7 table entry
        variant = pool.word_at(i, _OFF_VARIANT) != 0
        for slot in object_slots(
            pool.word_at(i, _OFF_SPRITE_ID),
            pool.word_at(i, _OFF_DRAW_TYPE),
            pool.word_at(i, _OFF_SLOT_0C),
            pool.word_at(i, _OFF_SLOT_10),
            ctx,
        ):
            block = _slot_block(slot, variant=variant)
            if block is not None:
                blocks.append(block)
    return blocks
