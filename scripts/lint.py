"""Lightweight lint pass for OVERKILL source.

This intentionally stays small and dependency-free:

- syntax/parse checks for repository Python files,
- import-time checks for first-party runtime modules,
- basic unresolved-import checks,
- a gameplay-layer guard against function-local imports.
"""
from __future__ import annotations

import ast
import importlib
import importlib.util
import pathlib
import sys
import traceback
from dataclasses import dataclass


ROOT = pathlib.Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "overkill_port"
SCRIPTS_ROOT = ROOT / "scripts"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))


@dataclass
class LintIssue:
    kind: str
    path: pathlib.Path
    lineno: int
    message: str


def _module_name_for_path(path: pathlib.Path) -> str | None:
    try:
        rel = path.relative_to(ROOT)
    except ValueError:
        return None
    if rel.suffix != ".py":
        return None
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _package_name_for_path(path: pathlib.Path) -> str | None:
    module = _module_name_for_path(path)
    if module is None:
        return None
    if path.name == "__init__.py":
        return module
    parts = module.split(".")
    return ".".join(parts[:-1])


def _resolve_relative_module(package: str, level: int, module: str | None) -> str:
    parts = package.split(".")
    if level <= 0:
        raise ValueError("relative import level must be positive")
    up = level - 1
    if up > len(parts):
        raise ValueError(f"relative import escapes package {package!r}")
    base_parts = parts[: len(parts) - up]
    if module:
        base_parts.extend(module.split("."))
    return ".".join(base_parts)


def _iter_python_files() -> list[pathlib.Path]:
    files = list(PACKAGE_ROOT.rglob("*.py"))
    files.extend(SCRIPTS_ROOT.glob("*.py"))
    return sorted(set(files))


def _internal_roots() -> set[str]:
    roots = {"overkill_port"}
    roots.update(path.stem for path in SCRIPTS_ROOT.glob("*.py"))
    return roots


def _collect_local_imports_issues(path: pathlib.Path, tree: ast.AST) -> list[LintIssue]:
    if "overkill_port/games/overkill" not in path.as_posix():
        return []
    issues: list[LintIssue] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.function_depth = 0

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self.function_depth += 1
            self.generic_visit(node)
            self.function_depth -= 1

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Import(self, node: ast.Import) -> None:
            if self.function_depth:
                issues.append(
                    LintIssue(
                        kind="local-import",
                        path=path,
                        lineno=node.lineno,
                        message="function-local import inside gameplay code",
                    )
                )

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            if self.function_depth:
                issues.append(
                    LintIssue(
                        kind="local-import",
                        path=path,
                        lineno=node.lineno,
                        message="function-local import inside gameplay code",
                    )
                )

    Visitor().visit(tree)
    return issues


def _collect_resolved_import_targets(path: pathlib.Path, tree: ast.AST) -> list[tuple[int, str]]:
    module_name = _module_name_for_path(path)
    package_name = _package_name_for_path(path)
    targets: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                targets.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                if package_name is None:
                    continue
                try:
                    base = _resolve_relative_module(package_name, node.level, node.module)
                except ValueError as exc:
                    targets.append((node.lineno, f"<relative-import-error> {exc}"))
                    continue
            else:
                if node.module is None:
                    continue
                base = node.module

            if node.module is None and node.level:
                for alias in node.names:
                    targets.append((node.lineno, f"{base}.{alias.name}"))
            else:
                targets.append((node.lineno, base))

    return targets


def _lint_file(path: pathlib.Path, internal_roots: set[str]) -> list[LintIssue]:
    issues: list[LintIssue] = []
    try:
        source = path.read_text(encoding="utf-8")
    except Exception as exc:
        issues.append(LintIssue("read-error", path, 1, str(exc)))
        return issues

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        issues.append(LintIssue("syntax", path, exc.lineno or 1, exc.msg))
        return issues

    issues.extend(_collect_local_imports_issues(path, tree))

    for lineno, target in _collect_resolved_import_targets(path, tree):
        if target.startswith("<relative-import-error>"):
            issues.append(LintIssue("import", path, lineno, target))
            continue
        root = target.split(".", 1)[0]
        if root not in internal_roots:
            continue
        if importlib.util.find_spec(target) is None:
            issues.append(LintIssue("missing-import", path, lineno, f"cannot resolve import target {target!r}"))

    return issues


def _import_first_party_modules() -> list[LintIssue]:
    issues: list[LintIssue] = []
    module_paths = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        module_name = _module_name_for_path(path)
        if module_name:
            module_paths.append((module_name, path))

    for module_name, path in sorted(module_paths):
        try:
            importlib.import_module(module_name)
        except Exception:
            tb = traceback.format_exc(limit=3)
            issues.append(
                LintIssue(
                    kind="import-error",
                    path=path,
                    lineno=1,
                    message=f"import {module_name} failed:\n{tb.rstrip()}",
                )
            )

    return issues


def main() -> int:
    issues: list[LintIssue] = []
    internal_roots = _internal_roots()
    for path in _iter_python_files():
        issues.extend(_lint_file(path, internal_roots))

    issues.extend(_import_first_party_modules())

    if issues:
        print("LINT FAILED")
        for issue in sorted(issues, key=lambda item: (str(item.path), item.lineno, item.kind)):
            print(f"{issue.kind}: {issue.path}:{issue.lineno}: {issue.message}")
        return 1

    print(f"Lint passed for {len(_iter_python_files())} Python files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
