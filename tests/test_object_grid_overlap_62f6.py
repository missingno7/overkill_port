"""VM-free unit tests for the pure 1010:62F6 object-vs-object grid overlap predicate.

Pins the cell-footprint match (``object_grid_overlap_62f6``): the candidate's vertical cell run
(two cells when its Y is not 8px-aligned, else one, always plus the cell above), the horizontal
run (cell + the one left), and the wide-scanner (object_type 2) widening of both runs -- narrowed
on X for logic ids 78h/79h.  The demo-level confirmation is the cross-check in the 62F6 scan hook
(`contact_side_effects._run_object_overlap_scan_62f6`), exercised by collision frame-replays.
"""
from __future__ import annotations

from overkill.recovered.systems.collision import object_grid_overlap_62f6


def test_aligned_candidate_narrow_scanner():
    # cand (0x80, 0x40) aligned, scanner object_type 1: y_cells [0x40,0x38], x_cells [0x80,0x78].
    assert object_grid_overlap_62f6(0x80, 0x40, 0x80, 0x40, 1, 0x10) is True
    assert object_grid_overlap_62f6(0x78, 0x38, 0x80, 0x40, 1, 0x10) is True
    assert object_grid_overlap_62f6(0x70, 0x40, 0x80, 0x40, 1, 0x10) is False  # x out of [80,78]
    assert object_grid_overlap_62f6(0x80, 0x30, 0x80, 0x40, 1, 0x10) is False  # y out of [40,38]


def test_unaligned_candidate_y_adds_cell():
    # cand_y = 0x44 (not 8px-aligned): y_cells [0x48,0x40,0x38].
    assert object_grid_overlap_62f6(0x80, 0x48, 0x80, 0x44, 1, 0x10) is True
    assert object_grid_overlap_62f6(0x80, 0x40, 0x80, 0x44, 1, 0x10) is True
    assert object_grid_overlap_62f6(0x80, 0x30, 0x80, 0x44, 1, 0x10) is False


def test_wide_scanner_widens_both_runs():
    # object_type 2: y_cells [0x40,0x38,0x30,0x28], x_cells [0x80,0x78,0x70,0x68].
    assert object_grid_overlap_62f6(0x68, 0x28, 0x80, 0x40, 2, 0x10) is True
    assert object_grid_overlap_62f6(0x60, 0x40, 0x80, 0x40, 2, 0x10) is False  # x out of the 4-cell run


def test_wide_scanner_x_narrowed_for_logic_78_79():
    # object_type 2 but logic id 78h/79h keeps the narrow 2-cell X run [0x80,0x78].
    assert object_grid_overlap_62f6(0x70, 0x28, 0x80, 0x40, 2, 0x78) is False
    assert object_grid_overlap_62f6(0x70, 0x28, 0x80, 0x40, 2, 0x10) is True   # non-78/79 widens X
