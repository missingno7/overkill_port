"""Native (VM-free) object -> sprite-block bridge: turn an object slot into its drawable sprite.

The VM's per-object sprite draw ``1010:75A6`` reads the object record and blits its sprite:

    sprite_id = obj[+08];  if sprite_id >= 0x1C:  si = cs:[0x9392 + (sprite_id-0x1C)*2]   (descriptor
        table, linear 0x400 steps -> the sprite's offset in the LEVEL sprite bank cs:[95AE] =
        NativeLevel.graphics);  di = obj[+0C];  anim = obj[+12];  the (mode,anim) dispatch at cs:[7628]
        selects the compositor -- Tandy (mode 2), anim 0 -> ``2E6E`` (8-word/32px masked, CX=0x10 rows).

This is the VM-free counterpart for the LEVEL bank (``sprite_id >= 0x1C``): map an object slot to the
recovered ``decode_masked_sprite`` texture at the descriptor offset, positioned at ``di``.  It reuses
the already-recovered decode + the byte-exact ``NativeLevel.graphics`` load, so no VM.

SCOPE (fail loud, no faking): only the LEVEL bank + the Tandy masked (anim 0, ``2E6E``) case is handled.
``sprite_id < 0x1C`` is the COMMON sprite bank ``cs:[95A6]`` (the player ship + shared effects, built
at boot from SHIP.BIC etc.) -- not loaded here yet; those slots are skipped, not faked. ``anim != 0``
maps to the dispatch's ``0x7688`` no-draw slot, and the ``obj[+24]`` flag selects the OR-inverted
``2ECB`` variant -- both are follow-ups. Verified byte-exact vs the VM's ``75A6`` by
``overkill/probes/verify_native_object_sprites.py``.
"""
from __future__ import annotations

from overkill.native_video.frame import SpriteBlock
from overkill.recovered.systems.sprite_textures import decode_masked_sprite

COMMON_BANK_THRESHOLD = 0x1C   # sprite_id < this -> the common bank cs:[95A6] (not handled here)
TANDY_WORDS_PER_ROW = 8        # 2E6E compositor: 8 words/row = 32 px
TANDY_ROWS = 0x10              # CX = 0x10 rows
_OFF_SPRITE_ID = 0x08
_OFF_DI = 0x0C
_OFF_ANIM = 0x12
_SPRITE_SRC_BYTES = TANDY_WORDS_PER_ROW * TANDY_ROWS * 4   # 512 bytes for one masked sprite


def level_object_sprite_blocks(pool, level_graphics: bytes, descriptor_table) -> list[SpriteBlock]:
    """The level-bank sprite blocks for a pool's active objects (Tandy 2E6E masked, anim 0).

    ``level_graphics`` is ``NativeLevel.graphics`` (the de-planarized G{n}.BIC sprite bank = the VM's
    ``cs:[95AE]``).  ``descriptor_table`` is the ``cs:[9392]`` word table (indexed by ``sprite_id-0x1C``)
    giving each sprite's byte offset into that bank -- it is NOT a simple ``*0x400`` formula (confirmed:
    high ids like 0x162 map to a non-linear offset), so the real table must be read.  Returns one
    :class:`SpriteBlock` per drawable level-bank object; common-bank (``sprite_id < 0x1C``),
    ``anim != 0`` and off-screen (``di == 0xFFFF``) slots are skipped (documented follow-ups, not faked).
    """
    blocks: list[SpriteBlock] = []
    for i in range(len(pool)):
        if pool.active_word(i) == 0:
            continue
        sprite_id = pool.word_at(i, _OFF_SPRITE_ID)
        if sprite_id < COMMON_BANK_THRESHOLD:
            continue
        if pool.word_at(i, _OFF_ANIM) != 0:
            continue
        di = pool.word_at(i, _OFF_DI)
        if di == 0xFFFF:
            continue
        table_index = sprite_id - COMMON_BANK_THRESHOLD
        if table_index >= len(descriptor_table):
            continue
        off = descriptor_table[table_index] & 0xFFFFF
        src = level_graphics[off:off + _SPRITE_SRC_BYTES]
        if len(src) < _SPRITE_SRC_BYTES:
            continue
        tex = decode_masked_sprite(src, TANDY_WORDS_PER_ROW, TANDY_ROWS)
        blocks.append(SpriteBlock(di, tex.pixels, tex.opaque))
    return blocks
