"""Shared detection of OVERKILL input-wait loops that produce no frame boundary.

Some original busy-wait loops poll the keyboard without ever reaching a timer
(1010:0679), retrace (1010:50C9), or presenter boundary.  Both emulation
drivers -- play.py's interactive ``emulator_loop`` and the headless
``run_frame_verifier`` -- must recognize these loops, otherwise demo replay
deadlocks: demo events are gated on a boundary counter, and a boundary-less
wait loop freezes that counter so a recorded key *release* can never be
delivered (the loop then waits forever for a release it cannot receive).

Keeping the detection here -- instead of duplicated inside one driver -- is what
lets the same fix apply to interactive play, ``--verify-hooks``, and
``--verify-frames`` alike.
"""
from __future__ import annotations

from dos_re.cpu import CPU8086

Addr = tuple[int, int]


def title_fire_release_wait(cpu: CPU8086) -> bool:
    """Detect the title/attract screen's wait-for-FIRE-release loop at D35C.

    The D318 title frame loop polls FIRE at D352; once FIRE (bit 10h of DS:98BE)
    is pressed it falls into a tight release loop:
    CALL 0162; TEST byte [98BE],10h; JNZ D35C.  Unlike the D318 body, this loop
    has no 0679 timer wait or 50C9 retrace wait, so it never produces a frame
    boundary.  Because CALL 0162 is hooked, a cooperative CPU burst usually
    lands at the 0162 entry rather than on the loop's own three instructions;
    recognize both (parked on D35C/D35F/D364, or inside the 0162 call this loop
    makes -- identified by the D35F return address, which distinguishes it from
    the D352 press poll returning to D355 and from every other 0162 caller).
    """
    cs, ip = cpu.addr()
    if cs != 0x1010:
        return False
    mem = cpu.mem
    in_loop = ip in (0xD35C, 0xD35F, 0xD364)
    if not in_loop and ip == 0x0162:
        in_loop = mem.rw(cpu.s.ss & 0xFFFF, cpu.s.sp & 0xFFFF) == 0xD35F
    if not in_loop:
        return False
    if mem.block(cs, 0xD35C, 10) != bytes.fromhex("e8 03 2e f6 06 be 98 10 75 f6"):
        return False
    return (mem.rb(cpu.s.ds & 0xFFFF, 0x98BE) & 0x10) != 0


# Canonical (kind, address) returned for a detected wait so that the frame
# verifier's reference and candidate sides agree on the boundary identity even
# if their cooperative bursts happen to stop on different instructions of the
# loop.  Using the loop head keeps compare_samples from flagging a spurious
# boundary-address difference.
_TITLE_FIRE_RELEASE_ADDR: Addr = (0x1010, 0xD35C)


# CBDD..CBE5: `mov al,[54]; cmp al,[54]; je $-6` -- the CBD5 frame-tick wait.
_FRAME_TICK_WAIT_SIG = bytes.fromhex("a0 54 00 3a 06 54 00 74 fa")


def advance_frame_tick_wait(cpu: CPU8086) -> bool:
    """Tick DS:[54] when a runtime is parked in the CBD5 frame-delay busy-wait.

    The menu-transition delay CB3E loops five times over CALL CBD5; each CBD5
    loads AL=[54] then spins ``cmp al,[54]; je`` until the INT 1Ch timer ISR
    (1010:06E5, whose tail does ``inc [54]; and [54],3``) advances the tick
    counter.  The frame verifier models time via the 0679 timer / 50C9 retrace
    boundaries and never fires that asynchronous ISR, so DS:[54] is frozen at 0
    and the loop spins until the frame budget -- the same boundary-less busy-wait
    problem the 0679/50C9 REFERENCE_ENV_HOOKS already solve, just keyed on the
    tick counter instead of a boundary address.  Interactive play fires the real
    ISR, so the live game is unaffected; this resolver is verifier-only.

    Advancing [54] one tick (matching 071D) lets the current CBD5 return and the
    delay drain in place.  Returns True when a tick was injected so the caller
    treats the step as handled and keeps stepping (no frame boundary is needed --
    both verifier sides tick identically and stay in lockstep).
    """
    cs, ip = cpu.addr()
    if cs != 0x1010 or ip not in (0xCBE0, 0xCBE4):
        return False
    mem = cpu.mem
    if mem.block(0x1010, 0xCBDD, 9) != _FRAME_TICK_WAIT_SIG:
        return False
    ds = cpu.s.ds & 0xFFFF
    # CBD5 only spins when the delay is armed ([55]!=0) and AL still equals the
    # frozen tick (otherwise the je falls through and CBD5 has already returned).
    if mem.rb(ds, 0x55) == 0 or (cpu.s.ax & 0xFF) != mem.rb(ds, 0x54):
        return False
    mem.wb(ds, 0x54, (mem.rb(ds, 0x54) + 1) & 0x03)
    return True


def frame_verify_input_wait(cpu: CPU8086) -> tuple[str, Addr] | None:
    """Frame-verifier adapter: return ("wait", canonical_addr) or None.

    Used as ``run_frame_verifier(input_wait_detector=...)`` so the headless and
    preview frame verifiers treat a boundary-less input-wait loop as a frame
    boundary, pump demo input there, and advance instead of spinning forever.

    Unlike :func:`title_fire_release_wait` (which accepts any instruction of the
    loop, because play.py only samples at coarse chunk boundaries), this fires
    *only* at the loop head D35C.  The frame verifier checks it every step, so
    both the reference and candidate stop at the identical instruction -- if they
    were allowed to stop at different sub-positions of the loop they would resume
    from different points when input is pumped and diverge spuriously.
    """
    # Resolve the CBD5 frame-delay timer busy-wait in place (advance DS:[54]).
    # No frame boundary is produced: the loop simply drains and execution
    # continues to the next real present/timer/retrace boundary.
    if advance_frame_tick_wait(cpu):
        return None
    if (cpu.s.cs & 0xFFFF) != 0x1010 or (cpu.s.ip & 0xFFFF) != 0xD35C:
        return None
    mem = cpu.mem
    if mem.block(0x1010, 0xD35C, 10) != bytes.fromhex("e8 03 2e f6 06 be 98 10 75 f6"):
        return None
    if (mem.rb(cpu.s.ds & 0xFFFF, 0x98BE) & 0x10) == 0:
        return None
    return "wait", _TITLE_FIRE_RELEASE_ADDR
