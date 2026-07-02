from __future__ import annotations

from dataclasses import dataclass

from dos_re.cpu import CPU8086, CPUState, IF
from dos_re.runtime import Runtime
from dos_re.verification import (
    Addr,
    HookVerifier as _GenericHookVerifier,
    HookVerifierConfig,
    HookVerifyDivergence,
    HookVerifyLimitReached,
    MemoryRange,
    GenericHookStop,
    parse_addr,
)
from overkill.sounds.loaded_driver import OPTIONAL_SOUND_DRIVER_SEGMENT


@dataclass(frozen=True)
class HookStop(GenericHookStop):
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
        try:
            return super().targets(cpu, before)
        except ValueError:
            pass
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
    (0x1010, 0xB00D): HookStop("near_ret"),
    (0x1010, 0xB032): HookStop("near_ret"),
    (0x1010, 0xBDE3): HookStop("near_ret_or_fixed_ip", 0x5059),
    (0x1010, 0xBDD0): HookStop("near_ret_or_fixed_ip", 0x5059),
    (0x1010, 0x8331): HookStop("near_ret"),
    (0x1010, 0x835B): HookStop("near_ret"),
    (0x1F8F, 0x081D): HookStop("far_ret"),
    (0x1F8F, 0x0922): HookStop("far_ret"),
    (0x1F8F, 0x0960): HookStop("near_ret"),
    # Temporary LZEXE-like bootstrap stubs are dynamic init materialization, not
    # game runtime, but their hot loop has an exact fixed continuation at 00FC.
    (0x1B65, 0x0069): HookStop("fixed_ip", 0x00FC),
    (0x1C43, 0x0069): HookStop("fixed_ip", 0x00FC),
    (0x23AD, 0x0069): HookStop("fixed_ip", 0x00FC),
    # Loaded optional AdLib driver at 2032:*; these are near/far routines inside
    # the resident sound driver selected by the compact PSP tail.
    (OPTIONAL_SOUND_DRIVER_SEGMENT, 0x0000): HookStop("far_ret"),
    (OPTIONAL_SOUND_DRIVER_SEGMENT, 0x0063): HookStop("near_ret"),
    (OPTIONAL_SOUND_DRIVER_SEGMENT, 0x00CD): HookStop("near_ret"),
    (OPTIONAL_SOUND_DRIVER_SEGMENT, 0x0181): HookStop("fixed_ip", 0x00F7),
    (OPTIONAL_SOUND_DRIVER_SEGMENT, 0x0244): HookStop("near_ret"),
    (OPTIONAL_SOUND_DRIVER_SEGMENT, 0x024F): HookStop("near_ret"),
    (OPTIONAL_SOUND_DRIVER_SEGMENT, 0x02AA): HookStop("near_ret"),
    (OPTIONAL_SOUND_DRIVER_SEGMENT, 0x02C9): HookStop("near_ret"),
    (OPTIONAL_SOUND_DRIVER_SEGMENT, 0x02F6): HookStop("near_ret"),
    (OPTIONAL_SOUND_DRIVER_SEGMENT, 0x0409): HookStop("near_ret"),
    (OPTIONAL_SOUND_DRIVER_SEGMENT, 0x04E9): HookStop("near_ret"),
    (OPTIONAL_SOUND_DRIVER_SEGMENT, 0x0557): HookStop("near_ret"),
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
    (0x1010, 0xB24D): HookStop("fixed_ips", ips=(0xAD5A, 0xADC9)),
    (0x1010, 0xB15A): HookStop("near_ret"),
    (0x1010, 0xB1B0): HookStop("near_ret"),
    (0x1010, 0xB86D): HookStop("fixed_ip", 0xBC4B),
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
    (0x1010, 0x3E12): HookStop("near_ret"),
    (0x1010, 0x3EE1): HookStop("near_ret"),
    (0x1010, 0x3EFB): HookStop("near_ret"),
    (0x1010, 0x3EFC): HookStop("near_ret"),
    (0x1010, 0x447B): HookStop("near_ret"),
    (0x1010, 0x469F): HookStop("near_ret"),
    (0x1010, 0x477E): HookStop("near_ret"),
    (0x1010, 0x497A): HookStop("near_ret"),
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
    (0x1010, 0x3824): HookStop("near_ret"),
    (0x1010, 0x4E0D): HookStop("near_ret"),
    (0x1010, 0x4E26): HookStop("near_ret"),
    (0x1010, 0x35AA): HookStop("near_ret"),
    (0x1010, 0x35CC): HookStop("near_ret"),
    (0x1010, 0x3657): HookStop("near_ret"),
    (0x1010, 0x7524): HookStop("near_ret"),
    (0x1010, 0x7573): HookStop("near_ret"),
    (0x1010, 0x8209): HookStop("near_ret"),
    (0x1010, 0x7547): HookStop("near_ret_or_fixed_ip", 0x7550),
    (0x1010, 0xA4EA): HookStop("near_ret_or_fixed_ip", 0x7550),
    (0x1010, 0xA4D7): HookStop("near_ret_or_fixed_ip", 0x7550),
    (0x1010, 0xA571): HookStop("near_ret"),
    (0x1010, 0xA515): HookStop("near_ret"),
    (0x1010, 0xA584): HookStop("near_ret"),
    (0x1010, 0xA3CA): HookStop("near_ret"),
    (0x1010, 0xA3FF): HookStop("near_ret"),
    (0x1010, 0xA2A0): HookStop("near_ret"),
    (0x1010, 0xA2F6): HookStop("near_ret"),
    (0x1010, 0xA337): HookStop("near_ret"),
    (0x1010, 0xA5D1): HookStop("near_ret"),
    (0x1010, 0xA5EA): HookStop("near_ret"),
    (0x1010, 0xA5F9): HookStop("near_ret"),
    (0x1010, 0xA607): HookStop("near_ret"),
    (0x1010, 0xA616): HookStop("near_ret"),
    (0x1010, 0xA63C): HookStop("near_ret"),
    (0x1010, 0xA648): HookStop("near_ret"),
    (0x1010, 0xA662): HookStop("near_ret"),
    (0x1010, 0xAFD8): HookStop("near_ret"),
    (0x1010, 0xAEE4): HookStop("near_ret"),
    (0x1010, 0xAF22): HookStop("near_ret"),
    (0x1010, 0xAF60): HookStop("near_ret"),
    (0x1010, 0xAF63): HookStop("near_ret"),
    (0x1010, 0xA66F): HookStop("near_ret"),
    (0x1010, 0xA746): HookStop("near_ret"),
    (0x1010, 0xA7E3): HookStop("near_ret"),
    (0x1010, 0xA74E): HookStop("near_ret"),
    (0x1010, 0xA7D0): HookStop("near_ret"),
    (0x1010, 0xA6FE): HookStop("near_ret"),
    (0x1010, 0xA781): HookStop("near_ret"),
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
    (0x1010, 0xCD8D): HookStop("fixed_ip", 0xCE02),
    (0x1010, 0xCDAA): HookStop("fixed_ip", 0xCE02),
    (0x1010, 0xCD68): HookStop("fixed_ips", ips=(0xCE13, 0xCC7F, 0xCDCC)),
    (0x1010, 0xCE40): HookStop("near_ret"),
    (0x1010, 0xCE5C): HookStop("near_ret_or_fixed_ip", 0xCE40),
    (0x1010, 0xCF78): HookStop("fixed_ips", ips=(0xCF90, 0xCF97)),
    (0x1010, 0x558B): HookStop.after_step("near_ret_or_fixed_ips", ips=(0x558B, 0x55FD)),
    (0x1010, 0x986E): HookStop.after_step("fixed_ips", ips=(0x986E, 0x9875)),
    (0x1010, 0x989E): HookStop.after_step("fixed_ips", ips=(0x989E, 0x98B6)),
    (0x1010, 0x98D8): HookStop.after_step("fixed_ips", ips=(0x98D8, 0x98DF)),
    (0x1010, 0x07C4): HookStop.after_step("fixed_ips", ips=(0x07C4, 0x07CB)),
    (0x1010, 0x07D0): HookStop.after_step("fixed_ips", ips=(0x07D0, 0x07D7)),
    (0x1010, 0x07D7): HookStop.after_step("fixed_ips", ips=(0x07D7, 0x07DE)),
    (0x1010, 0x4E9F): HookStop("near_ret"),
    (0x1010, 0x4EBF): HookStop("near_ret"),
    (0x1010, 0x53C9): HookStop.after_step("fixed_ips", ips=(0x53C9, 0x5408, 0x541E, 0x53FC, 0x54A7, 0x54AF)),
    (0x1010, 0x5497): HookStop("near_ret_or_fixed_ips", ips=(0x54A7, 0x54AF)),
    (0x1010, 0x50AB): HookStop("near_ret"),
    (0x1010, 0x50BA): HookStop("near_ret"),
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
    (0x1010, 0x60A2): HookStop("near_ret"),
    (0x1010, 0x97B2): HookStop.after_step("fixed_ips", ips=(0x97B2, 0x9734, 0x9902, 0x9908, 0x9862)),
    (0x1010, 0x9B2E): HookStop("near_ret"),
    (0x1010, 0x9CB6): HookStop("near_ret"),
    (0x1010, 0x9E19): HookStop("near_ret"),
    (0x1010, 0xA067): HookStop("near_ret"),
    (0x1010, 0x9FAF): HookStop("near_ret"),
    (0x1010, 0xD318): HookStop.after_step("near_ret_or_fixed_ip", ip=0xD318),
    (0x1010, 0xD367): HookStop("near_ret"),
    (0x1010, 0x5EDB): HookStop("near_ret"),
    (0x1010, 0xA212): HookStop("near_ret"),
    (0x1010, 0x5BDC): HookStop("dispatch_5bdc"),
    (0x1010, 0x5C74): HookStop("near_ret"),
    (0x1010, 0x58DF): HookStop("postcopy_58df"),
    (0x1010, 0x61C7): HookStop("near_ret"),
    (0x1010, 0x61F7): HookStop("fixed_ip", 0x61FC),
    (0x1010, 0x61DC): HookStop("near_ret"),
    (0x1010, 0x61CA): HookStop("near_ret"),
    (0x1010, 0x613E): HookStop("near_ret"),
    (0x1010, 0x615A): HookStop("near_ret"),
    (0x1010, 0x6120): HookStop("near_ret"),
    (0x1010, 0x8517): HookStop("near_ret"),
    (0x1010, 0x852B): HookStop("near_ret"),
    (0x1010, 0x859E): HookStop("near_ret"),
    (0x1010, 0x85D5): HookStop("near_ret"),
    (0x1010, 0x99CD): HookStop("fixed_ip", 0x99DD),
    (0x1010, 0x9CD9): HookStop("near_ret"),
    (0x1010, 0x9CF1): HookStop("near_ret"),
    (0x1010, 0xA031): HookStop("near_ret"),
    (0x1010, 0x9BFB): HookStop("near_ret"),
    (0x1010, 0x9BFE): HookStop("near_ret"),
    (0x1010, 0x9C01): HookStop("near_ret"),
    (0x1010, 0x9908): HookStop.after_step("fixed_ips", ips=(0x9773, 0x9921)),
    (0x1010, 0x9928): HookStop("fixed_ip", 0x9773),
    (0x1010, 0x6296): HookStop("near_ret"),
    (0x1010, 0xC3BF): HookStop("fixed_ip", 0xC3E7),
    (0x1010, 0xC3F1): HookStop("fixed_ip", 0xC42F),
    (0x1010, 0xC4E5): HookStop("fixed_ip", 0xC51D),
    (0x1010, 0xC4DB): HookStop("near_ret"),
    (0x1010, 0xC51D): HookStop("fixed_ip", 0x859E),
    (0x1010, 0x6176): HookStop("near_ret"),
    (0x1010, 0x9720): HookStop("fixed_ip", 0x9744),
    (0x1010, 0x5059): HookStop("near_ret"),
    (0x1010, 0x505B): HookStop("near_ret"),
    (0x1010, 0x4FF9): HookStop("near_ret"),
    (0x1010, 0x5073): HookStop("near_ret"),
    (0x1010, 0x50C9): HookStop("near_ret"),
    (0x1010, 0x5DB2): HookStop("near_ret"),
    (0x1010, 0xB729): HookStop("near_ret"),
    (0x1010, 0x5E42): HookStop("near_ret"),
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
    (0x1010, 0x77C5): HookStop("near_ret"),
    (0x1010, 0x77F6): HookStop("near_ret"),
    (0x1010, 0xAB34): HookStop("near_ret"),
    (0x1010, 0xAB4F): HookStop("near_ret"),
    (0x1010, 0xAC28): HookStop("near_ret_or_fixed_ip", 0xAA44),
    (0x1010, 0xAC81): HookStop("near_ret_or_fixed_ip", 0xACD9),
    (0x1010, 0xAC97): HookStop("near_ret_or_fixed_ip", 0xACD9),
    (0x1010, 0xAA71): HookStop("near_ret"),
    (0x1010, 0xBCB1): HookStop("near_ret"),
    (0x1010, 0xBC45): HookStop("near_ret"),
    (0x1010, 0xBC4B): HookStop("near_ret"),
    (0x1010, 0xAA2B): HookStop("dispatch_aa2b"),
    (0x1010, 0xAA44): HookStop("near_ret"),
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




