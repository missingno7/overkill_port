"""`play_cpuless.py --menu` -- the CPUless FRONT-END runs and presents.

The menu is drawn by the GENERATED corpus (the front-end half of the unification; gameplay is the
manual override), executed under the armed import wall, and presented through the native Tandy renderer
which only decodes the B800 bytes the recovered code wrote. This asserts the whole path end to end:
the menu root completes and produces a non-empty frame, with no CPU carrier anywhere.

Artifact-gated on the data-only boot image (original-game bytes, never committed).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BOOT_IMAGE = ROOT / "artifacts" / "frontend_intro_snapshot" / "memory_1mb.bin"


@pytest.mark.skipif(not BOOT_IMAGE.is_file(),
                    reason="no front-end boot image -- the CPUless menu run is artifact-gated")
def test_cpuless_menu_runs_and_draws():
    env = dict(os.environ, SDL_VIDEODRIVER="dummy")
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "play_cpuless.py"), "--menu", "--seconds", "1"],
        capture_output=True, text=True, timeout=600, env=env)
    assert r.returncode == 0, f"--menu failed:\nSTDOUT:{r.stdout}\nSTDERR:{r.stderr}"
    m = re.search(r"drew (\d+) lit pixels", r.stdout)
    assert m, f"no draw report in output:\n{r.stdout}"
    assert int(m.group(1)) > 1000, f"front-end drew almost nothing ({m.group(1)} px)"


@pytest.mark.skipif(not BOOT_IMAGE.is_file(),
                    reason="no front-end boot image -- the CPUless chain run is artifact-gated")
def test_cpuless_chain_menu_to_gameplay():
    """THE JOIN: the generated front-end reports a selection and hands off to the gameplay half.

    Front-end = generated corpus, level-load + gameplay = the manual override (ADR-2), both under the
    armed wall in one process."""
    env = dict(os.environ, SDL_VIDEODRIVER="dummy")
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "play_cpuless.py"), "--menu",
         "--auto-select", "--play", "--seconds", "2"],
        capture_output=True, text=True, timeout=900, env=env)
    assert r.returncode == 0, f"chain failed:\nSTDOUT:{r.stdout}\nSTDERR:{r.stderr}"
    assert "front-end SELECTED" in r.stdout, r.stdout
    assert "handing off to the gameplay half" in r.stdout, r.stdout
    m = re.search(r"(\d+) gameplay frames", r.stdout)
    assert m and int(m.group(1)) > 0, f"gameplay did not run:\n{r.stdout}"
