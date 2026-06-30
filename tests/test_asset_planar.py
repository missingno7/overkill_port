"""The 4-plane -> 4bpp chunky packer (asset_codecs.pack_planes_344b) vs the real 1010:344B ASM.

344B is the bit-interleave core of the OVERKILL graphics load transform (5BAC/33AF).  It has no
standalone hook, so the airtight check steps the real game code out of the 1MB runtime image from 344B
to its return (347B opaque-block path / 34AC sprite-mask path) and compares CL/CH to the pure form,
across both modes, transparency hits, and the passed-through input mask.
"""
from __future__ import annotations

import pathlib
import random

import pytest

from dos_re.cpu import CPU8086, CPUState
from dos_re.memory import Memory

from overkill.asset_codecs import pack_planes_344b

IMAGE = pathlib.Path(__file__).resolve().parent.parent / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"
SEG = 0x1010


def _run_asm_344b(plane0, plane1, plane2, plane3, sprite_mode, transparent, mask_in):
    mem = Memory()
    data = IMAGE.read_bytes()
    mem.data[: len(data)] = data
    cpu = CPU8086(mem, CPUState(cs=SEG, ds=SEG, ss=0x6000, sp=0x8000, ip=0x344B, flags=0x0202))
    cpu.trace_enabled = False
    cpu.set_reg8(0, plane0)  # AL = plane0
    cpu.set_reg8(4, plane1)  # AH = plane1
    cpu.set_reg8(2, plane2)  # DL = plane2
    cpu.set_reg8(6, plane3)  # DH = plane3
    cpu.set_reg8(5, mask_in)  # CH = passed-through mask
    mem.ww(SEG, 0x0BD6, 1 if sprite_mode else 0)
    mem.wb(SEG, 0x0000, transparent)
    for _ in range(300):
        if cpu.s.ip in (0x347B, 0x34AC):
            break
        cpu.step()
    else:
        raise AssertionError("344B did not return; ip=%04x" % cpu.s.ip)
    return cpu.get_reg8(1), cpu.get_reg8(5)  # CL = chunky, CH = mask


def test_pack_planes_pure_unit():
    # All four planes = 0x01 -> bit0 set in every plane -> pixel0 nibble = 0b1111 = 0xF; pixel1 = 0.
    # Pixels pack as (pixel1<<4)|pixel0 = 0x0F.  Block mode: mask passed through.
    assert pack_planes_344b(1, 1, 1, 1, sprite_mode=False, mask_in=0x00) == (0x0F, 0x00)
    # plane3 (MSB) only, bit0 -> pixel0 = 0b1000 = 8.
    assert pack_planes_344b(0, 0, 0, 1, sprite_mode=False)[0] == 0x08
    # Sprite mode, transparent=0: pixel1 (high nibble) is 0 -> flagged transparent in mask.
    chunky, mask = pack_planes_344b(1, 1, 1, 1, sprite_mode=True, transparent_color=0)
    assert (chunky, mask) == (0x0F, 0xF0)  # high pixel (0) transparent -> mask 0xF0, high nibble zeroed


@pytest.mark.skipif(not IMAGE.is_file(), reason="static_runtime_bundle/memory_1mb.bin not present")
def test_pack_planes_matches_real_asm():
    rng = random.Random(1)
    for _ in range(500):
        p0, p1, p2, p3 = (rng.randint(0, 255) for _ in range(4))
        sprite_mode = bool(rng.getrandbits(1))
        transparent = rng.choice([0, 1, 5, 15])
        mask_in = rng.randint(0, 255)
        pure = pack_planes_344b(p0, p1, p2, p3, sprite_mode=sprite_mode, transparent_color=transparent, mask_in=mask_in)
        asm = _run_asm_344b(p0, p1, p2, p3, sprite_mode, transparent, mask_in)
        assert pure == asm, (p0, p1, p2, p3, sprite_mode, transparent, mask_in, pure, asm)
