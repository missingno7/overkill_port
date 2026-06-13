from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Callable

from .cpu import CPU8086, CPUState, IF
from .dos import DOSMachine, FileHandle
from .memory import (
    EGA_APERTURE,
    EGA_PLANE_STRIDE,
    EGA_SHADOW_SIZE,
    Memory,
    linear,
)
from .runtime import Runtime


Addr = tuple[int, int]


class HookVerifyDivergence(RuntimeError):
    pass


class HookVerifyLimitReached(RuntimeError):
    pass


@dataclass(frozen=True)
class HookStop:
    kind: str
    ip: int | None = None
    ips: tuple[int, ...] = ()
    min_steps: int = 0

    @classmethod
    def after_step(cls, kind: str, ip: int | None = None, ips: tuple[int, ...] = ()) -> "HookStop":
        """Create metadata for a loop whose valid continuation can equal entry IP.

        Same-IP frame loops such as OVERKILL's D007 dispatcher need the ASM
        oracle to execute at least one instruction before accepting the target.
        Otherwise the verifier would stop immediately at the entry address and
        compare a hook that performed a whole frame against an untouched oracle.
        """
        return cls(kind, ip=ip, ips=ips, min_steps=1)

    def targets(self, cpu: CPU8086, before: CPUState) -> tuple[Addr, ...]:
        cs = before.cs & 0xFFFF
        if self.kind == "near_ret":
            return ((cs, cpu.mem.rw(before.ss, before.sp)),)
        if self.kind == "near_ret_or_fixed_ip":
            if self.ip is None:
                raise ValueError("near_ret_or_fixed_ip hook metadata needs ip")
            return ((cs, cpu.mem.rw(before.ss, before.sp)), (cs, self.ip & 0xFFFF))
        if self.kind == "near_ret_or_fixed_ips":
            return ((cs, cpu.mem.rw(before.ss, before.sp)),) + tuple((cs, ip & 0xFFFF) for ip in self.ips)
        if self.kind == "far_ret":
            return ((cpu.mem.rw(before.ss, (before.sp + 2) & 0xFFFF), cpu.mem.rw(before.ss, before.sp)),)
        if self.kind == "iret":
            return ((cpu.mem.rw(before.ss, (before.sp + 2) & 0xFFFF), cpu.mem.rw(before.ss, before.sp)),)
        if self.kind == "fixed_ip":
            if self.ip is None:
                raise ValueError("fixed_ip hook metadata needs ip")
            return ((cs, self.ip & 0xFFFF),)
        if self.kind == "fixed_ips":
            return tuple((cs, ip & 0xFFFF) for ip in self.ips)
        if self.kind == "ega_2824":
            outer = cpu.mem.rw(before.ss, before.sp)
            return ((cs, 0x27EB if outer > 1 else 0x27D9),)
        if self.kind == "dispatch_5a00":
            mode = cpu.mem.rw(cs, 0x95BC)
            if mode in (0, 1, 2):  # CGA + EGA + Tandy coordinate targets are fully hooked.
                return ((cs, cpu.mem.rw(before.ss, before.sp)),)
            bx = ((mode & 0xFFFF) << 1) & 0xFFFF
            return ((cs, cpu.mem.rw(cs, (0x5A0C + bx) & 0xFFFF)),)
        if self.kind == "dispatch_5a24":
            mode = cpu.mem.rw(cs, 0x95BC)
            if mode in (0, 1, 2):  # CGA + EGA + Tandy coordinate targets are fully hooked.
                return ((cs, cpu.mem.rw(before.ss, before.sp)),)
            bx = ((mode & 0xFFFF) << 1) & 0xFFFF
            return ((cs, cpu.mem.rw(cs, (0x5A30 + bx) & 0xFFFF)),)
        if self.kind == "dispatch_5a36":
            mode = cpu.mem.rw(cs, 0x95BC)
            if mode in (0, 1, 2):
                return ((cs, cpu.mem.rw(before.ss, before.sp)),)
            bx = ((mode & 0xFFFF) << 1) & 0xFFFF
            return ((cs, cpu.mem.rw(cs, (0x5A42 + bx) & 0xFFFF)),)
        if self.kind == "dispatch_5bdc":
            mode = cpu.mem.rw(cs, 0x95BC)
            bx = ((mode & 0xFFFF) << 1) & 0xFFFF
            return ((cs, cpu.mem.rw(cs, (0x5BE8 + bx) & 0xFFFF)),)
        if self.kind == "postcopy_58df":
            mode = cpu.mem.rw(cs, 0x95BC)
            return ((cs, 0x58F8 if mode == 0 else 0x58DF),)
        if self.kind == "dispatch_5ac8":
            mode = cpu.mem.rw(cs, 0x95BC)
            obj_type = cpu.mem.rw(before.ss, (before.bp + 0x14) & 0xFFFF)
            bx = ((obj_type + mode + mode + mode) << 1) & 0xFFFF
            return ((cs, cpu.mem.rw(cs, (0x5AE2 + bx) & 0xFFFF)),)
        if self.kind == "dispatch_5a6c":
            mode = cpu.mem.rw(cs, 0x95BC)
            bx = ((mode & 0xFFFF) << 1) & 0xFFFF
            return ((cs, cpu.mem.rw(cs, (0x5A78 + bx) & 0xFFFF)),)
        if self.kind == "dispatch_5a92":
            mode = cpu.mem.rw(cs, 0x95BC)
            obj_type = cpu.mem.rw(before.ss, (before.bp + 0x14) & 0xFFFF)
            bx = ((obj_type + mode + mode + mode) << 1) & 0xFFFF
            return ((cs, cpu.mem.rw(cs, (0x5AB6 + bx) & 0xFFFF)),)
        if self.kind == "dispatch_7596":
            obj_type = cpu.mem.rw(before.ss, (before.bp + 0x14) & 0xFFFF)
            bx = ((obj_type & 0xFFFF) << 1) & 0xFFFF
            return ((cs, cpu.mem.rw(cs, (0x75A0 + bx) & 0xFFFF)),)
        if self.kind in ("scan_present_a927", "scan_present_a90f"):
            cx = before.cx & 0xFFFF
            if cx == 0:
                cx = 0x10000
            ds = before.ds & 0xFFFF
            ss = before.ss & 0xFFFF
            table_base = 0x8D12 if self.kind == "scan_present_a90f" else 0x32CA
            call_ip = 0xA91E if self.kind == "scan_present_a90f" else 0xA936
            done_ip = 0xA924 if self.kind == "scan_present_a90f" else 0xA93C
            while cx:
                bx = ((cx & 0xFFFF) << 1) & 0xFFFF
                bp = cpu.mem.rw(ds, (table_base + bx) & 0xFFFF)
                if cpu.mem.rw(ss, bp & 0xFFFF) != 0:
                    return ((cs, call_ip),)
                cx = (cx - 1) & 0xFFFF
                if cx == 0:
                    break
            return ((cs, done_ip),)
        if self.kind == "scan_present_pair_a90c":
            def scan(table_base: int, count: int, call_ip: int, done_ip: int) -> tuple[Addr, bool]:
                cx = count & 0xFFFF
                if cx == 0:
                    cx = 0x10000
                ds = before.ds & 0xFFFF
                ss = before.ss & 0xFFFF
                while cx:
                    bx = ((cx & 0xFFFF) << 1) & 0xFFFF
                    bp = cpu.mem.rw(ds, (table_base + bx) & 0xFFFF)
                    if cpu.mem.rw(ss, bp & 0xFFFF) != 0:
                        return (cs, call_ip), False
                    cx = (cx - 1) & 0xFFFF
                    if cx == 0:
                        break
                return (cs, done_ip), True

            target, done = scan(0x8D12, 0x0022, 0xA91E, 0xA924)
            if not done:
                return (target,)
            target, done = scan(0x32CA, 0x0024, 0xA936, 0xA93C)
            if not done:
                return (target,)
            return ((cs, cpu.mem.rw(before.ss, before.sp)),)
        if self.kind == "scan_draw_a849":
            cx = before.cx & 0xFFFF
            if cx == 0:
                cx = 0x10000
            ds = before.ds & 0xFFFF
            ss = before.ss & 0xFFFF
            while cx:
                bx = ((cx & 0xFFFF) << 1) & 0xFFFF
                bp = cpu.mem.rw(ds, (0x32CA + bx) & 0xFFFF)
                if cpu.mem.rw(ss, bp & 0xFFFF) != 0:
                    return ((cs, 0xA858),)
                cx = (cx - 1) & 0xFFFF
                if cx == 0:
                    break
            return ((cs, 0xA85E),)
        if self.kind == "tandy_layer_sprite_768e":
            ss = before.ss & 0xFFFF
            bp = before.bp & 0xFFFF
            di = cpu.mem.rw(ss, (bp + 0x0C) & 0xFFFF)
            if di == 0xFFFF:
                return ((cs, cpu.mem.rw(before.ss, before.sp)),)
            bx = cpu.mem.rw(ss, (bp + 0x08) & 0xFFFF)
            if bx >= 0x00FA:
                bx = (bx - 0x00FA) & 0xFFFF
            bx = ((bx << 1) + 0x9192) & 0xFFFF
            mode = cpu.mem.rw(cs, 0x95BC)
            dispatch = (mode << 3) & 0xFFFF
            dispatch = (dispatch + cpu.mem.rw(ss, (bp + 0x12) & 0xFFFF)) & 0xFFFF
            table = 0x7716
            if cpu.mem.rw(ss, (bp + 0x24) & 0xFFFF) == 0:
                table = 0x76E6
            target = cpu.mem.rw(cs, (table + ((dispatch << 1) & 0xFFFF)) & 0xFFFF)
            if target in (
                0x103C, 0x10B7, 0x1AEB, 0x1D1B,
                0x2193, 0x21D6, 0x2223, 0x2285, 0x22FC,
                0x238D, 0x2410, 0x247E,
                0x3849, 0x387C, 0x38B7, 0x38D6, 0x38F9, 0x390E,
                0x409D, 0x40D7, 0x412B,
                0x2F81, 0x2F40, 0x2ECB, 0x2E6E, 0x2FB6,
            ):
                return ((cs, cpu.mem.rw(before.ss, before.sp)),)
            return ((cs, target),)
        if self.kind == "scan_layer1_a8c7":
            cx = before.cx & 0xFFFF
            if cx == 0:
                cx = 0x10000
            ds = before.ds & 0xFFFF
            ss = before.ss & 0xFFFF
            while cx:
                bx = ((cx & 0xFFFF) << 1) & 0xFFFF
                bp = cpu.mem.rw(ds, (0x32CA + bx) & 0xFFFF)
                if cpu.mem.rw(ss, bp & 0xFFFF) != 0:
                    should_call = True
                    mode = cpu.mem.rw(ds, 0xBDAC)
                    if mode != 1:
                        camera = cpu.mem.rw(ds, 0x2350)
                        if camera <= 0x00B6:
                            layer = cpu.mem.rw(ss, (bp + 0x16) & 0xFFFF)
                            if layer == 1:
                                should_call = False
                    if should_call and cpu.mem.rw(ss, (bp + 0x0A) & 0xFFFF) == 1:
                        return ((cs, 0xA8F1),)
                cx = (cx - 1) & 0xFFFF
                if cx == 0:
                    break
            return ((cs, 0xA8F7),)
        if self.kind == "dispatch_aa2b":
            obj_kind = cpu.mem.rw(before.ss, (before.bp + 0x16) & 0xFFFF)
            bx = ((obj_kind & 0xFFFF) << 1) & 0xFFFF
            return ((cs, cpu.mem.rw(cs, (0xAA36 + bx) & 0xFFFF)),)
        if self.kind == "dispatch_efae":
            logic_id = cpu.mem.rw(before.ss, (before.bp + 0x18) & 0xFFFF)
            bx = ((logic_id & 0xFFFF) << 1) & 0xFFFF
            return ((cs, cpu.mem.rw(cs, (0xEFC4 + bx) & 0xFFFF)),)
        raise ValueError(f"unknown hook stop kind {self.kind!r}")


