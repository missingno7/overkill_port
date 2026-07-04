"""Cold-load the AFD8 contact-step direction dispatch (contact_step_dispatch_adapter)."""
from __future__ import annotations

import pathlib

import pytest

from overkill.recovered.adapters.contact_step_dispatch_adapter import (
    CONTACT_STEP_DIRECTION_COUNT,
    load_contact_step_dispatch,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"
LIVE = ROOT / "artifacts" / "demos" / "demo_play_tandy_L1_start_20260618_143947" / "snapshot" / "memory_1mb.bin"


@pytest.mark.skipif(not BUNDLE.is_file(), reason="static runtime bundle not present")
def test_contact_step_dispatch_is_the_8_direction_family():
    table = load_contact_step_dispatch(BUNDLE.read_bytes())
    assert len(table) == CONTACT_STEP_DIRECTION_COUNT == 8
    # the axis handlers + the composing diagonals (disassembly-mapped; the +0x06 keying is pinned
    # at the AFD8 driven oracle in the stepper-recovery slice)
    assert table == (0xB07D, 0xB0C9, 0xB0CC, 0xB039, 0xB03C, 0xB10C, 0xB10F, 0xB07A)


@pytest.mark.skipif(not (BUNDLE.is_file() and LIVE.is_file()), reason="artifacts not present")
def test_contact_step_dispatch_is_static_cold_equals_live():
    assert load_contact_step_dispatch(BUNDLE.read_bytes()) == load_contact_step_dispatch(LIVE.read_bytes())
