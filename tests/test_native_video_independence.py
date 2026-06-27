"""The native video backend must be independent of the VM.

A hard rule of the native presentation layer: it consumes the recovered semantic
model + the pure Tandy decode, but never the emulator, the hooks, or the lifted
runtime. This guards against the backend quietly reaching back into the VM
framebuffer or runtime instead of the semantic source.
"""
from __future__ import annotations

import ast
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "overkill" / "native_video"

# Modules the native backend must never import (the VM and its coupling layers).
FORBIDDEN_PREFIXES = (
    "dos_re",
    "overkill.hooks",
    "overkill.hook_wrappers",
    "overkill.gameplay",
    "overkill.runtime",
    "overkill.coverage",
    "pygame",  # the pure backend logic stays display-free; the SDL adapter is separate
)


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def test_native_video_does_not_import_the_vm():
    offenders = []
    for path in PKG.rglob("*.py"):
        for name in _imported_names(path):
            if any(name == p or name.startswith(p + ".") for p in FORBIDDEN_PREFIXES):
                offenders.append((path.name, name))
    assert not offenders, f"native_video imported VM-coupled modules: {offenders}"
