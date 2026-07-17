"""The CPUless import wall -- what makes "CPUless" a PROVEN property of the unified runtime.

Two gates:
  * DYNAMIC (subprocess): scripts/check_cpuless_wall.py arms the guard and exercises BOTH runtime
    layers (the manual gameplay port + the generated corpus); neither may import a CPU-carrier module.
  * UNIT (in-process): the guard raises on a forbidden import, resolves RELATIVE imports before
    matching (the blind spot lemmings documented), and leaves non-forbidden imports alone.
"""
from __future__ import annotations

import builtins
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))

from overkill.cpuless_host import (CpuStandaloneWitness, _forbidden_hit,  # noqa: E402
                                   _resolve_import, install_import_guard)


def test_wall_holds_end_to_end_subprocess():
    """The whole unified runtime -- manual gameplay + generated corpus -- runs with no CPU carrier."""
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_cpuless_wall.py")],
                       capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, f"wall check failed:\nSTDOUT:{r.stdout}\nSTDERR:{r.stderr}"
    assert "WALL HOLDS" in r.stdout


def test_forbidden_hit_matching():
    assert _forbidden_hit("dos_re.cpu") == "dos_re.cpu"
    assert _forbidden_hit("dos_re.cpu.something") == "dos_re.cpu"       # submodule of a forbidden pkg
    assert _forbidden_hit("overkill.cpuless_adapters.func_x") == "overkill.cpuless_adapters"
    assert _forbidden_hit("dos_re.memory") is None                     # a permitted dos_re module
    assert _forbidden_hit("dos_re.cpuxyz") is None                     # not a package-prefix match


def test_resolve_relative_import():
    # 'from .cpu import X' inside package dos_re.lift -> absolute 'dos_re.lift.cpu'
    g = {"__package__": "dos_re.lift"}
    assert _resolve_import("cpu", g, 1) == "dos_re.lift.cpu"
    # level 2 climbs one package: 'from ..cpu import X' inside dos_re.lift -> 'dos_re.cpu'
    assert _resolve_import("cpu", g, 2) == "dos_re.cpu"
    assert _resolve_import("dos_re.cpu", g, 0) == "dos_re.cpu"          # absolute passes through


def test_guard_raises_on_forbidden_and_restores():
    saved = builtins.__import__
    try:
        install_import_guard()
        with pytest.raises(CpuStandaloneWitness):
            __import__("dos_re.cpu")
        # a permitted import still works under the guard
        __import__("json")
    finally:
        builtins.__import__ = saved
