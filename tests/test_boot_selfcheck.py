"""Synthetic-ASM oracle for the boot self-check checksum (overkill.asset_codecs.boot_selfcheck).

The boot self-check runs only at cold-boot (no snapshot-demo witness), so this pins
``boot_selfcheck_checksum`` byte-exact against the **original 1010:C916 opcodes**: it assembles the
exact inner-loop bytes, runs them on a real ``CPU8086`` over synthetic data, and asserts the AX the
ASM leaves equals the pure function.  (This is the accumulation a cold-boot witness harness
accelerates to get past the multi-million-instruction boot self-check.)
"""
from __future__ import annotations

from dos_re.cpu import CPU8086, CPUState
from dos_re.memory import Memory
from overkill.asset_codecs.boot_selfcheck import boot_selfcheck_checksum

# The exact 1010:C916-C91D inner loop (verified via scripts/lindis.py):
#   C916 mov dl,ds:[si] ; C918 add ax,dx ; C91A add ah,al ; C91C inc si ; C91D loop C916
CODE = bytes.fromhex("8a14" "03c2" "02e0" "46" "e2f7")
CS = 0x1010
IP0 = 0xC916
IP_DONE = 0xC91F        # fall-through past `loop` when cx hits 0


def _run_asm(seed_ax: int, data: bytes, *, ds=0x2000, si=0x0042) -> int:
    mem = Memory()
    code_phys = (CS << 4) + IP0
    for i, b in enumerate(CODE):
        mem.data[code_phys + i] = b
    for i, b in enumerate(data):
        mem.wb(ds, (si + i) & 0xFFFF, b)
    cpu = CPU8086(mem, CPUState(cs=CS, ip=IP0, ds=ds, si=si,
                                ax=seed_ax & 0xFFFF, dx=0x0000,   # dh=0 (set at C914)
                                cx=len(data) & 0xFFFF, flags=0x0002))  # DF=0
    for _ in range(2_000_000):
        if (cpu.s.ip & 0xFFFF) == IP_DONE:
            break
        cpu.step()
    else:  # pragma: no cover
        raise AssertionError("C916 oracle did not fall through")
    return cpu.s.ax & 0xFFFF


def _check(seed, data):
    assert _run_asm(seed, data) == boot_selfcheck_checksum(seed, data)


def test_single_byte():
    _check(0x0000, bytes([0x5A]))


def test_carry_into_ah_accumulation():
    # values that force al->ah carry interactions
    _check(0x1234, bytes([0xFF, 0x01, 0x80, 0x7F]))


def test_seed_is_respected():
    _check(0xABCD, bytes([0x10, 0x20, 0x30]))


def test_16bit_wraps():
    _check(0xFFF0, bytes([0xFF] * 8))


def test_longer_block():
    data = bytes((i * 37 + 5) % 256 for i in range(200))
    _check(0x0000, data)
    _check(0x9E37, data)


def test_matches_across_seeds():
    data = bytes([0x00, 0x01, 0xFE, 0xFF, 0x7F, 0x80, 0x55, 0xAA])
    for seed in (0x0000, 0x0100, 0x00FF, 0x8000, 0xFFFF):
        _check(seed, data)
