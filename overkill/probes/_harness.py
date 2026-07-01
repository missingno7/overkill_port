"""Shared produced-vs-VM probe harness.

Every native-producer probe runs a recorded demo through the frame verifier with
the VM (hooks stripped) as the ``ref`` oracle, tags that side so a step-hook can
read the oracle's state at a chosen ``CS:IP``, predicts the same result with a pure
recovered system, and asserts they agree.  The *scaffolding* for that -- loading
the demo, side-tagging the two runtimes, pumping demo input per frame, and running
the frame verifier with restore-on-exit -- was copy-pasted into all ~19 probes.

This module owns that scaffolding once, so a probe is just its capture/predict/
compare logic (an ``on_ref_step(cpu)`` callback).  It is the single verify
framework the native runtime's coverage gate and per-routine probes share.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

import overkill.frame_verify as fv
from dos_re.cpu import CPU8086
from dos_re.input_demo import InputDemoPlayback
from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier
from overkill.input_waits import pump_demo_frame

ROOT = Path(__file__).resolve().parents[2]


class LazyBytes:
    """Lazy byte ``Sequence`` over a VM ``segment:base`` region.

    Used to feed pure systems (e.g. the tile-plane / class-table inputs) without
    snapshotting whole regions up front.
    """

    def __init__(self, mem, seg: int, base: int, length: int) -> None:
        self._mem, self._seg, self._base, self._length = mem, seg & 0xFFFF, base & 0xFFFF, length

    def __len__(self) -> int:
        return self._length

    def __getitem__(self, index: int) -> int:
        return self._mem.rb(self._seg, (self._base + index) & 0xFFFF)


def load_demo(demo_name: str | None, default_demo: str) -> InputDemoPlayback:
    """Load a recorded demo by name (or ``default_demo`` when ``demo_name`` is falsy)."""
    return InputDemoPlayback.load(ROOT / "artifacts" / "demos" / (demo_name or default_demo))


def run_ref_step_probe(demo: InputDemoPlayback, max_frames: int, on_ref_step: Callable) -> None:
    """Replay ``demo`` through the frame verifier, calling ``on_ref_step(cpu)`` before
    every instruction executed on the ``ref`` (pure-VM oracle) side.

    The probe's callback owns all capture/predict/compare; this owns the verifier
    wiring and restores the patched ``CPU8086.step`` / ``fv._load_runtime`` on exit.
    """
    _run_ref_step_probe(demo, max_frames, on_ref_step, snapshot=str(demo.snapshot_path()))


def run_ref_step_probe_cold_start(demo: InputDemoPlayback, max_frames: int | None, on_ref_step: Callable) -> None:
    """Like :func:`run_ref_step_probe`, but for a COLD-START demo (no snapshot -- boots both
    sides from power-on).  Needed for front-end/menu probes: the recorded gameplay demos never
    exercise the intro/title/menu, only a cold-start session does.  ``max_frames=None`` uses the
    demo's own recorded ``end_boundary`` (+5 slack), matching ``verify_cold_start_demo.py``.

    Frame 1 runs the whole real (uncollapsed) LZEXE self-unpack on the ``ref`` (hooks-stripped)
    side, so this uses the same large ``frame_budget`` that harness needs to let it complete.
    """
    if not demo.is_cold_start:
        raise ValueError("run_ref_step_probe_cold_start requires a cold-start demo (no snapshot)")
    end = demo.end_boundary
    frames = (end + 5) if max_frames is None else max_frames
    _run_ref_step_probe(demo, frames, on_ref_step, snapshot=None, frame_budget=120_000_000)


def _run_ref_step_probe(
    demo: InputDemoPlayback, max_frames: int, on_ref_step: Callable, *, snapshot: str | None, frame_budget: int | None = None
) -> None:
    meta = demo.manifest.get("metadata", {})
    video = str(meta.get("video", "tandy"))
    # A cold-start demo has no snapshot to inherit video/sound state from, so the boot needs the
    # demo's own recorded command tail (matches verify_cold_start_demo.py); a snapshot-based demo
    # already encodes that state in the snapshot, so an empty tail is fine (and always was).
    command_tail = str(meta.get("command_tail", "")) if snapshot is None else b""

    orig_step = CPU8086.step

    def step(self):
        if getattr(self, "_side", "") == "ref":
            on_ref_step(self)
        return orig_step(self)

    CPU8086.step = step
    orig_load = fv._load_runtime
    sides = iter(("ref", "cand"))

    def patched_load(exe, assets, snap, tail):
        rt = orig_load(exe, assets, snap, tail)
        rt.cpu._side = next(sides)
        return rt

    fv._load_runtime = patched_load
    boundary = {"n": 0}

    def pump_inputs(ref_rt, cand_rt):
        boundary["n"], _ = pump_demo_frame(demo, boundary["n"], (ref_rt, cand_rt), ref_rt.cpu)
        boundary["n"] += 1

    kwargs = {} if frame_budget is None else {"frame_budget": frame_budget}
    cfg = FrameVerifyConfig(video=video, source="candidate", max_frames=max_frames,
                            semantic_state_check=False, stop_on_diff=False, log_every=0, **kwargs)
    try:
        run_frame_verifier(exe=ROOT / "assets" / "OVERKILL", assets=ROOT / "assets",
                           snapshot=snapshot, command_tail=command_tail, config=cfg, pump_inputs=pump_inputs)
    finally:
        fv._load_runtime = orig_load
        CPU8086.step = orig_step
