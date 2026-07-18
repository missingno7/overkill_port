"""The standalone CPUless host (overkill/cpuless_host.py) -- the runtime that runs the committed
recovered corpus over a flat image, toward play_native running the whole game CPUless.

Gates:
  * COMPLETENESS -- every committed recovered module imports cleanly, so the corpus is an
    internally-closed, importable runtime package (a missing callee = a broken commit).
  * COMPOSITION  -- run_recovered runs a pure recovered function over a flat image via the host
    API and returns its live outputs (mem mutated in place); a pure-memory function never touches
    the platform.
  * FAIL-LOUD    -- an unpromoted (frontier) function raises CpuStandaloneWitness, never a fallback;
    a reached platform effect with no host impl raises too.

Byte-exact CORRECTNESS of each recovered function is already proven by scripts/verify_cpuless.py
(the adapter differential vs the interpreter); this pins the RUNTIME wiring, not the lift.
"""
from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))

import overkill.cpuless_recovered as corpus  # noqa: E402
from overkill.cpuless_host import (CpuStandaloneWitness, FailLoudPlatform,  # noqa: E402
                                   load_recovered, module_name, run_recovered)
from overkill.recovered.adapters.flat_memory import MutFlatMemory  # noqa: E402


def _committed_func_modules():
    return sorted(info.name for info in pkgutil.iter_modules(corpus.__path__)
                  if info.name.startswith("func_"))


def test_corpus_is_a_closed_importable_package():
    names = _committed_func_modules()
    assert len(names) >= 500, f"expected the committed corpus (~561 fns), found {len(names)}"
    failures = []
    for name in names:
        try:
            mod = importlib.import_module(f"overkill.cpuless_recovered.{name}")
            assert hasattr(mod, name), f"{name} has no {name} callable"
        except Exception as exc:  # noqa: BLE001  -- a missing callee surfaces here
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
    assert not failures, "committed corpus is not internally closed:\n" + "\n".join(failures[:10])


def test_module_name_mapping():
    assert module_name("1010:5F61") == "func_1010_5f61"
    assert module_name("254A:04D7") == "func_254a_04d7"


def test_run_recovered_composes_over_a_flat_image():
    # The frame clock 1010:5F61 is pure-memory: run it over a synthetic image and confirm it
    # advances its DS:2324 counter and returns the live register outputs -- no platform touched.
    mem = MutFlatMemory(bytes(0x100000))
    out = run_recovered("1010:5F61", mem, ds=0x25CC, es=0x25CC, ss=0x2000, sp=0x1000)
    assert set(out) == {"ax", "bp", "bx", "cx", "di", "ds", "dx", "es", "si"}
    assert mem.rw(0x25CC, 0x2324) == 1, "frame counter should advance from 0 to 1"


def test_unpromoted_function_fails_loud():
    # 1010:97B2 is the gameplay frame root -- still on the CPUless frontier
    # (boundary-head-on-transfer), so it has no recovered module. (The tail-dispatch
    # functions that used to sit here are now promoted by the frameless stack-arg
    # capability, so they no longer serve as a frontier example.)
    with pytest.raises(CpuStandaloneWitness):
        load_recovered("1010:97B2")


def test_fail_loud_platform_raises_on_every_effect():
    plat = FailLoudPlatform()
    with pytest.raises(CpuStandaloneWitness):
        plat.intr(0x10, {}, 0)
    with pytest.raises(CpuStandaloneWitness):
        plat.inp(0x3DA, 1, 0)
    with pytest.raises(CpuStandaloneWitness):
        plat.outp(0x3D4, 0, 1, 0)
