"""The CPUless FRAME DRIVER -- the one per-frame model for the generated spine.

There is no interpreter here and no CPU to step: the recovered corpus runs as
plain Python and calls back OUT to the platform.  So the frame loop cannot be a
loop around a stepper -- it lives INSIDE the seam the recovered code reaches on
its own.

``boundary``
    OVERKILL paces off ``cs:[066B]``, a tick its IRQ0 ISR ``1010:06E5`` bumps
    (via ``1010:066C``, ``inc byte cs:[066B]``).  The wait is ``1010:0679``:
    ``cmp byte cs:[066B],0 ; jz self ; ret``.  That address is DECLARED a
    boundary head (``artifacts/lift_boundary_heads.txt``), so the GENERATED body
    calls ``plat.boundary(0x1010, 0x0679, 0x067F, regs, cost)`` from inside its
    own poll loop and this driver, installed on ``plat.boundary_cb``, decides
    whether to park.  The spine owns the yield; the host only answers it.

    This replaces a host OVERRIDE that used to intercept ``1010:0679`` and call
    a host yield.  That was flow the host invented, running BESIDE the generated
    program rather than inside it -- and it was also inert: it looked up
    ``plat.boundary`` expecting ``OverkillPlatform``'s one-argument host-yield
    method and got ``CPUlessPlatformRuntime.boundary``, the five-argument
    boundary-head observer, so the call raised ``TypeError``.  A seam that can
    only work against one of two platforms is not a seam.

PARK ON RE-ARRIVAL
    The 1st pass at a head in a frame lets the wait body run to steady state;
    the 2nd pass proves the wait is still unsatisfied with nothing left to do --
    that IS the frame boundary.  The shape is forced by where the observer sits:
    it fires AFTER the poll instruction, so a tick delivered during the park is
    only observed on the NEXT trip round the loop.  Parking on pass 1 cuts the
    frame early.  (skyroads_port/skyroads/cpuless_driver.py reached the same
    model independently; two ports agreeing is the argument for promoting it
    into dos_re.  Do not refactor skyroads from here.)

ORDER WITHIN A FRAME BOUNDARY -- fixed here, and getting it wrong is SILENT
    1. hand the FINISHED frame over (``present``),
    2. apply the NEXT frame's input BEFORE it renders (input N affects frame N),
    3. deliver that frame's timer IRQs through the game's OWN recovered ISR.
    A wrong order shows up only as a one-frame lag in a differential.

CPU-FREE by construction: this module imports nothing but the recovered ISR the
caller hands it.  ``dos_re/tools/lint_cpuless.py`` proves the whole reachable
graph.
"""
from __future__ import annotations

#: Register bundle the recovered IRQ0 ISR (``1010:06E5``) takes.  It is the
#: game's real INT 08h handler -- installed in the vector table of every
#: post-init snapshot -- and it is flags-live and CS-live (it far-calls the
#: AdLib driver at ``2032:0000`` and reads ``cs:[0738]`` to chain the original
#: BIOS handler), so ``cs`` and ``_flags_in`` are part of its contract.
TIMER_INPUTS = ("ax", "bp", "bx", "cs", "cx", "di", "ds", "dx", "es", "si",
                "sp", "ss")

#: OVERKILL's pacing: 2 IRQ0 ticks per displayed frame.  MEASURED, not assumed
#: -- the demo-lockstep gate records the INT 08h tick count per frame window
#: from the live vector (``1010:06E5``) and the distribution over the 8292-frame
#: L1 demo is ``{0: 2, 1: 1, 2: 8284, 7: 1, 402: 4}``: 2 ticks in 99.9% of
#: frames, the outliers being the boot window and the four death/respawn
#: continuations.  It also agrees with the programmed clock: the game's PIT
#: installer ``1010:068A`` writes divisor 0x4000, i.e. 1193182/16384 = 72.83 Hz
#: IRQ0, and 72.83/2 = 36.4 displayed frames per second.
#: NOT skyroads' 6 -- that is its own 180 Hz IRQ0 over 30 Hz frames.
TIMER_IRQS_PER_FRAME = 2


class CPUlessFrameDriver:
    """Drives frames for OVERKILL's recovered corpus under a CPUless runtime.

    ``present(frame)`` is called with each finished frame's number -- draw it,
    capture it, whatever the consumer needs.  It may raise to stop the run (the
    exception propagates out through the recovered call stack to the caller of
    the root).

    ``supply_input(frame, regs)`` is called for the UPCOMING frame, before it
    renders, so the consumer can deliver that frame's keys.
    """

    def __init__(self, mem, rt, timer_isr, *, present, supply_input=None,
                 irqs: int = TIMER_IRQS_PER_FRAME):
        self.mem = mem
        self.rt = rt
        self.timer_isr = timer_isr
        self.irqs = irqs
        self._present = present
        self._supply_input = supply_input
        self.frame = 0
        #: the boundary head that last cut a frame, ``(cs, ip)`` -- the witness a
        #: consumer reports ("reached the frame loop at 1010:0679").  None while
        #: no head has parked yet.
        self.head: "tuple[int, int] | None" = None
        self._seen: "set[tuple[int, int]]" = set()

    # -- the seam ----------------------------------------------------------

    def boundary(self, head_cs, head_ip, resume_ip, regs, cost):
        """``plat.boundary_cb``: park on RE-arrival (see the module docstring).

        Returns the platform-boundary contract ``(regs, flags, extra_cost)``.
        The register bundle is handed straight back: the recovered ISRs this
        driver runs take their own copies of the guest state through ``mem``,
        and the waiting function's live registers are unchanged by a park.
        """
        key = (head_cs, head_ip)
        if key not in self._seen:
            self._seen.add(key)             # 1st pass: let the wait body run
            return regs, regs.get("_flags_in", 2), 0
        self.head = key
        self.advance(regs)                  # 2nd pass: the frame is done
        return regs, regs.get("_flags_in", 2), 0

    def advance(self, regs):
        """Hand over the finished frame, then prepare the next one."""
        self._present(self.frame)
        self.frame += 1
        self._seen.clear()                  # a new frame starts a fresh pass count
        if self._supply_input is not None:
            self._supply_input(self.frame, regs)
        for _ in range(self.irqs):
            kw = {k: regs[k] for k in TIMER_INPUTS if k in regs}
            kw["_flags_in"] = regs.get("_flags_in", 2)
            kw["_df"] = regs.get("_df", 0)
            self.timer_isr(self.mem, self.rt, **kw)

    def install(self, rt) -> "CPUlessFrameDriver":
        """Wire the seam on a ``CPUlessPlatformRuntime`` and return self."""
        rt.boundary_cb = self.boundary
        return self
