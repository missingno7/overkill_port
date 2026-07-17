"""scripts/play_cpuless.py -- the standalone CPUless runner plays gameplay under the armed wall.

Runs the real runner headless (--frames) in a subprocess and asserts it completes: the unified game
(manual gameplay override + generated corpus over one image) plays with the CPU-carrier import wall
armed, so a carrier import would have aborted it. Artifact-gated on the game data (bundle + container,
original bytes never committed); the CI-safe carrier proof is tests/test_cpuless_wall.py.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))

from overkill.cpuless_runtime import assets_available  # noqa: E402


@pytest.mark.skipif(not assets_available(),
                    reason="no game data (bundle + asset container) -- gameplay run is artifact-gated")
def test_play_cpuless_runs_gameplay_headless_under_the_wall():
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "play_cpuless.py"), "--frames", "3", "--no-sound"],
        capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, f"play_cpuless failed:\nSTDOUT:{r.stdout}\nSTDERR:{r.stderr}"
    assert "gameplay frames" in r.stdout, f"no frame self-test line:\n{r.stdout}"
