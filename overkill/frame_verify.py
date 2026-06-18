"""OVERKILL-specific adapter for reusable DOS frame verification.

The generic verifier lives in :mod:`dos_re.frame_verify`.  This module only
knows OVERKILL-specific facts: frame boundary addresses, video memory layout,
command-line runtime loading, and how to render the game's CGA/EGA/Tandy frame
buffers into RGB samples.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from dos_re.frame_verify import (
    Addr,
    FrameSample,
    FrameVerifyConfig as GenericFrameVerifyConfig,
    FrameVerifyDivergence,
    make_frame_sample,
    run_frame_verifier as run_generic_frame_verifier,
)
from dos_re.memory import EGA_APERTURE, EGA_PLANE_STRIDE
from dos_re.runtime import Runtime
from .input_waits import frame_verify_input_wait
from .recovered.adapters.game_snapshot_adapter import decode_game_snapshot
from .recovered.domain.game_snapshot import diff_game_snapshot, format_divergence_report
from .runtime import create_overkill_runtime, load_overkill_snapshot

CGA_PRESENT_HOOK: Addr = (0x1010, 0x447B)
EGA_PRESENT_HOOK: Addr = (0x1010, 0x2750)
TANDY_PRESENT_HOOK: Addr = (0x1010, 0x3354)
TIMER_WAIT_HOOK: Addr = (0x1010, 0x0679)
RETRACE_WAIT_HOOK: Addr = (0x1010, 0x50C9)

B800_BASE = 0xB8000
B800_CGA_SIZE = 0x4000
B800_TANDY_SIZE = 0x8000
EGA_BYTES_PER_ROW = 40
WIDTH = 320
HEIGHT = 200

# Hardware/environment wait hooks that must remain hooked even in the reference
# runtime.  The interpreter has no asynchronous PIT/IRQ0 or real VGA retrace, so
# the original busy-wait ASM at these addresses can otherwise spin forever.  The
# verifier still compares everything around those waits at the next boundary.
REFERENCE_ENV_HOOKS: set[Addr] = {TIMER_WAIT_HOOK, RETRACE_WAIT_HOOK}

# Mirrors scripts/play.py: this lifted loop is only validated for CGA mode.
NON_CGA_INTERACTIVE_DISABLE: set[Addr] = {(0x1010, 0x58DF)}


@dataclass(frozen=True)
class FrameVerifyConfig(GenericFrameVerifyConfig):
    video: Literal["cga", "ega", "tandy"] = "tandy"
    palette: str = "1h"
    ega_start_address_units: Literal["byte", "word", "ignore"] = "byte"
    # Decode the running game's gameplay state each frame and diff the ASM-oracle
    # runtime against the hooked runtime at the *semantic* level (objects,
    # positions, flags, timers, score) -- catching divergences a pixel diff can
    # miss.  On by default so frame verification covers state, not just frames.
    semantic_state_check: bool = True


class SemanticFrameComparator:
    """Per-frame semantic state diff between the reference and candidate runtimes.

    ``_sample`` calls :meth:`observe` for the reference then the candidate at the
    same frame boundary; this decodes each into a recovered ``GameSnapshot`` and,
    once both sides of a frame are seen, diffs them.  The first divergence is
    reported loudly (a field-level report, not pixels); the run records that it
    diverged so the verifier can exit non-zero.
    """

    def __init__(self, status_callback: Callable[[str], None] | None = None) -> None:
        self._reference: dict[int, object] = {}
        self._status = status_callback
        self.divergence_frames = 0
        self.first_report: str | None = None

    def observe(self, cpu, side: str, frame_no: int) -> None:
        snapshot = decode_game_snapshot(cpu)
        if side == "reference":
            self._reference[frame_no] = snapshot
            return
        reference = self._reference.pop(frame_no, None)
        if reference is None:
            return
        divergences = diff_game_snapshot(reference, snapshot)
        if not divergences:
            return
        self.divergence_frames += 1
        if self.first_report is None:
            self.first_report = format_divergence_report(divergences)
            print(
                f"FRAME VERIFY SEMANTIC DIVERGENCE at frame {frame_no} "
                f"(decoded gameplay state differs between ASM oracle and hooked runtime):\n"
                f"{self.first_report}",
                flush=True,
            )
            if self._status is not None:
                self._status(f"semantic state divergence at frame {frame_no}")


def run_frame_verifier(
    *,
    exe: Path,
    assets: Path,
    snapshot: str | None,
    command_tail: bytes | str,
    config: FrameVerifyConfig,
    publish_candidate: Callable[[Runtime, FrameSample], None] | None = None,
    pump_inputs: Callable[[Runtime, Runtime], None] | None = None,
    on_divergence: Callable[[Runtime, Runtime, FrameSample, FrameSample, str], None] | None = None,
    stop_requested: Callable[[], bool] | None = None,
    status_callback: Callable[[str], None] | None = None,
) -> int:
    """Run the OVERKILL frame verifier using the generic DOS verifier engine."""
    ref = _load_runtime(exe, assets, snapshot, command_tail)
    cand = _load_runtime(exe, assets, snapshot, command_tail)

    print(
        f"FRAME VERIFY start video={config.video} source={config.source} "
        f"max_frames={config.max_frames} snapshot={snapshot or '<fresh>'} "
        f"semantic_state_check={config.semantic_state_check}",
        flush=True,
    )

    semantic = SemanticFrameComparator(status_callback) if config.semantic_state_check else None

    result = run_generic_frame_verifier(
        reference=ref,
        candidate=cand,
        config=config,
        boundary_hooks=_boundary_hooks(config),
        sample_builder=lambda rt, side, frame_no, kind, hook, boundary_steps, start, recent, recent_changes: _sample(
            rt, config, side, frame_no, kind, hook, boundary_steps, start, recent, recent_changes, semantic
        ),
        reference_env_hooks=REFERENCE_ENV_HOOKS,
        trace_sample=(lambda rt: _visible_vram(rt, config)) if config.trace_sample_changes else None,
        trace_sample_label="raw",
        disabled_hooks=NON_CGA_INTERACTIVE_DISABLE if config.video != "cga" else frozenset(),
        after_boundary=_after_boundary,
        publish_candidate=publish_candidate,
        pump_inputs=pump_inputs,
        on_divergence=on_divergence,
        input_wait_detector=frame_verify_input_wait,
        stop_requested=stop_requested,
        status_callback=status_callback,
        label="FRAME VERIFY",
    )

    if semantic is not None and semantic.divergence_frames:
        print(
            f"FRAME VERIFY semantic state diverged on {semantic.divergence_frames} frame(s)",
            flush=True,
        )
        return result or 1
    return result


def _load_runtime(exe: Path, assets: Path, snapshot: str | None, command_tail: bytes | str) -> Runtime:
    if snapshot:
        return load_overkill_snapshot(exe, snapshot, game_root=assets)
    return create_overkill_runtime(exe, game_root=assets, command_tail=command_tail)


def _boundary_hooks(config: FrameVerifyConfig) -> tuple[tuple[Addr, str], ...]:
    return (
        (_present_hook(config), "present"),
        (TIMER_WAIT_HOOK, "timer"),
        (RETRACE_WAIT_HOOK, "retrace"),
    )


def _present_hook(config: FrameVerifyConfig) -> Addr:
    if config.video == "ega":
        return EGA_PRESENT_HOOK
    if config.video == "tandy":
        return TANDY_PRESENT_HOOK
    return CGA_PRESENT_HOOK


def _after_boundary(rt: Runtime, kind: str, _hook: Addr) -> None:
    if kind == "present":
        rt.dos.text_mode_active = False


def _sample(
    rt: Runtime,
    config: FrameVerifyConfig,
    side: str,
    frame_no: int,
    kind: str,
    hook: Addr,
    boundary_steps: int,
    start_count: int,
    recent_hooks: tuple[str, ...],
    recent_sample_changes: tuple[str, ...] = (),
    semantic: "SemanticFrameComparator | None" = None,
) -> FrameSample:
    if semantic is not None:
        semantic.observe(rt.cpu, side, frame_no)
    raw = _visible_vram(rt, config)
    rgb = _render_rgb_bytes(rt, config)
    return make_frame_sample(
        rt=rt,
        side=side,
        frame_no=frame_no,
        kind=kind,
        hook=hook,
        boundary_steps=boundary_steps,
        start_count=start_count,
        recent_hooks=recent_hooks,
        recent_sample_changes=recent_sample_changes,
        raw=raw,
        rgb=rgb,
        display_start=_display_start(rt, config),
        width=WIDTH,
        height=HEIGHT,
        context=config.video,
    )


def _display_start(rt: Runtime, config: FrameVerifyConfig) -> int:
    raw_start = rt.program.memory.ega_display_start & 0xFFFF
    if config.video != "ega":
        return 0
    if config.ega_start_address_units == "ignore":
        return 0
    if config.ega_start_address_units == "word":
        return (raw_start << 1) & 0xFFFF
    return raw_start


def _visible_vram(rt: Runtime, config: FrameVerifyConfig) -> bytes:
    data = rt.program.memory.data
    if config.video == "tandy":
        return bytes(data[B800_BASE:B800_BASE + B800_TANDY_SIZE])
    if config.video == "cga":
        return bytes(data[B800_BASE:B800_BASE + B800_CGA_SIZE])

    # Normalize the EGA visible window from the active CRTC display start rather
    # than comparing the entire shadow store, which includes off-screen pages.
    start = _display_start(rt, config)
    out = bytearray()
    for plane in range(4):
        plane_base = EGA_APERTURE + plane * EGA_PLANE_STRIDE
        for y in range(HEIGHT):
            row = (start + y * EGA_BYTES_PER_ROW) & 0xFFFF
            if row <= 0x10000 - EGA_BYTES_PER_ROW:
                out += data[plane_base + row:plane_base + row + EGA_BYTES_PER_ROW]
            else:
                tail = 0x10000 - row
                out += data[plane_base + row:plane_base + 0x10000]
                out += data[plane_base:plane_base + (EGA_BYTES_PER_ROW - tail)]
    return bytes(out)


def _render_rgb_bytes(rt: Runtime, config: FrameVerifyConfig) -> bytes:
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from render_frame import render_ega_ppm, render_ppm, render_tandy_ppm

    mem = bytes(rt.program.memory.data)
    if config.video == "tandy":
        ppm = render_tandy_ppm(mem, 0xB800, 1)[2]
    elif config.video == "ega":
        ppm = render_ega_ppm(mem, 0xA000, 1, _display_start(rt, config))[2]
    else:
        ppm = render_ppm(mem, 0xB800, config.palette, 1)[2]
    return ppm.split(b"255\n", 1)[1]
