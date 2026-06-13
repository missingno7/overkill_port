from __future__ import annotations

import argparse
from pathlib import Path

from .cpu import HaltExecution, UnsupportedInstruction
from .hook_verify import HookVerifierConfig, install_hook_verifier, parse_addr as parse_verify_addr
from .runtime import create_runtime
from .snapshot import parse_addr, run_until, write_snapshot, load_snapshot


def add_verify_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--verify-hooks", action="store_true", help="differentially verify all hooks at hook boundaries")
    p.add_argument("--verify-hook", action="append", default=[], help="differentially verify one hook address; may be repeated")
    p.add_argument("--verify-max", type=int, default=None, help="stop verifying after N hook calls")
    p.add_argument("--verify-stop-on-diff", action="store_true", help="raise on the first hook divergence")
    p.add_argument("--verify-log-diffs", action="store_true", help="print detailed hook divergence reports and continue")
    p.add_argument("--verify-full-memory", action="store_true", help="deprecated compatibility flag; full memory is now the default")
    p.add_argument("--verify-fast-ranges", action="store_true", help="debug/perf only: compare named memory ranges instead of the full memory image")
    p.add_argument("--verify-require-metadata", action="store_true", help="fail instead of silently skipping a hook that has no verifier continuation metadata")


def maybe_install_verifier(rt, args: argparse.Namespace) -> None:
    if not getattr(args, "verify_hooks", False) and not getattr(args, "verify_hook", []):
        return
    hooks = {parse_verify_addr(text) for text in args.verify_hook}
    config = HookVerifierConfig(
        verify_all=args.verify_hooks,
        hooks=hooks,
        max_verified=args.verify_max,
        stop_on_diff=args.verify_stop_on_diff,
        log_diffs=args.verify_log_diffs,
        full_memory=args.verify_full_memory or not args.verify_fast_ranges,
        require_metadata=args.verify_require_metadata,
    )
    install_hook_verifier(rt, config)


def cmd_info(args: argparse.Namespace) -> int:
    from .mz import parse_mz
    exe = parse_mz(args.exe)
    h = exe.header
    print(f"path: {exe.path}")
    print(f"load module: {len(exe.load_module)} bytes")
    print(f"overlay: {len(exe.overlay)} bytes")
    print(f"entry CS:IP: {h.cs:04X}:{h.ip:04X}")
    print(f"stack SS:SP: {h.ss:04X}:{h.sp:04X}")
    print(f"relocations: {len(exe.relocations)}")
    print(f"min/max extra paragraphs: {h.min_extra_paragraphs}/{h.max_extra_paragraphs}")
    return 0


def cmd_trace(args: argparse.Namespace) -> int:
    rt = create_runtime(args.exe, game_root=args.game_root)
    maybe_install_verifier(rt, args)
    out = Path(args.out) if args.out else None
    try:
        rt.cpu.run(args.steps)
        status = f"stopped after {args.steps} steps"
    except HaltExecution:
        status = "program halted"
    except UnsupportedInstruction as e:
        status = f"unsupported instruction: {e}"
    except Exception as e:
        status = f"exception: {type(e).__name__}: {e}"
    lines = [status, rt.cpu.s.snapshot(), "", *rt.cpu.trace]
    text = "\n".join(lines) + "\n"
    if out:
        out.write_text(text, encoding="utf-8")
        print(f"wrote {out}")
    else:
        print(text)
    if rt.dos.stdout:
        print("--- DOS stdout ---")
        print("".join(rt.dos.stdout))
    return 0



def cmd_snapshot(args: argparse.Namespace) -> int:
    rt = create_runtime(args.exe, game_root=args.game_root)
    maybe_install_verifier(rt, args)
    stop_at = parse_addr(args.stop_at) if args.stop_at else None
    status, steps, tail = run_until(rt, max_steps=args.steps, stop_at=stop_at, trace_tail=args.trace_tail)
    write_snapshot(rt, args.out_dir, status=status, steps=steps, trace_tail=tail)
    print(f"{status}; steps={steps}; wrote {args.out_dir}")
    print(rt.cpu.s.snapshot())
    return 0


def cmd_continue_snapshot(args: argparse.Namespace) -> int:
    rt = load_snapshot(args.exe, args.snapshot_dir, game_root=args.game_root)
    maybe_install_verifier(rt, args)
    stop_at = parse_addr(args.stop_at) if args.stop_at else None
    status, steps, tail = run_until(rt, max_steps=args.steps, stop_at=stop_at, trace_tail=args.trace_tail)
    write_snapshot(rt, args.out_dir, status=status, steps=steps, trace_tail=tail)
    print(f"{status}; continued_steps={steps}; wrote {args.out_dir}")
    print(rt.cpu.s.snapshot())
    return 0

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="overkill-port", description="OVERKILL-specific DOS interpreter/source-port scaffold")
    sub = p.add_subparsers(required=True)
    i = sub.add_parser("info", help="print MZ metadata")
    i.add_argument("exe")
    i.set_defaults(func=cmd_info)
    t = sub.add_parser("trace", help="execute and trace original DOS code")
    t.add_argument("exe")
    t.add_argument("--game-root", default=None)
    t.add_argument("--steps", type=int, default=1000)
    t.add_argument("--out", default=None)
    add_verify_args(t)
    t.set_defaults(func=cmd_trace)

    snap = sub.add_parser("snapshot", help="run and dump full 1MB memory image plus JSON state")
    snap.add_argument("exe")
    snap.add_argument("--game-root", default=None)
    snap.add_argument("--steps", type=int, default=100000)
    snap.add_argument("--stop-at", default=None, help="optional CS:IP hex stop address, e.g. 1010:45CB")
    snap.add_argument("--trace-tail", type=int, default=0, help="keep only the last N trace lines")
    snap.add_argument("--out-dir", default="artifacts/snapshot")
    add_verify_args(snap)
    snap.set_defaults(func=cmd_snapshot)

    cont = sub.add_parser("continue-snapshot", help="resume execution from a saved snapshot and write a new snapshot")
    cont.add_argument("exe")
    cont.add_argument("snapshot_dir")
    cont.add_argument("--game-root", default=None)
    cont.add_argument("--steps", type=int, default=100000)
    cont.add_argument("--stop-at", default=None, help="optional CS:IP hex stop address, e.g. 1010:45CB")
    cont.add_argument("--trace-tail", type=int, default=0)
    cont.add_argument("--out-dir", default="artifacts/evidence/snapshot_continued")
    add_verify_args(cont)
    cont.set_defaults(func=cmd_continue_snapshot)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
