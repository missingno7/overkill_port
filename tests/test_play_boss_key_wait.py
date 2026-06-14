from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from play import boss_key_wait_window  # noqa: E402


def test_boss_key_wait_window_covers_whole_poll_instructions() -> None:
    # CPU.run(max_steps) can stop after either instruction in these tiny loops;
    # detecting only the loop heads made the F9 screen appear nondeterministically.
    for ip in (0x07C4, 0x07C9, 0x07CA, 0x07D0, 0x07D5, 0x07D6, 0x07D7, 0x07DC, 0x07DD):
        assert boss_key_wait_window(ip) is not None


def test_boss_key_wait_window_rejects_neighbouring_code() -> None:
    for ip in (0x07C3, 0x07CB, 0x07CF, 0x07DE, 0x0765, 0x07E0):
        assert boss_key_wait_window(ip) is None
