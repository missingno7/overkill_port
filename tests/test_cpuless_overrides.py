"""THE STITCH: manual implementations patch the autolifted corpus at named addresses.

`overkill/cpuless_overrides.py` is the mechanism that lets the GENERATED corpus own the game's control
flow while hand-recovered code replaces individual addresses inside it.  These tests pin the two
properties the whole scheme rests on: the shadow really is what dependents bind to, and the generated
function stays reachable as its own differential oracle.
"""
from __future__ import annotations

import sys

import pytest

from overkill import cpuless_overrides as ov


@pytest.fixture(autouse=True)
def _clean():
    ov.uninstall_overrides()
    yield
    ov.uninstall_overrides()


class _Plat:
    def __init__(self):
        self.yields = []

    def boundary(self, kind="timer"):
        self.yields.append(kind)


class _Mem:
    """Just the four accessors the recovered contract uses."""

    def __init__(self):
        self.cells = {}

    def rb(self, seg, off):
        return self.cells.get((seg, off), 0)

    def wb(self, seg, off, val):
        self.cells[(seg, off)] = val & 0xFF


def test_names_map_addresses_to_the_corpus_layout():
    assert ov.module_name("1010:0679") == "overkill.cpuless_recovered.func_1010_0679"
    assert ov.func_name("1010:0679") == "func_1010_0679"


def test_install_shadows_the_module_dependents_bind_to():
    plat = _Plat()
    installed = ov.install_overrides(plat)
    assert "1010:0679" in installed
    mod = sys.modules["overkill.cpuless_recovered.func_1010_0679"]
    assert getattr(mod, "_OVERRIDE_SHADOW", False), "the shadow must be identifiable as one"
    # A dependent importing the callee by name gets the OVERRIDE, which is the entire mechanism:
    # generated code binds its callees at import time, so the module object is the only seam.
    from overkill.cpuless_recovered.func_1010_0679 import func_1010_0679
    assert func_1010_0679 is getattr(mod, "func_1010_0679")


def test_generated_stays_reachable_as_its_own_oracle():
    """An override must never make the autolifted function unreachable -- it is the differential
    oracle, and overrides that only ADD an effect delegate to it."""
    plat = _Plat()
    ov.install_overrides(plat)
    gen = ov.generated("1010:0679")
    shadowed = getattr(sys.modules["overkill.cpuless_recovered.func_1010_0679"], "func_1010_0679")
    assert gen is not shadowed, "generated() must bypass the shadow"


def test_unknown_address_fails_loud_rather_than_silently_doing_nothing():
    """A stale/typo'd override is the failure mode that would silently drop a manual patch after a
    corpus regeneration -- it must raise, not no-op."""
    with pytest.raises(LookupError):
        ov.install_overrides(_Plat(), addrs=["1010:FFFE"])


def test_timer_env_wait_yields_then_lets_the_generated_body_return():
    """`1010:0679` spins on the tick flag `[066B]` that the absent INT 8 handler would set. The
    override yields to the host, supplies the tick, and delegates -- so the wait TERMINATES."""
    plat = _Plat()
    ov.install_overrides(plat)
    fn = getattr(sys.modules["overkill.cpuless_recovered.func_1010_0679"], "func_1010_0679")

    mem = _Mem()
    assert mem.rb(ov._CS, ov._TICK_FLAG) == 0, "precondition: the tick flag is clear (would block)"
    out, compat = fn(mem)                       # must not spin
    assert plat.yields == ["timer"], "a blocking wait must hand the host a scheduler boundary"
    assert mem.rb(ov._CS, ov._TICK_FLAG) == 1, "the tick the absent interrupt owed us"
    assert out == {} and "flags" in compat, "the generated contract is preserved"


def test_no_yield_when_the_wait_would_not_have_blocked():
    """An already-set flag returns immediately on real hardware; the override must not invent a
    yield (that would slow the flow by a frame every time it is polled)."""
    plat = _Plat()
    ov.install_overrides(plat)
    fn = getattr(sys.modules["overkill.cpuless_recovered.func_1010_0679"], "func_1010_0679")

    mem = _Mem()
    mem.wb(ov._CS, ov._TICK_FLAG, 3)            # already ticked
    fn(mem)
    assert plat.yields == [], "no block -> no yield"
    assert mem.rb(ov._CS, ov._TICK_FLAG) == 3, "and no spurious extra tick"


def test_every_override_names_an_address_the_corpus_actually_contains():
    """The ratchet against corpus regeneration silently orphaning a manual patch."""
    ov.install_overrides(_Plat())               # raises LookupError if any entry is stale


# ---------------------------------------------------------------------------------------------------
# INSTALLATION-ORDER INDEPENDENCE.  Carried over from skyroads_port, which found that a sys.modules
# shadow silently misses calls in two ways: a caller that ALREADY imported the callee holds a direct
# reference the shadow never touches, and the dynamic-dispatch registry CACHES resolved functions, so
# a cache populated before the install keeps serving the generated body.  Both are silent -- the
# override simply never runs -- which is the worst failure mode a verification seam can have.
# ---------------------------------------------------------------------------------------------------

def test_override_reaches_a_caller_that_already_imported_the_callee():
    """The realistic order: something imported the corpus before overrides were installed."""
    import importlib

    caller = importlib.import_module("overkill.cpuless_recovered.func_1010_d007")
    generated = caller.func_1010_0679                      # bound by `from ... import ...`

    ov.install_overrides(_Plat())
    override = getattr(sys.modules["overkill.cpuless_recovered.func_1010_0679"], "func_1010_0679")

    assert caller.func_1010_0679 is not generated, (
        "the caller still holds the GENERATED function: a sys.modules shadow cannot reach a name "
        "already bound by `from ... import ...`, so the override silently never runs")
    assert caller.func_1010_0679 is override


def test_override_reaches_a_cached_dynamic_dispatch():
    """`_dyncall` memoizes resolved targets; a cache warmed before install would bypass overrides."""
    import importlib

    dyn = importlib.import_module("overkill.cpuless_recovered._dyncall")
    dyn._cache[("DISPATCH", "1010:0679")] = "STALE-PRE-INSTALL-ENTRY"

    ov.install_overrides(_Plat())

    assert ("DISPATCH", "1010:0679") not in dyn._cache, (
        "the dynamic-dispatch cache still holds a pre-install entry, so indirect transfers keep "
        "reaching the generated body after an override is installed")


def test_uninstall_restores_retro_patched_callers():
    """Teardown must undo the retro-patch too, or a torn-down override lives on in the callers it
    was patched into and the corpus stays silently overridden."""
    import importlib

    caller = importlib.import_module("overkill.cpuless_recovered.func_1010_d007")
    generated = caller.func_1010_0679

    ov.install_overrides(_Plat())
    assert caller.func_1010_0679 is not generated
    ov.uninstall_overrides()
    assert caller.func_1010_0679 is generated, "uninstall must put the generated function back"
