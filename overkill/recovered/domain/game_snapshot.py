"""Pure recovered whole-frame game-state snapshot + semantic diff.

A source-like value object for one decoded gameplay frame: the per-frame
countdown timers, the packed-BCD score, and every object-table slot (proven
named fields plus the full raw record for byte-exact fidelity).  The adapter in
``overkill.recovered.adapters.game_snapshot_adapter`` decodes one of these from
the live runtime; :func:`diff_game_snapshot` produces a structured, field-level
divergence report (not an RGB diff) that the frame verifier uses to compare the
ASM-oracle runtime against the hooked runtime each frame.

Pure: ordinary values only, no VM/cpu/memory/addresses (audited).
"""
from __future__ import annotations

from dataclasses import dataclass, fields


@dataclass(frozen=True, slots=True)
class ObjectSlotSnapshot:
    """One decoded object-table record: proven named fields + the raw 0x38 bytes."""

    table: str
    index: int
    active_word: int
    x_word: int
    y_word: int
    direction_or_step: int
    sprite_or_state: int
    object_type: int
    draw_layer: int
    logic_id: int
    previous_logic_id: int
    substate: int
    target_x_word: int
    target_y_word: int
    raw: bytes


@dataclass(frozen=True, slots=True)
class GameSnapshot:
    frame_timers: tuple[int, ...]
    score_bcd: bytes
    objects: tuple[ObjectSlotSnapshot, ...]


@dataclass(frozen=True, slots=True)
class FieldDivergence:
    path: str
    expected: object
    actual: object

    def __str__(self) -> str:
        return f"{self.path}: expected {self.expected!r}, got {self.actual!r}"


_SLOT_NAMED_FIELDS = tuple(
    f.name for f in fields(ObjectSlotSnapshot) if f.name not in ("table", "index", "raw")
)


def _diff_slot(expected: ObjectSlotSnapshot, actual: ObjectSlotSnapshot) -> list[FieldDivergence]:
    out: list[FieldDivergence] = []
    label = f"objects[{expected.table}:{expected.index}]"
    for name in _SLOT_NAMED_FIELDS:
        ev = getattr(expected, name)
        av = getattr(actual, name)
        if ev != av:
            out.append(FieldDivergence(f"{label}.{name}", ev, av))
    if expected.raw != actual.raw:
        out.append(FieldDivergence(f"{label}.raw", expected.raw.hex(), actual.raw.hex()))
    return out


def diff_game_snapshot(expected: GameSnapshot, actual: GameSnapshot) -> list[FieldDivergence]:
    """Field-level divergences between two decoded frames (empty == identical)."""
    out: list[FieldDivergence] = []
    if expected.frame_timers != actual.frame_timers:
        out.append(FieldDivergence("frame_timers", expected.frame_timers, actual.frame_timers))
    if expected.score_bcd != actual.score_bcd:
        out.append(FieldDivergence("score_bcd", expected.score_bcd.hex(), actual.score_bcd.hex()))
    if len(expected.objects) != len(actual.objects):
        out.append(FieldDivergence("objects.len", len(expected.objects), len(actual.objects)))
    else:
        for exp_obj, act_obj in zip(expected.objects, actual.objects):
            out.extend(_diff_slot(exp_obj, act_obj))
    return out


def format_divergence_report(divergences: list[FieldDivergence], *, limit: int = 40) -> str:
    if not divergences:
        return "game state identical"
    lines = [f"{len(divergences)} field(s) differ:"]
    for d in divergences[:limit]:
        lines.append(f"  - {d}")
    if len(divergences) > limit:
        lines.append(f"  ... and {len(divergences) - limit} more")
    return "\n".join(lines)
