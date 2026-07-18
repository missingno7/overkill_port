"""verify_cpuless_coldstart.py -- FRAME-INDEXED proof that the no-CPU corpus reproduces the game.

This is OVERKILL's first cold-start CPUless differential.  Both machines start from the SAME cold
image at the SAME address and are then run INDEPENDENTLY for the whole run; their per-frame observable
is compared.  It is the CPUless analogue of the demo-lockstep gate, and the analogue of skyroads'
`verify_cpuless.py`.

WHAT MAKES THIS DIFFERENT FROM THE PORT'S EXISTING GATES, and why it had to be built
------------------------------------------------------------------------------------
`overkill/probes/verify_native_lockstep.py` and `frame_verify.py` RE-SEED the candidate from the
oracle's state at every frame boundary.  That is the right instrument for growing one frame function,
but it structurally cannot see CROSS-FRAME DRIFT: an error introduced in frame N is erased before
frame N+1 starts, so a corpus that is wrong in a way that only compounds still passes every frame.
Here the candidate ENTERS ITS ROOT ONCE and runs the entire session; nothing is ever copied into it.
Divergence therefore accumulates exactly as it would in the shipped runner.

THE FRAME MODEL -- shared with the shipped runner, not re-implemented
---------------------------------------------------------------------
The candidate is driven by `overkill.cpuless_driver.CPUlessFrameDriver`, the SAME object
`coldboot_frontier.py` uses: park on the 2nd pass at a declared boundary head (`1010:0679`, the timer
tick wait), present the finished frame, then deliver that frame's timer IRQs through the game's own
recovered IRQ0 ISR `1010:06E5`.  A differential that proved a DIFFERENT model than the one that ships
would prove nothing about the shipped runner.  The oracle mirrors the same cut: 2 IRQ0 interrupts,
then run until `1010:0679` is reached the 2nd time.

THE ORACLE IS PROVEN PURE, NOT ASSUMED PURE
--------------------------------------------
`assert_pure_oracle` raises with the offenders named.  This is not ceremony: skyroads spent an entire
campaign localizing a "frontier" inside its candidate that turned out to be its ORACLE deviating from
the original program -- 29 replacements live on a supposedly pure-ASM reference, including a
deliberately behaviour-changing loop-skip.  A contaminated oracle does not fail; it reports a
plausible wrong answer.  OVERKILL has had no purity assertion at all: `overkill/frame_verify.py:54`
permanently allows three env hooks with nothing checking that they are the ONLY ones.

Usage:
    python scripts/verify_cpuless_coldstart.py                       # the default cold front-end
    python scripts/verify_cpuless_coldstart.py --frames 300

NOT YET: demo INPUT replay.  The two 2026-07-18 demos start at `1010:58F4`, which is not an entry
point at all -- it is the `pop cx` immediately after the `call 50C9` retrace wait inside
`func_1010_58df`, i.e. a mid-function RESUME.  The CPUless corpus has no resume entries (a recovered
function is entered at its entry, and `1010:58F4` is block 2 of that function), so the candidate
cannot be started where those demos were recorded, and their boundary indices are keyed to a start the
candidate cannot reproduce.  The attract demo carries ZERO input events, so the run below covers
exactly what it covers without needing them; the spine demo's 24 events need an input path that is
frame-aligned to THIS start, which is the next slice.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))

from dos_re.hooks import assert_pure_oracle  # noqa: E402
from dos_re.hooks import registry as hook_registry  # noqa: E402
from dos_re.interrupts import deliver_interrupt  # noqa: E402
from dos_re.lift.platform import CPUlessPlatformRuntime  # noqa: E402
from dos_re.x86 import HaltExecution  # noqa: E402

#: The cold image BOTH sides start from, and the address it is parked at.  Its own state.json records
#: `cs=0x1010 ip=0x96C8 steps=0`, so this is the recorded start state read back -- not a chosen one.
#: `1010:96C8` is the game's top level (front-end -> level select -> gameplay).
COLD_SNAPSHOT = ROOT / "artifacts" / "frontend_intro_snapshot"
ROOT_KEY = "1010:96C8"

#: The declared boundary head the frame is cut at (artifacts/lift_boundary_heads.txt).
HEAD = (0x1010, 0x0679)

#: THE OBSERVABLE.  OVERKILL on Tandy runs 320x200x16 out of a 32KB window at B800 with hardware
#: page flipping, so the displayed frame is NOT determined by the pixel bytes alone -- the CRTC
#: start-address pair (regs 0x0C/0x0D) selects which half is on screen.  Comparing the bytes without
#: the CRTC state would miss a page-flip divergence entirely (both pages present, wrong one shown);
#: comparing the CRTC without the bytes would miss everything else.  Both are compared.
#: There is no DAC to compare: Tandy's 16 colours are fixed hardware, unlike the VGA palette
#: skyroads' differential diffs.  Its analogue is the 3D8h/3D9h mode + colour-select register pair,
#: which is captured from the port stream (see `_PortTap`) because it has no memory-resident form.
B800 = 0xB8000
B800_TANDY_LEN = 0x8000
VIDEO_PORTS = range(0x3D0, 0x3E0)


class _PortTap:
    """Record the last value written to each 3Dx video register.

    Both sides reach the SAME `DOSMachine.port_write` -- the candidate through `plat.outp`, the
    oracle through the CPU's OUT -- so wrapping it is symmetric by construction and cannot favour
    either side.  These registers are write-only hardware with no memory-resident form, so a
    divergence in them (wrong video mode, wrong border/background colour) is invisible in the frame
    buffer and would otherwise be silently unproven.
    """

    def __init__(self, dos):
        self.regs: dict[int, int] = {}
        self._inner = dos.port_write
        dos.port_write = self._write

    def _write(self, cpu, port, value, bits):
        p = port & 0xFFFF
        if p in VIDEO_PORTS:
            self.regs[p] = value & 0xFF
            if bits == 16:                       # a word OUT writes index+data
                self.regs[p + 1] = (value >> 8) & 0xFF
        return self._inner(cpu, port, value, bits)

    def sample(self):
        return tuple(sorted(self.regs.items()))


def _crtc(dos):
    """The CRTC register file, which owns the displayed page (start address 0x0C/0x0D)."""
    return tuple(sorted(getattr(dos, "_crtc_regs", {}).items()))


def _observe(mem_data, dos, tap):
    return (bytes(mem_data[B800:B800 + B800_TANDY_LEN]), _crtc(dos), tap.sample())


# ---------------------------------------------------------------------------------------------------
# The ORACLE: the interpreted original.
# ---------------------------------------------------------------------------------------------------

def _capture_oracle(frames, irqs, step_budget):
    from overkill.runtime import load_overkill_snapshot

    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", COLD_SNAPSHOT,
                                game_root=ROOT / "assets")
    # POST-BOOT STRIP.  Loading a snapshot installs OVERKILL's whole hook registry (measured: 337
    # replacements live), so the reference would otherwise be a heavily modified original.  Guarding
    # the hooks IMPORT does not work -- the registry is populated at decoration time and install()
    # wires it on regardless -- which is exactly how skyroads' oracle stayed contaminated.
    hook_registry.uninstall(rt.cpu)
    # PROVE the reference side is the original program.  `allow` is EMPTY on purpose, and that is a
    # stronger claim than it looks: OVERKILL's other harnesses keep the timer (1010:0679), retrace
    # (1010:50C9) and sound-active (1010:9921) waits hooked even on their reference side, because an
    # interpreter with no asynchronous PIT would spin in them forever.  This harness does not need
    # that crutch -- it DELIVERS real INT 08h interrupts each frame, so the game's own ISR sets the
    # tick flag and its own wait loops terminate on their own code.  Every hook allowed here would be
    # a place the reference is not the original program.
    assert_pure_oracle(rt.cpu, allow=frozenset())

    cpu = rt.cpu
    cpu.trace_enabled = False
    tap = _PortTap(rt.dos)
    peak = 0
    out = []

    def run_to_cut(frame):
        """Run to this frame's cut, or FAIL LOUD.

        Exhausting the budget without reaching the cut must never return quietly: that leaves the
        oracle parked mid-frame -- a TRUNCATED reference that still looks authoritative -- so every
        later frame blames the candidate for the oracle's own truncation.  (skyroads' equivalent did
        exactly this and produced a confidently wrong frontier.)
        """
        nonlocal peak
        hits = 0
        for used in range(step_budget):
            if (cpu.s.cs, cpu.s.ip) == HEAD:
                hits += 1
                if hits >= 2:
                    cpu.step()
                    peak = max(peak, used)
                    return
            cpu.step()
        raise RuntimeError(
            f"oracle step budget exhausted at frame {frame}: {step_budget} steps without reaching "
            f"{HEAD[0]:04X}:{HEAD[1]:04X} twice (cs:ip={cpu.s.cs:04X}:{cpu.s.ip:04X}).  The oracle "
            f"is parked mid-frame; every comparison from here would blame the candidate for the "
            f"oracle's truncation.  Raise --step-budget.")

    for frame in range(frames):
        for _ in range(irqs):
            deliver_interrupt(rt, 0x08)
        try:
            run_to_cut(frame)
        except HaltExecution:
            print(f"[coldstart] oracle terminated (int 21/4C) after {frame} frames")
            break
        out.append(_observe(cpu.mem.data, rt.dos, tap))
        if frame % 100 == 0:
            print(f"  oracle frame {frame:5d}", flush=True)
    print(f"[coldstart] oracle peak {peak} steps/frame (budget {step_budget})")
    return out


# ---------------------------------------------------------------------------------------------------
# The CANDIDATE: the no-CPU corpus, entered ONCE.
# ---------------------------------------------------------------------------------------------------

class _Stop(Exception):
    pass


def _capture_candidate(frames, irqs):
    from overkill.cpuless_driver import CPUlessFrameDriver
    from overkill.cpuless_host import run_deep, run_recovered
    from overkill.recovered.adapters.flat_memory import MutFlatMemory

    img = MutFlatMemory((COLD_SNAPSHOT / "memory_1mb.bin").read_bytes())
    regs0 = json.loads((COLD_SNAPSHOT / "state.json").read_text(encoding="utf-8"))["cpu"]
    plat = CPUlessPlatformRuntime(img, ROOT / "assets")
    tap = _PortTap(plat.dos)

    out = []

    def present(frame):
        out.append(_observe(img.data, plat.dos, tap))
        if frame % 100 == 0:
            print(f"  candidate frame {frame:5d}", flush=True)
        if frame + 1 >= frames:
            raise _Stop()

    from overkill.cpuless_recovered.func_1010_06e5 import func_1010_06e5   # the game's own IRQ0 ISR

    driver = CPUlessFrameDriver(img, plat, func_1010_06e5, present=present,
                                irqs=irqs).install(plat)

    regs = {r: regs0[r] for r in ("ax", "bx", "cx", "dx", "si", "di", "bp", "ds", "es", "ss", "sp")}
    # ENTERED ONCE.  Everything after this point is the corpus running itself; no state is ever
    # copied in from the oracle, which is the whole point of this harness.
    try:
        run_deep(run_recovered, ROOT_KEY, img, plat, **regs)
        print(f"[coldstart] candidate root RETURNED after {driver.frame} frames")
    except _Stop:
        pass
    return out


def _report(o, c, i):
    vo, ko, po = o
    vc, kc, pc = c
    if vo != vc:
        bad = [j for j, (a, b) in enumerate(zip(vo, vc)) if a != b]
        print(f"\n[coldstart] VIDEO DIVERGED at frame {i}: {len(bad)} of {len(vo)} bytes differ; "
              f"first at B800+{bad[0]:04X} (oracle={vo[bad[0]]:02X} corpus={vc[bad[0]]:02X})")
        # WHERE ON SCREEN.  Tandy 320x200x16 interleaves four 8KB banks (one per scanline group) at
        # 160 bytes (2 pixels/byte) per row, so a raw B800 offset says nothing on its own.  Decoding
        # it names the object: a tight cluster of rows is one sprite or glyph, a full-width band is a
        # blit or a scroll, scattered singles point at timing rather than at drawing.
        for j in bad[:8]:
            bank, off = divmod(j, 0x2000)
            row, col = divmod(off, 160)
            print(f"    B800+{j:04X} -> row {row * 4 + bank:3d} x={col * 2:3d}  "
                  f"oracle={vo[j]:02X} corpus={vc[j]:02X}")
        if len(bad) > 8:
            print(f"    ... and {len(bad) - 8} more")
        rows = sorted({(j % 0x2000) // 160 * 4 + j // 0x2000 for j in bad})
        cols = sorted({(j % 0x2000) % 160 * 2 for j in bad})
        print(f"    spans rows {rows[0]}..{rows[-1]} ({len(rows)} distinct), "
              f"x {cols[0]}..{cols[-1] + 1} ({len(cols)} distinct byte columns)")
        return True
    if ko != kc:
        print(f"\n[coldstart] CRTC DIVERGED at frame {i} (the displayed page is selected here):")
        for reg in sorted({r for r, _ in ko} | {r for r, _ in kc}):
            a, b = dict(ko).get(reg), dict(kc).get(reg)
            if a != b:
                print(f"    CRTC[{reg:02X}] oracle={a} corpus={b}")
        return True
    if po != pc:
        print(f"\n[coldstart] VIDEO REGISTER DIVERGED at frame {i}:")
        for reg in sorted({r for r, _ in po} | {r for r, _ in pc}):
            a, b = dict(po).get(reg), dict(pc).get(reg)
            if a != b:
                print(f"    port {reg:03X}h oracle={a} corpus={b}")
        return True
    return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--frames", type=int, default=200)
    ap.add_argument("--irqs", type=int, default=0,
                    help="IRQ0 ticks per frame (default: the driver's MEASURED 2)")
    ap.add_argument("--step-budget", type=int, default=8_000_000,
                    help="oracle steps per frame before FAILING LOUD (never truncates silently)")
    args = ap.parse_args(argv)

    if not (COLD_SNAPSHOT / "memory_1mb.bin").is_file():
        print(f"no cold image at {COLD_SNAPSHOT} -- build one with scripts/make_frontend_snapshot.py "
              f"from your own copy of the game")
        return 2

    from overkill.cpuless_driver import TIMER_IRQS_PER_FRAME
    irqs = args.irqs or TIMER_IRQS_PER_FRAME

    print(f"[coldstart] cold start {ROOT_KEY} over {COLD_SNAPSHOT.name}, {args.frames} frames, "
          f"{irqs} IRQ0/frame; cut = 2nd pass at {HEAD[0]:04X}:{HEAD[1]:04X}")
    print("[coldstart] running the interpreted ASM oracle ...")
    oracle = _capture_oracle(args.frames, irqs, args.step_budget)
    print(f"[coldstart] oracle captured {len(oracle)} frames")
    print("[coldstart] running the NO-CPU recovered corpus (entered ONCE) ...")
    cand = _capture_candidate(args.frames, irqs)
    print(f"[coldstart] candidate captured {len(cand)} frames")

    n = min(len(oracle), len(cand))
    for i in range(n):
        if _report(oracle[i], cand[i], i):
            print(f"    ({i} frame(s) were identical before this one)")
            return 1
        if i % 50 == 0:
            print(f"  frame {i:5d}: video + CRTC + registers identical")
    if len(oracle) != len(cand):
        print(f"\n[coldstart] FRAME COUNT MISMATCH: oracle {len(oracle)}, candidate {len(cand)} "
              f"(they agreed for all {n} comparable frames)")
        return 1
    print(f"\n[coldstart] PASS -- {n} frames from a COLD START: Tandy video plane, CRTC registers "
          f"and video ports identical to the ASM oracle, NO CPU, candidate entered ONCE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
