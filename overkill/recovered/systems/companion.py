"""The type-6 COMPANION handler (``1010:AB10``) -- the ship's exhaust flame, pure.

Type 6 records (the ``AA36`` type dispatch routes them straight to ``AB10``; the ``+0x18`` behavior
table is not consulted) are the player-attached effects.  Per frame: the flame HIDES (``AC22``:
``+0x00 = 0``, deactivate) when the SHIP is in a non-normal pose -- ``DS:2384``, which IS the
``237C`` anchor record's ``+0x08`` sprite field (``0x237C + 8 = 0x2384``; a probe first read it as
a separate mode global and the oracle caught the aliasing) -- reads ``>= 3``, or when the
scripted-input mode ``DS:A47C >= 3``.  Otherwise it animates (sprite = ``A40C[[2336]] + 9``, the
``& 7`` frame divider through an 8-byte anim table) and FOLLOWS the anchor: position = anchor x/y
plus the ``(dx, dy)`` pair at ``A414 + anchor_sprite * 4`` -- the offset tracks the ship's pose
(sprites 0..2), so the flame sits on the exhaust in every pose.
"""
from __future__ import annotations

from dataclasses import dataclass

from overkill.recovered.islands import recovered_island

COMPANION_HIDE_ANCHOR_SPRITE = 3   # DS:2384 == the 237C anchor's +0x08 (the ship pose sprite)
COMPANION_HIDE_A47C = 3
COMPANION_ANIM_TABLE = 0xA40C     # 8 bytes, indexed by the DS:2336 (& 7) divider
COMPANION_SPRITE_BIAS = 9
COMPANION_OFFSET_TABLE = 0xA414   # (dx, dy) word pairs, indexed by the ANCHOR's sprite * 4


@dataclass(frozen=True)
class CompanionStep:
    """One frame of the companion: deactivate, or the new sprite + anchored position."""

    deactivate: bool
    sprite: int = 0
    x_word: int = 0
    y_word: int = 0


@recovered_island(
    asm=("1010:AB10..AB4E", "1010:AC22..AC27"),
    contract="the type-6 companion (exhaust flame): deactivate when the ANCHOR SPRITE (DS:2384 == "
             "the 237C record's +0x08, oracle-pinned aliasing) >= 3 or [A47C] >= 3; else sprite = "
             "A40C[[2336]] + 9 and position = the anchor + the A414[anchor_sprite*4] (dx, dy) pair",
    status="VERIFIED",
    merge_target="PlayerSystem",
    unknowns="",
)
def step_companion_ab10(*, scripted_a47c: int, divider_2336: int,
                        anchor_x: int, anchor_y: int, anchor_sprite: int,
                        anim_table, offset_pair_at) -> CompanionStep:
    """One frame of ``1010:AB10`` (pure).  ``anim_table`` is the 8-byte ``A40C`` table;
    ``offset_pair_at(anchor_sprite) -> (dx, dy)`` serves the ``A414`` pair reads."""
    if (anchor_sprite & 0xFFFF) >= COMPANION_HIDE_ANCHOR_SPRITE \
            or (scripted_a47c & 0xFFFF) >= COMPANION_HIDE_A47C:
        return CompanionStep(deactivate=True)
    sprite = (anim_table[divider_2336 & 0x7] + COMPANION_SPRITE_BIAS) & 0xFFFF
    dx, dy = offset_pair_at(anchor_sprite & 0xFFFF)
    return CompanionStep(deactivate=False, sprite=sprite,
                         x_word=(anchor_x + dx) & 0xFFFF, y_word=(anchor_y + dy) & 0xFFFF)
