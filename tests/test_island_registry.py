"""The recovered-island manifest must stay in sync with the in-code metadata.

These tests enforce the "code is the source of truth" rule: the markdown ledger
is generated from ``@recovered_island`` decorators, so it can never silently
drift.  If this fails after adding/changing an island, run
``python scripts/gen_island_manifest.py``.
"""
from __future__ import annotations

from overkill.recovered.islands import (
    MANIFEST_PATH,
    STATUSES,
    collect_islands,
    render_manifest,
)


def _norm(text: str) -> str:
    return text.replace("\r\n", "\n")


def test_manifest_in_sync_with_code() -> None:
    expected = render_manifest()
    actual = _norm(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert actual == expected, (
        "docs/overkill/recovered_islands.md is stale — run "
        "`python scripts/gen_island_manifest.py`"
    )


def test_every_island_has_valid_metadata() -> None:
    islands = collect_islands()
    assert islands, "no recovered islands discovered — scan packages or decorators broke"
    for modname, name, link in islands:
        assert link.status in STATUSES, f"{modname}.{name}: bad status {link.status!r}"
        assert link.contract.strip(), f"{modname}.{name}: empty contract"
        for boundary in link.asm:
            # boundaries read like SEG:OFF (e.g. 1010:A5D1)
            assert ":" in boundary, f"{modname}.{name}: malformed ASM boundary {boundary!r}"
