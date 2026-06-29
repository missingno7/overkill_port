"""Tests for the pure-layer boundary audit (``scripts/audit_recovered_layers.py``).

Guards two things: the real pure layers pass, and the audit is not vacuously
passing -- it really flags VM imports, ``cpu``/``mem`` names, capitalised VM/CPU
*types*, and original memory-layout constants, while honouring the
``# layout-justified`` escape hatch.
"""
from __future__ import annotations

import importlib.util
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_audit():
    spec = importlib.util.spec_from_file_location(
        "audit_recovered_layers", ROOT / "scripts" / "audit_recovered_layers.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = mod  # frozen dataclass needs the module registered
    spec.loader.exec_module(mod)
    return mod


def _audit_source(audit, source: str):
    path = pathlib.Path(tempfile.mktemp(suffix=".py"))
    path.write_text(source, encoding="utf-8")
    try:
        return audit.audit_file(path)
    finally:
        os.unlink(path)


def test_real_pure_layers_pass():
    audit = _load_audit()
    assert audit.main() == 0


def test_catches_forbidden_import_and_vm_names():
    audit = _load_audit()
    issues = _audit_source(
        audit,
        "from overkill.recovered.adapters.x import y\n"
        "def f(cpu):\n"
        "    return mem\n",
    )
    msgs = " ".join(i.message for i in issues)
    assert "must not import" in msgs
    assert "cpu" in msgs and "mem" in msgs


def test_catches_capitalised_vm_types_in_annotations_and_names():
    audit = _load_audit()
    issues = _audit_source(
        audit,
        "def f(state: CPU, m: Memory) -> Registers:\n"
        "    return m\n",
    )
    flagged = {i.message for i in issues}
    joined = " ".join(flagged)
    for typ in ("CPU", "Memory", "Registers"):
        assert typ in joined, f"expected the audit to flag VM/CPU type {typ}"


def test_catches_memory_layout_constants():
    audit = _load_audit()
    issues = _audit_source(
        audit,
        "SEG = 0x1010\n"
        "OBJ_TABLE = 0x2B5C\n",
    )
    msgs = " ".join(i.message for i in issues)
    assert "0x1010" in msgs and "0x2b5c" in msgs


def test_layout_justified_comment_is_an_escape_hatch():
    audit = _load_audit()
    issues = _audit_source(
        audit,
        "PRESENT_TABLE = 0x32CA  # layout-justified: documented pointer-table base\n",
    )
    assert issues == [], "the # layout-justified marker should suppress the layout-constant rule"


def test_gameplay_value_that_is_not_a_layout_constant_is_allowed():
    audit = _load_audit()
    # A normal domain constant (a span/bias) must not be flagged.
    issues = _audit_source(audit, "POSTMOVE_CONTACT_Y_SPAN = 0x002C\n")
    assert issues == []
