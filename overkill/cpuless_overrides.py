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
  computation.  ``1010:0679`` below is the model: it supplies the missing timer tick and then calls
  the generated body, so the returned flags are the generated ones and cannot drift.

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
#: The timer-tick flag the INT 8 handler sets (`1010:066C` does ``inc byte [066B]``) and the
#: `1010:0679` env-wait spins on.
_TICK_FLAG = 0x66B


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

def _timer_env_wait(plat) -> Callable:
    """``1010:0679`` -- wait for the next TIMER TICK.

    The original spins on ``[066B]`` until the INT 8 handler (``1010:066C``: ``inc byte [066B]``)
    sets it.  A CPUless build has no interrupt to run that handler, so the flag never changes and the
    wait is unsatisfiable -- the generated body spins to its 20M-iteration guard.  This is exactly the
    ENV-WAIT frontier `artifacts/lift_keep_interpreted.txt` declared and the pipeline promoted anyway.

    The recovered semantic is a SCHEDULER YIELD: hand the host a boundary (pace the frame, present,
    pump input), then run the tick the absent interrupt owed us, then let the GENERATED body observe
    the now-set flag and return -- so the flags/cost it reports are the generated ones.

    The tick is applied only when the flag is clear, i.e. only when the original would actually have
    BLOCKED.  An already-set flag returns immediately, as it does on real hardware."""
    real = generated("1010:0679")

    def func_1010_0679(mem, *, ss=0):
        if mem.rb(_CS, _TICK_FLAG) == 0:
            boundary = getattr(plat, "boundary", None)
            if boundary is not None:
                boundary("timer")
            mem.wb(_CS, _TICK_FLAG, (mem.rb(_CS, _TICK_FLAG) + 1) & 0xFF)
        return real(mem, ss=ss)

    return func_1010_0679


#: address -> factory(plat) -> generated-contract callable.  Keep this list SMALL and justified: every
#: entry is a place the generated corpus is not the truth, and each one needs the reason in its
#: docstring.  Everything absent here is served by the autolifted corpus.
OVERRIDES: "dict[str, Callable]" = {
    "1010:0679": _timer_env_wait,
}


def install_overrides(plat, addrs=None) -> "list[str]":
    """Shadow each override's corpus module in ``sys.modules``.  Returns the installed addresses.

    MUST be called before the first import of any module that depends on an overridden one, which in
    practice means before the corpus root is loaded at all.  Raises ``LookupError`` if an override
    names an address the corpus does not contain (a typo, or a stale entry after a regeneration)."""
    installed = []
    for addr in (addrs if addrs is not None else sorted(OVERRIDES)):
        name = module_name(addr)
        if importlib.util.find_spec(name) is None:
            raise LookupError(
                f"override {addr} has no generated module ({name}) -- the corpus does not contain "
                f"that address; fix or drop the OVERRIDES entry")
        fn = OVERRIDES[addr](plat)
        attr = func_name(addr)
        shadow = types.ModuleType(name)
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
