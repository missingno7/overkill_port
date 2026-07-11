"""GameOverReached -- the game-over signal that lets play_native present the high-score entry.

The interactive high-score NAME ENTRY (532D -> 5497) reads DOS INT 21h AH=07 console input, which the
VM-less frame + the scancode key table never feed, so the screen ignored keys and hung.  native_frame
now raises :class:`GameOverReached` on out-of-lives WHEN the caller passes ``menu_pick=None`` (play_native),
carrying a ``resume(pick)`` that runs the 98EB restart.  The lockstep passes a real ``menu_pick`` and
keeps 98EB inline + byte-exact -- these tests pin both paths.
"""
from __future__ import annotations

import pathlib

import pytest

from overkill.native_frame import GameOverReached, _respawn_continuation_9908
from overkill.recovered.adapters.cold_level_start import build_cold_level_start_image
from overkill.recovered.domain.gaps import RecoveryGap

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"
CONTAINER = ROOT / "assets" / "OVERKILL"
DS = 0x25CC
_HAVE = BUNDLE.is_file() and CONTAINER.exists()


def _assets():
    from scripts.play_native import make_level_assets
    bundle = BUNDLE.read_bytes()
    return bundle, make_level_assets(CONTAINER.read_bytes(), bundle)


def _last_life_image(bundle):
    img = build_cold_level_start_image(bundle, 0, CONTAINER.read_bytes())
    img.ww(DS, 0x2358, 0x0000)          # last life -> 990B dec -> 0xFFFF (game over)
    img.wb(DS, 0x978D, 0)               # no lives cheat
    return img


@pytest.mark.skipif(not _HAVE, reason="bundle / container not present")
def test_menu_pick_none_raises_game_over_signal_and_resume_restarts():
    bundle, level_assets = _assets()
    img = _last_life_image(bundle)
    with pytest.raises(GameOverReached) as ei:
        _respawn_continuation_9908(img, 2, level_assets, None)
    assert not isinstance(ei.value, RecoveryGap)     # a recovered transition, not a fail-loud gap
    ei.value.resume(0)                               # the app-collected pick -> 98EB restart
    assert img.rw(DS, 0x2356) == 1                   # fresh game at level 1 (98EB: [2356] = pick + 1)
    assert img.rw(DS, 0x2358) == 3                   # lives reset


@pytest.mark.skipif(not _HAVE, reason="bundle / container not present")
def test_menu_pick_int_keeps_98eb_inline():
    # the lockstep path: a real menu_pick restarts inline (no signal), so the byte-exact gate is intact
    bundle, level_assets = _assets()
    img = _last_life_image(bundle)
    _respawn_continuation_9908(img, 2, level_assets, 0)   # must NOT raise
    assert img.rw(DS, 0x2356) == 1 and img.rw(DS, 0x2358) == 3
