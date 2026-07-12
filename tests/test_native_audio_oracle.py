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
def test_vmfree_driver_byte_exact_over_music_window():
    """The VM-free driver reproduces the VM's OPL writes byte-exact across a clean single-page window
    (the first game/SFX event is far later, ~gameplay-frame 309, so this span is music-only)."""
    from overkill.probes.verify_native_audio import clean_window

    matched, diverge, detail = clean_window(_DEMO, 130, seed_at=2)
    # Any mismatch INSIDE the window is a driver bug (the game event boundary is well past this span),
    # so the whole captured window must stay byte-exact.
    assert diverge is None, f"driver diverged at gameplay-frame {diverge}: {detail}"
    assert matched >= 40, f"captured too short a window to be meaningful ({matched} frames)"
