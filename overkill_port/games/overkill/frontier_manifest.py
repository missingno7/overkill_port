"""Explicit OVERKILL cold-start frontier classification.

This is a triage manifest, not an execution dependency.  It prevents the last
few interpreted addresses from becoming an undifferentiated ``unknown`` bucket:
each leftover is either a real hook candidate, an intentionally interpreted
bootstrap fragment, a bounded-original rare branch owned by a larger hook, or a
harmless scratch/tail address inside an already-lifted block.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

Addr = tuple[int, int]


class FrontierCategory(StrEnum):
    FINAL_ORCHESTRATOR = "final-orchestrator"
    SAME_IP_LOOP_GATE = "same-ip-loop-gate"
    DO_NOT_HOOK_BOOTSTRAP = "do-not-hook-bootstrap"
    BOUNDED_ORIGINAL_RARE_BRANCH = "bounded-original-rare-branch"
    UNCLASSIFIED_HARMLESS_TAIL = "unclassified-harmless-scratch-tail"
    HOOK_CANDIDATE = "hook-candidate"


@dataclass(frozen=True)
class FrontierEntry:
    addr: Addr
    name: str
    island: str
    category: FrontierCategory
    status: str
    owner: Addr | None = None
    notes: str = ""


FRONTIER_MANIFEST: tuple[FrontierEntry, ...] = (
    FrontierEntry(
        (0x1010, 0xD007),
        "overkill_main_frame_loop_d007",
        "game_state",
        FrontierCategory.FINAL_ORCHESTRATOR,
        "replaced",
        notes=(
            "One full gameplay/attract frame iteration.  Same-IP loop metadata "
            "requires the ASM verifier to execute at least one step before "
            "accepting D007 as a continuation."
        ),
    ),
    FrontierEntry(
        (0x1010, 0xD03E),
        "main_frame_same_ip_loop_gate_d03e",
        "game_state",
        FrontierCategory.SAME_IP_LOOP_GATE,
        "owned-by-D007",
        owner=(0x1010, 0xD007),
        notes="Final CMP/JZ gate that loops back to D007 when DS:98C3 is zero.",
    ),
    FrontierEntry(
        (0x1010, 0xD040),
        "main_frame_exit_tail_d040",
        "game_state",
        FrontierCategory.HOOK_CANDIDATE,
        "classified-frontier",
        owner=(0x1010, 0xD007),
        notes=(
            "Exit tail after D007 breaks out of the frame loop.  It clears BDAC "
            "and calls the mode/input transition helpers at 5AEE and 526A."
        ),
    ),
    FrontierEntry(
        (0x32FF, 0x0052),
        "inner_unpack_relocation_bootstrap_32ff_0052",
        "bootstrap",
        FrontierCategory.DO_NOT_HOOK_BOOTSTRAP,
        "classified-do-not-hook",
        notes=(
            "Runtime allocated transient unpack/self-relocation bootstrap.  Keep "
            "classified away from gameplay unknowns; do not lift unless boot "
            "performance itself becomes the target."
        ),
    ),
    FrontierEntry((0x1010, 0x0744), "frame_service_gate_enabled_tail_0744", "game_state", FrontierCategory.BOUNDED_ORIGINAL_RARE_BRANCH, "bounded-original", owner=(0x1010, 0x073C)),
    FrontierEntry((0x1010, 0xA2D6), "demo_object_spawn_allocator_a2d6", "game_state", FrontierCategory.BOUNDED_ORIGINAL_RARE_BRANCH, "bounded-original", owner=(0x1010, 0xA212)),
    FrontierEntry((0x1010, 0xA067), "frame_ui_state_object_helper_a067", "game_state", FrontierCategory.BOUNDED_ORIGINAL_RARE_BRANCH, "bounded-original", owner=(0x1010, 0xD04D)),
    FrontierEntry((0x1010, 0x859E), "script_state_transition_helper_859e", "game_state", FrontierCategory.BOUNDED_ORIGINAL_RARE_BRANCH, "bounded-original", owner=(0x1010, 0xD04D)),
    FrontierEntry((0x1010, 0x7476), "formation_spawn_helper_7476", "gameplay_objects", FrontierCategory.BOUNDED_ORIGINAL_RARE_BRANCH, "bounded-original", owner=(0x1010, 0xB9F0)),
    FrontierEntry((0x1010, 0x5E1B), "score_or_effect_text_helper_5e1b", "gameplay_objects", FrontierCategory.BOUNDED_ORIGINAL_RARE_BRANCH, "bounded-original", owner=(0x1010, 0xB9F0)),
    FrontierEntry((0x1010, 0x5E42), "score_or_effect_text_helper_5e42", "gameplay_objects", FrontierCategory.BOUNDED_ORIGINAL_RARE_BRANCH, "bounded-original", owner=(0x1010, 0xB9F0)),
    FrontierEntry((0x1010, 0x61DC), "rare_status_display_helper_61dc", "gameplay_objects", FrontierCategory.BOUNDED_ORIGINAL_RARE_BRANCH, "bounded-original", owner=(0x1010, 0x9E69)),
    FrontierEntry((0x1010, 0xD2A4), "rare_target_chase_tail_d2a4", "gameplay_objects", FrontierCategory.BOUNDED_ORIGINAL_RARE_BRANCH, "bounded-original", owner=(0x1010, 0xD281)),
    FrontierEntry((0x1010, 0xAB99), "object_scroll_collision_tail_ab99", "gameplay_objects", FrontierCategory.BOUNDED_ORIGINAL_RARE_BRANCH, "bounded-original", owner=(0x1010, 0xAB77)),
    FrontierEntry((0x1010, 0x837A), "object_transition_helper_837a", "gameplay_objects", FrontierCategory.BOUNDED_ORIGINAL_RARE_BRANCH, "bounded-original", owner=(0x1010, 0xABCA)),
)


FRONTIER_BY_ADDR: dict[Addr, FrontierEntry] = {entry.addr: entry for entry in FRONTIER_MANIFEST}


def fmt_addr(addr: Addr) -> str:
    return f"{addr[0]:04X}:{addr[1]:04X}"


def frontier_summary_lines() -> list[str]:
    lines = ["== explicit cold-start frontier manifest =="]
    for entry in FRONTIER_MANIFEST:
        owner = f" owner={fmt_addr(entry.owner)}" if entry.owner else ""
        lines.append(
            f"  - {fmt_addr(entry.addr)} {entry.category.value:<34} "
            f"{entry.status:<24} {entry.name}{owner}"
        )
    return lines
