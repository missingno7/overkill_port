"""Fast (VM-free) tests for the native object-update coverage gate.

These pin the gate's classification logic -- the registry wiring and the
PASS / NO-EVENTS / FAIL exit semantics -- without running a full demo (the
end-to-end run is exercised by the probe itself, e.g. L5_continue: AE09
777/777, see docs/overkill/run_status.md).
"""
from __future__ import annotations

from overkill.probes import verify_native_object_update as drv


def test_registry_wires_ae09_at_its_entry_ip():
    by_logic = {h.logic_id: h for h in drv.NATIVE_HANDLERS}
    assert 0x0C in by_logic, "AE09 (logic_id 0x0C) should be the first wired native handler"
    ae09 = by_logic[0x0C]
    assert ae09.entry_ip == drv.AE09_IP == 0xAE09
    assert (drv.CS, 0xAE09) in drv._HANDLER_BY_IP


def test_report_pass_when_native_handler_exact():
    code = drv._report(
        "demo", 700,
        coverage={0x0C: 777, 0x02: 1000},
        native_ok={0x0C: 777},
        native_fail={},
    )
    assert code == 0


def test_report_fail_on_divergence():
    code = drv._report(
        "demo", 700,
        coverage={0x0C: 5},
        native_ok={0x0C: 4},
        native_fail={0x0C: [((1, 2, 3, 4, 5, 6), (1, 2, 3, 4, 5, 7))]},
    )
    assert code == 1, "a wired-handler divergence must fail the gate"


def test_report_no_events_is_not_a_failure():
    # A demo that never spawns a wired handler: counted, but not a failure.
    code = drv._report(
        "demo", 700,
        coverage={0x02: 1203, 0x1D: 1170},
        native_ok={},
        native_fail={},
    )
    assert code == 0, "no wired handler reached should be NO-EVENTS (not a failure)"
