"""The AUDIO ORACLE GATE as a regression test.

`overkill.probes.verify_native_audio` seeds the VM-free AdLib driver from the VM's own seg-2032 image
and replays it forward in lockstep with the reference VM, diffing the YM3812 register writes.  Over a
steady single-page music window the recovered `tick_2032_0063` spine must reproduce the VM's OPL stream
BYTE-EXACT.  This test locks a short window of that proof into the suite so the driver can't regress;
the full multi-window proof runs standalone (`python -m overkill.probes.verify_native_audio`).
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))

_DEMO = "demo_play_tandy_L2_full_20260617_180221"
_HAVE = (ROOT / "assets" / "OVERKILL").exists() and (ROOT / "artifacts" / "demos" / _DEMO).is_dir()


@pytest.mark.skipif(not _HAVE, reason="needs the OVERKILL exe + the L2 demo corpus")
def test_vmfree_driver_byte_exact_per_tick():
    """The strongest form: at every 2032:0063 tick entry the VM-free driver, seeded from the true
    seg-2032 image, reproduces the VM's OPL writes byte-exact.  (A short window here for suite speed;
    the standalone probe proves the full L1-L6 demos, SFX and page changes included.)"""
    from overkill.probes.verify_native_audio import per_tick

    ticks, bad = per_tick(_DEMO, 130)
    assert bad is None, f"driver diverged at tick {bad[0]}: VM {bad[1][:6]} vs VM-free {bad[2][:6]}"
    assert ticks >= 80, f"captured too few ticks to be meaningful ({ticks})"
