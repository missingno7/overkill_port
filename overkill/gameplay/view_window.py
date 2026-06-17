"""Lifted OVERKILL view/contact-window wrapper helpers.

The source-like AA46 decision now lives in ``overkill.recovered``: the adapter
projects the DS:214E offset-table center into DS:95F2/95F4 and then reuses the
canonical 8331 signed rectangle test.  This module remains as the historical
address-facing import used by BC4B/BCCB lifted parents.
"""
from __future__ import annotations

from overkill.recovered.adapters.collision_adapter import run_view_window_check_aa46_body


def _run_view_window_check_aa46(cpu) -> None:
    """Run the observed AA46 -> 8331 view-window check path.

    Used from BCCB inside the BC4B post-move pass.  The recovered adapter owns
    the DOS globals, offset-table reads, and exact SI/FLAGS-producing 8331
    compare sequence; this compatibility wrapper deliberately returns no value
    because the original caller observes only CF and scratch state.
    """
    run_view_window_check_aa46_body(cpu)
