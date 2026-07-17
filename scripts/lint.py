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
# dos_re/ is now the framework submodule's own repo root, not the package --
# that's one level deeper, at dos_re/dos_re/. Scanning the submodule root
# would also sweep in its own tests/tools/examples (dos_re has its own lint
# for those). pynuked_opl3 is not vendored here and is no longer even a dos_re
# submodule: it is an EXTERNAL, opt-in accuracy package (DOSRE_OPL3_BACKEND=nuked),
# so it is checked like any other external import below -- see dos_re.audio_sink.
PACKAGE_ROOTS = (ROOT / "dos_re" / "dos_re", ROOT / "overkill")
SCRIPTS_ROOT = ROOT / "scripts"

# dos_re/ MUST come first: `pip install -e` of a dos_re checkout from ANY other
# project registers a global `dos_re` distribution, and without this entry
# `import dos_re.x` silently resolves to THAT checkout instead of this repo's
# submodule -- so lint would import a different revision than the one it is
# scanning (and than the tests, which all insert this path themselves).
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))


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
    # dos_re/ is a submodule -- a full repo root, not the package itself
    # (that's one level deeper, at dos_re/dos_re/). Collapse the extra
    # nesting so computed module names match what's actually importable.
    if len(parts) >= 2 and parts[0] == "dos_re" and parts[1] == "dos_re":
        parts = parts[1:]
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
    files = []
    for package_root in PACKAGE_ROOTS:
        files.extend(package_root.rglob("*.py"))
    files.extend(SCRIPTS_ROOT.glob("*.py"))
    return sorted(set(files))


def _internal_roots() -> set[str]:
    # pynuked_opl3 is NOT internal: it is an external, opt-in accuracy package
    # (see dos_re.audio_sink.load_opl3) that is not expected to be installed.
    roots = {"dos_re", "overkill"}
    roots.update(path.stem for path in SCRIPTS_ROOT.glob("*.py"))
    return roots


def _collect_local_imports_issues(path: pathlib.Path, tree: ast.AST) -> list[LintIssue]:
    rel_parts = path.relative_to(ROOT).parts if path.is_relative_to(ROOT) else ()
    guarded_dirs = {"asset_codecs", "file_io", "gameplay", "rendering", "sounds"}
    if not path.is_relative_to(ROOT / "overkill") or len(rel_parts) < 2 or rel_parts[1] not in guarded_dirs:
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





def _collect_package_boundary_issues(path: pathlib.Path, tree: ast.AST) -> list[LintIssue]:
    if not path.is_relative_to(ROOT / "dos_re"):
        return []
    issues: list[LintIssue] = []
    package_name = _package_name_for_path(path)
    for lineno, target in _collect_resolved_import_targets(path, tree):
        if target.startswith("<relative-import-error>"):
            continue
        if target == "overkill" or target.startswith("overkill."):
            issues.append(
                LintIssue(
                    kind="package-boundary",
                    path=path,
                    lineno=lineno,
                    message="dos_re must not import the OVERKILL-specific package",
                )
            )
    return issues



def _collect_recovered_layer_boundary_issues(path: pathlib.Path, tree: ast.AST) -> list[LintIssue]:
    pure_roots = (ROOT / "overkill" / "recovered" / "domain", ROOT / "overkill" / "recovered" / "systems")
    if not any(path.is_relative_to(root) for root in pure_roots):
        return []
    forbidden_imports = (
        "dos_re",
        "overkill.hooks",
        "overkill.gameplay",
        "overkill.recovered.adapters",
        "overkill.recovered.views",
    )
    forbidden_names = {"cpu", "mem", "memory"}
    issues: list[LintIssue] = []

    for lineno, target in _collect_resolved_import_targets(path, tree):
        if target.startswith("<relative-import-error>"):
            continue
        if any(target == forbidden or target.startswith(forbidden + ".") for forbidden in forbidden_imports):
            issues.append(
                LintIssue(
                    kind="recovered-layer-boundary",
                    path=path,
                    lineno=lineno,
                    message=f"pure recovered layer must not import {target!r}",
                )
            )

    class Visitor(ast.NodeVisitor):
        def visit_arg(self, node: ast.arg) -> None:
            if node.arg in forbidden_names:
                issues.append(
                    LintIssue(
                        kind="recovered-layer-boundary",
                        path=path,
                        lineno=node.lineno,
                        message=f"pure recovered layer argument {node.arg!r} looks VM-bound",
                    )
                )

        def visit_Name(self, node: ast.Name) -> None:
            if node.id in forbidden_names:
                issues.append(
                    LintIssue(
                        kind="recovered-layer-boundary",
                        path=path,
                        lineno=node.lineno,
                        message=f"pure recovered layer name {node.id!r} looks VM-bound",
                    )
                )

    Visitor().visit(tree)
    return issues

