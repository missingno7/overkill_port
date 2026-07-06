"""The pure AFD8/B022 contact-step handlers (systems/contact_step)."""
from __future__ import annotations

from overkill.recovered.domain.contact_step import ContactStepState
from overkill.recovered.systems.contact_step import TILE_COLUMN_STRIDE, contact_step_b022

OPEN = {}  # every tile class 0 (walkable)


def _cls(walls: set[int]):
    return lambda off: 1 if off in walls else 0


def _no_contact(mirror_dx_x: int = 0, mirror_dx_y: int = 0) -> bool:
    return False


def test_step_pos_x_steps_and_wraps_the_sample_counter_into_the_next_column():
    st = ContactStepState(x_word=0x30, y_word=0x40, tile_offset=0x90, sample_215a=0xF)
    out = contact_step_b022(4, st, _cls(set()), _no_contact)
    assert (out.x_word, out.y_word) == (0x31, 0x40)
    assert not out.blocked and out.mirror_dx_x == 1
    assert out.sample_215a == 0x0
    assert out.tile_offset == 0x90 - TILE_COLUMN_STRIDE  # wrapped one column right


def test_step_pos_x_is_refused_by_a_leading_wall_and_checks_the_row_straddle():
    st = ContactStepState(0x30, 0x40, 0x90, 0x3)
    wall = _cls({0x90 - TILE_COLUMN_STRIDE})
    out = contact_step_b022(4, st, wall, _no_contact)
    assert out.blocked and (out.x_word, out.sample_215a) == (0x30, 0x3)
    # y & 0xF != 0 -> the row below the leading edge is checked too
    st2 = ContactStepState(0x30, 0x48, 0x90, 0x3)
    wall2 = _cls({0x90 - TILE_COLUMN_STRIDE + 1})
    assert contact_step_b022(4, st2, wall2, _no_contact).blocked


def test_step_neg_x_checks_terrain_only_at_a_column_boundary():
    walls = _cls({0x90 + TILE_COLUMN_STRIDE})
    # mid-column (sample != 0): no terrain check -> steps into the "wall" column freely
    mid = contact_step_b022(0, ContactStepState(0x30, 0x40, 0x90, 0x3), walls, _no_contact)
    assert not mid.blocked and mid.x_word == 0x2F and mid.sample_215a == 0x2
    # at the boundary (sample 0): the leading column is checked -> refused
    edge = contact_step_b022(0, ContactStepState(0x30, 0x40, 0x90, 0x0), walls, _no_contact)
    assert edge.blocked and edge.x_word == 0x30
    # boundary + open terrain: steps, sample wraps 0 -> 0xF, offset shifts one column left
    ok = contact_step_b022(0, ContactStepState(0x30, 0x40, 0x90, 0x0), _cls(set()), _no_contact)
    assert ok.x_word == 0x2F and ok.sample_215a == 0xF
    assert ok.tile_offset == 0x90 + TILE_COLUMN_STRIDE


def test_step_pos_y_advances_the_tile_offset_at_a_row_boundary():
    out = contact_step_b022(2, ContactStepState(0x30, 0x4F, 0x90, 0x0), _cls(set()), _no_contact)
    assert (out.y_word, out.tile_offset) == (0x50, 0x91)  # crossed into the next row
    stay = contact_step_b022(2, ContactStepState(0x30, 0x44, 0x90, 0x0), _cls(set()), _no_contact)
    assert (stay.y_word, stay.tile_offset) == (0x45, 0x90)


def test_step_neg_y_checks_terrain_only_at_a_row_boundary_with_column_straddle():
    walls = _cls({0x8F})
    assert contact_step_b022(6, ContactStepState(0x30, 0x40, 0x90, 0x0), walls, _no_contact).blocked
    mid = contact_step_b022(6, ContactStepState(0x30, 0x47, 0x90, 0x0), walls, _no_contact)
    assert not mid.blocked and mid.y_word == 0x46
    # straddling columns (sample != 0) also checks the second column above
    walls2 = _cls({0x8F - TILE_COLUMN_STRIDE})
    assert contact_step_b022(6, ContactStepState(0x30, 0x40, 0x90, 0x5), walls2, _no_contact).blocked


def test_contact_hit_undoes_the_step_and_flags_blocked():
    out = contact_step_b022(4, ContactStepState(0x30, 0x40, 0x90, 0x3), _cls(set()), lambda *_: True)
    assert out.blocked
    assert (out.x_word, out.y_word, out.sample_215a, out.tile_offset) == (0x30, 0x40, 0x3, 0x90)
    assert out.mirror_dx_x == 0  # the A438 mirror inc is undone too


def test_contact_probe_afd8_off_map_blocks_without_stepping():
    from overkill.recovered.domain.tilemap import LevelTileContext
    from overkill.recovered.systems.contact_step import contact_probe_afd8

    tiles = LevelTileContext(origin_x_word=0x000F, row_base_word=0x009C,
                             tile_plane=bytes(0x1000), class_table=(0,) * 256)
    # x + a278 - 0x10 lands in the negative-adjusted-X range -> the 5073 off-map early-out
    r = contact_probe_afd8(0x9000, 0x40, 4, 0x0000, tiles, lambda *_: False)
    assert r.blocked and (r.x_word, r.y_word) == (0x9000, 0x40)
    assert (r.snap_x, r.snap_y) == (r.mirror_x, r.mirror_y) == (0x9000, 0x40)
    assert r.tile_offset == 0xFFFF
    # a walkable step: the A278 bias cancels -- the record moves exactly one pixel
    r2 = contact_probe_afd8(0x30, 0x40, 4, 0x0020, tiles, lambda *_: False)
    assert not r2.blocked and (r2.x_word, r2.y_word) == (0x31, 0x40)
    assert (r2.mirror_x, r2.mirror_y) == (0x31, 0x40) and (r2.snap_x, r2.snap_y) == (0x30, 0x40)


def test_diagonal_composes_both_axes_and_accumulates_blocked():
    # key 3 = +Y then +X; both open -> both step
    out = contact_step_b022(3, ContactStepState(0x30, 0x40, 0x90, 0x3), _cls(set()), _no_contact)
    assert (out.x_word, out.y_word) == (0x31, 0x41)
    # +Y refused by a wall below, +X still attempted (original control flow) and steps
    walls = _cls({0x91})
    out2 = contact_step_b022(3, ContactStepState(0x30, 0x40, 0x90, 0x3), walls, _no_contact)
    assert out2.blocked and (out2.x_word, out2.y_word) == (0x31, 0x40)
