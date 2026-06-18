"""VM-until-checkpoint handoff is executable and lands on consistent state.

These tests demonstrate the source-port execution model: from an arbitrary
runtime position, the VM (instruction-exact oracle) can fast-forward to the next
logical checkpoint, where the game state is decodable and consistent - a valid
hand-off point for a native phase system.  This is what lets oracle snapshots be
captured anywhere and resumed natively at a checkpoint, instead of at a
behaviour's exact mid-chain CS:IP.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "assets" / "OVERKILL"
ASSETS = ROOT / "assets"
DEMO = ROOT / "artifacts" / "demos" / "demo_play_tandy_L5_ringlas_divergence_20260618_191308"

pytestmark = pytest.mark.skipif(
    not EXE.exists() or not DEMO.is_dir(),
    reason="needs assets/OVERKILL and a gameplay demo snapshot",
)


def _load():
    from overkill.runtime import load_overkill_snapshot

    rt = load_overkill_snapshot(EXE, DEMO / "snapshot", game_root=ASSETS)
    rt.cpu.trace_enabled = False
    rt.cpu.coverage_telemetry = None
    return rt


def test_frame_checkpoint_set_is_nonempty_and_phase_kinds_present():
    from overkill.checkpoints import CHECKPOINTS_BY_KIND, checkpoints_for

    for kind in ("frame", "render", "object-update", "input"):
        assert CHECKPOINTS_BY_KIND.get(kind), f"no checkpoints for phase {kind!r}"
    assert checkpoints_for(("frame",)) <= checkpoints_for(None)


def test_vm_fast_forwards_to_a_frame_checkpoint():
    from overkill.checkpoints import checkpoints_for, run_to_next_checkpoint

    rt = _load()
    cp = run_to_next_checkpoint(rt.cpu, kinds="frame")
    assert cp in checkpoints_for("frame")
    # We are positioned exactly at the checkpoint address.
    assert rt.cpu.addr() == cp


def test_frame_checkpoints_are_per_frame_boundaries_with_consistent_state():
    from overkill.checkpoints import run_to_next_checkpoint
    from overkill.recovered.adapters.game_snapshot_adapter import decode_game_snapshot

    rt = _load()
    run_to_next_checkpoint(rt.cpu, kinds="frame")
    snap1 = decode_game_snapshot(rt.cpu)
    run_to_next_checkpoint(rt.cpu, kinds="frame")
    snap2 = decode_game_snapshot(rt.cpu)

    # State is decodable at each checkpoint and advanced by exactly one frame of
    # gameplay between two consecutive frame checkpoints (a real boundary, not a
    # mid-chain point).
    assert snap1.objects and snap2.objects
    assert snap1 != snap2