def _collect_hardcoded_workspace_path_issues(path: pathlib.Path, source: str) -> list[LintIssue]:
    if not path.is_relative_to(SCRIPTS_ROOT):
        return []
    forbidden = ("/mnt" + "/data/", "C:" + "\\games\\", "C:" + "/games/")
    issues: list[LintIssue] = []
    for lineno, line in enumerate(source.splitlines(), start=1):
        if any(token in line for token in forbidden):
            issues.append(
                LintIssue(
                    kind="hardcoded-workspace-path",
                    path=path,
                    lineno=lineno,
                    message="diagnostic scripts must use repository-relative paths or CLI arguments",
                )
            )
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
    issues.extend(_collect_package_boundary_issues(path, tree))
    issues.extend(_collect_recovered_layer_boundary_issues(path, tree))
    issues.extend(_collect_hardcoded_workspace_path_issues(path, source))

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
    for package_root in PACKAGE_ROOTS:
        for path in package_root.rglob("*.py"):
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



def _collect_documentation_layout_issues() -> list[LintIssue]:
    issues: list[LintIssue] = []
    allowed_root_docs = {"README.md"}
    docs_root = ROOT / "docs"
    for path in sorted(docs_root.glob("*.md")):
        if path.name not in allowed_root_docs:
            issues.append(
                LintIssue(
                    kind="documentation-layout",
                    path=path,
                    lineno=1,
                    message="durable docs must live under docs/dos_re, docs/overkill, or docs/architecture",
                )
            )
    forbidden_root_docs = {"RUN_STATUS.md", "PERFORMANCE_INVESTIGATION.md"}
    for name in forbidden_root_docs:
        path = ROOT / name
        if path.exists():
            issues.append(
                LintIssue(
                    kind="documentation-layout",
                    path=path,
                    lineno=1,
                    message="project status/investigation docs belong under docs/overkill",
                )
            )
    return issues


def _collect_legacy_reference_issues() -> list[LintIssue]:
    issues: list[LintIssue] = []
    # dos_re/dos_re/ (not the whole dos_re/ submodule, which also carries its
    # own tests/tools/docs -- irrelevant to OVERKILL-specific legacy tokens).
    scanned_roots = (ROOT / "README.md", ROOT / "AGENTS.md", ROOT / "docs", ROOT / "dos_re" / "dos_re", ROOT / "overkill", ROOT / "scripts", ROOT / "tests")
    forbidden = {
        "from render_cga import": "use scripts/render_frame.py / render_frame module",
        "import render_cga as": "use scripts/render_frame.py / render_frame module",
        "render_cga.py": "use scripts/render_frame.py",
        "overkill_port.": "use the separated dos_re/overkill packages",
        "overkill.hook_verify": "use overkill.verification",
        "replacements.py": "use overkill/hooks.py",
    }
    candidates: list[pathlib.Path] = []
    for root in scanned_roots:
        if not root.exists():
            continue
        if root.is_file():
            candidates.append(root)
        else:
            candidates.extend(path for path in root.rglob("*") if path.suffix in {".py", ".md"})
    for path in sorted(set(candidates)):
        if path == ROOT / "scripts" / "lint.py":
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(source.splitlines(), start=1):
            for token, message in forbidden.items():
                if token in line:
                    issues.append(
                        LintIssue(
                            kind="legacy-reference",
                            path=path,
                            lineno=lineno,
                            message=message,
                        )
                    )
    return issues

def main() -> int:
    issues: list[LintIssue] = []
    internal_roots = _internal_roots()
    for path in _iter_python_files():
        issues.extend(_lint_file(path, internal_roots))

    issues.extend(_import_first_party_modules())
    issues.extend(_collect_documentation_layout_issues())
    issues.extend(_collect_legacy_reference_issues())

    if issues:
        print("LINT FAILED")
        for issue in sorted(issues, key=lambda item: (str(item.path), item.lineno, item.kind)):
            print(f"{issue.kind}: {issue.path}:{issue.lineno}: {issue.message}")
        return 1

    print(f"Lint passed for {len(_iter_python_files())} Python files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
