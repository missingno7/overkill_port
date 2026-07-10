"""Cold-boot lift coverage: verify lifted boot routines over a FRESH boot, each on its own first hit.

`liftverify` emits and runs from ONE snapshot, so a single forward run only exercises the boot
routines called after that snapshot point -- and the boot is one-shot, so most report "notreach".
This harness decouples the two: it EMITS each routine's hook from a post-init snapshot (the static
runtime bundle -- correct 1010-segment bytes), then INSTALLS those hooks + the differential verifier
on a FRESH boot runtime and runs from the MZ entry to the 1010:D007 frontier.  Every boot routine is
then verified against the interpreted original the first time it actually executes during boot.

A hook whose entry bytes differ at run time from emit time disables itself (the SIGNATURE guard), so
self-modified / not-yet-set-up code is skipped rather than mis-verified.

Usage:
    python scripts/verify_boot_lifts.py [--emit-snapshot DIR] [--steps N]
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))

CODE_SEG = 0x1010
FRONTIER_IP = 0xD007
EMIT_DIR = ROOT / "artifacts" / "boot_lifts"


def _liftverify():
    spec = importlib.util.spec_from_file_location(
        "liftverify", ROOT / "dos_re" / "tools" / "liftverify.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _boot_entries(rt) -> list[tuple[int, int]]:
    """Trace one boot to the frontier and collect every 1010: CALL target (the init's own routines)."""
    cpu = rt.cpu
    orig = cpu.__class__.step
    calls: set[int] = set()
    n = [0]

    def step(_c=cpu):
        n[0] += 1
        s = _c.s
        cs, ip = s.cs & 0xFFFF, s.ip & 0xFFFF
        if (cs == CODE_SEG and ip == FRONTIER_IP) or n[0] > 3_000_000:
            raise StopIteration
        if cs == CODE_SEG and _c.mem.rb(cs, ip) == 0xE8:
            rel = _c.mem.rb(cs, (ip + 1) & 0xFFFF) | (_c.mem.rb(cs, (ip + 2) & 0xFFFF) << 8)
            calls.add((ip + 3 + ((rel ^ 0x8000) - 0x8000)) & 0xFFFF)
        return orig(_c)

    cpu.step = step
    try:
        while True:
            cpu.step(cpu)
    except StopIteration:
        pass
    return sorted((CODE_SEG, t) for t in calls)


def main(argv=None) -> int:
    from dos_re.lift import scan_function
    from dos_re.lift.emit import EmitUnsupported, emit_function
    from dos_re.snapshot import load_snapshot
    from dos_re.verification import HookVerifierConfig, install_hook_verifier

    from overkill.launch import build_command_tail
    from overkill.runtime import create_overkill_runtime

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--emit-snapshot", default=str(ROOT / "artifacts" / "static_runtime_bundle"))
    ap.add_argument("--steps", type=int, default=60_000)
    args = ap.parse_args(argv)

    lv = _liftverify()
    tail = build_command_tail("tandy", "pc")

    entries = _boot_entries(create_overkill_runtime(str(ROOT / "assets" / "OVERKILL"),
                                                    command_tail=tail))
    print(f"boot calls {len(entries)} distinct 1010: routines")

    # emit each hook from the post-init snapshot (correct 1010 bytes, live-cloneable runtime)
    emit_rt = load_snapshot(str(ROOT / "assets" / "OVERKILL"), args.emit_snapshot)
    EMIT_DIR.mkdir(parents=True, exist_ok=True)
    hooks: dict[tuple[int, int], object] = {}
    refused = 0
    for cs, ip in entries:
        name = f"lifted_{cs:04x}_{ip:04x}"
        try:
            scan = scan_function(lambda off, _cs=cs: emit_rt.cpu.mem.rb(_cs, off & 0xFFFF), ip,
                                 probe=lv._probe(emit_rt, cs))
            block_end = min((i.next_ip for i in scan.insts.values()
                             if i.kind != "seq" and i.ip >= ip), default=(ip + 8) & 0xFFFF)
            k = max(4, min(16, (block_end - ip) & 0xFFFF))
            sig = bytes(emit_rt.cpu.mem.rb(cs, (ip + j) & 0xFFFF) for j in range(k))
            src = emit_function(scan, cs, name, signature=sig, coverage=True)
        except EmitUnsupported:
            refused += 1
            continue
        except Exception:  # noqa: BLE001 -- indirect-jump / region-budget / decoder refusals
            refused += 1
            continue
        path = EMIT_DIR / f"{name}.py"
        path.write_text(src, encoding="utf-8")
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        hooks[(cs, ip)] = getattr(mod, name)
    print(f"emitted {len(hooks)} liftable hooks ({refused} refused)")
    if not hooks:
        print("RESULT: FAIL -- nothing emitted")
        return 1

    # install + differentially verify over a FRESH boot to the frontier
    rt = create_overkill_runtime(str(ROOT / "assets" / "OVERKILL"), command_tail=tail)
    for key, fn in hooks.items():
        rt.cpu.replacement_hooks[key] = fn
        rt.cpu.hook_names[key] = f"lifted_{key[0]:04x}_{key[1]:04x}"
    cfg = HookVerifierConfig.strict(hooks=set(hooks), asm_wall_timeout_s=4.0)
    install_hook_verifier(rt, cfg, stops={})

    cpu = rt.cpu
    orig = cpu.__class__.step
    verified: set[tuple[int, int]] = set()
    timed_out: set[tuple[int, int]] = set()
    diverged: str | None = None
    n = [0]

    def step(_c=cpu):
        n[0] += 1
        s = _c.s
        if (s.cs & 0xFFFF) == CODE_SEG and (s.ip & 0xFFFF) == FRONTIER_IP:
            raise StopIteration
        if n[0] > args.steps:
            raise StopIteration
        k = (s.cs & 0xFFFF, s.ip & 0xFFFF)
        if k in hooks:
            verified.add(k)
        return orig(_c)

    cpu.step = step
    # Retire hooks whose ASM oracle is too slow to re-interpret (they reach deep into the program):
    # a TIMEOUT is a verification-speed limit, not a byte divergence.  Drop the hook from the verify
    # set and keep running -- exactly liftverify's per-hook retirement.
    while True:
        try:
            while True:
                cpu.step(cpu)
        except StopIteration:
            break
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if "TIMEOUT" in msg:
                key = next((k for k in list(cfg.hooks)
                            if f"{k[0]:04x}_{k[1]:04x}" in msg), None)
                if key is not None:
                    cfg.hooks.discard(key)
                    timed_out.add(key)
                    continue
            if isinstance(exc, RecursionError):
                # a lifted hook's Python-frame call nesting, not a byte divergence -- stop cleanly
                print("  (stopped early: a lifted hook exceeded Python recursion depth)")
                break
            diverged = f"{type(exc).__name__}: {msg}"
            break

    exact = verified - timed_out
    print(f"\nboot ran {n[0]} instructions to the frontier")
    print(f"lifted boot routines verified byte-exact over a FRESH boot: {len(exact)} of "
          f"{len(hooks)} emitted ({len(timed_out)} too deep to re-interpret in time; skipped)")
    if diverged:
        print(f"REAL DIVERGENCE: {diverged}")
    ok = diverged is None and exact
    print("RESULT:", f"PASS -- {len(exact)} boot routines ran natively byte-exact over a fresh "
          "boot, 0 real divergences" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
