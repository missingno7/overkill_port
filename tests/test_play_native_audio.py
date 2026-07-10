"""The host PC-speaker sink reads the sound engine's live output correctly.

``read_speaker`` is a pure function of the D50E engine's DGROUP cells (the same cells the ISR at
1010:D530..D563 selects the PIT period from), so it can be checked without pygame: channel 0 wins
over channel 1, a zero status is silence, and the frequency is the PIT clock over the period.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from overkill.recovered.adapters.flat_memory import MutFlatMemory  # noqa: E402

DS = 0x25CC


def _img():
    return MutFlatMemory(bytes(0x100000))


def test_silence_when_no_channel_active():
    import play_native as pn

    img = _img()
    assert pn.read_speaker(img) == (False, 0.0)


def test_channel0_frequency():
    import play_native as pn

    img = _img()
    img.wb(DS, 0xBFB3, 1)          # channel 0 status
    img.ww(DS, 0xBFB0, 0x182C)     # its PIT period -> ~192 Hz
    enabled, freq = pn.read_speaker(img)
    assert enabled
    assert round(freq) == 193      # 1193182 / 0x182C


def test_channel0_wins_over_channel1():
    import play_native as pn

    img = _img()
    img.wb(DS, 0xBFB3, 1)
    img.ww(DS, 0xBFB0, 0x0400)
    img.wb(DS, 0xBFC3, 1)          # channel 1 also active...
    img.ww(DS, 0xBFC0, 0x0800)
    _enabled, freq = pn.read_speaker(img)
    assert round(freq) == round(1193182 / 0x0400)   # ...but channel 0 is programmed


def test_channel1_when_channel0_idle():
    import play_native as pn

    img = _img()
    img.wb(DS, 0xBFC3, 1)
    img.ww(DS, 0xBFC0, 0x0500)
    enabled, freq = pn.read_speaker(img)
    assert enabled
    assert round(freq) == round(1193182 / 0x0500)


def test_zero_period_is_silence():
    import play_native as pn

    img = _img()
    img.wb(DS, 0xBFB3, 1)
    img.ww(DS, 0xBFB0, 0)         # active status but no period -> off (no divide-by-zero)
    assert pn.read_speaker(img) == (False, 0.0)
