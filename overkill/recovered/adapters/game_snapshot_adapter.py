"""Decode the live runtime into a recovered :class:`GameSnapshot` (bridge).

Reads the original DOS memory of the *running* game (no parallel native runtime)
using the canonical layout facts in :mod:`overkill.recovered.views.object_slots`,
and projects them into the pure :mod:`overkill.recovered.domain.game_snapshot`
value object the frame verifier diffs.
"""
from __future__ import annotations

from overkill.recovered.domain.game_snapshot import GameSnapshot, ObjectSlotSnapshot
from overkill.recovered.views.object_slots import (
    EFFECT_OBJECT_TABLE_BASE,
    EFFECT_OBJECT_TABLE_COUNT,
    FRAME_TIMER_COUNT,
    FRAME_TIMER_TABLE_BASE,
    GAMEPLAY_OBJECT_TABLE_BASE,
    GAMEPLAY_OBJECT_TABLE_COUNT,
    OBJECT_SLOT_STRIDE,
    OFF_ACTIVE_WORD,
    OFF_DIRECTION_OR_STEP,
    OFF_DRAW_LAYER,
    OFF_LOGIC_ID,
    OFF_OBJECT_TYPE,
    OFF_PREVIOUS_LOGIC_ID,
    OFF_SPRITE_OR_STATE,
    OFF_SUBSTATE,
    OFF_TARGET_X,
    OFF_TARGET_Y,
    OFF_X,
    OFF_Y,
    SCORE_BCD_BASE,
    SCORE_BCD_LENGTH,
)

GAME_DATA_SEGMENT_POINTER = (0x1010, 0x9596)


def _game_ds(cpu) -> int:
    seg, off = GAME_DATA_SEGMENT_POINTER
    return cpu.mem.rw(seg & 0xFFFF, off & 0xFFFF) & 0xFFFF


def _read_record(cpu, ds: int, base: int) -> bytes:
    return bytes(cpu.mem.rb(ds, (base + i) & 0xFFFF) for i in range(OBJECT_SLOT_STRIDE))


def _decode_slot(raw: bytes, table: str, index: int) -> ObjectSlotSnapshot:
    def w(o: int) -> int:
        return raw[o] | (raw[o + 1] << 8)

    return ObjectSlotSnapshot(
        table=table,
        index=index,
        active_word=w(OFF_ACTIVE_WORD),
        x_word=w(OFF_X),
        y_word=w(OFF_Y),
        direction_or_step=w(OFF_DIRECTION_OR_STEP),
        sprite_or_state=w(OFF_SPRITE_OR_STATE),
        object_type=w(OFF_OBJECT_TYPE),
        draw_layer=w(OFF_DRAW_LAYER),
        logic_id=w(OFF_LOGIC_ID),
        previous_logic_id=w(OFF_PREVIOUS_LOGIC_ID),
        substate=w(OFF_SUBSTATE),
        target_x_word=w(OFF_TARGET_X),
        target_y_word=w(OFF_TARGET_Y),
        raw=raw,
    )


def _decode_table(cpu, ds: int, base: int, count: int, table: str) -> list[ObjectSlotSnapshot]:
    return [
        _decode_slot(_read_record(cpu, ds, base + i * OBJECT_SLOT_STRIDE), table, i)
        for i in range(count)
    ]


def decode_game_snapshot(cpu) -> GameSnapshot:
    ds = _game_ds(cpu)
    frame_timers = tuple(
        cpu.mem.rw(ds, (FRAME_TIMER_TABLE_BASE + i * 2) & 0xFFFF) for i in range(FRAME_TIMER_COUNT)
    )
    score_bcd = bytes(cpu.mem.rb(ds, (SCORE_BCD_BASE + i) & 0xFFFF) for i in range(SCORE_BCD_LENGTH))
    objects = (
        _decode_table(cpu, ds, EFFECT_OBJECT_TABLE_BASE, EFFECT_OBJECT_TABLE_COUNT, "effect")
        + _decode_table(cpu, ds, GAMEPLAY_OBJECT_TABLE_BASE, GAMEPLAY_OBJECT_TABLE_COUNT, "gameplay")
    )
    return GameSnapshot(frame_timers=frame_timers, score_bcd=score_bcd, objects=tuple(objects))
