"""Pure 1010:30D2 object screen-di projection (Tandy): di = (obj_y >> 1) + column_di, with a cull
when obj_x >= 0xE0 or the column entry is FFFFh.  Byte-exactness vs the VM is separately gated by
overkill/probes/verify_native_projection.py (4624/4624 on L2); this locks the formula + the cull
edges in a VM-free unit test."""
from __future__ import annotations

from overkill.native_video.projection import (
    PROJECTION_CULL_ENTRY,
    PROJECTION_X_CULL,
    project_object_to_di,
)


def test_project_object_to_di_core_formula():
    # Confirmed vs the VM: y=0x60, column_di=0x4b28 -> 0x4b58 (== slot +0C minus scroll/phase).
    assert project_object_to_di(0x0050, 0x0060, 0x4B28) == 0x4B58
    assert project_object_to_di(0x0000, 0x000A, 0x0100) == 0x0105  # (0x0A >> 1) + 0x0100
    # 16-bit wrap on the add.
    assert project_object_to_di(0x0010, 0x0004, 0xFFFE) == 0x0000  # (4 >> 1) + 0xFFFE -> 0


def test_project_object_to_di_culls():
    assert project_object_to_di(PROJECTION_X_CULL, 0x40, 0x1000) is None   # x == 0xE0 (off right edge)
    assert project_object_to_di(0x0123, 0x40, 0x1000) is None              # x past the edge
    assert project_object_to_di(0x40, 0x40, PROJECTION_CULL_ENTRY) is None  # column entry FFFFh
    # x just under the cull boundary still projects.
    assert project_object_to_di(0x00DF, 0x40, 0x1000) == ((0x40 >> 1) + 0x1000) & 0xFFFF
