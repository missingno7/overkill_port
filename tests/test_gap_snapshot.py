"""Fast test for play_native's on-gap snapshot dump (the reproduce-and-fill workflow).

When the native app hits a RecoveryGap during play it must write a ``--snapshot``-loadable image of
the PRE-frame state so the exact gap can be reproduced and filled; this pins the file layout, the
address parsing, and that the dumped bytes are the reproduction seed (not the post-gap image).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import play_native as pn  # noqa: E402
from overkill.recovered.domain.gaps import RecoveryGap  # noqa: E402


class _Img:
    """Minimal image stub exposing the DS-word reads dump_gap_snapshot needs."""

    def __init__(self, cells):
        self._c = cells

    def rw(self, _seg, off):
        return self._c.get(off, 0)


def _mk(planet=1, diff=2, lives=3):
    return _Img({0x2356: planet, 0xBEDC: diff, 0x2358: lives})


def test_dump_writes_reproducible_seed_and_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(pn, "ROOT", tmp_path)
    pre = bytes(range(256)) * 8            # a distinctive "pre-frame" seed
    exc = RecoveryGap("8546's upgrade handler CS:8463 -- not an [A958] level stub", "unrecovered")
    out = pn.dump_gap_snapshot(pre, _mk(planet=1), exc, tick=1065)

    assert out.parent.name == "gap_snapshots"
    assert out.name == "gap_8463_p1_t1065"                       # CS:8463 parsed as the address
    assert (out / "memory_1mb.bin").read_bytes() == pre          # the PRE-frame seed, byte-for-byte
    info = json.loads((out / "gap_info.json").read_text())
    assert info["address"] == "8463" and info["tick"] == 1065 and info["planet"] == 1
    assert "--snapshot" in info["reproduce"]


def test_bare_address_token_is_parsed(tmp_path, monkeypatch):
    monkeypatch.setattr(pn, "ROOT", tmp_path)
    exc = RecoveryGap("the 98EB game-over continuation ([2358] wrapped)", "unrecovered")
    out = pn.dump_gap_snapshot(b"\x00" * 16, _mk(planet=2), exc, tick=42)
    assert out.name == "gap_98EB_p2_t42"                         # bare 4-hex routine token
