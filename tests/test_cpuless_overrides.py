"""THE STITCH: manual implementations patch the autolifted corpus at named addresses.

`overkill/cpuless_overrides.py` is the mechanism that lets the GENERATED corpus own the game's control
flow while hand-recovered code replaces individual addresses inside it.  These tests pin the two
properties the whole scheme rests on: the shadow really is what dependents bind to, and the generated
function stays reachable as its own differential oracle.

RE-POINTED 2026-07-18.  These used to exercise the mechanism through the shipped `1010:0679` env-wait
override.  That override is RETIRED -- an env-wait is a declared BOUNDARY HEAD answered by
`overkill.cpuless_driver`, not an address the host intercepts (see the note on `ov.OVERRIDES`) -- so
`OVERRIDES` is now legitimately empty.  The MECHANISM is unchanged and still has to hold, so the tests
now install a TEST-LOCAL override at a real corpus address via the `_probe_override` fixture.  Testing
it through a fixture rather than through whatever happens to ship is strictly better: the mechanism is
address-agnostic, and these no longer rot the next time the override list changes.  The behaviour the
retired override used to assert is now asserted against the GENERATED spine in
`tests/test_cpuless_frame_driver.py`.
"""
from __future__ import annotations

import sys

import pytest

from overkill import cpuless_overrides as ov

#: A real corpus address to hang the test-local override on.  `1010:0679` is deliberately still the
#: choice: it is the address the mechanism was originally proven at, it is guaranteed present, and
#: using it keeps these tests comparable to the ones they replace.
PROBE_ADDR = "1010:0679"


@pytest.fixture(autouse=True)
def _clean():
    ov.uninstall_overrides()
    yield
    ov.uninstall_overrides()


@pytest.fixture
def _probe_override():
    """Register a TEST-LOCAL override so the stitch has something to install.

    The shipped `OVERRIDES` is empty by design; the mechanism it implements still has to work the
    moment a real override is added, and that is what these tests are for."""
    def factory(_plat):
        def probe(mem, *_a, **_k):
            return {}, {"flags": 0, "fmask": 0, "cost": 0}
        probe._IS_TEST_PROBE = True
        return probe

    ov.OVERRIDES[PROBE_ADDR] = factory
    try:
        yield PROBE_ADDR
    finally:
        ov.OVERRIDES.pop(PROBE_ADDR, None)


class _Plat:
    """A platform stand-in.  It deliberately has NO `boundary` attribute: the retired override looked
    one up by name and found the wrong protocol's method, so nothing here should tempt that back."""


def test_names_map_addresses_to_the_corpus_layout():
    assert ov.module_name("1010:0679") == "overkill.cpuless_recovered.func_1010_0679"
    assert ov.func_name("1010:0679") == "func_1010_0679"


def test_shipped_override_list_is_empty_and_that_is_the_point():
    """With `OVERRIDES = {}` the composite is bit-for-bit the generated program, so a passing cold
    run proves the GENERATED CORPUS rather than the stitch.  This is an assertion about what the
    milestone claims, not a convenience: if an override is added, whoever adds it must come here and
    say why the generated body is not the truth at that address."""
    assert ov.OVERRIDES == {}, (
        f"unjustified override(s) {sorted(ov.OVERRIDES)}: every entry weakens what a green cold-start "
        f"differential proves, so each one needs its reason recorded on OVERRIDES")


def test_install_shadows_the_module_dependents_bind_to(_probe_override):
    plat = _Plat()
    installed = ov.install_overrides(plat)
    assert "1010:0679" in installed
    mod = sys.modules["overkill.cpuless_recovered.func_1010_0679"]
    assert getattr(mod, "_OVERRIDE_SHADOW", False), "the shadow must be identifiable as one"
    # A dependent importing the callee by name gets the OVERRIDE, which is the entire mechanism:
    # generated code binds its callees at import time, so the module object is the only seam.
    from overkill.cpuless_recovered.func_1010_0679 import func_1010_0679
    assert func_1010_0679 is getattr(mod, "func_1010_0679")


def test_generated_stays_reachable_as_its_own_oracle(_probe_override):
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


def test_every_override_names_an_address_the_corpus_actually_contains(_probe_override):
    """The ratchet against corpus regeneration silently orphaning a manual patch."""
    ov.install_overrides(_Plat())               # raises LookupError if any entry is stale


# ---------------------------------------------------------------------------------------------------
# INSTALLATION-ORDER INDEPENDENCE.  Carried over from skyroads_port, which found that a sys.modules
# shadow silently misses calls in two ways: a caller that ALREADY imported the callee holds a direct
# reference the shadow never touches, and the dynamic-dispatch registry CACHES resolved functions, so
# a cache populated before the install keeps serving the generated body.  Both are silent -- the
# override simply never runs -- which is the worst failure mode a verification seam can have.
# ---------------------------------------------------------------------------------------------------

def test_override_reaches_a_caller_that_already_imported_the_callee(_probe_override):
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


def test_override_reaches_a_cached_dynamic_dispatch(_probe_override):
    """`_dyncall` memoizes resolved targets; a cache warmed before install would bypass overrides."""
    import importlib

    dyn = importlib.import_module("overkill.cpuless_recovered._dyncall")
    dyn._cache[("DISPATCH", "1010:0679")] = "STALE-PRE-INSTALL-ENTRY"

    ov.install_overrides(_Plat())

    assert ("DISPATCH", "1010:0679") not in dyn._cache, (
        "the dynamic-dispatch cache still holds a pre-install entry, so indirect transfers keep "
        "reaching the generated body after an override is installed")


def test_uninstall_restores_retro_patched_callers(_probe_override):
    """Teardown must undo the retro-patch too, or a torn-down override lives on in the callers it
    was patched into and the corpus stays silently overridden."""
    import importlib

    caller = importlib.import_module("overkill.cpuless_recovered.func_1010_d007")
    generated = caller.func_1010_0679

    ov.install_overrides(_Plat())
    assert caller.func_1010_0679 is not generated
    ov.uninstall_overrides()
    assert caller.func_1010_0679 is generated, "uninstall must put the generated function back"
