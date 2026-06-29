"""Bucket C: the BC4B post-move bounds half -- object_postmove_x_bounds_deactivates_bc4b (the X-bounds
death) + the recovered Y clamp, VM-free.  Byte-exactness vs the real VM BC4B (y + active) is gated by
overkill/probes/verify_native_object_postmove_bounds_bc4b.py (L2 1498/1498, L6_boss 2257/2257,
player_death 2181/2181, 0 divergence); this locks the precise/wide box selection + the bounds."""
from __future__ import annotations

from overkill.recovered.systems.collision import (
    clamp_postmove_y_bcb1,
    object_postmove_x_bounds_deactivates_bc4b,
)


def test_postmove_x_bounds_precise_box():
    # Not wide (global_disable 0, normal logic id): the box is [-C0h, F0h).
    assert object_postmove_x_bounds_deactivates_bc4b(0x0050, 0, 0x20) is False  # inside
    assert object_postmove_x_bounds_deactivates_bc4b(0xFF3F, 0, 0x20) is True   # -C1h < -C0h
    assert object_postmove_x_bounds_deactivates_bc4b(0xFF40, 0, 0x20) is False  # -C0h == lower (kept)
    assert object_postmove_x_bounds_deactivates_bc4b(0x00F0, 0, 0x20) is True   # F0h >= upper
    assert object_postmove_x_bounds_deactivates_bc4b(0x00EF, 0, 0x20) is False  # EFh inside


def test_postmove_x_bounds_wide_box_when_global_disable_set():
    # global_disable != 0 -> wide box [-14h, F0h).
    assert object_postmove_x_bounds_deactivates_bc4b(0xFFEC, 1, 0x20) is False  # -14h == lower (kept)
    assert object_postmove_x_bounds_deactivates_bc4b(0xFFEB, 1, 0x20) is True   # -15h < -14h
    assert object_postmove_x_bounds_deactivates_bc4b(0xFF40, 1, 0x20) is True   # -C0h killed by the wide box


def test_postmove_x_bounds_wide_box_for_exempt_logic_ids():
    # An exempt logic id (e.g. 0x48) uses the wide box even with global_disable 0.
    assert object_postmove_x_bounds_deactivates_bc4b(0xFF40, 0, 0x48) is True   # -C0h < -14h
    assert object_postmove_x_bounds_deactivates_bc4b(0xFFEC, 0, 0x48) is False  # -14h kept
    # A non-exempt id at the same X with the precise box survives.
    assert object_postmove_x_bounds_deactivates_bc4b(0xFF80, 0, 0x20) is False  # -80h inside precise box


def test_postmove_y_clamp_is_the_bc4b_y_half():
    # The Y half of the BC4B bounds transform is the recovered BCB1 clamp into [0, C0h].
    assert clamp_postmove_y_bcb1(0x0050).y_word == 0x0050
    assert clamp_postmove_y_bcb1(0x00D0).y_word == 0x00C0  # > C0h clamps down
    assert clamp_postmove_y_bcb1(0xFFF0).y_word == 0x0000  # negative clamps to 0
