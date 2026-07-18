"""The CPUless import wall as OVERKILL binds it -- what makes "CPUless" a PROVEN property here.

The wall MECHANISM (relative-import resolution, prefix matching, the fail-loud platform and loader) is
framework-generic and tested in dos_re: ``tests/test_lift_standalone.py``. What is port-specific, and
tested here, is the BINDING: that OVERKILL's wall also refuses this port's CPU-ABI adapters, and that
the whole unified runtime -- the manual gameplay port AND the generated corpus -- runs under it with no
carrier (the dynamic subprocess check).
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

from overkill.cpuless_host import (FORBIDDEN_IMPORTS, CpuStandaloneWitness,  # noqa: E402
                                   install_import_guard)


def test_wall_holds_end_to_end_subprocess():
    """The whole unified runtime -- manual gameplay + generated corpus -- runs with no CPU carrier."""
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_cpuless_wall.py")],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, f"wall check failed:\nSTDOUT:{r.stdout}\nSTDERR:{r.stderr}"
    assert "WALL HOLDS" in r.stdout


def test_port_wall_refuses_this_ports_adapters():
    """OVERKILL's CPU-ABI adapters are verification shims, never runtime source: the binding must add
    them to the framework's base carrier set."""
    assert "overkill.cpuless_adapters" in FORBIDDEN_IMPORTS
    assert "dos_re.cpu" in FORBIDDEN_IMPORTS          # the framework base set is still in force


def test_guard_raises_on_carrier_and_adapters_then_restores():
    saved = builtins.__import__
    try:
        install_import_guard()
        with pytest.raises(CpuStandaloneWitness):
            __import__("dos_re.cpu")
        with pytest.raises(CpuStandaloneWitness):
            __import__("overkill.cpuless_adapters")
        __import__("json")                            # a permitted import still works
    finally:
        builtins.__import__ = saved
