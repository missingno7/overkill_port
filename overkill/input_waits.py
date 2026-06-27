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


# The title/menu/level-select screens poll the keyboard through a *family* of
# byte-identical 10-byte busy-wait loops that never reach a 0679 timer or 50C9
# retrace boundary:
#
#     CALL 0162 ; (TEST|CMP) byte [98BE], imm8 ; (JE|JNZ) <loop head>
#
# read_player_input (0162) repacks DS:98BE, then the loop spins on it until the
# tested bit(s) change -- e.g. wait-for-FIRE-release (TEST [98BE],10h; JNZ self,
# at D35C/D305/D390), wait-for-all-release (CMP [98BE],0; JNZ self, at D43B/50D2),
# wait-for-any-press (CMP [98BE],0; JE self).  Only the CALL displacement, the
# compare and the branch sense differ between sites; the body is always 10 bytes
# with the branch jumping -10 back to the head, so it provably contains no
# boundary.  Replay must treat the head as one synthetic frame boundary so the
# recorded key change can be pumped in.  (Interactive play keeps a few extra
# screen-specific gates in play.py; the families that deadlock demo replay live
# here so the verifier and play.py share them.)


def _is_input_wait_head(mem, head: int) -> bool:
    """True if 1010:head heads a ``CALL 0162; cmp/test [98BE],imm8; Jcc head`` loop."""
    b = mem.block(0x1010, head & 0xFFFF, 10)
    if b[0] != 0xE8:                                              # CALL rel16 ...
        return False
    if ((head + 3 + (b[1] | (b[2] << 8))) & 0xFFFF) != 0x0162:    # ... to read_player_input
        return False
    if b[3:5] not in (b"\xf6\x06", b"\x80\x3e"):                  # TEST or CMP byte ptr ...
        return False
    if b[5:7] != b"\xbe\x98":                                     # ... [98BE]
        return False
    return b[8] in (0x74, 0x75) and b[9] == 0xF6                  # JE/JNZ, rel8 -10 -> head


def _input_wait_spinning(mem, ds: int, head: int) -> bool:
    """For a matched head, True iff the branch will jump back now (still spinning)."""
    b = mem.block(0x1010, head & 0xFFFF, 10)
    imm = b[7]
    val = mem.rb(ds, 0x98BE)
    zero = (val & imm) == 0 if b[3] == 0xF6 else (val & 0xFF) == imm  # TEST vs CMP -> ZF
    return zero if b[8] == 0x74 else not zero                        # JE takes ZF; JNZ takes !ZF


def _flag_poll_spin(mem, ds: int, head: int) -> bool:
    """True if 1010:head is a ``CMP byte [98xx],imm8 ; Jcc head`` 2-instruction spin
    that is currently looping.

    Distinct from the CALL-0162 family: these poll a single input/menu flag byte
    (e.g. the selector's confirm-key debounce ``CMP [98E4],1; JE D434``, which spins
    until INT 09h clears the key-state on release).  A 2-instruction self-loop has
    nothing between the compare and the back-branch, so it is provably boundary-less
    and only a pumped key change can end it.
    """
    b = mem.block(0x1010, head & 0xFFFF, 7)
    if b[0:2] != b"\x80\x3e":            # CMP byte ptr [disp16], imm8
        return False
    off = b[2] | (b[3] << 8)
    if not (0x98BE <= off <= 0x98FF):    # input/menu flag area only
        return False
    if b[5] not in (0x74, 0x75) or b[6] != 0xF9:  # JE/JNZ, rel8 -7 -> head
        return False
    zero = (mem.rb(ds, off) & 0xFF) == b[4]        # CMP -> ZF
    return zero if b[5] == 0x74 else not zero       # JE takes ZF; JNZ takes !ZF


