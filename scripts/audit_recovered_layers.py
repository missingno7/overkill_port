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
    def __init__(self, path: pathlib.Path) -> None:
        self.path = path
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

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in FORBIDDEN_NAMES:
            self.issues.append(Issue(self.path, node.lineno, f"pure recovered layer name {node.id!r} looks VM-bound"))


def audit_file(path: pathlib.Path) -> list[Issue]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    visitor = PureLayerVisitor(path)
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
