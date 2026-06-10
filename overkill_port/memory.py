from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .mz import MZExecutable, parse_mz


MEM_SIZE = 1024 * 1024
PSP_SIZE = 256
DEFAULT_LOAD_SEGMENT = 0x1000


def linear(seg: int, off: int) -> int:
    return (((seg & 0xFFFF) << 4) + (off & 0xFFFF)) & 0xFFFFF


EGA_APERTURE = 0xA0000        # physical base of the EGA A000h aperture
EGA_PLANE_STRIDE = 0x2000     # shadow-plane spacing; must match render_cga.py
EGA_PLANE_WINDOW = 0x2000     # CPU offsets 0..1FFFh map into one plane


class Memory:
    def __init__(self, size: int = MEM_SIZE):
        self.data = bytearray(size)
        self.size = size
        # EGA planar emulation.  Real EGA exposes four hardware bitplanes that all
        # share the same CPU offset inside A000h; the sequencer map-mask register
        # (03C4h index 02h) selects which planes a write lands in.  Our memory is a
        # flat bytearray, so without this a 16-colour image drawn plane-by-plane
        # (map mask cycling 1,2,4,8) collapses into a single plane and renders
        # monochrome.  We shadow each plane at A000h + plane*EGA_PLANE_STRIDE, the
        # exact layout render_cga.py / the 2750 present blit already expect, and
        # route A000h writes there per the current map mask.  Activated lazily the
        # first time the game programs the EGA sequencer (CGA never touches 03C4h),
        # so the long-tested CGA path keeps its plain flat-memory behaviour.
        self.ega_planar = False
        self.ega_map_mask = 0x0F

    def check(self, addr: int, n: int = 1) -> int:
        addr &= 0xFFFFF
        if addr + n > self.size:
            raise MemoryError(f"memory access past 1MB: {addr:05X}+{n}")
        return addr

    def rb_phys(self, addr: int) -> int:
        return self.data[self.check(addr)]

    def rw_phys(self, addr: int) -> int:
        addr = self.check(addr, 2)
        return self.data[addr] | (self.data[addr + 1] << 8)

    def wb_phys(self, addr: int, value: int) -> None:
        self.data[self.check(addr)] = value & 0xFF

    def ww_phys(self, addr: int, value: int) -> None:
        addr = self.check(addr, 2)
        self.data[addr] = value & 0xFF
        self.data[addr + 1] = (value >> 8) & 0xFF

    # Hot path: inline the 20-bit address calculation and skip the linear()/
    # check()/*_phys() call chain.  ``addr`` is always masked to 0..0xFFFFF, so a
    # byte access is always in range; word accesses wrap at the 1 MB boundary like
    # real-mode hardware instead of raising.
    def rb(self, seg: int, off: int) -> int:
        return self.data[((((seg & 0xFFFF) << 4) + (off & 0xFFFF)) & 0xFFFFF)]

    def rw(self, seg: int, off: int) -> int:
        a = (((seg & 0xFFFF) << 4) + (off & 0xFFFF)) & 0xFFFFF
        d = self.data
        if a == 0xFFFFF:
            return d[a] | (d[0] << 8)
        return d[a] | (d[a + 1] << 8)

    def wb(self, seg: int, off: int, value: int) -> None:
        a = ((((seg & 0xFFFF) << 4) + (off & 0xFFFF)) & 0xFFFFF)
        if self.ega_planar:
            po = a - EGA_APERTURE
            if 0 <= po < EGA_PLANE_WINDOW:
                self._ega_wb(po, value)
                return
        self.data[a] = value & 0xFF

    def ww(self, seg: int, off: int, value: int) -> None:
        a = (((seg & 0xFFFF) << 4) + (off & 0xFFFF)) & 0xFFFFF
        d = self.data
        if self.ega_planar:
            po = a - EGA_APERTURE
            if 0 <= po < EGA_PLANE_WINDOW:
                self._ega_wb(po, value & 0xFF)
                if po + 1 < EGA_PLANE_WINDOW:
                    self._ega_wb(po + 1, (value >> 8) & 0xFF)
                else:
                    d[a + 1] = (value >> 8) & 0xFF
                return
        d[a] = value & 0xFF
        if a == 0xFFFFF:
            d[0] = (value >> 8) & 0xFF
        else:
            d[a + 1] = (value >> 8) & 0xFF

    def _ega_wb(self, plane_off: int, value: int) -> None:
        """Route one A000h byte into the shadow planes the map mask selects."""
        v = value & 0xFF
        m = self.ega_map_mask
        d = self.data
        base = EGA_APERTURE + plane_off
        if m & 0x01:
            d[base] = v
        if m & 0x02:
            d[base + EGA_PLANE_STRIDE] = v
        if m & 0x04:
            d[base + EGA_PLANE_STRIDE * 2] = v
        if m & 0x08:
            d[base + EGA_PLANE_STRIDE * 3] = v

    def load(self, seg: int, off: int, payload: bytes) -> None:
        addr = self.check(linear(seg, off), len(payload))
        self.data[addr:addr + len(payload)] = payload

    def block(self, seg: int, off: int, n: int) -> bytes:
        addr = self.check(linear(seg, off), n)
        return bytes(self.data[addr:addr+n])


@dataclass
class LoadedProgram:
    exe: MZExecutable
    memory: Memory
    psp_segment: int
    load_segment: int
    entry_cs: int
    entry_ip: int
    initial_ss: int
    initial_sp: int
    overlay: bytes


def create_psp(memory: Memory, psp_segment: int, command_tail: bytes = b"") -> None:
    # Minimal PSP. Enough for DOS startup code that expects INT 20h and command tail.
    memory.wb(psp_segment, 0x00, 0xCD)
    memory.wb(psp_segment, 0x01, 0x20)
    memory.ww(psp_segment, 0x02, 0x9FFF)
    memory.wb(psp_segment, 0x80, min(len(command_tail), 126))
    memory.load(psp_segment, 0x81, command_tail[:126] + b"\r")


def load_mz_program(path: str | Path, *, psp_segment: int = DEFAULT_LOAD_SEGMENT,
                    command_tail: bytes = b"") -> LoadedProgram:
    exe = parse_mz(path)
    mem = Memory()
    create_psp(mem, psp_segment, command_tail)
    load_segment = (psp_segment + 0x10) & 0xFFFF
    mem.load(load_segment, 0, exe.load_module)

    # Apply relocations. LZEXE-unpacked OVERKILL currently has zero relocations, but this
    # is kept here so the loader remains correct if we later swap in another build.
    for r in exe.relocations:
        value = mem.rw(load_segment + r.segment, r.offset)
        mem.ww(load_segment + r.segment, r.offset, (value + load_segment) & 0xFFFF)

    return LoadedProgram(
        exe=exe,
        memory=mem,
        psp_segment=psp_segment,
        load_segment=load_segment,
        entry_cs=(load_segment + exe.header.cs) & 0xFFFF,
        entry_ip=exe.header.ip,
        initial_ss=(load_segment + exe.header.ss) & 0xFFFF,
        initial_sp=exe.header.sp,
        overlay=exe.overlay,
    )
