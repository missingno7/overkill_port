"""Project-wide architectural layer audit for the OVERKILL port.

The codebase grew from verified ASM hooks toward source-like systems.  This
script makes the intended layering explicit and *enforced*, so future edits
cannot quietly pull the VM/CPU/segment-memory world back into the clean layers.

Layers (high level = closer to original ASM, low level = closer to pure source):

    vm/orchestration   overkill top-level (runtime, verification, coverage, ...)
                       + the external ``dos_re`` VM.  May depend on anything.
    hook_boundary      overkill/hooks.py, overkill/hook_wrappers/*.  Thin glue
                       between the hook registry and lifted routines.
    lifted             overkill/gameplay/*.  VM-aware Python that reproduces
                       original behaviour on the original memory layout.
    backend            overkill/rendering/*, overkill/sounds/*,
                       overkill/asset_codecs/*, overkill/file_io/*.  Backend-
                       specific (Tandy/EGA/CGA, PC speaker, AdLib, assets).
    bridge             overkill/recovered/{adapters,views} + the recovered/*
                       compatibility facades.  Project VM memory <-> domain.
    source_pure        overkill/recovered/{domain,systems}.  Portable, VM-free.
    game_core          overkill/game_core/*.  Backend-agnostic native-core seam.

Dependency rules (only the *hard* ones fail the audit; softer notes are printed):

  * source_pure and game_core MUST NOT import the VM (``dos_re``), hooks,
    hook_wrappers, gameplay, backends, or the recovered bridge.  They are the
    clean core and must stay reachable without the emulator.
  * game_core MUST NOT import any other ``overkill`` package at all (it is a
    standalone, platform-neutral seam).
  * backend code MUST NOT import gameplay (lifted core logic): backends sit
    behind a boundary and must not reach up into the game systems.

This complements, not replaces, the finer-grained checks in
``audit_recovered_layers.py`` (cpu/mem name leaks in the pure recovered layer)
and ``tests/test_game_core_backends.py`` (game_core purity + protocol contracts).
"""
from __future__ import annotations

import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PKG = ROOT / "overkill"


def layer_of(rel: str) -> str:
    """Map an ``overkill/...`` posix path to its architectural layer."""
    if rel.startswith("overkill/game_core/"):
        return "game_core"
    if rel.startswith("overkill/recovered/domain/") or rel.startswith("overkill/recovered/systems/"):
        return "source_pure"
    if rel.startswith("overkill/recovered/adapters/") or rel.startswith("overkill/recovered/views/"):
        return "bridge"
    if rel == "overkill/recovered/islands.py":
        return "source_pure"  # pure self-describing metadata (stdlib only); importable by systems/domain
    if rel.startswith("overkill/recovered/"):
        return "bridge"  # top-level recovered/* are compatibility facades
    if rel == "overkill/hooks.py" or rel.startswith("overkill/hook_wrappers/"):
        return "hook_boundary"
    if rel.startswith("overkill/gameplay/"):
        return "lifted"
    if (
        rel.startswith("overkill/rendering/")
        or rel.startswith("overkill/sounds/")
        or rel.startswith("overkill/asset_codecs/")
        or rel.startswith("overkill/file_io/")
    ):
        return "backend"
    return "vm"  # overkill top-level orchestration


def module_layer(dotted: str) -> str | None:
    """Layer of an imported module name, or None if outside the project."""
    if dotted == "dos_re" or dotted.startswith("dos_re."):
        return "vm_external"
    if dotted == "overkill" or dotted.startswith("overkill."):
        return layer_of(dotted.replace(".", "/") + ".py")
    return None


# Forbidden target layers per source layer (hard failures).
FORBIDDEN: dict[str, set[str]] = {
    "source_pure": {"vm_external", "hook_boundary", "lifted", "backend", "bridge"},
    "game_core": {"vm_external", "hook_boundary", "lifted", "backend", "bridge", "vm"},
    "backend": {"lifted"},
}

# Documented, tolerated cross-layer edges (lifted code may reference a backend
# hardware constant from its single source of truth).
ALLOWED_EXCEPTIONS: set[tuple[str, str]] = {
    # frame_orchestration loads the AdLib music-driver segment constant.
    ("overkill/gameplay/frame_orchestration.py", "overkill.sounds.loaded_driver"),
}


def _abs_imports(tree: ast.AST) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.extend((node.lineno, a.name) for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue  # relative imports resolve within the same package
            if node.module:
                out.append((node.lineno, node.module))
    return out


def main() -> int:
    violations: list[str] = []
    counts: dict[str, int] = {}
    edges: set[tuple[str, str]] = set()

    for path in sorted(PKG.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(ROOT).as_posix()
        src_layer = layer_of(rel)
        counts[src_layer] = counts.get(src_layer, 0) + 1
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:  # pragma: no cover - lint.py already guards this
            violations.append(f"{rel}: syntax error {exc}")
            continue
        for lineno, dotted in _abs_imports(tree):
            tgt_layer = module_layer(dotted)
            if tgt_layer is None:
                continue
            edges.add((src_layer, tgt_layer))
            if tgt_layer in FORBIDDEN.get(src_layer, set()):
                if (rel, dotted) in ALLOWED_EXCEPTIONS:
                    continue
                violations.append(
                    f"{rel}:{lineno}: {src_layer} layer must not import "
                    f"{dotted!r} ({tgt_layer})"
                )

    print("Architecture layer inventory:")
    for layer in ("vm", "hook_boundary", "lifted", "backend", "bridge", "source_pure", "game_core"):
        print(f"  {layer:14} {counts.get(layer, 0):3d} modules")

    if violations:
        print("\nFORBIDDEN dependencies found:")
        for v in violations:
            print(f"  {v}")
        print(f"\naudit_architecture FAILED: {len(violations)} violation(s)")
        return 1

    print("\naudit_architecture passed: layer dependency rules hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
