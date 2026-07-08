"""Explicit OVERKILL cold-start frontier classification.

This is a triage manifest, not an execution dependency.  It prevents the last
few interpreted addresses from becoming an undifferentiated ``unknown`` bucket:
each leftover is either a real hook candidate, an intentionally interpreted
bootstrap fragment, a bounded-original rare branch owned by a larger hook, or a
harmless scratch/tail address inside an already-lifted block.

``FrontierCategory``/``FrontierEntry`` and the summary/lookup helpers were
promoted verbatim into ``dos_re.frontier`` (they took no OVERKILL-specific
logic, just the manifest as a parameter instead of a module import); only the
25-entry manifest below stayed behind as real game knowledge.
"""
from __future__ import annotations

from dos_re.frontier import FrontierCategory, FrontierEntry
from dos_re.frontier import by_addr as _by_addr
from dos_re.frontier import fmt_addr
from dos_re.frontier import frontier_summary_lines as _frontier_summary_lines

Addr = tuple[int, int]


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
    FrontierEntry((0x1010, 0xA067), "overkill_frame_action_spawn_fanout_a067", "game_state", FrontierCategory.BOUNDED_ORIGINAL_RARE_BRANCH, "replaced", owner=(0x1010, 0x9B2E), notes="Input-bit gated frame action/object-spawn fanout reached from 9B2E and D04D; composes A4EA and now-lifted A515/A584/A3FF/A3CA/A2A0/A2F6/A337 children; only invalid/out-of-range A958 table targets remain action-spawn frontiers."),
    FrontierEntry((0x1010, 0xA515), "overkill_frame_action_linked_anchor_spawn_a515", "game_state", FrontierCategory.BOUNDED_ORIGINAL_RARE_BRANCH, "replaced", owner=(0x1010, 0xA067), notes="A067 child frontier: gated one-slot anchor/link spawn through 7547, A571, and B15A; structural only, no semantic entity name yet."),
    FrontierEntry((0x1010, 0xA584), "overkill_frame_action_dual_anchor_spawn_a584", "game_state", FrontierCategory.BOUNDED_ORIGINAL_RARE_BRANCH, "replaced", owner=(0x1010, 0xA067), notes="A067 child frontier: gated two-slot anchor spawn through A4EA/A571, aligned Y and raw slot-field stamps; structural only."),
    FrontierEntry((0x1010, 0xA3CA), "overkill_frame_action_side_anchor_spawn_a3ca", "game_state", FrontierCategory.BOUNDED_ORIGINAL_RARE_BRANCH, "replaced", owner=(0x1010, 0xA067), notes="A067 child frontier: four-source raw side-anchor spawn dispatcher via A966/A968/A96A/A96C and the A41A jump-table body; structural only."),
    FrontierEntry((0x1010, 0xA3FF), "overkill_frame_action_mirrored_anchor_spawn_a3ff", "game_state", FrontierCategory.BOUNDED_ORIGINAL_RARE_BRANCH, "replaced", owner=(0x1010, 0xA067), notes="A067 child frontier: two-source mirrored anchor spawn dispatcher via A962/A964, the A41A jump-table body, and the A378 SI follow-up; open A378 creates two slots via call/fallthrough; structural only."),
    FrontierEntry((0x1010, 0xA2A0), "overkill_frame_action_listed_anchor_spawn_a2a0", "game_state", FrontierCategory.BOUNDED_ORIGINAL_RARE_BRANCH, "replaced", owner=(0x1010, 0xA067), notes="A067/A0E8 child frontier: A958==5 raw listed two-slot spawn; clears a CS:9596-segment A3B4 word list, seeds DS:A3EA, then runs the A2D6 spawn/list/projection body through call and fallthrough; structural only."),
    FrontierEntry((0x1010, 0xA2F6), "overkill_frame_action_pair_spawn_a2f6", "game_state", FrontierCategory.BOUNDED_ORIGINAL_RARE_BRANCH, "replaced", owner=(0x1010, 0xA067), notes="A067/A0E8 child frontier: A958==4 gated raw two-slot spawn tail; BEFF=17, A970 increments twice, A4EA/A1AE compose both slots; structural only."),
    FrontierEntry((0x1010, 0xA337), "overkill_frame_action_pair_spawn_a337", "game_state", FrontierCategory.BOUNDED_ORIGINAL_RARE_BRANCH, "replaced", owner=(0x1010, 0xA067), notes="A067/A0E8 child frontier: A958==3 sibling raw two-slot spawn tail; BEFF=16, A970 increments twice, A4EA/A1AE compose both slots; structural only."),
    FrontierEntry((0x1010, 0x859E), "script_state_transition_helper_859e", "game_state", FrontierCategory.BOUNDED_ORIGINAL_RARE_BRANCH, "bounded-original", owner=(0x1010, 0xD04D)),
    FrontierEntry((0x1010, 0x7476), "formation_spawn_helper_7476", "gameplay_objects", FrontierCategory.BOUNDED_ORIGINAL_RARE_BRANCH, "bounded-original", owner=(0x1010, 0xB9F0)),
    FrontierEntry((0x1010, 0x5E1B), "score_or_effect_text_helper_5e1b", "gameplay_objects", FrontierCategory.BOUNDED_ORIGINAL_RARE_BRANCH, "bounded-original", owner=(0x1010, 0xB9F0)),
    FrontierEntry((0x1010, 0x5E42), "runtime_patched_object_steer_5e42", "gameplay_objects", FrontierCategory.BOUNDED_ORIGINAL_RARE_BRANCH, "hooked-runtime-patched-gameplay-variant", owner=(0x1010, 0xB9F0), notes="Cold executable bytes at 5E42 are a different display helper; the hot gameplay-patched object-steering variant is now hooked and verified."),
    FrontierEntry((0x1010, 0x61DC), "overkill_status_display_parent_61dc", "game_state", FrontierCategory.BOUNDED_ORIGINAL_RARE_BRANCH, "replaced", owner=(0x1010, 0x9E69), notes="Absorbed as a composed raw status/counter display parent around 61F7, 5A00, 6296, and 5A6C."),
    FrontierEntry((0x1010, 0x9C01), "overkill_frame_axis_condition_dispatch_9c01", "game_state", FrontierCategory.BOUNDED_ORIGINAL_RARE_BRANCH, "replaced", owner=(0x1010, 0x9B2E), notes="Absorbed child frontier inside 9B2E; combines input/axis counters and a jump table into ret/A60A/A5FC tails."),
    FrontierEntry((0x1010, 0x9CB6), "overkill_frame_contact_probe_fanout_9cb6", "game_state", FrontierCategory.BOUNDED_ORIGINAL_RARE_BRANCH, "replaced", owner=(0x1010, 0x9B2E), notes="Absorbed frame-controller contact-probe fanout around 4FF9 and BEDC-gated 9E19 calls; 9E19 is now lifted as a shared status-counter helper."),
    FrontierEntry((0x1010, 0x9E19), "overkill_post_contact_status_helper_9e19", "game_state", FrontierCategory.BOUNDED_ORIGINAL_RARE_BRANCH, "replaced", owner=(0x1010, 0x9CB6), notes="Shared post-contact/status counter helper reached by 9CB6 and B24D; gates A47C/2384/A95A, decrements A95C/A95A, emits raw BEFF event bytes, and composes 61DC/511F display children."),
    FrontierEntry((0x1010, 0xB15A), "overkill_player_chase_candidate_scan_b15a", "gameplay_objects", FrontierCategory.BOUNDED_ORIGINAL_RARE_BRANCH, "replaced", notes="Shared rotating DS:A43A effect/contact-slot candidate scan used by B1B0 and A515; pure object predicate owns the candidate gate."),
    FrontierEntry((0x1010, 0xD2A4), "rare_target_chase_tail_d2a4", "gameplay_objects", FrontierCategory.BOUNDED_ORIGINAL_RARE_BRANCH, "bounded-original", owner=(0x1010, 0xD281)),
    FrontierEntry((0x1010, 0xAB99), "object_scroll_collision_tail_ab99", "gameplay_objects", FrontierCategory.BOUNDED_ORIGINAL_RARE_BRANCH, "bounded-original", owner=(0x1010, 0xAB77)),
    FrontierEntry((0x1010, 0x837A), "object_transition_helper_837a", "gameplay_objects", FrontierCategory.BOUNDED_ORIGINAL_RARE_BRANCH, "bounded-original", owner=(0x1010, 0xABCA)),
)


FRONTIER_BY_ADDR: dict[Addr, FrontierEntry] = _by_addr(FRONTIER_MANIFEST)


def frontier_summary_lines() -> list[str]:
    return _frontier_summary_lines(FRONTIER_MANIFEST)


__all__ = [
    "FrontierCategory", "FrontierEntry", "fmt_addr",
    "FRONTIER_MANIFEST", "FRONTIER_BY_ADDR", "frontier_summary_lines",
]
