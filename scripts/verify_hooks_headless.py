#!/usr/bin/env python3
"""Headless live hook verifier for OVERKILL snapshots.

This is the non-SDL companion to ``scripts/play.py --verify-hooks``.  It loads a
snapshot, installs the differential hook verifier, and steps the runtime until a
verification limit, divergence, or step budget is reached.  It is intentionally
safe to run in CI or minimal shells where pygame/SDL is not installed.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dos_re.input_demo import InputDemoPlayback
from overkill.coverage import CoverageTelemetry, OverkillCoverageClassifier
from overkill.frame_verify import (
    CGA_PRESENT_HOOK,
    EGA_PRESENT_HOOK,
    NON_CGA_INTERACTIVE_DISABLE,
    RETRACE_WAIT_HOOK,
    TANDY_PRESENT_HOOK,
    TIMER_WAIT_HOOK,
)
from overkill.verification import (
    HookVerifierConfig,
    HookVerifyDivergence,
    HookVerifyLimitReached,
    install_hook_verifier,
)
from overkill.runtime import load_overkill_snapshot


def _present_hook_for_mode(mode: int):
    if mode == 1:
        return EGA_PRESENT_HOOK
    if mode == 2:
        return TANDY_PRESENT_HOOK
    return CGA_PRESENT_HOOK


def _parse_addr(text: str) -> tuple[int, int]:
    if ":" not in text:
        raise argparse.ArgumentTypeError("address must be CS:IP, e.g. 1010:58DF")
    cs_text, ip_text = text.split(":", 1)
    try:
        return int(cs_text, 16) & 0xFFFF, int(ip_text, 16) & 0xFFFF
    except ValueError as exc:
        raise argparse.ArgumentTypeError("address must be hexadecimal CS:IP") from exc


def _remove_hook(rt, addr: tuple[int, int]) -> None:
    rt.cpu.replacement_hooks.pop(addr, None)
    rt.cpu.hook_names.pop(addr, None)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Headless differential verification for OVERKILL replacement hooks."
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=None,
        help="snapshot directory created by scripts/play.py; defaults to the demo's start snapshot when --demo is given",
    )
    parser.add_argument(
        "--demo",
        type=Path,
        default=None,
        help="replay a recorded input demo (dir or input_demo.json) while verifying; loads its start snapshot unless --snapshot is also given",
    )
    parser.add_argument(
        "--demo-continue",
        action="store_true",
        help="keep verifying after the input demo ends instead of stopping when it finishes",
    )
    parser.add_argument(
        "--exe",
        type=Path,
        default=ROOT / "assets" / "OVERKILL",
        help="original OVERKILL executable/container path",
    )
    parser.add_argument(
        "--game-root",
        type=Path,
        default=ROOT / "assets",
        help="directory containing original game assets",
    )
    parser.add_argument(
        "--verify-max",
        type=int,
        default=1000,
        help="stop successfully after this many verified hook calls",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=4_000_000,
        help="maximum outer CPU steps before stopping without reaching the verify limit",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=0,
        help="print CPU state every N outer steps; 0 disables progress logging",
    )
    parser.add_argument(
        "--fast-ranges",
        action="store_true",
        help="compare verifier named memory ranges instead of the full memory image",
    )
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="collect coverage telemetry while verifying",
    )
    parser.add_argument(
        "--keep-non-cga-interactive-hooks",
        action="store_true",
        help="keep hooks such as 1010:58DF that need the SDL/play loop outside CGA",
    )
    parser.add_argument(
        "--disable-hook",
        action="append",
        default=[],
        type=_parse_addr,
        metavar="CS:IP",
        help="remove a hook before verification; may be repeated",
    )
    parser.add_argument(
        "--no-nested",
        action="store_true",
        help="legacy/perf mode: do not recursively verify child hooks reached inside a verified parent hook",
    )
    parser.add_argument(
        "--verify-strict",
        action="store_true",
        help=(
            "slow/simple oracle mode: run the Python hook first, use its real "
            "continuation as the ASM target, compare full memory, verify nested "
            "hooks, and stop on the first diff"
        ),
    )
    args = parser.parse_args()

    demo: InputDemoPlayback | None = None
    if args.demo is not None:
        demo = InputDemoPlayback.load(args.demo)
        if args.snapshot is None:
            args.snapshot = demo.snapshot_path()
    if args.snapshot is None:
        parser.error("--snapshot is required unless --demo is given")

    rt = load_overkill_snapshot(args.exe, args.snapshot, game_root=args.game_root)

    if args.coverage:
        rt.cpu.coverage_telemetry = CoverageTelemetry(
            classifier=OverkillCoverageClassifier(ROOT / "symbols.json"),
            enabled=True,
        )
    else:
        rt.cpu.coverage_telemetry = None

    mode = rt.cpu.mem.rw(0x1010, 0x95BC)
    if mode != 0 and not args.keep_non_cga_interactive_hooks:
        for addr in NON_CGA_INTERACTIVE_DISABLE:
            _remove_hook(rt, addr)

    for addr in args.disable_hook:
        _remove_hook(rt, addr)

    if args.verify_strict:
        verifier_config = HookVerifierConfig.strict(
            verify_all=True,
            max_verified=args.verify_max,
            asm_max_steps=1_000_000,
        )
    else:
        verifier_config = HookVerifierConfig(
            verify_all=True,
            max_verified=args.verify_max,
            stop_on_diff=True,
            full_memory=not args.fast_ranges,
            verify_nested_hooks=not args.no_nested,
            asm_max_steps=1_000_000,
        )

    verifier = install_hook_verifier(rt, verifier_config)

    # Frame/timer/retrace boundaries define the demo's replay clock, exactly as
    # in scripts/play.py and the frame verifier.  The verifier already counts
    # each verified hook call on the live runtime (asm-oracle clones never run
    # the verifier), so summing those counts gives a clone-safe boundary index
    # without installing any extra wrapper hooks.
    boundary_keys = (_present_hook_for_mode(mode), TIMER_WAIT_HOOK, RETRACE_WAIT_HOOK)

    def boundary_count() -> int:
        return sum(verifier.counts.get(key, 0) for key in boundary_keys)

    print(
        "hook verify start "
        f"snapshot={args.snapshot} video_mode={mode:04X} "
        f"verify_max={args.verify_max} full_memory={verifier.config.full_memory} "
        f"strict={verifier.config.auto_continuation} "
        f"demo={args.demo if demo is not None else '<none>'}"
    )
    print(rt.cpu.s.snapshot())

    demo_boundary = 0

    try:
        if demo is not None:
            demo.apply_to_runtime(demo_boundary, rt)
        for step in range(1, args.max_steps + 1):
            rt.cpu.step()
            if demo is not None and boundary_count() > demo_boundary:
                demo_boundary = boundary_count()
                if not args.demo_continue and demo.finished(demo_boundary):
                    print(f"OK input demo finished at boundary={demo_boundary} verified={verifier.total_verified}")
                    print(rt.cpu.s.snapshot())
                    return 0
                demo.apply_to_runtime(demo_boundary, rt)
            if args.progress_every and step % args.progress_every == 0:
                print(f"step {step}: boundary={demo_boundary} {rt.cpu.s.snapshot()}")
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
        f"after max_steps={args.max_steps}; last state: {rt.cpu.s.snapshot()}"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
