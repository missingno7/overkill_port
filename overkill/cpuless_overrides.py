"""THE STITCH: manual (hand-recovered) implementations patched over the autolifted CPUless corpus.

This is ADR-2's coarse override seam made MECHANICAL.  The generated corpus is the game's real
control flow -- by construction, because it was lifted from the original's own code -- so it drives.
Manual code does not re-implement the flow; it PATCHES individual addresses inside it, and every
address with no manual implementation is served by the generated function automatically.  The whole
thing therefore holds together without anyone hand-wiring screen-to-screen transitions.

WHY THIS SHAPE (the constraint that picked it):

    A generated module binds its callees AT IMPORT TIME with direct imports --
        from overkill.cpuless_recovered.func_1010_cc4f import func_1010_cc4f
    -- so there is no per-call resolver to hook.  The only seam is the MODULE OBJECT, and
    :func:`install_overrides` shadows ``sys.modules`` entries ahead of the corpus load.

    A ``sys.modules`` shadow ALONE IS NOT ENOUGH, and both gaps are silent -- the override simply
    never runs, with nothing reporting it.  (Carried over from skyroads_port, which hit both; the
    corrected claim replaces an earlier note here that said dynamic transfers needed "no separate
    patch".)  So installation also:

      * RETRO-PATCHES already-imported callers.  A module that already ran
        ``from ...func_1010_0679 import func_1010_0679`` holds a direct reference no shadow can
        reach.  Originals are recorded so teardown restores them.
      * CLEARS ``_dyncall``'s resolution cache.  The dispatch registry memoizes
        ``(kind, key) -> callable`` on first use, so a cache warmed before the install keeps serving
        the generated body for every INDIRECT transfer -- an override that applies to direct calls
        only is a split-brain seam, worse than no seam.

    Consequence: installation order must not matter, and the tests assert exactly that.

INVARIANTS:

* An override MUST match the generated contract exactly: ``(mem[, plat], *, _base, _df, _flags_in,
  **regs) -> (outputs_dict, _compat)``.  The generated callers unpack ``_o, _c`` positionally.
* An override for an address the corpus does not contain is a FAIL-LOUD error, not a no-op -- that
  is the typo guard, and it keeps this registry honest as the corpus is regenerated.
* THE GENERATED FUNCTION STAYS AVAILABLE as the differential oracle (:func:`generated`), and an
  override should DELEGATE to it wherever it only needs to add an effect rather than replace the
  computation, so the returned flags are the generated ones and cannot drift.
* AN ENV-WAIT IS NOT AN OVERRIDE.  A scheduler yield (timer tick, retrace) belongs in the GENERATED
  spine as a declared BOUNDARY HEAD answered by :mod:`overkill.cpuless_driver`, not as an address the
  host intercepts.  See the retirement note on :data:`OVERRIDES`.

Usage (see scripts/play_cpuless.py):

    from overkill.cpuless_overrides import install_overrides
    install_overrides(plat)          # BEFORE the first corpus import
    run_recovered(PKG, ROOT, mem, plat, ...)
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
import types
from typing import Callable

#: The package holding the autolifted corpus the overrides patch.
RECOVERED_PKG = "overkill.cpuless_recovered"

#: The game's CS for every recovered code address.
_CS = 0x1010


#: (module, attr, original) for every retro-patched binding, so teardown restores the corpus.
_PATCHED: "list" = []


def module_name(addr: str) -> str:
    """``'1010:0679'`` -> the corpus module name for it."""
    seg, off = addr.split(":")
    return f"{RECOVERED_PKG}.func_{seg.lower()}_{off.lower()}"


def func_name(addr: str) -> str:
    """``'1010:0679'`` -> the corpus function name inside its module."""
    seg, off = addr.split(":")
    return f"func_{seg.lower()}_{off.lower()}"


def generated(addr: str) -> Callable:
    """The AUTOLIFTED function for ``addr``, bypassing any installed override.

    This is the differential oracle: an override can call it to keep the generated computation while
    adding an effect, and a test can diff override-vs-generated on the paths where both are valid."""
    name = module_name(addr)
    real = sys.modules.get(f"{name}__generated")
    if real is None:
        # Import the real module under its own name only if it is not already shadowed; otherwise
        # load it fresh from source so the shadow cannot hide it from its own oracle.
        mod = sys.modules.get(name)
        if mod is not None and getattr(mod, "_OVERRIDE_SHADOW", False):
            spec = importlib.util.find_spec(name)
            if spec is None:                       # pragma: no cover - corpus missing entirely
                raise LookupError(f"no generated module for {addr}")
            real = importlib.util.module_from_spec(spec)
            sys.modules[f"{name}__generated"] = real
            spec.loader.exec_module(real)
        else:
            real = importlib.import_module(name)
            sys.modules[f"{name}__generated"] = real
    return getattr(real, func_name(addr))


# ---------------------------------------------------------------------------------------------------
# The overrides.  Each entry is a FACTORY taking the platform and returning the generated-contract fn,
# so an override may close over host services (clock, presenter) the generated signature cannot carry.
# ---------------------------------------------------------------------------------------------------

#: address -> factory(plat) -> generated-contract callable.  Keep this list SMALL and justified: every
#: entry is a place the generated corpus is not the truth, and each one needs the reason in its
#: docstring.  Everything absent here is served by the autolifted corpus.
#:
#: EMPTY IS THE CORRECT STATE RIGHT NOW, and an empty registry is not a dead mechanism -- with
#: ``OVERRIDES = {}`` the composite is bit-for-bit the generated program, so a passing cold run proves
#: the GENERATED CORPUS, which is exactly what this milestone is about.  (skyroads_port keeps its own
#: mirror of this registry empty for the same reason.)
#:
#: RETIRED 2026-07-18 -- ``1010:0679`` (`_timer_env_wait`).  It supplied the timer tick the absent
#: IRQ0 owed, so the tick-wait would terminate.  Two things were wrong with it:
#:
#:   * IT BYPASSED THE SPINE.  Intercepting an address and calling a host yield is flow the HOST
#:     invents, running beside the generated program instead of inside it.  The game-agnostic model --
#:     the one dos_re is built around and skyroads already uses -- is that an env-wait is a BOUNDARY
#:     HEAD: the generated body itself calls ``plat.boundary(...)`` at the declared address and a
#:     frame driver on ``plat.boundary_cb`` decides whether to park.  ``1010:0679`` is now declared in
#:     ``artifacts/lift_boundary_heads.txt`` and the emitted body carries the call.
#:   * IT WAS INERT ANYWAY.  ``getattr(plat, "boundary", None)`` then ``boundary("timer")`` targets
#:     ``OverkillPlatform.boundary(kind="timer")``, the host-yield protocol.  Under the cold-start
#:     runtime the platform is dos_re's ``CPUlessPlatformRuntime``, whose ``boundary(head_cs, head_ip,
#:     resume_ip, regs, cost)`` is the boundary-head OBSERVER protocol -- so the call raised
#:     ``TypeError``.  The ``getattr(..., None)`` guard read as defensive but actually found the WRONG
#:     method: a name collision between two unrelated protocols is not something a None-check can see.
#:     Note for anyone adding an override that wants a host service: check the TYPE, not the name.
#:
#: The replacement lives in :mod:`overkill.cpuless_driver`.
OVERRIDES: "dict[str, Callable]" = {}


def install_overrides(plat, addrs=None) -> "list[str]":
    """Shadow each override's corpus module in ``sys.modules``.  Returns the installed addresses.

    MUST be called before the first import of any module that depends on an overridden one, which in
    practice means before the corpus root is loaded at all.  Raises ``LookupError`` if an override
    names an address the corpus does not contain (a typo, or a stale entry after a regeneration)."""
    installed = []
    for addr in (addrs if addrs is not None else sorted(OVERRIDES)):
        name = module_name(addr)
        spec = importlib.util.find_spec(name)
        if spec is None:
            raise LookupError(
                f"override {addr} has no generated module ({name}) -- the corpus does not contain "
                f"that address; fix or drop the OVERRIDES entry")
        fn = OVERRIDES[addr](plat)
        attr = func_name(addr)
        shadow = types.ModuleType(name)
        # CARRY THE REAL SPEC.  A bare ModuleType has `__spec__ = None`, and `find_spec` on a name
        # already in `sys.modules` reads that attribute -- so a spec-less shadow makes the very
        # lookup `generated()` uses raise `ValueError` instead of finding the autolifted module.
        # That would sever the differential oracle from behind the shadow, which is the one thing
        # the shadow must never do.  It was latent until now only because the shipped override
        # happened to warm the `__generated` alias from its factory before the shadow went in.
        shadow.__spec__ = spec
        shadow.__loader__ = spec.loader
        shadow._OVERRIDE_SHADOW = True
        shadow._OVERRIDE_ADDR = addr
        setattr(shadow, attr, fn)
        sys.modules[name] = shadow
        _retro_patch(attr, fn, skip=name)
        installed.append(addr)
    _clear_dispatch_cache()
    return installed


def _retro_patch(attr: str, fn, *, skip: str) -> None:
    """Rebind ``attr`` to ``fn`` in every ALREADY-IMPORTED corpus module that holds it.

    A ``sys.modules`` shadow only affects imports that happen AFTER it is installed. A generated
    module that already ran ``from ...func_1010_0679 import func_1010_0679`` holds a DIRECT reference
    the shadow can never reach, so the override silently never runs for that caller -- the worst
    failure mode a verification seam can have, because nothing reports it.

    The original binding is recorded so :func:`uninstall_overrides` can put it back; otherwise a
    teardown would leave the corpus permanently patched."""
    for modname, mod in list(sys.modules.items()):
        if modname == skip or not modname.startswith(RECOVERED_PKG + "."):
            continue
        # Never patch a shadow, and never patch an ORACLE copy: `generated()` loads the autolifted
        # module under a `__generated` alias precisely so the override can delegate to it, and
        # rebinding that would make the oracle return the override -- silently turning the
        # differential into a comparison of the override against itself.
        if getattr(mod, "_OVERRIDE_SHADOW", False) or modname.endswith("__generated"):
            continue
        current = getattr(mod, attr, None)
        if current is None or current is fn:
            continue
        _PATCHED.append((mod, attr, current))
        setattr(mod, attr, fn)


def _clear_dispatch_cache() -> None:
    """Drop ``_dyncall``'s memoized resolutions.

    The dynamic-dispatch registry caches ``(kind, key) -> resolved callable`` on first use. A cache
    warmed BEFORE an override is installed keeps serving the generated body for every indirect
    transfer, so the override would apply to direct calls only -- a split-brain seam that is worse
    than no seam at all."""
    dyn = sys.modules.get(f"{RECOVERED_PKG}._dyncall")
    cache = getattr(dyn, "_cache", None)
    if cache is not None:
        cache.clear()


def uninstall_overrides() -> None:
    """Drop every installed shadow (and any oracle copies) so the next load is pure generated code.

    Also RESTORES every retro-patched binding: without that, a torn-down override would live on in
    the callers it was patched into, and the corpus would silently stay overridden."""
    while _PATCHED:
        mod, attr, original = _PATCHED.pop()
        setattr(mod, attr, original)
    for name in [n for n, m in list(sys.modules.items())
                 if getattr(m, "_OVERRIDE_SHADOW", False) or n.endswith("__generated")]:
        del sys.modules[name]
    _clear_dispatch_cache()
