"""Tests for the project-wide architecture layer audit.

These guard two things: the real codebase obeys the layer rules, and the audit
is not vacuously passing (it really would flag a forbidden edge).
"""
from __future__ import annotations

import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_audit():
    spec = importlib.util.spec_from_file_location(
        "audit_architecture", ROOT / "scripts" / "audit_architecture.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_layer_assignment_matches_intended_boundaries():
    audit = _load_audit()
    cases = {
        "overkill/game_core/backends.py": "game_core",
        "overkill/recovered/domain/movement.py": "source_pure",
        "overkill/recovered/systems/collision.py": "source_pure",
        "overkill/recovered/adapters/world_adapter.py": "bridge",
        "overkill/recovered/views/object_slots.py": "bridge",
        "overkill/recovered/coords.py": "bridge",
        "overkill/hooks.py": "hook_boundary",
        "overkill/hook_wrappers/sounds.py": "hook_boundary",
        "overkill/gameplay/object_runtime.py": "lifted",
        "overkill/native_video/sprite_compose.py": "native_render",
        "overkill/rendering/ega.py": "backend",
        "overkill/sounds/pc_speaker.py": "backend",
        "overkill/runtime.py": "vm",
    }
    for rel, expected in cases.items():
        assert audit.layer_of(rel) == expected, (rel, audit.layer_of(rel))


def test_module_layer_resolves_external_and_project_modules():
    audit = _load_audit()
    assert audit.module_layer("dos_re") == "vm_external"
    assert audit.module_layer("dos_re.cpu") == "vm_external"
    assert audit.module_layer("overkill.gameplay.collision") == "lifted"
    assert audit.module_layer("overkill.game_core.types") == "game_core"
    assert audit.module_layer("numpy") is None


def test_forbidden_rules_would_catch_a_core_layer_importing_the_vm():
    """Negative check: the rule table really forbids the edges we care about."""
    audit = _load_audit()
    # A pure/source layer pulling in the VM or hooks is forbidden.
    assert audit.module_layer("dos_re") in audit.FORBIDDEN["source_pure"]
    assert "hook_boundary" in audit.FORBIDDEN["game_core"]
    assert "backend" in audit.FORBIDDEN["source_pure"]
    # A backend reaching up into gameplay is forbidden.
    assert "lifted" in audit.FORBIDDEN["backend"]
    # The native render host must not reach into the VM world (hooks/lifted/VM-adapters).
    for forbidden in ("bridge", "hook_boundary", "lifted", "vm_external"):
        assert forbidden in audit.FORBIDDEN["native_render"], forbidden


def test_real_codebase_passes_the_architecture_audit():
    audit = _load_audit()
    assert audit.main() == 0


def test_object_runtime_split_modules_keep_their_surface():
    """Guard the object_runtime split: the carved-out modules expose their
    routines and object_runtime re-exports them (so hooks.py imports resolve)."""
    import overkill.hooks  # noqa: F401 - registers hooks

    from overkill.gameplay import (
        contact_side_effects,
        object_behaviors,
        object_bounds,
        object_deactivation,
        object_movement,
        object_postmove,
        object_runtime,
        object_runtime_common,
        object_spawns,
    )

    # Postmove hub + contact side-effects own their seams.
    assert callable(object_postmove.run_object_postmove_prelude_bc45)
    assert callable(object_postmove._run_object_postmove_bc4b)
    assert callable(contact_side_effects._run_object_overlap_scan_62f6)
    assert callable(contact_side_effects._run_collision_handler_bec5_observed)
    # Behaviour families + bounds tail own their seams.
    assert callable(object_behaviors._run_object_behavior_b73e)
    assert callable(object_behaviors._run_object_logic_dispatch_aa2b)
    assert callable(object_bounds._run_object_bounds_tile_tail_ad60)
    assert callable(object_bounds.run_object_bounds_tile_prelude_ad5a)

    # Each new module owns a clear responsibility.
    assert callable(object_spawns.run_object_spawn_seed_a4ea)
    assert callable(object_spawns._find_free_object_slot_7573)
    assert callable(object_runtime_common._raise_unverified_path)
    assert callable(object_runtime_common._run_interpreted_near_call_observed)
    assert callable(object_runtime_common._no_patch_guard)
    assert callable(object_deactivation._run_collision_death_tail_bfc7)
    assert callable(object_deactivation._run_deactivate_bd17_observed)
    assert callable(object_movement.run_object_x_step_left_clamp_a5d1)
    assert callable(object_movement.run_object_target_move_b729)

    # object_runtime re-exports them (the hooks.py import surface relies on this).
    for name in (
        "run_object_spawn_seed_a4ea",
        "_find_free_object_slot_7573",
        "_run_collision_death_tail_bfc7",
        "_run_deactivate_bd17_observed",
        "_raise_unverified_path",
        "run_object_x_step_left_clamp_a5d1",
        "run_object_target_move_b729",
        "_no_patch_guard",
        "run_object_postmove_prelude_bc45",
        "_run_object_postmove_bc4b",
        "_run_object_overlap_scan_62f6",
        "_run_collision_handler_bec5_observed",
        "_run_post_contact_9e69_observed",
        "_run_object_behavior_b73e",
        "_run_object_logic_dispatch_aa2b",
        "_run_object_bounds_tile_tail_ad60",
        "run_object_bounds_tile_prelude_ad5a",
    ):
        assert hasattr(object_runtime, name), f"object_runtime lost re-export of {name}"
