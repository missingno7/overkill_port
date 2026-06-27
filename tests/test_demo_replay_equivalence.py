"""Deterministic demo-replay equivalence: native (hooked) runtime == VM oracle.

This is the standing proof-spine test the source-port plan calls for.  For each
recorded input demo, it replays the same inputs into two runtimes loaded from the
demo's start snapshot:

* the **reference** runs the original 8086 ASM (the generic verifier strips every
  replacement hook except the unavoidable timer/retrace environment waits), and
* the **candidate** keeps all native Python hooks installed.

``run_frame_verifier`` advances both to each frame boundary and asserts they stay
identical on the visible framebuffer, the rendered RGB pixels, *and* the decoded
semantic game state (objects, positions, flags, timers, score).  Any divergence
between the live hooked game and the original is a failure.

By default the suite runs a bounded prefix of each demo so it stays fast enough
for normal runs.  Set ``OVERKILL_FULL_DEMO_VERIFY=1`` to also replay each demo all
the way to its recorded end boundary (minutes per demo; use pytest, not the
fail-safe runner, for those).  ``OVERKILL_DEMO_VERIFY_FRAMES`` overrides the
bounded prefix length.

One zero-argument test function is generated per demo (rather than using
``pytest.mark.parametrize`` with a fixture argument) so this module runs under
both pytest and the pytest-free ``scripts/run_tests.py`` fail-safe runner.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "assets" / "OVERKILL"
ASSETS = ROOT / "assets"
DEMOS_ROOT = ROOT / "artifacts" / "demos"

DEFAULT_BOUNDED_FRAMES = int(os.environ.get("OVERKILL_DEMO_VERIFY_FRAMES", "150"))
RUN_FULL = os.environ.get("OVERKILL_FULL_DEMO_VERIFY") == "1"


def _discover_demos() -> list[Path]:
    if not DEMOS_ROOT.is_dir():
        return []
    return sorted(d for d in DEMOS_ROOT.glob("demo_*") if (d / "input_demo.json").is_file())


DEMOS = _discover_demos()


def _run_demo_equivalence(demo_dir: Path, *, max_frames: int, to_end: bool) -> None:
    # Guard so the pytest-free runner (which ignores skip marks) is still safe
    # in a tree without the original binary or any recorded demo.
    if not EXE.exists() or not demo_dir.is_dir():
        return

    from dos_re.input_demo import InputDemoPlayback
    from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier
    from overkill.input_waits import pump_demo_frame

    demo = InputDemoPlayback.load(demo_dir)
    snapshot = demo.snapshot_path()
    assert snapshot.exists(), f"demo start snapshot missing: {snapshot}"
    video = str(demo.manifest.get("metadata", {}).get("video", "tandy"))

    boundary = {"n": 0}

    def pump_inputs(ref_rt, cand_rt) -> None:
        # Paced-by-consumption in menu keyboard-waits (the original selector runs as
        # raw ASM on both sides), scheduled-by-boundary otherwise.
        boundary["n"], _ = pump_demo_frame(demo, boundary["n"], (ref_rt, cand_rt), ref_rt.cpu)
        boundary["n"] += 1

    stop_requested = None
    if to_end:
        def stop_requested() -> bool:  # noqa: E306 - intentional local closure
            return demo.finished(boundary["n"])

    config = FrameVerifyConfig(
        video=video,
        source="both",
        max_frames=0 if to_end else max_frames,
        semantic_state_check=True,
        stop_on_diff=True,
        log_every=0,
    )

    rc = run_frame_verifier(
        exe=EXE,
        assets=ASSETS,
        snapshot=str(snapshot),
        command_tail=b"",
        config=config,
        pump_inputs=pump_inputs,
        stop_requested=stop_requested,
    )
    assert rc == 0, (
        f"native (hooked) runtime diverged from the VM oracle while replaying "
        f"{demo_dir.name} (see FRAME VERIFY output above)"
    )


def _make_bounded_test(demo_dir: Path):
    # Each factory call captures its own ``demo_dir``; the test takes no
    # arguments so the fail-safe runner (which treats every parameter as a
    # fixture) can call it directly.
    def test() -> None:
        """Bounded prefix: native == VM on framebuffer + RGB + semantic state."""
        _run_demo_equivalence(demo_dir, max_frames=DEFAULT_BOUNDED_FRAMES, to_end=False)

    return pytest.mark.skipif(
        not EXE.exists() or not DEMOS,
        reason="needs assets/OVERKILL and at least one recorded demo under artifacts/demos/",
    )(test)


def _make_full_test(demo_dir: Path):
    def test() -> None:
        """Full demo to its recorded end boundary (opt-in; minutes per demo)."""
        if not RUN_FULL:  # keep the fail-safe runner from running the long path
            return
        _run_demo_equivalence(demo_dir, max_frames=0, to_end=True)

    return pytest.mark.skipif(
        not RUN_FULL,
        reason="set OVERKILL_FULL_DEMO_VERIFY=1 to run full-length demos",
    )(test)


# Generate one zero-argument test per demo so both pytest and the fail-safe
# runner discover and execute them individually.
for _demo in DEMOS:
    globals()[f"test_demo_replay_native_matches_vm_bounded__{_demo.name}"] = _make_bounded_test(_demo)
    globals()[f"test_demo_replay_native_matches_vm_full__{_demo.name}"] = _make_full_test(_demo)
