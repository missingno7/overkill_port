from __future__ import annotations

import json
from pathlib import Path

from overkill_port.games.overkill.bootstrap_boundary import (
    bootstrap_boundary_manifest,
    write_bootstrap_boundary_manifest,
)


def test_static_runtime_boundary_marks_only_original_assets_as_canonical_inputs():
    manifest = bootstrap_boundary_manifest(video="tandy", sound="adlib")

    assert manifest["original_inputs"] == ("assets/OVERKILL", "assets/OVERKILL.EXE")
    assert "assets/OVERKILL.UNLZEXE.EXE" in manifest["generated_noncanonical_inputs"]
    assert "assets/OVERKILL.OVERLAY.BIN" in manifest["generated_noncanonical_inputs"]
    assert manifest["command_tail_hex"] == "0D 02 41"
    assert "not target gameplay source" in manifest["source_port_rule"]


def test_static_runtime_boundary_records_known_inner_runtime_frontiers():
    manifest = bootstrap_boundary_manifest()

    assert manifest["first_inner_transfer"]["addr"] == "1010:95C9"
    entries = {item["addr"]: item for item in manifest["canonical_runtime_entries"]}
    assert entries["1010:D007"]["role"] == "current high-level game/frame orchestration frontier"
    assert "EDRAX" in entries["1010:D445"]["notes"]
    assert any("32FF:*" in item for item in manifest["bootstrap_islands"])


def test_write_static_runtime_boundary_manifest_is_json(tmp_path: Path):
    out = tmp_path / "boundary.json"

    write_bootstrap_boundary_manifest(out, video="ega", sound="roland")

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema"] == "overkill.static_runtime_boundary.v1"
    assert payload["video"] == "ega"
    assert payload["sound"] == "roland"
    assert payload["command_tail_hex"] == "0D 01 52"
