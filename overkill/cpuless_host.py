"""OVERKILL's binding of the shared CPUless standalone host.

The mechanism itself -- the import WALL, the recovered-module loader, the fail-loud default device
model, and the deep-stack runner for bounded tail-dispatch loops -- is framework-generic and lives in
:mod:`dos_re.lift.standalone` (promoted there once three ports had each grown their own copy). This
module is only the OVERKILL-specific binding: which corpus package to import from, and which extra
package the wall must refuse.

Everything re-exported here keeps its original name, so callers (`scripts/play_cpuless.py`,
`scripts/check_cpuless_wall.py`, the tests) are unchanged.
"""
from __future__ import annotations

import contextlib

from dos_re.lift.standalone import (BASE_FORBIDDEN, CpuStandaloneWitness, FailLoudPlatform,
                                    module_name, run_deep, uninstall_import_guard)
from dos_re.lift.standalone import install_import_guard as _install_import_guard
from dos_re.lift.standalone import load_recovered as _load_recovered
from dos_re.lift.standalone import run_recovered as _run_recovered

__all__ = ["RECOVERED_PKG", "FORBIDDEN_IMPORTS", "CpuStandaloneWitness", "FailLoudPlatform",
           "install_import_guard", "uninstall_import_guard", "import_guard",
           "load_recovered", "run_recovered", "run_deep", "module_name"]

#: The committed generated corpus -- runtime source, not a disposable artifact.
RECOVERED_PKG = "overkill.cpuless_recovered"

#: The CPU-ABI adapters are OVERKILL's own verification shims (they occupy the lifted slot and touch the
#: carrier), so the wall must refuse them on top of the framework's base set.
_EXTRA_FORBIDDEN = ("overkill.cpuless_adapters",)

#: The full wall for this port -- exported because the wall checks report against it.
FORBIDDEN_IMPORTS = tuple(BASE_FORBIDDEN) + _EXTRA_FORBIDDEN


def install_import_guard() -> None:
    """Arm the CPUless wall for OVERKILL (framework carrier + this port's CPU-ABI adapters).

    PROCESS-GLOBAL. In any process that outlives the walled run -- above all the TEST SUITE, which
    also drives the interpreted oracle -- use :func:`import_guard` instead: a leaked guard makes every
    later interpreter import raise far from the code that armed it."""
    _install_import_guard(extra_forbidden=_EXTRA_FORBIDDEN)


@contextlib.contextmanager
def import_guard():
    """Arm OVERKILL's CPUless wall for a BLOCK, disarming it even if the block raises."""
    install_import_guard()
    try:
        yield
    finally:
        uninstall_import_guard()


def load_recovered(key: str):
    """Import promoted recovered function ``key`` ('CS:IP') from OVERKILL's committed corpus."""
    return _load_recovered(RECOVERED_PKG, key)


def run_recovered(key: str, mem, plat=None, **regs):
    """Run recovered function ``key`` over ``mem`` with ``plat``, returning its live-output registers."""
    return _run_recovered(RECOVERED_PKG, key, mem, plat, **regs)
