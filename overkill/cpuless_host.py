"""The standalone CPUless host: run the committed recovered corpus over a flat image.

This is the runtime-facing core the eventual ``scripts/play_cpuless.py`` builds on (mirrors
``lemmings_port``'s ``play_cpuless._load_recovered`` / ``CPUlessPlatformRuntime`` split). A recovered
function is a pure ``func(mem, plat, *, <regs>) -> (outputs, _compat)`` (DOS_RE 2.0 stage 3); it touches
no CPU carrier. ``run_recovered`` imports it FROM THE COMMITTED CORPUS
(``overkill.cpuless_recovered`` -- the game's default implementations) and calls it directly; the
function's recovered callees are plain imports, so one root call runs the whole composed graph.

Fail loud, never fall back to the VM: an unpromoted function (or an unpromoted transitive callee,
which surfaces as a missing-module import) and a reached platform effect with no host implementation
both raise :class:`CpuStandaloneWitness`.
"""
from __future__ import annotations

import builtins
import importlib
import sys

#: The committed generated corpus -- runtime source, not a disposable artifact.
RECOVERED_PKG = "overkill.cpuless_recovered"

#: Modules the standalone CPUless runtime must NEVER import -- the interpreter / CPU
#: carrier, the VMless graph installer + lifted-call support, the EXE/VM runtime builder,
#: and the CPU-ABI adapters. A recovered program that reaches for any of these has not
#: actually detached from the VM. (Mirrors lemmings_port's FORBIDDEN_IMPORTS.)
FORBIDDEN_IMPORTS = (
    "dos_re.cpu",                 # the interpreter / CPU8086 carrier
    "dos_re.cpu386",
    "dos_re.lift.install",        # the VMless graph installer
    "dos_re.lift.runtime",        # the VMless lifted-call support (emulate_*)
    "dos_re.runtime",             # the EXE loader / VM runtime builder
    "overkill.cpuless_adapters",  # the CPU-ABI adapters (verification shims, never runtime)
)


class CpuStandaloneWitness(RuntimeError):
    """The standalone CPUless host cannot proceed without the VM: an unpromoted
    function on the frontier, a reached platform effect with no host impl, or an
    attempt to import a forbidden CPU-carrier module (the wall was breached)."""


def _resolve_import(name: str, globals_, level: int) -> str:
    """The ABSOLUTE dotted name of an import request. A RELATIVE import (``from .cpu
    import X``, level=1) reaches ``__import__`` as name='cpu' WITHOUT the package, so
    matching the raw name against 'dos_re.cpu' never hits -- the blind spot that let
    dos_re.cpu slip past lemmings' first guard. Resolve it before matching."""
    if not level:
        return name
    pkg = (globals_ or {}).get("__package__")
    if pkg is None:
        modname = (globals_ or {}).get("__name__", "")
        spec = (globals_ or {}).get("__spec__", None)
        pkg = getattr(spec, "parent", None)
        if pkg is None:
            pkg = modname.rpartition(".")[0] if modname else ""
    parts = [p for p in str(pkg).split(".") if p]
    if level > 1:
        parts = parts[:-(level - 1)] or []
    if name:
        parts = parts + name.split(".")
    return ".".join(parts)


def _forbidden_hit(dotted: str) -> "str | None":
    base = dotted.split(".")
    for forb in FORBIDDEN_IMPORTS:
        fparts = forb.split(".")
        if base[:len(fparts)] == fparts:
            return forb
    return None


def install_import_guard() -> None:
    """Arm the CPUless wall: any import (absolute or relative) of a forbidden CPU-carrier
    module raises :class:`CpuStandaloneWitness`. Fires only on an EXECUTED path; pair with
    a STATIC import-graph lint for paths no run takes. Call once, before importing a root."""
    real_import = builtins.__import__

    def guarded(name, globals=None, locals=None, fromlist=(), level=0):
        dotted = _resolve_import(name, globals, level)
        hit = _forbidden_hit(dotted)
        if hit is not None:
            via = f"{name!r} (relative, level={level})" if level else f"{name!r}"
            raise CpuStandaloneWitness(
                f"standalone CPUless runtime attempted to import {via} -> {dotted!r} "
                f"[forbidden: {hit}] -- it must not depend on the interpreter, the VMless "
                f"graph, the VM runtime, or the CPU-ABI adapters.")
        return real_import(name, globals, locals, fromlist, level)

    builtins.__import__ = guarded


