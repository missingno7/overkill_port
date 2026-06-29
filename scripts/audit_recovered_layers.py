"""Audit source-port boundaries inside ``overkill.recovered``.

The recovered source layer is split into:

- ``views``: may know DOS memory layout,
- ``adapters``: may touch CPU/memory and project to/from domain records,
- ``domain`` and ``systems``: must stay portable and VM-free.

This audit keeps future AI-assisted edits from accidentally pulling ``cpu`` or
``mem`` back into the pure layers.
"""
from __future__ import annotations

import ast
import pathlib
import sys
from dataclasses import dataclass

ROOT = pathlib.Path(__file__).resolve().parents[1]
PURE_ROOTS = (ROOT / "overkill" / "recovered" / "domain", ROOT / "overkill" / "recovered" / "systems")
FORBIDDEN_IMPORTS = (
    "dos_re",
    "overkill.hooks",
    "overkill.gameplay",
    "overkill.recovered.adapters",
    "overkill.recovered.views",
)
FORBIDDEN_NAMES = {"cpu", "mem", "memory"}
# Capitalised VM/CPU *types* must not be referenced (annotations or bare names)
# in the pure layers either: the future native core never sees these.
FORBIDDEN_TYPE_NAMES = {"CPU", "CPUState", "Memory", "Mem", "Registers", "Register", "DosRuntime"}
# Original memory-layout / segment execution constants.  These are addresses, not
# gameplay values, so they must not appear as bare literals in the pure layers.
# Documented in docs/overkill/recovered_source_layer.md (table bases + code seg).
# A genuinely-justified single value may carry a ``# layout-justified`` line comment.
LAYOUT_CONSTANTS = {
    0x1010,  # OVERKILL code segment
    0x23B4,  # DS:23B4 effect/contact slot table base
    0x2B5C,  # DS:2B5C gameplay object slot table base
    0x32CA,  # DS:32CA update/draw/present pointer table base
    0x8D12,  # DS:8D12 compact/effect pointer table base
    0x95D8,  # DS:95D8 effect allocator cursor
}
LAYOUT_JUSTIFIED_MARKER = "layout-justified"


@dataclass(frozen=True)
class Issue:
    path: pathlib.Path
    lineno: int
    message: str


def _iter_pure_files() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for root in PURE_ROOTS:
        if root.exists():
            files.extend(root.rglob("*.py"))
    return sorted(files)


def _import_target(node: ast.Import | ast.ImportFrom) -> list[tuple[int, str]]:
    if isinstance(node, ast.Import):
        return [(node.lineno, alias.name) for alias in node.names]
    if node.level:
        # Relative imports within the pure layer are allowed; lint.py checks that
        # they resolve.  Avoid guessing package names here.
        return []
    if node.module is None:
        return []
    return [(node.lineno, node.module)]


def _is_forbidden_import(target: str) -> bool:
    return any(target == forbidden or target.startswith(forbidden + ".") for forbidden in FORBIDDEN_IMPORTS)


class PureLayerVisitor(ast.NodeVisitor):
    def __init__(self, path: pathlib.Path, source_lines: list[str]) -> None:
        self.path = path
        self.source_lines = source_lines
        self.issues: list[Issue] = []

    def visit_Import(self, node: ast.Import) -> None:
        for lineno, target in _import_target(node):
            if _is_forbidden_import(target):
                self.issues.append(Issue(self.path, lineno, f"pure recovered layer must not import {target!r}"))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for lineno, target in _import_target(node):
            if _is_forbidden_import(target):
                self.issues.append(Issue(self.path, lineno, f"pure recovered layer must not import {target!r}"))

    def visit_arg(self, node: ast.arg) -> None:
        if node.arg in FORBIDDEN_NAMES:
            self.issues.append(Issue(self.path, node.lineno, f"pure recovered layer argument {node.arg!r} looks VM-bound"))
        # Recurse so type annotations on the argument (e.g. ``x: CPU``) are visited.
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in FORBIDDEN_NAMES:
            self.issues.append(Issue(self.path, node.lineno, f"pure recovered layer name {node.id!r} looks VM-bound"))
        elif node.id in FORBIDDEN_TYPE_NAMES:
            self.issues.append(
                Issue(self.path, node.lineno, f"pure recovered layer references VM/CPU type {node.id!r}")
            )

    def _line_is_layout_justified(self, lineno: int) -> bool:
        if 1 <= lineno <= len(self.source_lines):
            return LAYOUT_JUSTIFIED_MARKER in self.source_lines[lineno - 1]
        return False

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, int) and not isinstance(node.value, bool) and node.value in LAYOUT_CONSTANTS:
            if not self._line_is_layout_justified(node.lineno):
                self.issues.append(
                    Issue(
                        self.path,
                        node.lineno,
                        f"pure recovered layer uses memory-layout constant {node.value:#06x} "
                        f"(add a '# {LAYOUT_JUSTIFIED_MARKER}' comment if this is a real domain value)",
                    )
                )


def audit_file(path: pathlib.Path) -> list[Issue]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    visitor = PureLayerVisitor(path, source.splitlines())
    visitor.visit(tree)
    return visitor.issues


def main() -> int:
    issues: list[Issue] = []
    for path in _iter_pure_files():
        issues.extend(audit_file(path))
    if issues:
        print("RECOVERED LAYER AUDIT FAILED")
        for issue in sorted(issues, key=lambda item: (str(item.path), item.lineno, item.message)):
            rel = issue.path.relative_to(ROOT)
            print(f"{rel}:{issue.lineno}: {issue.message}")
        return 1
    print(f"Recovered layer audit passed for {len(_iter_pure_files())} pure files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
