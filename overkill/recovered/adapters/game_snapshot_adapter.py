"""Decode the live runtime into a recovered :class:`GameSnapshot` (bridge).

Reads the original DOS memory of the *running* game (no parallel native runtime)
using the canonical layout facts in :mod:`overkill.recovered.views.object_slots`,
and projects them into the pure :mod:`overkill.recovered.domain.game_snapshot`
value object the frame verifier diffs.
"""
from __future__ import annotations

from overkill.recovered.adapters.world_adapter import RUNTIME_GLOBAL_WORDS
from overkill.recovered.domain.game_snapshot import GameSnapshot, ObjectSlotSnapshot
from overkill.recovered.views.frame_timers import FrameTimersView
from overkill.recovered.views.object_slots import (
    EFFECT_OBJECT_TABLE_BASE,
    EFFECT_OBJECT_TABLE_COUNT,
    GAMEPLAY_OBJECT_TABLE_BASE,
    GAMEPLAY_OBJECT_TABLE_COUNT,
    ObjectSlotView,
    ObjectTableView,
    SCORE_BCD_BASE,
    SCORE_BCD_LENGTH,
)

GAME_DATA_SEGMENT_POINTER = (0x1010, 0x9596)

# Curated global counters/gates the frame verifier should compare each frame.
# Reuses the evidence-backed world-projection globals and adds the gameplay
# counters that drive object lifecycles - notably the action-spawn/weapon-list
# counters DS:A970..A978 (the ringlas bug diverged on DS:A972 but it was not in
# the snapshot, so it was only caught downstream once it corrupted object slots).
SNAPSHOT_GLOBAL_WORDS: tuple[tuple[str, int], ...] = tuple(RUNTIME_GLOBAL_WORDS) + (
    ("action_spawn_counter_a970", 0xA970),
    ("action_spawn_counter_a972", 0xA972),
    ("action_spawn_counter_a974", 0xA974),
    ("action_spawn_counter_a976", 0xA976),
    ("action_spawn_counter_a978", 0xA978),
    ("logic_a_counter_a97e", 0xA97E),
    ("formation_game_counter_2340", 0x2340),
    ("game_gate_2330", 0x2330),
    ("game_gate_232e", 0x232E),
    ("game_mode_2356", 0x2356),
    ("contact_fanout_bedc", 0xBEDC),
    ("mode_flag_bdac", 0xBDAC),
    # Frame-controller (9B2E) phase/progress state.  DS:A47C gates the 99F6
    # round-to-even of the camera anchor (DS:2380); DS:2350 is the level-progress
    # counter A66F compares to 0xEA0 (mothership trigger) that sets A47C=1.  Both
    # are guarded here so a divergence in either is caught at its own frame rather
    # than only downstream once it perturbs the camera anchor.
    ("phase_gate_a47c", 0xA47C),
    ("level_progress_2350", 0x2350),
)


def _game_ds(cpu) -> int:
    seg, off = GAME_DATA_SEGMENT_POINTER
    return cpu.mem.rw(seg & 0xFFFF, off & 0xFFFF) & 0xFFFF


def _decode_slot(slot: ObjectSlotView, table: str, index: int) -> ObjectSlotSnapshot:
    # The view owns the object-record field layout, so the offset->field mapping
    # lives in one place (no parallel decode here); record_bytes() keeps the exact
    # raw image alongside the named fields for byte-level fidelity.  Decode does no
    # CPU stepping, so the per-field reads and the block read see identical memory.
    return ObjectSlotSnapshot(
        table=table,
        index=index,
        active_word=slot.active_word,
        x_word=slot.x_word,
        y_word=slot.y_word,
        direction_or_step=slot.direction_or_step,
        sprite_or_state=slot.sprite_or_state,
        object_type=slot.object_type,
        draw_layer=slot.draw_layer,
        logic_id=slot.logic_id,
        previous_logic_id=slot.previous_logic_id,
        substate=slot.substate,
        target_x_word=slot.target_x_word,
        target_y_word=slot.target_y_word,
        raw=slot.record_bytes(),
    )


def _decode_table(cpu, ds: int, base: int, count: int, table: str) -> list[ObjectSlotSnapshot]:
    # A live table lens over the resolved game DS (not cpu.s.ds, which can be
    # anything at the checkpoint the verifier samples).
    view = ObjectTableView(cpu.mem, ds, base, count)
    return [_decode_slot(slot, table, i) for i, slot in enumerate(view)]


def decode_game_snapshot(cpu) -> GameSnapshot:
    ds = _game_ds(cpu)
    frame_timers = FrameTimersView(cpu.mem, ds).values()
    score_bcd = bytes(cpu.mem.rb(ds, (SCORE_BCD_BASE + i) & 0xFFFF) for i in range(SCORE_BCD_LENGTH))
    objects = (
        _decode_table(cpu, ds, EFFECT_OBJECT_TABLE_BASE, EFFECT_OBJECT_TABLE_COUNT, "effect")
        + _decode_table(cpu, ds, GAMEPLAY_OBJECT_TABLE_BASE, GAMEPLAY_OBJECT_TABLE_COUNT, "gameplay")
    )
    state_globals = tuple(
        (name, cpu.mem.rw(ds, off & 0xFFFF) & 0xFFFF) for name, off in SNAPSHOT_GLOBAL_WORDS
    )
    return GameSnapshot(
        frame_timers=frame_timers,
        score_bcd=score_bcd,
        objects=tuple(objects),
        state_globals=state_globals,
    )
