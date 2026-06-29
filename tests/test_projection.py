"""Pure 1010:30D2 object screen-di projection (Tandy): di = (obj_y >> 1) + column_di, with a cull
when obj_x >= 0xE0 or the column entry is FFFFh.  Byte-exactness vs the VM is separately gated by
overkill/probes/verify_native_projection.py (4624/4624 on L2); this locks the formula + the cull
edges in a VM-free unit test."""
from __future__ import annotations

from overkill.native_video.projection import (
    PROJECTION_CULL_ENTRY,
    PROJECTION_X_CULL,
    build_native_sprite_layer,
    project_object_screen_di,
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


def test_project_object_screen_di_adds_scroll():
    # +0C = core + DS:234C (35CC: 35CF writes core, 35D8 add ds:[234C], 35DC rewrites +0C).
    # Confirmed-vs-VM core (y=0x60, col=0x4b28 -> 0x4b58); with scroll 0x40 the slot +0C is 0x4b98.
    assert project_object_screen_di(0x0050, 0x0060, 0x4B28, 0x0040) == 0x4B98
    assert project_object_screen_di(0x0000, 0x000A, 0x0100, 0x0000) == 0x0105  # scroll 0 -> core di
    # 16-bit wrap on the scroll add: (4>>1) + 0xFFF0 + 0x20 = 0x10012 -> 0x0012.
    assert project_object_screen_di(0x0010, 0x0004, 0xFFF0, 0x0020) == 0x0012
    # culls propagate (no scroll applied) -- 30D2 jumps to 25B2, +0C stays FFFFh off-screen.
    assert project_object_screen_di(PROJECTION_X_CULL, 0x40, 0x1000, 0x0040) is None      # x >= 0xE0
    assert project_object_screen_di(0x40, 0x40, PROJECTION_CULL_ENTRY, 0x0040) is None    # column FFFFh


def test_build_native_sprite_layer_composes_via_projection():
    # column_table indexed by object X: cols 0x00-0x0F -> 0x1000, 0x10-0x1F -> 0x2000,
    # 0x20-0x2F -> FFFF (off-screen cull).  scroll (DS:234C) adds to every on-screen di.
    column_table = [0x1000] * 0x10 + [0x2000] * 0x10 + [PROJECTION_CULL_ENTRY] * 0x10
    scroll = 0x0100
    objects = [
        (0x0041, 0x05, 0x10),   # col 0x1000 -> (0x10>>1)+0x1000+scroll = 0x1108
        (0x0042, 0x14, 0x20),   # col 0x2000 -> (0x20>>1)+0x2000+scroll = 0x2110
        (0x0099, 0x25, 0x30),   # col FFFF -> culled
        (0x00AB, 0xF0, 0x40),   # x >= 0xE0 (and past the table) -> culled
    ]
    assert build_native_sprite_layer(objects, column_table, scroll) == (
        (0x0041, 0x1108),
        (0x0042, 0x2110),
    )
    assert build_native_sprite_layer([], column_table, scroll) == ()
