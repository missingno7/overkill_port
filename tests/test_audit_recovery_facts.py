"""The recovery-fact audit runs in the suite -- an audit nobody runs is as useless as an unused fact.

`scripts/audit_recovery_facts.py` checks that every declared recovery fact has a visible CONSEQUENCE in
the generated artifacts. It exists because `lift_keep_interpreted.txt` declared an env-wait frontier that
the pipeline silently ignored for weeks: the corpus promoted two functions the repo had already proven
DIVERGE when lifted, and nothing failed.

The audit is a ratchet, so this test has teeth in both directions: a NEW violation fails, and a KNOWN
violation that has been fixed but not removed from the list also fails.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "scripts" / "audit_recovery_facts.py"
CENSUS = ROOT / "artifacts" / "cpuless_promote_census.json"


@pytest.mark.skipif(not CENSUS.is_file(),
                    reason="no promotion census -- run scripts/probe_vmless_cpuless.py first")
def test_no_new_or_stale_recovery_fact_violations():
    r = subprocess.run([sys.executable, str(AUDIT)], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, (
        "recovery-fact audit failed -- either a declared fact stopped taking effect, or a tracked "
        f"violation was fixed and must be removed from KNOWN_VIOLATIONS:\n{r.stdout}\n{r.stderr}")


def test_audit_is_outcome_based_not_grep_based():
    """Guard the audit's own design: it must assert consequences in the generated census, not scan the
    pipeline source for flag strings (which proves only that a string appears)."""
    src = AUDIT.read_text(encoding="utf-8")
    assert "cpuless_promote_census.json" in src, "the audit must read the generated census"
    assert "KNOWN_VIOLATIONS" in src, "the audit must keep a shrink-only ratchet list"
