from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .cpu import CPU8086, HaltExecution, UnsupportedInstruction, CF, ZF


@dataclass
class FileHandle:
    path: Path
    data: bytearray
    pos: int = 0
    writable: bool = False


@dataclass
class DOSMachine:
    root: Path
    stdout: list[str] = field(default_factory=list)
    files: dict[int, FileHandle] = field(default_factory=dict)
    next_handle: int = 5
    # Minimal DOS heap allocator.  Earlier scaffolding returned 7000h for
    # every AH=48h call, which was good enough for bootstrap probing but made
    # OVERKILL's later source/image/work buffers alias each other.  Keep this
    # intentionally simple and deterministic: allocate paragraph blocks from
    # below VGA memory and remember sizes for snapshots/audits.
    next_alloc_segment: int = 0x7000
    allocation_limit_segment: int = 0xA000
    allocations: dict[int, int] = field(default_factory=dict)
    video_mode: int = 3
    ticks: int = 0
    vga_status_reads: int = 0
    _seq_index: int = 0  # last EGA sequencer index latched via 03C4h
    _crtc_index: int = 0  # last colour CRTC index latched via 03D4h/03B4h
    port_log: list[tuple[str, int, int, int]] = field(default_factory=list)
    # Pending BIOS keystrokes as 16-bit values (high byte = scan code, low byte =
    # ASCII).  An interactive front-end pushes keys here; when empty the runtime
    # keeps its previous deterministic headless behaviour.
    key_queue: list[int] = field(default_factory=list)
    # Latest raw keyboard scan code presented on port 60h.  A front-end sets this
    # and then invokes the installed INT 9 handler (see overkill_port.interrupts).
    current_scancode: int = 0


    def seed_initial_memory_block(self, psp_segment: int, top_segment: int = 0xA000) -> None:
        """Register the DOS-owned initial PSP memory block.

        A real DOS process starts with one allocation whose owner is the PSP.
        OVERKILL immediately shrinks that block with INT 21h/AH=4Ah before
        requesting its own buffers with AH=48h.  Modelling that block avoids
        treating the shrink as an error while still keeping the allocator
        narrow and deterministic.
        """
        psp = psp_segment & 0xFFFF
        top = top_segment & 0xFFFF
        if top <= psp:
            raise ValueError(f"invalid DOS memory block {psp:04X}..{top:04X}")
        self.allocation_limit_segment = top
        self.allocations[psp] = top - psp
        self.next_alloc_segment = top

    def read_asciiz(self, cpu: CPU8086, seg: int, off: int, limit: int = 260) -> str:
        bs = bytearray()
        for i in range(limit):
            b = cpu.mem.rb(seg, (off + i) & 0xFFFF)
            if b == 0:
                break
            bs.append(b)
        return bs.decode("cp437", errors="replace")

    def read_dollar_string(self, cpu: CPU8086, seg: int, off: int, limit: int = 4096) -> str:
        bs = bytearray()
        for i in range(limit):
            b = cpu.mem.rb(seg, (off + i) & 0xFFFF)
            if b == ord("$"):
                break
            bs.append(b)
        return bs.decode("cp437", errors="replace")

    def resolve_game_path(self, name: str) -> Path:
        # DOS paths are often relative and uppercase. Keep this intentionally narrow.
        clean = name.replace("\\", "/").strip().lstrip("/")
        direct = self.root / clean
        if direct.exists():
            return direct
        target = clean.upper()
        for p in self.root.rglob("*"):
            if str(p.relative_to(self.root)).replace("/", "\\").upper() == target.replace("/", "\\"):
                return p
            if p.name.upper() == Path(clean).name.upper():
                return p
        return direct


    def port_read(self, cpu: CPU8086, port: int, bits: int) -> int:
        # VGA input status register 1. Bit 3 is vertical retrace. Toggle it so
        # busy-wait loops that wait for retrace high/low both make progress.
        if port == 0x03DA and bits == 8:
            self.vga_status_reads += 1
            return 0x08 if (self.vga_status_reads & 1) else 0x00
        if port == 0x60 and bits == 8:
            # 8042 keyboard data port: the game's INT 9 handler reads the scan code here.
            return self.current_scancode & 0xFF
        return 0

    def port_write(self, cpu: CPU8086, port: int, value: int, bits: int) -> None:
        if len(self.port_log) < 4096:
            self.port_log.append(("out", port & 0xFFFF, value & ((1 << bits) - 1), bits))
        self._track_ega_ports(cpu, port & 0xFFFF, value, bits)

    def _track_ega_ports(self, cpu: CPU8086, port: int, value: int, bits: int) -> None:
        # Track just enough EGA sequencer state to drive planar A000h writes (see
        # Memory.ega_planar).  The game programs the map-mask register at 03C4h
        # index 02h, either as two byte OUTs (index then data) or a single 16-bit
        # OUT where AL=index and AH=data.  Touching the sequencer at all means we
        # are in EGA mode, so enable planar routing here.
        mem = cpu.mem
        if port == 0x3C4:
            mem.ega_planar = True
            if bits == 16:
                if (value & 0xFF) == 0x02:
                    mem.ega_map_mask = (value >> 8) & 0x0F
            else:
                self._seq_index = value & 0xFF
        elif port == 0x3C5:
            mem.ega_planar = True
            if getattr(self, "_seq_index", None) == 0x02:
                mem.ega_map_mask = value & 0x0F
        elif port == 0x3CE:
            mem.ega_planar = True
            if bits == 16:
                if (value & 0xFF) == 0x04:
                    mem.ega_read_plane = (value >> 8) & 0x03
            else:
                self._gc_index = value & 0xFF
        elif port == 0x3CF:
            mem.ega_planar = True
            if getattr(self, "_gc_index", None) == 0x04:
                mem.ega_read_plane = value & 0x03
        elif port in (0x3D4, 0x3B4):
            if bits == 16:
                index = value & 0xFF
                data = (value >> 8) & 0xFF
                self._write_crtc_register(mem, index, data)
            else:
                self._crtc_index = value & 0xFF
        elif port in (0x3D5, 0x3B5):
            self._write_crtc_register(mem, getattr(self, "_crtc_index", 0), value & 0xFF)

    def _write_crtc_register(self, mem, index: int, value: int) -> None:
        index &= 0xFF
        value &= 0xFF
        if index == 0x0C:
            mem.ega_display_start = ((value << 8) | (mem.ega_display_start & 0x00FF)) & 0xFFFF
        elif index == 0x0D:
            mem.ega_display_start = ((mem.ega_display_start & 0xFF00) | value) & 0xFFFF

    def interrupt(self, cpu: CPU8086, num: int) -> None:
        if num == 0x20:
            cpu.halted = True
            raise HaltExecution()
        if num == 0x21:
            self.int21(cpu)
            return
        if num == 0x10:
            self.int10(cpu)
            return
        if num == 0x11:  # BIOS equipment list
            cpu.s.ax = 0x0020  # EGA/VGA-style display, no exotic peripherals
            return
        if num == 0x12:  # conventional memory size in KB
            cpu.s.ax = 640
            return
        if num == 0x16:
            self.int16(cpu)
            return
        if num == 0x1A:
            self.int1a(cpu)
            return
        if num == 0x33:
            self.int33(cpu)
            return
        raise UnsupportedInstruction(f"Unhandled interrupt INT {num:02X}h at {cpu.s.cs:04X}:{cpu.s.ip:04X}")

    def int21(self, cpu: CPU8086) -> None:
        ah = (cpu.s.ax >> 8) & 0xFF
        al = cpu.s.ax & 0xFF
        if ah == 0x00 or ah == 0x4C:
            cpu.halted = True
            raise HaltExecution()
        if ah == 0x09:
            text = self.read_dollar_string(cpu, cpu.s.ds, cpu.s.dx)
            self.stdout.append(text)
            cpu.s.ax = (cpu.s.ax & 0xFF00) | ord("$")
            return
        if ah == 0x02:
            self.stdout.append(chr(cpu.s.dx & 0xFF))
            return
        if ah in (0x01, 0x07, 0x08):
            # Console character input.
            #
            # AH=01h: wait for character, echo, Ctrl-C checked by DOS.
            # AH=07h: direct character input, no echo, no Ctrl-C check.
            # AH=08h: character input, no echo, Ctrl-C checked by DOS.
            #
            # This emulator does not have a real DOS stdin stream.  Use the same
            # deterministic keyboard queue as INT 16h when available, returning
            # the ASCII byte in AL.  When no queued key exists, return Esc, matching
            # the existing headless INT 16h fallback and preventing blocking DOS
            # read paths from crashing automated play runs.
            key = self.key_queue.pop(0) if self.key_queue else 0x011B
            ch = key & 0xFF
            if ch == 0 and (key >> 8):
                # DOS extended keys are reported as 00h first; a second read
                # would return the scan code on real DOS.  Keeping the leading
                # zero is the safest narrow emulation for code that distinguishes
                # extended keys.
                ch = 0
            cpu.s.ax = (cpu.s.ax & 0xFF00) | ch
            if ah == 0x01:
                self.stdout.append(chr(ch))
            return
        if ah == 0x30:  # get DOS version
            cpu.s.ax = 0x0005
            cpu.s.bx = 0x0000
            cpu.s.cx = 0x0000
            cpu.set_flag(CF, False)
            return
        if ah == 0x35:  # get interrupt vector AL -> ES:BX
            vec = al & 0xFF
            cpu.s.bx = cpu.mem.rw(0, vec * 4)
            cpu.s.es = cpu.mem.rw(0, vec * 4 + 2)
            return
        if ah == 0x25:  # set interrupt vector AL = DS:DX (write the real IVT)
            vec = al & 0xFF
            cpu.mem.ww(0, vec * 4, cpu.s.dx)
            cpu.mem.ww(0, vec * 4 + 2, cpu.s.ds)
            return
        if ah == 0x19:  # get current default drive (0=A, 2=C). Return C:.
            cpu.s.ax = (cpu.s.ax & 0xFF00) | 2
            return
        if ah == 0x1A:  # set DTA
            return
        if ah == 0x3C:  # create/truncate file
            name = self.read_asciiz(cpu, cpu.s.ds, cpu.s.dx)
            path = self.resolve_game_path(name)
            handle = self.next_handle
            self.next_handle += 1
            # Keep writes in-memory so RE runs are deterministic and do not
            # mutate the user's original game directory.
            self.files[handle] = FileHandle(path, bytearray(), pos=0, writable=True)
            cpu.s.ax = handle
            cpu.set_flag(CF, False)
            return
        if ah == 0x3D:  # open file
            name = self.read_asciiz(cpu, cpu.s.ds, cpu.s.dx)
            path = self.resolve_game_path(name)
            if not path.exists():
                cpu.s.ax = 2
                cpu.set_flag(CF, True)
                return
            handle = self.next_handle
            self.next_handle += 1
            self.files[handle] = FileHandle(path, bytearray(path.read_bytes()))
            cpu.s.ax = handle
            cpu.set_flag(CF, False)
            return
        if ah == 0x3E:  # close
            self.files.pop(cpu.s.bx, None)
            cpu.set_flag(CF, False)
            return
        if ah == 0x3F:  # read
            h = self.files.get(cpu.s.bx)
            if h is None:
                cpu.s.ax = 6
                cpu.set_flag(CF, True)
                return
            n = min(cpu.s.cx, len(h.data) - h.pos)
            for i in range(n):
                cpu.mem.wb(cpu.s.ds, (cpu.s.dx + i) & 0xFFFF, h.data[h.pos + i])
            h.pos += n
            cpu.s.ax = n
            cpu.set_flag(CF, False)
            return
        if ah == 0x40:  # write
            data = cpu.mem.block(cpu.s.ds, cpu.s.dx, cpu.s.cx)
            if cpu.s.bx in (1, 2):
                self.stdout.append(data.decode("cp437", errors="replace"))
                cpu.s.ax = cpu.s.cx
                cpu.set_flag(CF, False)
                return
            h = self.files.get(cpu.s.bx)
            if h is None:
                cpu.s.ax = 6
                cpu.set_flag(CF, True)
                return
            end = h.pos + len(data)
            if end > len(h.data):
                h.data.extend(b"\x00" * (end - len(h.data)))
            h.data[h.pos:end] = data
            h.pos = end
            cpu.s.ax = len(data)
            cpu.set_flag(CF, False)
            return
        if ah == 0x58:  # get/set allocation strategy
            # AL=00h get strategy, AL=01h set strategy.  OVERKILL only needs
            # this to succeed before DOS heap/free logic; keep first-fit.
            if al == 0x00:
                cpu.s.ax = 0x0000
                cpu.set_flag(CF, False)
                return
            if al == 0x01:
                cpu.set_flag(CF, False)
                return
            cpu.s.ax = 1
            cpu.set_flag(CF, True)
            return
        if ah == 0x47:  # get current directory
            # DS:SI receives an ASCIZ path without drive letter or leading slash.
            cpu.mem.wb(cpu.s.ds, cpu.s.si, 0)
            cpu.set_flag(CF, False)
            return
        if ah == 0x42:  # lseek
            h = self.files.get(cpu.s.bx)
            if h is None:
                cpu.s.ax = 6; cpu.set_flag(CF, True); return
            delta = ((cpu.s.cx << 16) | cpu.s.dx)
            if delta & 0x80000000:
                delta -= 0x100000000
            origin = al
            if origin == 0: h.pos = max(0, delta)
            elif origin == 1: h.pos = max(0, h.pos + delta)
            elif origin == 2: h.pos = max(0, len(h.data) + delta)
            cpu.s.dx = (h.pos >> 16) & 0xFFFF
            cpu.s.ax = h.pos & 0xFFFF
            cpu.set_flag(CF, False)
            return
        if ah == 0x48:  # allocate memory (BX paragraphs)
            paragraphs = cpu.s.bx & 0xFFFF
            if paragraphs == 0:
                cpu.s.ax = 8  # insufficient memory / invalid zero-size request for our narrow runtime
                cpu.s.bx = max(0, self.allocation_limit_segment - self.next_alloc_segment) & 0xFFFF
                cpu.set_flag(CF, True)
                return
            seg = self.next_alloc_segment & 0xFFFF
            end = seg + paragraphs
            if end > self.allocation_limit_segment:
                cpu.s.ax = 8  # insufficient memory
                cpu.s.bx = max(0, self.allocation_limit_segment - self.next_alloc_segment) & 0xFFFF
                cpu.set_flag(CF, True)
                return
            self.allocations[seg] = paragraphs
            self.next_alloc_segment = end
            cpu.s.ax = seg
            cpu.set_flag(CF, False)
            return
        if ah == 0x49:  # free memory block (ES segment)
            # OVERKILL startup does not need coalescing.  Removing the record
            # is enough for traceability while keeping addresses deterministic.
            self.allocations.pop(cpu.s.es & 0xFFFF, None)
            cpu.set_flag(CF, False)
            return
        if ah == 0x4A:  # resize memory block (ES segment, BX paragraphs)
            seg = cpu.s.es & 0xFFFF
            new_size = cpu.s.bx & 0xFFFF
            old_size = self.allocations.get(seg)
            if old_size is None:
                cpu.s.ax = 7  # memory control blocks destroyed / unknown block
                cpu.set_flag(CF, True)
                return
            # Only support in-place shrink or growing the most recently allocated block.
            old_end = seg + old_size
            new_end = seg + new_size
            if new_end <= old_end or old_end == self.next_alloc_segment:
                if new_end > self.allocation_limit_segment:
                    cpu.s.ax = 8
                    cpu.s.bx = max(0, self.allocation_limit_segment - seg) & 0xFFFF
                    cpu.set_flag(CF, True)
                    return
                self.allocations[seg] = new_size
                if old_end == self.next_alloc_segment:
                    self.next_alloc_segment = new_end
                cpu.set_flag(CF, False)
                return
            cpu.s.ax = 8
            cpu.s.bx = old_size
            cpu.set_flag(CF, True)
            return
        raise UnsupportedInstruction(f"Unhandled DOS INT 21h AH={ah:02X}h")

    def int10(self, cpu: CPU8086) -> None:
        ah = (cpu.s.ax >> 8) & 0xFF
        al = cpu.s.ax & 0xFF
        if ah == 0x00:
            self.video_mode = al
            return
        if ah == 0x0F:
            cpu.s.ax = (80 << 8) | self.video_mode
            cpu.s.bx = 0
            return
        if ah in (0x01, 0x02, 0x06, 0x07, 0x0B, 0x10, 0x12):
            return
        raise UnsupportedInstruction(f"Unhandled BIOS INT 10h AH={ah:02X}h")

    def int16(self, cpu: CPU8086) -> None:
        ah = (cpu.s.ax >> 8) & 0xFF
        if ah == 0x00:  # blocking read keystroke
            if self.key_queue:
                cpu.s.ax = self.key_queue.pop(0) & 0xFFFF
                return
            cpu.s.ax = 0x011B  # Esc fallback keeps headless runs deterministic
            return
        if ah == 0x01:  # check keystroke: ZF=0 + AX=key if available, ZF=1 if not
            if self.key_queue:
                cpu.set_flag(ZF, False)
                cpu.s.ax = self.key_queue[0] & 0xFFFF
                return
            cpu.set_flag(ZF, True)
            return
        raise UnsupportedInstruction(f"Unhandled BIOS INT 16h AH={ah:02X}h")

    def int1a(self, cpu: CPU8086) -> None:
        ah = (cpu.s.ax >> 8) & 0xFF
        if ah == 0x00:
            self.ticks += 1
            cpu.s.cx = (self.ticks >> 16) & 0xFFFF
            cpu.s.dx = self.ticks & 0xFFFF
            cpu.s.ax &= 0xFF00
            return
        raise UnsupportedInstruction(f"Unhandled BIOS INT 1Ah AH={ah:02X}h")

    def int33(self, cpu: CPU8086) -> None:
        # Mouse API. Report absent but don't crash.
        ax = cpu.s.ax
        if ax == 0x0000:
            cpu.s.ax = 0
            cpu.s.bx = 0
            return
        return
