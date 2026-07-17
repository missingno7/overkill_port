"""OverkillPlatform -- the standalone CPUless game's device model (the video-port half).

Pins the correct-by-hardware-definition behavior of the CGA/Tandy video ports (write-only registers
recorded with no DGROUP effect; the 3DAh retrace poll toggles so a wait-loop progresses) and that every
un-modeled service still FAILS LOUD (inherited from FailLoudPlatform), so a reached-but-unimplemented
effect is a visible frontier item, never a silent wrong answer. INT 10h is byte-faithful work for the
next slice (verified against the dos_re oracle) and correctly fails loud here.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))

from overkill.cpuless_host import CpuStandaloneWitness  # noqa: E402
from overkill.cpuless_runtime import OverkillPlatform  # noqa: E402


def test_video_port_writes_are_recorded():
    plat = OverkillPlatform()
    plat.outp(0x3D8, 0x1A, 1, 0)     # CGA/Tandy mode control
    plat.outp(0x3D9, 0x0F, 1, 0)     # colour select
    assert plat.video_ports == {0x3D8: 0x1A, 0x3D9: 0x0F}


def test_retrace_poll_makes_progress():
    plat = OverkillPlatform()
    seen = {plat.inp(0x3DA, 1, 0) for _ in range(4)}
    # a wait-for-retrace loop needs the retrace bit (0x08) to become set at least sometimes
    assert any(v & 0x08 for v in seen) and any(not (v & 0x08) for v in seen)


def test_unmodeled_effects_fail_loud():
    plat = OverkillPlatform()
    with pytest.raises(CpuStandaloneWitness):
        plat.intr(0x10, {}, 0)                 # INT 10h -- byte-faithful port is the next slice
    with pytest.raises(CpuStandaloneWitness):
        plat.outp(0x21, 0, 1, 0)               # PIC mask -- not a video port
    with pytest.raises(CpuStandaloneWitness):
        plat.inp(0x60, 1, 0)                   # keyboard data port -- not modeled here
