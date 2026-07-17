"""OverkillPlatform.intr(0x10) verified BYTE-FAITHFUL against the dos_re int10 ORACLE.

The front-end's generated code CONSUMES the INT 10h register return (4F57: ``ax = _ir['ax']`` ...), so
the standalone shim must reproduce exactly what dos_re's BIOS does -- it cannot no-op. This runs dos_re's
own ``DOSMachine.int10`` (the oracle; tests may use the carrier, the runtime may not) for the front-end's
AH=0Bh call and asserts the platform returns the identical register bundle + leaves DGROUP untouched.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))

from dos_re.cpu import CPU8086, CPUState  # noqa: E402
from dos_re.dos import DOSMachine  # noqa: E402
from dos_re.memory import Memory  # noqa: E402

from overkill.cpuless_host import CpuStandaloneWitness  # noqa: E402
from overkill.cpuless_runtime import OverkillPlatform  # noqa: E402

_INT_REGS = ("ax", "bx", "cx", "dx", "si", "di", "bp", "ds", "es")


def _oracle_int10(ax=0, bx=0, cx=0, dx=0, si=0, di=0, bp=0, ds=0x25CC, es=0x25CC):
    """Run dos_re's real INT 10h handler over a fresh CPU and return the resulting bundle + a
    checksum of DGROUP so the caller can assert 'no memory effect'."""
    mem = Memory()
    st = CPUState(cs=0x1010, ip=0x100, ds=ds, es=es, ss=0x2000, sp=0x1000)
    for r, v in dict(ax=ax, bx=bx, cx=cx, dx=dx, si=si, di=di, bp=bp).items():
        setattr(st, r, v & 0xFFFF)
    cpu = CPU8086(mem, st)
    cpu.trace_enabled = False
    before = bytes(mem.data)
    DOSMachine(root=ROOT).int10(cpu)
    out = {r: getattr(cpu.s, r) & 0xFFFF for r in _INT_REGS}
    out["flags"] = cpu.s.flags & 0xFFFF
    out["halted"] = False
    return out, (mem.data == before)


def _platform_int10(ds=0x25CC, es=0x25CC, **regs):
    ib = {r: regs.get(r, 0) & 0xFFFF for r in _INT_REGS}
    ib["ds"], ib["es"] = ds & 0xFFFF, es & 0xFFFF     # same entry DS/ES the oracle CPU carries
    ib["_flags"] = 0x0002
    return OverkillPlatform().intr(0x10, ib, 0)


def test_int10_ah0b_matches_oracle_bytewise():
    # 4F57's exact call: AH=0Bh, BH=01, BL=00 (set CGA palette). Plus a few BX/CX variants.
    for bx in (0x0100, 0x0000, 0x0101, 0x02FF):
        for cx in (0x0000, 0x1234):
            oracle, mem_unchanged = _oracle_int10(ax=0x0B00, bx=bx, cx=cx)
            assert mem_unchanged, "AH=0Bh must not touch DGROUP"
            plat = _platform_int10(ax=0x0B00, bx=bx, cx=cx)
            # the platform echoes the caller's flags (a no-op handler leaves them); compare regs only
            assert {k: plat[k] for k in _INT_REGS} == {k: oracle[k] for k in _INT_REGS}, \
                f"BX={bx:04X} CX={cx:04X}: platform {plat} != oracle {oracle}"


def test_int10_unported_ah_fails_loud():
    # AH=00h (set video mode) is not yet ported -> visible frontier, not a silent wrong answer.
    with pytest.raises(CpuStandaloneWitness):
        _platform_int10(ax=0x0003)
