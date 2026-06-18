#!/usr/bin/env python
"""OVERKILL source-port status: how far has code migrated ASM -> clean source?

A read-only dashboard for "where are we" decisions.  It reuses the *enforced*
layer map from ``audit_architecture.py`` (so it can never drift from what the
build checks) and reports, per architecture layer:

* module count and line mass,
* ``cpu``/``mem`` reference density (a proxy for how ASM-bound the code still is).

Then it prints the headline migration metric -- what fraction of game-logic code
mass is already in the pure, VM-free source layer -- plus a few structural
flags (oversized hook-boundary files, pure-rule inventory, registered hooks).

This is evidence/visibility tooling, not a hook.  It changes no behaviour.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from audit_architecture import layer_of  # canonical, enforced layer map

PKG = ROOT / "overkill"
CPU_MEM_RE = re.compile(r"\bcpu\.|\.mem\.|\bmem\.|cpu\.s\.")

# Layer -> (one-line role, bucket).  Buckets group layers for the headline ratio.
LAYER_ROLE = {
    "vm": ("emulator / oracle / test harness", "harness"),
    "hook_boundary": ("ASM-facing @registry.replace glue", "asm"),
    "lifted": ("VM-aware bodies on the original memory layout", "asm"),
    "bridge": ("DOS-memory <-> portable domain projection", "asm"),
    "backend": ("Tandy/EGA/CGA render, sound, assets (isolated)", "backend"),
    "source_pure": ("PURE VM-free game logic (future native core)", "source"),
    "game_core": ("backend-agnostic protocols/types", "source"),
}
LAYER_ORDER = ["vm", "hook_boundary", "lifted", "bridge", "backend", "source_pure", "game_core"]


def _iter_py() -> list[Path]:
    return [p for p in PKG.rglob("*.py") if "__pycache__" not in p.parts]


def main() -> int:
    by_layer: dict[str, dict[str, int]] = {
        lyr: {"modules": 0, "lines": 0, "cpu_mem": 0} for lyr in LAYER_ORDER
    }
    oversized: list[tuple[str, int]] = []

    for path in _iter_py():
        rel = path.relative_to(ROOT).as_posix()
        layer = layer_of(rel)
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.count("\n") + 1
        cpu_mem = len(CPU_MEM_RE.findall(text))
        agg = by_layer.setdefault(layer, {"modules": 0, "lines": 0, "cpu_mem": 0})
        agg["modules"] += 1
        agg["lines"] += lines
        agg["cpu_mem"] += cpu_mem
        if layer == "hook_boundary" and lines > 1500:
            oversized.append((rel, lines))

    print("OVERKILL source-port status\n")
    print(f"  {'layer':14} {'mods':>4} {'lines':>7} {'cpu/mem':>8}   role")
    print(f"  {'-'*14} {'-'*4:>4} {'-'*7:>7} {'-'*8:>8}   {'-'*40}")
    for lyr in LAYER_ORDER:
        a = by_layer[lyr]
        role = LAYER_ROLE[lyr][0]
        print(f"  {lyr:14} {a['modules']:4d} {a['lines']:7d} {a['cpu_mem']:8d}   {role}")

    # Headline: of the *game-logic* mass (exclude harness + backend, which are
    # not part of the ASM->source migration), how much is pure source?
    asm_mass = sum(by_layer[l]["lines"] for l in LAYER_ORDER if LAYER_ROLE[l][1] == "asm")
    src_mass = sum(by_layer[l]["lines"] for l in LAYER_ORDER if LAYER_ROLE[l][1] == "source")
    logic_mass = asm_mass + src_mass
    pct = (100.0 * src_mass / logic_mass) if logic_mass else 0.0
    print("\n  Migration (game logic only; excludes vm harness + backend):")
    print(f"    ASM-like  (hook_boundary + lifted + bridge): {asm_mass:7d} lines")
    print(f"    Source    (source_pure + game_core):         {src_mass:7d} lines")
    print(f"    => {pct:5.1f}% of game-logic code mass is pure source-like")

    # Pure-rule inventory and structural flags.
    sys_dir = PKG / "recovered" / "systems"
    pure_defs = sum(
        len(re.findall(r"^def ", p.read_text(encoding="utf-8", errors="replace"), re.M))
        for p in sys_dir.glob("*.py")
    )
    print(f"\n  Pure rules in recovered/systems: {pure_defs} top-level functions")

    try:
        import overkill.hooks  # noqa: F401 - registers all replacements
        from dos_re.hooks import registry

        print(f"  Registered VM hooks: {len(registry.replacements)}")
    except Exception as exc:  # noqa: BLE001
        print(f"  Registered VM hooks: <unavailable: {type(exc).__name__}>")

    if oversized:
        print("\n  Oversized hook_boundary files (registration glue should stay thin):")
        for rel, n in sorted(oversized, key=lambda x: -x[1]):
            print(f"    {rel}  ({n} lines)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