@dataclass
class MemoryRange:
    name: str
    start: int
    size: int


@dataclass
class HookVerifierConfig:
    verify_all: bool = False
    hooks: set[Addr] = field(default_factory=set)
    max_verified: int | None = None
    stop_on_diff: bool = False
    log_diffs: bool = False
    asm_max_steps: int = 500_000
    full_memory: bool = True
    require_metadata: bool = False
    progress_callback: Callable[[str], None] | None = None


DEFAULT_STOPS: dict[Addr, HookStop] = {
    (0x1010, 0x06E5): HookStop("iret"),
    (0x1010, 0x0679): HookStop("near_ret"),
    (0x1010, 0x073C): HookStop("near_ret"),
    (0x1010, 0x9921): HookStop("fixed_ip", 0x9928),
    (0x1010, 0x0672): HookStop("near_ret"),
    (0x1010, 0x3153): HookStop("near_ret"),
    (0x1010, 0x519A): HookStop("near_ret"),
    (0x1010, 0x518C): HookStop("near_ret"),
    (0x1010, 0x5F06): HookStop("near_ret"),
    (0x1010, 0xBDE3): HookStop("near_ret_or_fixed_ip", 0x5059),
    (0x1F8F, 0x0922): HookStop("far_ret"),
    (0x1F8F, 0x0960): HookStop("near_ret"),
    (0x1010, 0x0162): HookStop("near_ret"),
    (0x1010, 0x017E): HookStop("fixed_ip", 0x018B),
    (0x254A, 0x04D7): HookStop("far_ret"),
    (0x254A, 0x05A1): HookStop("fixed_ips", ips=(0x0607, 0x0640)),
    (0x254A, 0x05D9): HookStop("fixed_ips", ips=(0x0607, 0x0637)),
    (0x254A, 0x05BF): HookStop("fixed_ip", 0x05C6),
    (0x254A, 0x0582): HookStop("fixed_ips", ips=(0x058D, 0x0640)),
    (0x254A, 0x0701): HookStop("far_ret"),
    (0x1010, 0x0324): HookStop("fixed_ips", ips=(0x02A8, 0x02B2)),
    (0x1010, 0x0367): HookStop("fixed_ips", ips=(0x02A8, 0x02B2)),
    (0x1010, 0x03A8): HookStop("fixed_ips", ips=(0x02A8, 0x02B2)),
    (0x1010, 0x0615): HookStop("near_ret"),
    (0x1010, 0x0624): HookStop("near_ret"),
    (0x1010, 0x0F0B): HookStop("fixed_ip", 0x526A),
    (0x1010, 0x0FA3): HookStop("fixed_ip", 0x526A),
    (0x1010, 0x0FE4): HookStop("near_ret"),
    (0x1010, 0x96C5): HookStop("fixed_ip", 0x96CA),
    (0x1010, 0x96C8): HookStop("fixed_ips", ips=(0x96C5, 0x96CA)),
    (0x1010, 0x103C): HookStop("near_ret"),
    (0x1010, 0x10B7): HookStop("near_ret"),
    (0x1010, 0x2193): HookStop("near_ret"),
    (0x1010, 0x21D6): HookStop("near_ret"),
    (0x1010, 0x238D): HookStop("near_ret"),
    (0x1010, 0x2410): HookStop("near_ret"),
    (0x1010, 0x247E): HookStop("near_ret"),
    (0x1010, 0x2223): HookStop("near_ret"),
    (0x1010, 0x2285): HookStop("near_ret"),
    (0x1010, 0x22FC): HookStop("near_ret"),
    (0x1010, 0x1AEB): HookStop("near_ret"),
    (0x1010, 0x75A6): HookStop("near_ret"),
    (0x1010, 0xB73E): HookStop("near_ret"),
    (0x1010, 0xB9F0): HookStop("fixed_ip", 0xBC4B),
    (0x1010, 0x13E7): HookStop("near_ret"),
    (0x1010, 0x1D1B): HookStop("near_ret"),
    (0x1010, 0x2750): HookStop("near_ret"),
    (0x1010, 0x29C6): HookStop("near_ret"),
    (0x1010, 0x2AB9): HookStop("near_ret"),
    (0x1010, 0x27EB): HookStop("fixed_ip", 0x27D9),
    (0x1010, 0x280D): HookStop("fixed_ip", 0x2824),
    (0x1010, 0x2824): HookStop("ega_2824"),
    (0x1010, 0x291C): HookStop("near_ret"),
    (0x1010, 0x2932): HookStop("near_ret"),
    (0x1010, 0x2E6E): HookStop("near_ret"),
    (0x1010, 0x2ECB): HookStop("near_ret"),
    (0x1010, 0x2F40): HookStop("near_ret"),
    (0x1010, 0x2F81): HookStop("near_ret"),
    (0x1010, 0x2FB6): HookStop("near_ret"),
    (0x1010, 0x306F): HookStop("near_ret"),
    (0x1010, 0x30B0): HookStop("near_ret"),
    (0x1010, 0x30BA): HookStop("near_ret"),
    (0x1010, 0x3389): HookStop("near_ret"),
    (0x1010, 0x33AF): HookStop("fixed_ip", 0x44AA),
    (0x1010, 0x33B2): HookStop("fixed_ips", ips=(0x33AF, 0x44AA)),
    (0x1010, 0x3354): HookStop("near_ret"),
    (0x1010, 0x33DD): HookStop("near_ret"),
    (0x1010, 0x34AD): HookStop("near_ret"),
    (0x1010, 0x34C5): HookStop("near_ret"),
    (0x1010, 0x34D8): HookStop("near_ret"),
    (0x1010, 0x3542): HookStop("near_ret"),
    (0x1010, 0x356C): HookStop("near_ret"),
    (0x1010, 0x36A2): HookStop("near_ret"),
    (0x1010, 0x60C5): HookStop("near_ret"),
    (0x1010, 0x375B): HookStop("near_ret"),
    (0x1010, 0x4E0D): HookStop("near_ret"),
    (0x1010, 0x4E26): HookStop("near_ret"),
    (0x1010, 0x35AA): HookStop("near_ret"),
    (0x1010, 0x35CC): HookStop("near_ret"),
    (0x1010, 0x3657): HookStop("near_ret"),
    (0x1010, 0x3849): HookStop("near_ret"),
    (0x1010, 0x387C): HookStop("near_ret"),
    (0x1010, 0x38D6): HookStop("near_ret"),
    (0x1010, 0x390E): HookStop("near_ret"),
    (0x1010, 0x38B7): HookStop("near_ret"),
    (0x1010, 0x38F9): HookStop("near_ret"),
    (0x1010, 0x409D): HookStop("near_ret"),
    (0x1010, 0x41A6): HookStop("near_ret"),
    (0x1010, 0x41DA): HookStop("near_ret"),
    (0x1010, 0x40D7): HookStop("near_ret"),
    (0x1010, 0x412B): HookStop("near_ret"),
    (0x1010, 0x450C): HookStop("fixed_ip", 0x44AA),
    (0x1010, 0x4511): HookStop("fixed_ip", 0x450C),
    (0x1010, 0x4537): HookStop("near_ret"),
    (0x1010, 0x45CB): HookStop("near_ret"),
    (0x1010, 0x45F6): HookStop("near_ret"),
    (0x1010, 0xC713): HookStop("near_ret_or_fixed_ip", 0xC720),
    (0x1010, 0xC916): HookStop("fixed_ip", 0xC91F),
    (0x1010, 0xD50E): HookStop("near_ret"),
    (0x1010, 0xECF2): HookStop("near_ret"),
    (0x1010, 0xED7A): HookStop("fixed_ip", 0xED26),
    (0x1010, 0xED97): HookStop("near_ret"),
    (0x1010, 0xEDE9): HookStop("near_ret"),
    (0x1010, 0xCC7F): HookStop("fixed_ips", ips=(0xCE13, 0x24D7, 0xCDCC)),
    (0x1010, 0xCD68): HookStop("fixed_ips", ips=(0xCE13, 0xCC7F, 0xCDCC)),
    (0x1010, 0xCE40): HookStop("near_ret"),
    (0x1010, 0xCE5C): HookStop("near_ret_or_fixed_ip", 0xCE40),
    (0x1010, 0xCF78): HookStop("fixed_ips", ips=(0xCF90, 0xCF97)),
    (0x1010, 0xCCAA): HookStop("fixed_ip", 0xCD08),
    (0x1010, 0xCCC4): HookStop("fixed_ip", 0xCD08),
    (0x1010, 0xCCF0): HookStop("fixed_ip", 0xCD08),
    (0x1010, 0x4CED): HookStop("near_ret"),
    (0x1010, 0x4D15): HookStop("near_ret"),
    (0x1010, 0x4D64): HookStop("near_ret"),
    (0x1010, 0x4D6F): HookStop("near_ret"),
    (0x1010, 0x511F): HookStop("near_ret"),
    (0x1010, 0x5160): HookStop("near_ret_or_fixed_ip", 0x5169),
    (0x1010, 0x5F61): HookStop("near_ret"),
    (0x1010, 0xA212): HookStop("near_ret"),
    (0x1010, 0x5BDC): HookStop("dispatch_5bdc"),
    (0x1010, 0x5C74): HookStop("near_ret"),
    (0x1010, 0x58DF): HookStop("postcopy_58df"),
    (0x1010, 0x61C5): HookStop("near_ret"),
    (0x1010, 0x61CA): HookStop("near_ret"),
    (0x1010, 0x5059): HookStop("near_ret"),
    (0x1010, 0x505B): HookStop("near_ret"),
    (0x1010, 0x5073): HookStop("near_ret"),
    (0x1010, 0x50C9): HookStop("near_ret"),
    (0x1010, 0x5DB2): HookStop("near_ret"),
    (0x1010, 0x5827): HookStop("fixed_ip", 0x58A4),
    (0x1010, 0x5A00): HookStop("dispatch_5a00"),
    (0x1010, 0x5A24): HookStop("dispatch_5a24"),
    (0x1010, 0x5A36): HookStop("dispatch_5a36"),
    (0x1010, 0x5A6C): HookStop("dispatch_5a6c"),
    (0x1010, 0x5AC8): HookStop("dispatch_5ac8"),
    (0x1010, 0x5A92): HookStop("dispatch_5a92"),
    (0x1010, 0x5EF9): HookStop("near_ret"),
    (0x1010, 0x7596): HookStop("dispatch_7596"),
    (0x1010, 0x768E): HookStop("tandy_layer_sprite_768e"),
    (0x1010, 0x7746): HookStop("near_ret"),
    (0x1010, 0xA846): HookStop("fixed_ip", 0xA849),
    (0x1010, 0xA849): HookStop("scan_draw_a849"),
    (0x1010, 0xA858): HookStop("dispatch_5ac8"),
    (0x1010, 0xA85B): HookStop("fixed_ips", ips=(0xA849, 0xA85E)),
    (0x1010, 0xA85E): HookStop("fixed_ip", 0xA861),
    (0x1010, 0xA861): HookStop("fixed_ips", ips=(0xA870, 0xA876)),
    (0x1010, 0xA870): HookStop("dispatch_5ac8"),
    (0x1010, 0xA873): HookStop("fixed_ips", ips=(0xA861, 0xA876)),
    (0x1010, 0xA876): HookStop("fixed_ip", 0xA879),
    (0x1010, 0xA879): HookStop("fixed_ip", 0xA87C),
    (0x1010, 0xA87C): HookStop("fixed_ips", ips=(0xA88B, 0xA891)),
    (0x1010, 0xA88B): HookStop("fixed_ip", 0xA88E),
    (0x1010, 0xA88E): HookStop("fixed_ips", ips=(0xA87C, 0xA891)),
    (0x1010, 0xA891): HookStop("fixed_ip", 0xA894),
    (0x1010, 0xA894): HookStop("fixed_ips", ips=(0xA8BE, 0xA8C4)),
    (0x1010, 0xA8BE): HookStop("dispatch_7596"),
    (0x1010, 0xA8C1): HookStop("fixed_ips", ips=(0xA894, 0xA8C4)),
    (0x1010, 0xA8C4): HookStop("fixed_ip", 0xA8C7),
    (0x1010, 0xA8C7): HookStop("scan_layer1_a8c7"),
    (0x1010, 0xA8F1): HookStop("dispatch_7596"),
    (0x1010, 0xA8F4): HookStop("fixed_ips", ips=(0xA8C7, 0xA8F7)),
    (0x1010, 0xA8F7): HookStop("near_ret_or_fixed_ip", 0xA8FF),
    (0x1010, 0xA90C): HookStop("scan_present_pair_a90c"),
    (0x1010, 0xA90F): HookStop("scan_present_a90f"),
    (0x1010, 0xA91E): HookStop("dispatch_5a92"),
    (0x1010, 0xA921): HookStop("fixed_ips", ips=(0xA90F, 0xA924)),
    (0x1010, 0xA924): HookStop("fixed_ip", 0xA927),
    (0x1010, 0xA927): HookStop("scan_present_a927"),
    (0x1010, 0xA93C): HookStop("near_ret"),
    (0x1010, 0xA940): HookStop("fixed_ips", ips=(0xA9DA, 0xA9E0)),
    (0x1010, 0x9FEA): HookStop("near_ret"),
    (0x1010, 0xD04D): HookStop("near_ret_or_fixed_ips", ips=(0xD160, 0x44AF, 0xD19F, 0xD229, 0xD183, 0xD24A, 0xD1DC, 0xD1F8, 0xD14D, 0xD152, 0xD13A, 0xD159)),
    (0x1010, 0xD007): HookStop.after_step("fixed_ips", ips=(0xD007, 0xD040)),
    (0x1010, 0xA936): HookStop("dispatch_5a92"),
    (0x1010, 0xA939): HookStop("fixed_ips", ips=(0xA927, 0xA93C)),
    (0x1010, 0xA9E0): HookStop("fixed_ips", ips=(0xAA01, 0xAA07)),
    (0x1010, 0xAA01): HookStop("dispatch_aa2b"),
    (0x1010, 0xAA04): HookStop("fixed_ips", ips=(0xA9E0, 0xAA07)),
    (0x1010, 0xAA07): HookStop("fixed_ip", 0xAA10),
    (0x1010, 0x77F6): HookStop("near_ret"),
    (0x1010, 0xAB34): HookStop("near_ret"),
    (0x1010, 0xAB4F): HookStop("near_ret"),
    (0x1010, 0xAC28): HookStop("near_ret_or_fixed_ip", 0xAA44),
    (0x1010, 0xAC81): HookStop("near_ret_or_fixed_ip", 0xACD9),
    (0x1010, 0xAC97): HookStop("near_ret_or_fixed_ip", 0xACD9),
    (0x1010, 0xBCB1): HookStop("near_ret"),
    (0x1010, 0xBC45): HookStop("near_ret"),
    (0x1010, 0xBC4B): HookStop("near_ret"),
    (0x1010, 0xAA2B): HookStop("dispatch_aa2b"),
    (0x1010, 0xAA10): HookStop("fixed_ips", ips=(0xAA1F, 0xAA25)),
    (0x1010, 0xAA1F): HookStop("dispatch_aa2b"),
    (0x1010, 0xAA22): HookStop("fixed_ips", ips=(0xAA10, 0xAA25)),
    (0x1010, 0xAA25): HookStop("near_ret"),
    (0x1010, 0xAB10): HookStop("near_ret"),
    (0x1010, 0xABA3): HookStop("near_ret_or_fixed_ips", ips=(0xABC0, 0xABBD, 0xACD9)),
    (0x1010, 0xAB59): HookStop("fixed_ip", 0xAB77),
    (0x1010, 0xAB61): HookStop("fixed_ip", 0xAB77),
    (0x1010, 0xAB69): HookStop("fixed_ip", 0xAB77),
    (0x1010, 0xAB71): HookStop("fixed_ip", 0xAB77),
    (0x1010, 0xAB77): HookStop("near_ret_or_fixed_ips", ips=(0xAB8F, 0xAB8C, 0xACD9)),
    (0x1010, 0xABCA): HookStop("near_ret_or_fixed_ip", 0xACD9),
    (0x1010, 0xEFAE): HookStop("dispatch_efae"),
    (0x1010, 0xAE09): HookStop("near_ret"),
    (0x1010, 0xAE2C): HookStop("near_ret"),
    (0x1010, 0xAE7D): HookStop("near_ret"),
    (0x1010, 0xAED8): HookStop("near_ret"),
    (0x1010, 0xAD60): HookStop("near_ret"),
    (0x1010, 0xAD5A): HookStop("near_ret"),
    (0x1010, 0xD281): HookStop("near_ret"),
    (0x1010, 0xAD04): HookStop("near_ret_or_fixed_ips", ips=(0xABCA, 0xAB71, 0xAB69, 0xAB61, 0xAB59, 0xABA3)),
}


