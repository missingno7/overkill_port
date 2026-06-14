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

from overkill.coverage import CoverageTelemetry, OverkillCoverageClassifier
from overkill.frame_verify import NON_CGA_INTERACTIVE_DISABLE
from overkill.verification import (
    HookVerifierConfig,
    HookVerifyDivergence,
    HookVerifyLimitReached,
    install_hook_verifier,
)
from overkill.runtime import load_overkill_snapshot


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
        required=True,
        type=Path,
        help="snapshot directory created by scripts/play.py",
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
    args = parser.parse_args()

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

    install_hook_verifier(
        rt,
        HookVerifierConfig(
            verify_all=True,
            max_verified=args.verify_max,
            stop_on_diff=True,
            full_memory=not args.fast_ranges,
            asm_max_steps=1_000_000,
        ),
    )

    print(
        "hook verify start "
        f"snapshot={args.snapshot} video_mode={mode:04X} "
        f"verify_max={args.verify_max} full_memory={not args.fast_ranges}"
    )
    print(rt.cpu.s.snapshot())

    try:
        for step in range(1, args.max_steps + 1):
            rt.cpu.step()
            if args.progress_every and step % args.progress_every == 0:
                print(f"step {step}: {rt.cpu.s.snapshot()}")
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
