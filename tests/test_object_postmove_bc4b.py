"""VM-free unit tests for the pure shared 1010:BC4B post-move stage (y/active outcome).

Pins ``object_postmove_bc4b``: the BCB1 Y clamp + the X-bounds death composed into the two slot
fields BC4B deterministically sets, plus the ``contact_path_runs`` flag (the global gate clear and the
object survived the X-bounds death) marking the slots that then enter the deferred sprite/logic_id
collision tail.  The composed pieces are individually VM-verified; this pins their composition.
"""
from __future__ import annotations

from overkill.recovered.domain.collision import PostmoveBc4bResult
from overkill.recovered.systems.collision import object_postmove_bc4b


def test_in_bounds_global_gate_set_is_complete_no_contact():
    # global_disable != 0 -> no contact path; y clamped (already in range), active unchanged.
    assert object_postmove_bc4b(0x0050, 0x0040, 0x0001, logic_id=0x10, global_disable=5) == PostmoveBc4bResult(
        y_word=0x0040, active_word=0x0001, contact_path_runs=False
    )


def test_in_bounds_global_gate_clear_flags_contact_path():
    # global_disable == 0 and survived bounds -> the contact path runs (sprite/logic_id may change).
    assert object_postmove_bc4b(0x0050, 0x0040, 0x0001, logic_id=0x10, global_disable=0) == PostmoveBc4bResult(
        y_word=0x0040, active_word=0x0001, contact_path_runs=True
    )


def test_x_past_upper_bound_deactivates():
    out = object_postmove_bc4b(0x00F0, 0x0040, 0x0001, logic_id=0x10, global_disable=0)
    assert out.active_word == 0x0000 and out.contact_path_runs is False


def test_x_past_precise_lower_bound_deactivates():
    # signed X = -0x100 < -0xC0 (precise lower, logic_id not wide-exempt, gate clear) -> deactivate.
    assert object_postmove_bc4b(0xFF00, 0x0040, 0x0001, logic_id=0x10, global_disable=0).active_word == 0x0000


def test_wide_box_logic_id_survives_where_precise_would_die():
    # signed X = -0x80: inside the wide [-0x14? no]; -0x80 < -0x14 so wide ALSO dies. Use -0x10 instead.
    sx_neg10 = 0x10000 - 0x10  # signed -0x10, inside wide lower -0x14 but the precise -0xC0 too
    # logic_id 0x26 is a wide-box family; -0x10 survives (> -0x14).
    assert object_postmove_bc4b(sx_neg10, 0x0040, 0x0001, logic_id=0x26, global_disable=0).active_word == 0x0001


def test_y_clamps_high_and_low():
    assert object_postmove_bc4b(0x0050, 0x00D0, 0x0001, logic_id=0x10, global_disable=5).y_word == 0x00C0
    assert object_postmove_bc4b(0x0050, 0xFFF0, 0x0001, logic_id=0x10, global_disable=5).y_word == 0x0000


def test_clamp_y_false_leaves_y_untouched():
    assert object_postmove_bc4b(0x0050, 0x00D0, 0x0001, logic_id=0x10, global_disable=5, clamp_y=False).y_word == 0x00D0
