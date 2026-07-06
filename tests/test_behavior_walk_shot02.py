"""The walk's player-shot (behavior 0x02) handler delegates to the verified object_update_aed8."""
from __future__ import annotations

import pathlib

import pytest

from overkill.recovered.adapters.flat_memory import MutFlatMemory

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"
DS = 0x25CC


@pytest.mark.skipif(not BUNDLE.is_file(), reason="static runtime bundle not present")
def test_step_shot_02_matches_a_direct_object_update_aed8_call():
    from overkill.native_walk_frame import level_tiles
    from overkill.recovered.adapters.behavior_walk import _step_shot_02
    from overkill.recovered.systems.objects import object_update_aed8

    mem = MutFlatMemory(BUNDLE.read_bytes())
    tiles = level_tiles(mem)
    rec = 0x2400
    # a synthetic player shot: type 4 / behavior 2, moving, a live substate timer
    fields = {0x00: 1, 0x02: 0x0080, 0x04: 0x0050, 0x06: 0x0002, 0x0A: 0x0001,
              0x16: 0x0004, 0x18: 0x0002, 0x1C: 0x0010, 0x1E: 0x0000}
    for off, val in fields.items():
        mem.ww(DS, rec + off, val)

    # the reference: call the VERIFIED whole-AED8 update directly with the same field mapping
    # (hazard_class is +0x16, NOT +0x0A -- matches the adapter's corrected field read)
    u = object_update_aed8(
        fields[0x1C], fields[0x06], fields[0x02], fields[0x04], fields[0x00], fields[0x1E],
        fields[0x16], fields[0x18], mem.rw(DS, 0x237E), mem.rw(DS, 0x2380), mem.rw(DS, 0xA278),
        False, tiles)
    assert u is not None      # the chosen case is on the modeled path

    _step_shot_02(mem, rec, tiles)
    # the handler must have written exactly the update's four changed fields back to the record
    assert mem.rw(DS, rec + 0x1C) == u.substate
    assert mem.rw(DS, rec + 0x02) == u.x_word
    assert mem.rw(DS, rec + 0x04) == u.y_word
    assert mem.rw(DS, rec + 0x00) == u.active_word


@pytest.mark.skipif(not BUNDLE.is_file(), reason="static runtime bundle not present")
def test_step_shot_02_fails_loud_on_the_timer_death_subpath():
    from overkill.native_walk_frame import level_tiles
    from overkill.recovered.adapters.behavior_walk import _step_shot_02
    from overkill.recovered.domain.gaps import RecoveryGap

    mem = MutFlatMemory(BUNDLE.read_bytes())
    tiles = level_tiles(mem)
    rec = 0x2400
    for off, val in {0x00: 1, 0x02: 0x80, 0x04: 0x50, 0x06: 2, 0x16: 4, 0x18: 2, 0x1C: 1}.items():
        mem.ww(DS, rec + off, val)   # substate 1 -> decrements to 0 -> the unmodeled ADC9 death
    with pytest.raises(RecoveryGap):
        _step_shot_02(mem, rec, tiles)