def _selector_idle_head(cpu: CPU8086):
    """Return the level/difficulty selector's idle-loop head (D445), or None.

    The selector dispatch loop is longer than the simple press/release family:

        D445: CMP [98E4],1 ; JE <confirm>     ; loop head (exit when confirmed)
        D44C: CALL 0162                        ; read_player_input
              <TEST [98BE],bit ; JNE handler>  ; x4 direction bits
              TEST [98BE],10h ; JE D445        ; idle -> spin back to the head
        ... handlers adjust [beda] and RET / JMP back to D445 ...

    Every iteration passes back through D445 and the loop never reaches a timer or
    retrace boundary, so replay must treat D445 as a synthetic boundary until a
    recorded key advances or confirms the selection ([98E4]==1).  Matched by the
    head signature so it is build-displacement independent; also recognized when a
    coarse sampler parks inside the hooked 0162 call (return address D44F).
    """
    cs, ip = cpu.addr()
    if cs != 0x1010:
        return None
    mem = cpu.mem
    cands = [ip, (ip - 7) & 0xFFFF]  # head, or parked on the CALL at head+7
    if ip == 0x0162:
        cands.append((mem.rw(cpu.s.ss & 0xFFFF, cpu.s.sp & 0xFFFF) - 0x0A) & 0xFFFF)
    for head in cands:
        b = mem.block(0x1010, head & 0xFFFF, 10)
        if b[0:5] != b"\x80\x3e\xe4\x98\x01" or b[5] != 0x74 or b[7] != 0xE8:
            continue  # CMP [98E4],1 ; JE rel8 ; CALL ...
        if ((head + 10 + (b[8] | (b[9] << 8))) & 0xFFFF) != 0x0162:
            continue  # ... read_player_input
        if mem.rb(cpu.s.ds & 0xFFFF, 0x98E4) != 1:  # not yet confirmed -> still idle
            return head
    return None


def title_fire_release_wait(cpu: CPU8086) -> bool:
    """Detect a boundary-less ``CALL 0162`` keyboard-poll loop (title *and* menus).

    Originally only the title screen's D35C fire-release loop was handled; the
    level-select and other menu screens use byte-identical loops at other
    addresses (D305/D390/D43B/...), which deadlocked demo replay crossing them.
    Recognize the whole family by shape, at any head.

    Because CALL 0162 is hooked, a cooperative CPU burst usually lands at the 0162
    entry rather than on the loop's own three instructions; recognize both -- parked
    on the head / head+3 (compare) / head+8 (branch), or inside the 0162 call this
    loop makes (identified by the return address head+3, after the CALL).
    """
    cs, ip = cpu.addr()
    if cs != 0x1010:
        return False
    mem = cpu.mem
    if ip == 0x0162:
        # Inside the hooked read_player_input: the return address is head+3.
        heads = (((mem.rw(cpu.s.ss & 0xFFFF, cpu.s.sp & 0xFFFF) - 3) & 0xFFFF),)
    else:
        heads = (ip, (ip - 3) & 0xFFFF, (ip - 8) & 0xFFFF)  # head / compare / branch
    ds = cpu.s.ds & 0xFFFF
    if any(_is_input_wait_head(mem, h) and _input_wait_spinning(mem, ds, h) for h in heads):
        return True
    if _flag_poll_spin(mem, ds, ip) or _flag_poll_spin(mem, ds, (ip - 5) & 0xFFFF):
        return True  # 2-instr flag-poll: head, or coarse-parked on the branch
    return _selector_idle_head(cpu) is not None


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

    Covers every boundary-less keyboard wait the menus use: the CALL-0162 press/
    release family, the 2-instruction [98xx] flag-poll (D434), and the level-select
    idle loop (D445).  Unlike :func:`title_fire_release_wait` (which accepts any
    instruction of the loop, because play.py only samples at coarse chunk
    boundaries), this fires *only* at each loop's head.  The frame verifier checks
    it every step, so both the reference and candidate stop at the identical
    instruction -- if they were allowed to stop at different sub-positions they
    would resume from different points when input is pumped and diverge spuriously.
    The canonical address is that head, so both sides agree.
    """
    # Resolve the CBD5 frame-delay timer busy-wait in place (advance DS:[54]).
    # No frame boundary is produced: the loop simply drains and execution
    # continues to the next real present/timer/retrace boundary.
    if advance_frame_tick_wait(cpu):
        return None
    cs, ip = cpu.addr()
    mem = cpu.mem
    ds = cpu.s.ds & 0xFFFF
    if cs != 0x1010:
        return None
    if _is_input_wait_head(mem, ip) and _input_wait_spinning(mem, ds, ip):
        return "wait", (0x1010, ip)
    if _flag_poll_spin(mem, ds, ip):  # 2-instruction [98xx] flag-poll spin (e.g. D434)
        return "wait", (0x1010, ip)
    # Selector idle loop: fire only at the exact head (every-step lockstep); the
    # multi-candidate lookup also matches the body, which is for play.py's coarse
    # sampler -- here it would double-fire per iteration, so require head == ip.
    head = _selector_idle_head(cpu)
    if head is not None and head == (cpu.s.ip & 0xFFFF):
        return "wait", (0x1010, head)
    return None
