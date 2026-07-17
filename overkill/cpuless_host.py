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

import importlib

#: The committed generated corpus -- runtime source, not a disposable artifact.
RECOVERED_PKG = "overkill.cpuless_recovered"


class CpuStandaloneWitness(RuntimeError):
    """The standalone CPUless host cannot proceed without the VM: an unpromoted
    function on the frontier, or a reached platform effect with no host impl."""


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


def run_recovered(key: str, mem, plat=None, **regs):
    """Run recovered function ``key`` over ``mem`` with ``plat``, returning its live-output
    register dict. Pure composition: the function calls its recovered callees directly. When
    ``plat`` is omitted a :class:`FailLoudPlatform` is used, so any reached platform effect
    fails loud rather than silently no-oping."""
    fn = load_recovered(key)
    outputs, _compat = fn(mem, FailLoudPlatform() if plat is None else plat, **regs)
    return outputs
