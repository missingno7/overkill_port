#!/usr/bin/env python3
"""Audit verifier-visible hook-boundary composition.

This is a static guardrail for the bug class where a large Python parent hook
calls a child hook's Python function directly.  A direct call can make the child
routine a shared black box inside the parent transaction, so ``--verify-hooks``
may pass even when the child is wrong.  Complete child routines should be called
through ``call_installed_hook_like_near_call`` with their real CS:IP key.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

Addr = tuple[int, int]


def _parse_registered_hooks(paths: list[Path]) -> dict[str, Addr]:
    out: dict[str, Addr] = {}
    for path in paths:
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            for deco in node.decorator_list:
                if not isinstance(deco, ast.Call):
                    continue
                func = deco.func
                if not (
                    isinstance(func, ast.Attribute)
                    and func.attr == "replace"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "registry"
                ):
                    continue
                if len(deco.args) < 2:
                    continue
                cs_node, ip_node = deco.args[:2]
                if isinstance(cs_node, ast.Constant) and isinstance(ip_node, ast.Constant):
                    out[node.name] = (int(cs_node.value) & 0xFFFF, int(ip_node.value) & 0xFFFF)
    return out


def _parse_hookstop_metadata(verification_py: Path) -> set[Addr]:
    text = verification_py.read_text()
    return {
        (int(cs, 16) & 0xFFFF, int(ip, 16) & 0xFFFF)
        for cs, ip in re.findall(r"\(0x([0-9A-Fa-f]+),\s*0x([0-9A-Fa-f]+)\):\s*HookStop", text)
    }


def _iter_parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    return parents


def _enclosing_function(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> ast.FunctionDef | None:
    cur = node
    while cur in parents:
        cur = parents[cur]
        if isinstance(cur, ast.FunctionDef):
            return cur
    return None


def _find_direct_registered_function_calls(path: Path, registered: dict[str, Addr]) -> list[str]:
    """Find Python calls that bypass a registered original CS:IP boundary.

    If a lifted parent calls ``overkill_child_xxxx(cpu)`` directly, both the
    candidate side and the ASM-oracle clone can share that child as a black box.
    Complete child routines must be reached via the generic installed-boundary
    helpers instead.
    """
    text = path.read_text()
    tree = ast.parse(text, filename=str(path))
    parents = _iter_parent_map(tree)
    bad: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name):
            continue
        handler = node.func.id
        if handler not in registered:
            continue
        enclosing = _enclosing_function(node, parents)
        # Recursive self-calls are not child-boundary composition.  They are not
        # used by current hooks, but this keeps the rule precise.
        if enclosing is not None and enclosing.name == handler:
            continue
        line = text.splitlines()[node.lineno - 1].strip()
        cs, ip = registered[handler]
        bad.append(
            f"{path.relative_to(ROOT)}:{node.lineno}: direct call to registered hook "
            f"{handler} ({cs:04X}:{ip:04X}); route through "
            "call_installed_hook_like_near_call or jump_installed_hook_boundary "
            f"instead: {line}"
        )
    return bad


def _find_raw_call_hook_like_registered_args(path: Path, registered: dict[str, Addr]) -> list[str]:
    text = path.read_text()
    bad: list[str] = []
    pattern = re.compile(r"_call_hook_like_near_call\(\s*cpu\s*,\s*([A-Za-z_][A-Za-z0-9_]*)\s*,", re.MULTILINE)
    for match in pattern.finditer(text):
        handler = match.group(1)
        if handler in registered:
            line = text.count("\n", 0, match.start()) + 1
            cs, ip = registered[handler]
            bad.append(
                f"{path.relative_to(ROOT)}:{line}: raw near-call helper to registered hook "
                f"{handler} ({cs:04X}:{ip:04X}); use call_installed_hook_like_near_call"
            )
    return bad


def _find_rendering_tandy_direct_5a36(path: Path) -> list[str]:
    text = path.read_text()
    bad: list[str] = []
    needle = "_call_hook_like_near_call(cpu, runtime.object_row_address_from_mode_dispatch_5a36"
    start = 0
    while True:
        idx = text.find(needle, start)
        if idx < 0:
            break
        line = text.count("\n", 0, idx) + 1
        bad.append(
            f"{path.relative_to(ROOT)}:{line}: direct child call to 1010:5A36; "
            "use the installed verifier-visible boundary helper"
        )
        start = idx + 1
    return bad


def main() -> int:
    overkill_paths = sorted(
        path for path in (ROOT / "overkill").rglob("*.py")
        if "__pycache__" not in path.parts
    )
    verification_py = ROOT / "overkill" / "verification.py"
    registered = _parse_registered_hooks(overkill_paths)
    metadata = _parse_hookstop_metadata(verification_py)

    errors: list[str] = []
    missing_metadata = sorted(set(registered.values()) - metadata)
    for cs, ip in missing_metadata:
        errors.append(f"registered hook {cs:04X}:{ip:04X} is missing HookStop metadata")

    for path in overkill_paths:
        errors.extend(_find_direct_registered_function_calls(path, registered))
        errors.extend(_find_raw_call_hook_like_registered_args(path, registered))
    errors.extend(_find_rendering_tandy_direct_5a36(ROOT / "overkill" / "rendering" / "tandy.py"))

    if errors:
        print("Hook-oracle audit failed:")
        for err in errors:
            print(f"  - {err}")
        return 1

    print(
        "Hook-oracle audit passed: "
        f"{len(registered)} registered hooks, {len(metadata)} metadata entries, "
        "no direct registered child calls detected."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