class FailLoudPlatform:
    """The honest default device model: every platform effect fails loud until a real
    host (video / keyboard / timing / DOS) is bound for that service. A pure-memory
    recovered function never calls it; one that does names exactly the missing service."""

    def intr(self, num, regs, cost):
        raise CpuStandaloneWitness(
            f"INT {num & 0xFF:#04x} reached with no host platform implementation "
            f"(bind the device that services it before running this path)")

    def inp(self, port, width, cost):
        raise CpuStandaloneWitness(
            f"IN from port {port & 0xFFFF:#06x} with no host platform implementation")

    def outp(self, port, value, width, cost):
        raise CpuStandaloneWitness(
            f"OUT to port {port & 0xFFFF:#06x} with no host platform implementation")


def module_name(key: str) -> str:
    """The recovered module basename for a 'CS:IP' key, e.g. '1010:5F61' -> 'func_1010_5f61'."""
    cs, ip = key.split(":")
    return f"func_{int(cs, 16):04x}_{int(ip, 16):04x}"


def load_recovered(key: str):
    """Import promoted recovered function ``key`` ('CS:IP') from the committed corpus.

    Fail loud (never the VM) if the function -- or any recovered callee it imports -- is
    not promoted (a missing module) so the CPUless frontier is always visible, not papered."""
    name = module_name(key)
    try:
        mod = importlib.import_module(f"{RECOVERED_PKG}.{name}")
    except ModuleNotFoundError as exc:
        raise CpuStandaloneWitness(
            f"{key}: no recovered module ({name}) -- it (or a recovered callee) is on the "
            f"CPUless frontier; promote it or bind a native override.") from exc
    return getattr(mod, name)


#: A tail dispatch is currently emitted as a NESTED `_dyn` call, so a tail-dispatch
#: LOOP (the machine reuses the frame; we stack a Python frame per hop) grows the
#: stack instead of iterating.  The loops are BOUNDED -- a blitter walking rows
#: terminates -- so running them just needs headroom.  This is deliberately a
#: RUNTIME ACCOMMODATION, not a fix: the correct repair is to emit an intra-routine
#: dispatch as a block goto and a cross-routine tail cycle through a trampoline
#: (see docs/overkill/campaigns/cpuless_app.md).  Until then, run the graph on a
#: thread with a big stack -- raising the recursion limit alone would overflow the
#: C stack and crash instead of raising.
_DEEP_STACK_BYTES = 64 * 1024 * 1024      # 512MB is rejected on Windows; 64MB is portable
_DEEP_RECURSION = 300_000


def run_deep(fn, *args, **kwargs):
    """Run ``fn`` on a thread with a large stack and a raised recursion limit, so a
    bounded tail-dispatch loop completes instead of dying on Python's frame limit.
    Result and exception are propagated to the caller unchanged."""
    import threading

    box: dict = {}

    def _target():
        sys.setrecursionlimit(_DEEP_RECURSION)
        try:
            box["value"] = fn(*args, **kwargs)
        except BaseException as exc:            # noqa: BLE001 -- propagated verbatim
            box["error"] = exc

    prev = threading.stack_size(_DEEP_STACK_BYTES)
    try:
        t = threading.Thread(target=_target)
        t.start()
        t.join()
    finally:
        threading.stack_size(prev)
    if "error" in box:
        raise box["error"]
    return box.get("value")


def run_recovered(key: str, mem, plat=None, **regs):
    """Run recovered function ``key`` over ``mem`` with ``plat``, returning its live-output
    register dict. Pure composition: the function calls its recovered callees directly. When
    ``plat`` is omitted a :class:`FailLoudPlatform` is used, so any reached platform effect
    fails loud rather than silently no-oping."""
    fn = load_recovered(key)
    outputs, _compat = fn(mem, FailLoudPlatform() if plat is None else plat, **regs)
    return outputs
