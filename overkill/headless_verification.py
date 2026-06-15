"""Single headless hook-verification backend used by ``scripts/play.py``.

The public tool is intentionally just ``scripts/play.py``.  This module keeps the
non-SDL verifier loop out of the viewer file without creating a second CLI.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import time

from dos_re.input_demo import InputDemoPlayback
from dos_re.verification import Addr
from overkill.frame_verify import (
    CGA_PRESENT_HOOK,
    EGA_PRESENT_HOOK,
    NON_CGA_INTERACTIVE_DISABLE,
    RETRACE_WAIT_HOOK,
    TANDY_PRESENT_HOOK,
    TIMER_WAIT_HOOK,
)
from overkill.launch import build_command_tail
from overkill.runtime import create_overkill_runtime, load_overkill_snapshot
from overkill.verification import (
    HookVerifierConfig,
    HookVerifyDivergence,
    HookVerifyLimitReached,
    install_hook_verifier,
)


@dataclass(frozen=True)
class HeadlessHookVerifyConfig:
    exe: Path
    game_root: Path
    snapshot: Path | str | None = None
    demo: Path | str | None = None
    demo_continue: bool = False
    video: str = "tandy"
    sound: str = "pc"
    command_tail: bytes | str | None = None
    verify_all: bool = True
    hooks: set[Addr] = field(default_factory=set)
    max_verified: int = 1000
    max_steps: int = 4_000_000


def run_headless_hook_verifier(config: HeadlessHookVerifyConfig) -> int:
    """Run the strict hook oracle without launching SDL.

    This is deliberately slow and simple: every observed hook runs with the
    automatic-continuation full-memory oracle.  There is no legacy/fast mode in
    the public tool surface; focused verification should be trusted before it is
    fast.
    """
    demo: InputDemoPlayback | None = None
    snapshot = config.snapshot
    if config.demo is not None:
        demo = InputDemoPlayback.load(config.demo)
        if snapshot is None:
            snapshot = demo.snapshot_path()

    if snapshot is not None:
        rt = load_overkill_snapshot(config.exe, snapshot, game_root=config.game_root)
    else:
        command_tail = config.command_tail or build_command_tail(config.video, config.sound)
        rt = create_overkill_runtime(config.exe, game_root=config.game_root, command_tail=command_tail)
        rt.dos.text_mode_active = False
    rt.dos.console_input_fallback = None
    rt.cpu.trace_enabled = False
    rt.cpu.coverage_telemetry = None

    mode = rt.cpu.mem.rw(0x1010, 0x95BC)
    if mode not in (0, 1, 2):
        mode = {"cga": 0, "ega": 1, "tandy": 2}.get(config.video, 0)
    if mode != 0:
        for addr in NON_CGA_INTERACTIVE_DISABLE:
            _remove_hook(rt, addr)

    last_progress = {"at": 0.0, "verified": -1, "kind": "", "start": ""}

    def progress(text: str) -> None:
        now = time.monotonic()
        if text.startswith("verified "):
            print(f"HOOK VERIFY {text}", flush=True)
            m = re.match(r"verified (\d+)", text)
            if m:
                last_progress["verified"] = int(m.group(1))
            last_progress["at"] = now
            last_progress["kind"] = "verified"
            return
        m = re.search(r"after verified=(\d+)", text)
        verified = int(m.group(1)) if m else -1
        if verified <= 0:
            return
        if verified % 500 == 0 and (
            verified != last_progress["verified"]
            or last_progress["kind"] == "verified"
            or text != last_progress["start"]
        ):
            print(f"HOOK VERIFY {text}", flush=True)
            last_progress["verified"] = verified
            last_progress["at"] = now
            last_progress["kind"] = "verifying"
            last_progress["start"] = text
            return
        if now - last_progress["at"] >= 10.0:
            print(f"HOOK VERIFY {text}", flush=True)
            last_progress["verified"] = verified
            last_progress["at"] = now
            last_progress["kind"] = "verifying"
            last_progress["start"] = text

    verifier = install_hook_verifier(
        rt,
        HookVerifierConfig.strict(
            verify_all=config.verify_all,
            hooks=set(config.hooks),
            max_verified=config.max_verified,
            asm_max_steps=1_000_000,
            progress_callback=progress,
        ),
    )

    boundary_keys = (_present_hook_for_mode(mode), TIMER_WAIT_HOOK, RETRACE_WAIT_HOOK)

    def boundary_count() -> int:
        return sum(verifier.counts.get(key, 0) for key in boundary_keys)

    hook_label = "all" if config.verify_all else ",".join(f"{cs:04X}:{ip:04X}" for cs, ip in sorted(config.hooks))
    print(
        "HOOK VERIFY start "
        f"snapshot={snapshot or '<fresh>'} video_mode={mode:04X} "
        f"hooks={hook_label or '<none>'} verify_max={config.max_verified} "
        f"strict=True full_memory=True demo={config.demo if demo is not None else '<none>'}",
        flush=True,
    )
    print(rt.cpu.s.snapshot())

    demo_boundary = 0

    try:
        if demo is not None:
            demo.apply_to_runtime(demo_boundary, rt)
        for step in range(1, config.max_steps + 1):
            rt.cpu.step()
            if demo is not None and boundary_count() > demo_boundary:
                demo_boundary = boundary_count()
                if not config.demo_continue and demo.finished(demo_boundary):
                    print(f"OK input demo finished at boundary={demo_boundary} verified={verifier.total_verified}")
                    print(rt.cpu.s.snapshot())
                    return 0
                demo.apply_to_runtime(demo_boundary, rt)
    except HookVerifyLimitReached as exc:
        print(f"OK {exc}")
        print(rt.cpu.s.snapshot())
        return 0
    except HookVerifyDivergence as exc:
        print("HOOK VERIFY DIVERGENCE")
        print(exc)
        print(rt.cpu.s.snapshot())
        return 1

    print(
        "VERIFY LIMIT NOT REACHED "
        f"after max_steps={config.max_steps}; verified={verifier.total_verified}; "
        f"last state: {rt.cpu.s.snapshot()}"
    )
    return 2


def _present_hook_for_mode(mode: int) -> Addr:
    if mode == 1:
        return EGA_PRESENT_HOOK
    if mode == 2:
        return TANDY_PRESENT_HOOK
    return CGA_PRESENT_HOOK


def _remove_hook(rt, addr: Addr) -> None:
    rt.cpu.replacement_hooks.pop(addr, None)
    rt.cpu.hook_names.pop(addr, None)
