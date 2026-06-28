"""Enforce the undefined-name guard (scripts/check_undefined_names.py).

Regression coverage for two latent ``NameError`` landmines that shipped because lint did
not resolve names: the dead ``efae`` predictor's undefined ``slot`` and
``tandy.postcopy_scaled_blit_375b`` calling an unimported ``_inc_reg16_preserve_cf``.
"""
from __future__ import annotations

import ast

from scripts.check_undefined_names import BUILTIN_NAMES, _check_scope, main


def test_overkill_package_has_no_undefined_names():
    # main() returns non-zero (and prints offenders) if any reference resolves to no
    # parameter, local, enclosing scope, module global, star-import, or builtin.
    assert main() == 0


def test_guard_flags_a_synthetic_undefined_name():
    # A guard that can never fail is worthless: prove it catches the efae/375b shape --
    # a Load of a name bound nowhere in scope.
    tree = ast.parse("def f(a):\n    return a + nonexistent_xyz\n")
    findings: list[tuple[str, int, str]] = []
    _check_scope(tree.body[0], set(BUILTIN_NAMES), findings, "synthetic.py")
    assert any(name == "nonexistent_xyz" for _, _, name in findings)


def test_guard_does_not_flag_a_bound_local():
    # And it must not cry wolf on a normally-bound local.
    tree = ast.parse("def f(a):\n    b = a + 1\n    return b\n")
    findings: list[tuple[str, int, str]] = []
    _check_scope(tree.body[0], set(BUILTIN_NAMES), findings, "synthetic.py")
    assert findings == []