class HookVerifier(_GenericHookVerifier):
    def __init__(self, rt: Runtime, config: HookVerifierConfig) -> None:
        super().__init__(
            rt,
            config,
            DEFAULT_STOPS,
            asm_wait_handler=_overkill_asm_wait_handler,
            context_lines=_overkill_context_lines,
        )


def install_hook_verifier(rt: Runtime, config: HookVerifierConfig) -> HookVerifier:
    verifier = HookVerifier(rt, config)
    rt.cpu.hook_verifier_verify_nested_calls = config.verify_nested_hooks
    rt.cpu.hook_verifier = verifier.verify
    return verifier


def _overkill_context_lines(rt: Runtime) -> list[str]:
    mode = rt.program.memory.rw(rt.cpu.s.cs, 0x95BC)
    return [f"video: {_video_name(mode)} ({mode:04X})"]


def _video_name(mode: int) -> str:
    return {0: "cga", 1: "ega", 2: "tandy"}.get(mode & 0xFFFF, "unknown")


def _overkill_asm_wait_handler(cpu: CPU8086, target_set: set[Addr]) -> bool:
    if (
        cpu.addr() in ((0x1010, 0x0679), (0x1010, 0x067F))
        and cpu.addr() not in cpu.replacement_hooks
        and cpu.mem.rb(0x1010, 0x066B) == 0
    ):
        from .sounds.timing import deliver_overkill_timer_irq0

        if not deliver_overkill_timer_irq0(cpu):
            raise HookVerifyDivergence(
                "HOOK VERIFY ASM TIMER WAIT has no installed OVERKILL INT 08h "
                f"at={cpu.s.cs:04X}:{cpu.s.ip:04X}"
            )
        return True
    if (
        cpu.addr() in ((0x1010, 0x9921), (0x1010, 0x9926))
        and cpu.addr() not in cpu.replacement_hooks
        and cpu.mem.rb(cpu.s.ds & 0xFFFF, 0xBEFE) != 0
    ):
        from .sounds.timing import deliver_overkill_timer_irq0

        if not deliver_overkill_timer_irq0(cpu):
            raise HookVerifyDivergence(
                "HOOK VERIFY ASM SOUND WAIT has no installed OVERKILL INT 08h "
                f"at={cpu.s.cs:04X}:{cpu.s.ip:04X}"
            )
        return True
    if cpu.addr() == (0x1010, 0x072F):
        # OVERKILL's timer ISR chains the original BIOS INT 08h every fourth
        # tick via JMP FAR CS:[0738]. The runtime's IRQ deliverer bounds that
        # external BIOS path and returns to the interrupted frame after the
        # game-side work; mirror that here so 06E5 can be differentially verified.
        cpu.s.ds = cpu.pop()
        cpu.s.ax = cpu.pop()
        cpu.set_flag(IF, True)
        if cpu.port_writer:
            cpu.port_writer(cpu, 0x20, 0x20, 8)
        cpu.s.ip = cpu.pop()
        cpu.s.cs = cpu.pop()
        cpu.s.flags = cpu.pop() | 0x0002
        return True
    return False
