"""Suite-wide invariants.

RATCHET -- THE CPULESS IMPORT GUARD MUST NOT LEAK.  ``install_import_guard`` replaces
``builtins.__import__`` process-globally.  A test that arms it without disarming leaves the wall up
for every test that runs afterwards, so anything legitimately needing the interpreter dies with a
``CpuStandaloneWitness`` raised nowhere near the code that caused it.  That happened: one bare
``install_import_guard()`` in a front-end cross-validation test turned 239 unrelated tests red, and
because each of them PASSES in isolation the failure looked like corpus drift rather than pollution.

The fixture below turns that whole class of bug into an immediate, local failure naming the culprit
test.  Use ``overkill.cpuless_host.import_guard()`` (scoped) in tests; the bare install is for a
process that exists only to run the walled code.
"""
from __future__ import annotations

import builtins

import pytest


@pytest.fixture(autouse=True)
def _no_leaked_import_guard():
    before = builtins.__import__
    yield
    after = builtins.__import__
    if after is not before:
        builtins.__import__ = before          # repair, so the rest of the session is unaffected
        pytest.fail(
            "this test leaked a CPUless import guard: builtins.__import__ was replaced and not "
            "restored, which arms the wall for every later test in the session. Use the scoped "
            "form -- `with overkill.cpuless_host.import_guard(): ...` -- instead of a bare "
            "install_import_guard().")