def parse_addr(text: str) -> Addr:
    cs, ip = text.split(":", 1)
    return int(cs, 16) & 0xFFFF, int(ip, 16) & 0xFFFF


def install_hook_verifier(rt: Runtime, config: HookVerifierConfig) -> "HookVerifier":
    verifier = HookVerifier(rt, config)
    rt.cpu.hook_verifier = verifier.verify
    return verifier


class HookVerifier:
    def __init__(self, rt: Runtime, config: HookVerifierConfig) -> None:
        self.rt = rt
        self.config = config
        # Keep the hook table as it looked when verification was installed.
        # scripts/play.py installs UI pacing wrappers for a few hardware/boundary
        # hooks (50C9 retrace wait, 0679 timer wait, present blits) after creating
        # the verifier.  Those wrappers sleep, publish frames and raise control-flow
        # exceptions, which is correct for interactive execution but wrong inside a
        # differential hook transaction.  During verification, any hook listed in
        # cpu.hook_verifier_passthrough is restored from this table on both the
        # ASM oracle clone and the live hook side, so nested CALLs see the pure
        # environment hook instead of the UI wrapper.
        self._install_time_hooks = dict(rt.cpu.replacement_hooks)
        self._install_time_names = dict(rt.cpu.hook_names)
        self.counts: dict[Addr, int] = {}
        self.total_verified = 0
        self.skipped: set[Addr] = set()

    def verify(self, cpu: CPU8086, key: Addr, handler: Callable[[CPU8086], None], name: str) -> None:
        if not self._should_verify(key):
            try:
                handler(cpu)
            finally:
                if cpu.coverage_telemetry is not None:
                    cpu.coverage_telemetry.record_hook_unverified(key, name)
            return

        stop = DEFAULT_STOPS.get(key)
        if stop is None:
            msg = f"HOOK VERIFY MISSING METADATA {key[0]:04X}:{key[1]:04X} {name}: no continuation metadata"
            if self.config.require_metadata:
                raise HookVerifyDivergence(msg)
            if key not in self.skipped:
                print(msg.replace("MISSING METADATA", "SKIP"))
                self.skipped.add(key)
            try:
                handler(cpu)
            finally:
                if cpu.coverage_telemetry is not None:
                    cpu.coverage_telemetry.record_hook_skipped(key, name)
            return

        call_no = self.counts.get(key, 0) + 1
        self.counts[key] = call_no
        before = CPUState(**cpu.s.__dict__)
        if self.config.progress_callback is not None:
            self.config.progress_callback(f"verifying {key[0]:04X}:{key[1]:04X} {name} call {call_no}")
        asm_rt = self._clone_runtime()
        asm_cpu = asm_rt.cpu
        asm_cpu.hook_verifier = None
        asm_cpu.replacement_hooks.pop(key, None)
        asm_cpu.hook_names.pop(key, None)
        targets = stop.targets(asm_cpu, before)

        self._restore_passthrough_hooks(asm_cpu)
        asm_steps = self._run_asm_to_target(asm_cpu, targets, min_steps=stop.min_steps)
        with self._live_passthrough_hooks(cpu):
            handler(cpu)
        self.total_verified += 1
        if cpu.coverage_telemetry is not None:
            cpu.coverage_telemetry.record_hook_verified(key, name, asm_steps)

        report = self._diff_report(
            key=key,
            name=name,
            call_no=call_no,
            targets=targets,
            asm_rt=asm_rt,
            hook_rt=self.rt,
            asm_steps=asm_steps,
        )
        if report:
            if self.config.log_diffs or self.config.stop_on_diff:
                print(report)
            if self.config.stop_on_diff:
                raise HookVerifyDivergence(report)
        if self.config.max_verified is not None and self.total_verified >= self.config.max_verified:
            raise HookVerifyLimitReached(f"HOOK VERIFY LIMIT REACHED verified={self.total_verified}")

    def _should_verify(self, key: Addr) -> bool:
        if self.config.max_verified is not None and self.total_verified >= self.config.max_verified:
            return False
        return self.config.verify_all or key in self.config.hooks

    def _restore_passthrough_hooks(self, cpu: CPU8086) -> None:
        """Replace interactive passthrough wrappers with install-time base hooks.

        The pass-through set is owned by the live CPU and may be populated after
        this verifier is constructed.  That is intentional: play.py knows which
        hooks are UI pacing boundaries only after it has chosen the active video
        backend.
        """
        for key in getattr(cpu, "hook_verifier_passthrough", set()):
            if key in self._install_time_hooks:
                cpu.replacement_hooks[key] = self._install_time_hooks[key]
                if key in self._install_time_names:
                    cpu.hook_names[key] = self._install_time_names[key]
            else:
                cpu.replacement_hooks.pop(key, None)
                cpu.hook_names.pop(key, None)

    class _LivePassthroughHooks:
        def __init__(self, verifier: "HookVerifier", cpu: CPU8086) -> None:
            self.verifier = verifier
            self.cpu = cpu
            self.saved_hooks: dict[Addr, Callable[[CPU8086], None] | None] = {}
            self.saved_names: dict[Addr, str | None] = {}

        def __enter__(self) -> None:
            for key in getattr(self.cpu, "hook_verifier_passthrough", set()):
                self.saved_hooks[key] = self.cpu.replacement_hooks.get(key)
                self.saved_names[key] = self.cpu.hook_names.get(key)
                if key in self.verifier._install_time_hooks:
                    self.cpu.replacement_hooks[key] = self.verifier._install_time_hooks[key]
                    if key in self.verifier._install_time_names:
                        self.cpu.hook_names[key] = self.verifier._install_time_names[key]
                else:
                    self.cpu.replacement_hooks.pop(key, None)
                    self.cpu.hook_names.pop(key, None)

        def __exit__(self, exc_type, exc, tb) -> bool:
            for key, hook in self.saved_hooks.items():
                if hook is None:
                    self.cpu.replacement_hooks.pop(key, None)
                else:
                    self.cpu.replacement_hooks[key] = hook
            for key, name in self.saved_names.items():
                if name is None:
                    self.cpu.hook_names.pop(key, None)
                else:
                    self.cpu.hook_names[key] = name
            return False

    def _live_passthrough_hooks(self, cpu: CPU8086) -> "HookVerifier._LivePassthroughHooks":
        return HookVerifier._LivePassthroughHooks(self, cpu)

    def _run_asm_to_target(self, cpu: CPU8086, targets: tuple[Addr, ...], *, min_steps: int = 0) -> int:
        target_set = set(targets)
        min_steps = max(0, int(min_steps))
        for steps in range(self.config.asm_max_steps + 1):
            if steps >= min_steps and cpu.addr() in target_set:
                return steps
            if (
                cpu.addr() in ((0x1010, 0x0679), (0x1010, 0x067F))
                and cpu.addr() not in cpu.replacement_hooks
                and cpu.mem.rb(0x1010, 0x066B) == 0
            ):
                from .games.overkill.sounds.pc_speaker import deliver_overkill_timer_irq0

                if not deliver_overkill_timer_irq0(cpu):
                    raise HookVerifyDivergence(
                        "HOOK VERIFY ASM TIMER WAIT has no installed OVERKILL INT 08h "
                        f"at={cpu.s.cs:04X}:{cpu.s.ip:04X}"
                    )
            if (
                cpu.addr() in ((0x1010, 0x9921), (0x1010, 0x9926))
                and cpu.addr() not in cpu.replacement_hooks
                and cpu.mem.rb(cpu.s.ds & 0xFFFF, 0xBEFE) != 0
            ):
                from .games.overkill.sounds.pc_speaker import deliver_overkill_timer_irq0

                if not deliver_overkill_timer_irq0(cpu):
                    raise HookVerifyDivergence(
                        "HOOK VERIFY ASM SOUND WAIT has no installed OVERKILL INT 08h "
                        f"at={cpu.s.cs:04X}:{cpu.s.ip:04X}"
                    )
            if cpu.addr() == (0x1010, 0x072F):
                # OVERKILL's timer ISR chains the original BIOS INT 08h every
                # fourth tick via JMP FAR CS:[0738]. The runtime's IRQ deliverer
                # bounds that external BIOS path and returns to the interrupted
                # frame after the game-side work; mirror that here so 06E5 can be
                # differentially verified.
                cpu.s.ds = cpu.pop()
                cpu.s.ax = cpu.pop()
                cpu.set_flag(IF, True)
                if cpu.port_writer:
                    cpu.port_writer(cpu, 0x20, 0x20, 8)
                cpu.s.ip = cpu.pop()
                cpu.s.cs = cpu.pop()
                cpu.s.flags = cpu.pop() | 0x0002
                if cpu.addr() in target_set:
                    return steps
                continue
            cpu.step()
        labels = ", ".join(f"{cs:04X}:{ip:04X}" for cs, ip in targets)
        raise HookVerifyDivergence(
            f"HOOK VERIFY ASM TIMEOUT target={labels} "
            f"at={cpu.s.cs:04X}:{cpu.s.ip:04X}"
        )

    def _clone_runtime(self) -> Runtime:
        src = self.rt
        mem = Memory(0)
        mem.data = src.program.memory.data.copy()
        mem.size = src.program.memory.size
        mem.ega_planar = src.program.memory.ega_planar
        mem.ega_map_mask = src.program.memory.ega_map_mask
        mem.ega_read_plane = src.program.memory.ega_read_plane
        mem.ega_display_start = src.program.memory.ega_display_start

        dos = DOSMachine(src.dos.root)
        dos.stdout = list(src.dos.stdout)
        dos.files = {
            handle: FileHandle(f.path, bytearray(f.data), f.pos, f.writable)
            for handle, f in src.dos.files.items()
        }
        dos.next_handle = src.dos.next_handle
        dos.next_alloc_segment = src.dos.next_alloc_segment
        dos.allocation_limit_segment = src.dos.allocation_limit_segment
        dos.allocations = dict(src.dos.allocations)
        dos.video_mode = src.dos.video_mode
        dos.ticks = src.dos.ticks
        dos.vga_status_reads = src.dos.vga_status_reads
        dos._pit_channel2_access = getattr(src.dos, "_pit_channel2_access", 3)
        dos._pit_channel2_latch = getattr(src.dos, "_pit_channel2_latch", 0)
        dos._pit_channel2_write_low = getattr(src.dos, "_pit_channel2_write_low", True)
        dos.pit_channel2_reload = src.dos.pit_channel2_reload
        dos.speaker_control = src.dos.speaker_control
        dos._seq_index = getattr(src.dos, "_seq_index", 0)
        dos._crtc_index = getattr(src.dos, "_crtc_index", 0)
        dos.current_scancode = src.dos.current_scancode
        dos.console_input_fallback = src.dos.console_input_fallback
        dos.key_queue = list(src.dos.key_queue)
        dos.port_log = list(src.dos.port_log)

        cpu = CPU8086(mem, CPUState(**src.cpu.s.__dict__))
        cpu.halted = src.cpu.halted
        cpu.trace_enabled = False
        cpu.call_depth = src.cpu.call_depth
        cpu.instruction_count = src.cpu.instruction_count
        cpu.max_rep_count = src.cpu.max_rep_count
        cpu.replacement_hooks = dict(src.cpu.replacement_hooks)
        cpu.hook_names = dict(src.cpu.hook_names)
        cpu.hook_verifier_passthrough = set(src.cpu.hook_verifier_passthrough)
        self._restore_passthrough_hooks(cpu)
        cpu.interrupt_handler = dos.interrupt
        cpu.port_reader = dos.port_read
        cpu.port_writer = dos.port_write

        program = copy.copy(src.program)
        program.memory = mem
        return Runtime(program, cpu, dos)

    def _memory_ranges(self, rt: Runtime) -> list[MemoryRange]:
        if self.config.full_memory:
            return [MemoryRange("full memory", 0, len(rt.program.memory.data))]

        s = rt.cpu.s
        ranges = []

        def add_range(name: str, start: int, size: int) -> None:
            start = max(0, start)
            size = max(0, size)
            if any(existing.start == start and existing.size == size for existing in ranges):
                return
            ranges.append(MemoryRange(name, start, size))

        add_range("CS:0000-FFFF", linear(s.cs, 0), 0x10000)
        add_range("DS:0000-FFFF", linear(s.ds, 0), 0x10000)
        add_range("SS:0000-FFFF", linear(s.ss, 0), 0x10000)
        add_range("CPU A000:0000-FFFF", 0xA0000, 0x10000)
        add_range("CPU B800:0000-7FFF", 0xB8000, 0x8000)
        add_range("EGA shadow planes", EGA_APERTURE, EGA_SHADOW_SIZE)
        add_range("CS:5B00-5BFF temp rows", linear(s.cs, 0x5B00), 0x0100)
        sp = s.sp & 0xFFFF
        stack_start = (sp - 0x40) & 0xFFFF
        if stack_start + 0x100 <= 0x10000:
            add_range("stack around SS:SP", linear(s.ss, stack_start), 0x100)
        return ranges

    def _diff_report(
        self,
        *,
        key: Addr,
        name: str,
        call_no: int,
        targets: tuple[Addr, ...],
        asm_rt: Runtime,
        hook_rt: Runtime,
        asm_steps: int,
    ) -> str | None:
        sections: list[str] = []
        asm_cpu = asm_rt.cpu
        hook_cpu = hook_rt.cpu

        if asm_cpu.addr() != hook_cpu.addr():
            sections.append(
                "Continuation differences:\n"
                f"  ASM:  {asm_cpu.s.cs:04X}:{asm_cpu.s.ip:04X}\n"
                f"  HOOK: {hook_cpu.s.cs:04X}:{hook_cpu.s.ip:04X}"
            )

        reg_lines = []
        for field in ("ax", "bx", "cx", "dx", "si", "di", "bp", "sp"):
            av = getattr(asm_cpu.s, field) & 0xFFFF
            hv = getattr(hook_cpu.s, field) & 0xFFFF
            if av != hv:
                reg_lines.append(f"  {field.upper()}: asm={av:04X} hook={hv:04X}")
        if reg_lines:
            sections.append("Register differences:\n" + "\n".join(reg_lines))

        seg_lines = []
        for field in ("cs", "ds", "es", "ss"):
            av = getattr(asm_cpu.s, field) & 0xFFFF
            hv = getattr(hook_cpu.s, field) & 0xFFFF
            if av != hv:
                seg_lines.append(f"  {field.upper()}: asm={av:04X} hook={hv:04X}")
        if seg_lines:
            sections.append("Segment differences:\n" + "\n".join(seg_lines))

        if (asm_cpu.s.flags & 0x0FFF) != (hook_cpu.s.flags & 0x0FFF):
            sections.append(f"Flag differences:\n  FLAGS: asm={asm_cpu.s.flags & 0x0FFF:04X} hook={hook_cpu.s.flags & 0x0FFF:04X}")

        dos_lines = self._dos_diff(asm_rt, hook_rt)
        if dos_lines:
            sections.append("DOS/state differences:\n" + "\n".join(dos_lines))

        mem_sections = []
        for rng in self._memory_ranges(hook_rt):
            diff = self._range_diff(asm_rt.program.memory.data, hook_rt.program.memory.data, rng)
            if diff is not None:
                mem_sections.append(diff)
        if mem_sections:
            sections.append("Memory differences:\n" + "\n".join(mem_sections))

        if not sections:
            return None

        mode = asm_rt.program.memory.rw(asm_cpu.s.cs, 0x95BC)
        header = [
            "HOOK VERIFY DIVERGENCE",
            f"hook: {key[0]:04X}:{key[1]:04X} {name}",
            f"call: {call_no}",
            f"video: {self._video_name(mode)} ({mode:04X})",
            f"expected continuation: {self._format_targets(targets)}",
            f"ASM continuation: {asm_cpu.s.cs:04X}:{asm_cpu.s.ip:04X} after {asm_steps} steps",
            f"HOOK continuation: {hook_cpu.s.cs:04X}:{hook_cpu.s.ip:04X}",
        ]
        return "\n".join(header + ["", *sections])

    @staticmethod
    def _format_targets(targets: tuple[Addr, ...]) -> str:
        return ", ".join(f"{cs:04X}:{ip:04X}" for cs, ip in targets)

    def _dos_diff(self, asm_rt: Runtime, hook_rt: Runtime) -> list[str]:
        lines = []
        for field in (
            "next_handle",
            "next_alloc_segment",
            "allocation_limit_segment",
            "video_mode",
            "ticks",
            "vga_status_reads",
            "_seq_index",
            "_crtc_index",
            "current_scancode",
            "console_input_fallback",
        ):
            av = getattr(asm_rt.dos, field)
            hv = getattr(hook_rt.dos, field)
            if av != hv:
                lines.append(f"  {field}: asm={av!r} hook={hv!r}")
        for field in ("allocations", "key_queue", "stdout"):
            av = getattr(asm_rt.dos, field)
            hv = getattr(hook_rt.dos, field)
            if av != hv:
                lines.append(f"  {field}: asm={av!r} hook={hv!r}")
        if asm_rt.program.memory.ega_map_mask != hook_rt.program.memory.ega_map_mask:
            lines.append(f"  ega_map_mask: asm={asm_rt.program.memory.ega_map_mask:02X} hook={hook_rt.program.memory.ega_map_mask:02X}")
        if asm_rt.program.memory.ega_read_plane != hook_rt.program.memory.ega_read_plane:
            lines.append(f"  ega_read_plane: asm={asm_rt.program.memory.ega_read_plane} hook={hook_rt.program.memory.ega_read_plane}")
        if asm_rt.program.memory.ega_display_start != hook_rt.program.memory.ega_display_start:
            lines.append(
                f"  ega_display_start: asm={asm_rt.program.memory.ega_display_start:04X} "
                f"hook={hook_rt.program.memory.ega_display_start:04X}"
            )
        for field in (
            "_pit_channel2_access",
            "_pit_channel2_latch",
            "_pit_channel2_write_low",
            "pit_channel2_reload",
            "speaker_control",
        ):
            av = getattr(asm_rt.dos, field)
            hv = getattr(hook_rt.dos, field)
            if av != hv:
                lines.append(f"  {field}: asm={av!r} hook={hv!r}")
        if asm_rt.dos.port_log != hook_rt.dos.port_log:
            lines.append(
                "  port_log_tail:\n"
                f"    asm={asm_rt.dos.port_log[-8:]}\n"
                f"    hook={hook_rt.dos.port_log[-8:]}"
            )
        lines.extend(self._file_diff(asm_rt, hook_rt))
        return lines

    @staticmethod
    def _file_diff(asm_rt: Runtime, hook_rt: Runtime) -> list[str]:
        lines = []
        asm_handles = set(asm_rt.dos.files)
        hook_handles = set(hook_rt.dos.files)
        if asm_handles != hook_handles:
            lines.append(f"  file handles: asm={sorted(asm_handles)} hook={sorted(hook_handles)}")
        for handle in sorted(asm_handles & hook_handles):
            af = asm_rt.dos.files[handle]
            hf = hook_rt.dos.files[handle]
            for field in ("path", "pos", "writable"):
                av = getattr(af, field)
                hv = getattr(hf, field)
                if av != hv:
                    lines.append(f"  file[{handle}].{field}: asm={av!r} hook={hv!r}")
            if len(af.data) != len(hf.data):
                lines.append(f"  file[{handle}].data length: asm={len(af.data)} hook={len(hf.data)}")
                continue
            if af.data != hf.data:
                first = next(i for i, (a, h) in enumerate(zip(af.data, hf.data)) if a != h)
                lines.append(
                    f"  file[{handle}].data: first diff at {first} "
                    f"asm={af.data[first]:02X} hook={hf.data[first]:02X}"
                )
        return lines

    @staticmethod
    def _range_diff(asm: bytearray, hook: bytearray, rng: MemoryRange) -> str | None:
        start = max(0, rng.start)
        end = min(len(asm), len(hook), start + rng.size)
        asm_view = memoryview(asm)[start:end]
        hook_view = memoryview(hook)[start:end]
        if asm_view == hook_view:
            return None
        first = None
        count = 0
        for rel, (asm_byte, hook_byte) in enumerate(zip(asm_view, hook_view)):
            if asm_byte != hook_byte:
                count += 1
                if first is None:
                    first = start + rel
        if first is None:
            return None
        dump_start = max(start, first - 8)
        dump_end = min(end, first + 16)
        asm_hex = " ".join(f"{b:02X}" for b in asm[dump_start:dump_end])
        hook_hex = " ".join(f"{b:02X}" for b in hook[dump_start:dump_end])
        return (
            f"  range {rng.name}:\n"
            f"    differing bytes: {count}\n"
            f"    first diff: {first:05X} asm={asm[first]:02X} hook={hook[first]:02X}\n"
            f"    asm : {asm_hex}\n"
            f"    hook: {hook_hex}"
        )

    @staticmethod
    def _video_name(mode: int) -> str:
        return {0: "cga", 1: "ega", 2: "tandy"}.get(mode & 0xFFFF, "unknown")
