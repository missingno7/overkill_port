"""THE FRAME DRIVER answers the boundary heads the GENERATED spine calls.

These pin the properties the whole no-CPU frame model rests on, and they replace the two behaviour
tests that used to live in `test_cpuless_overrides.py` against the retired `1010:0679` host override.
The property under test is the same one -- a timer env-wait must TERMINATE and must cut a frame -- but
it is now asserted where the behaviour actually lives: in the generated corpus plus
`overkill/cpuless_driver.py`, rather than in host code that intercepted the address.
"""
from __future__ import annotations

import pytest

from overkill.cpuless_driver import TIMER_IRQS_PER_FRAME, CPUlessFrameDriver

_CS = 0x1010
#: the timer-tick flag `1010:066C` (`inc byte cs:[066B]`) sets and `1010:0679` spins on.
_TICK_FLAG = 0x66B
#: the declared head and its resume point, as the emitted body passes them.
_HEAD = (0x1010, 0x0679)
_RESUME = 0x067F


class _Mem:
    def __init__(self):
        self.cells = {}

    def rb(self, seg, off):
        return self.cells.get((seg, off), 0)

    def wb(self, seg, off, val):
        self.cells[(seg, off)] = val & 0xFF


def _regs(**over):
    r = {k: 0 for k in ("ax", "bx", "cx", "dx", "si", "di", "bp", "sp",
                        "ds", "es", "ss", "cs")}
    r["_flags_in"] = 2
    r["_df"] = 0
    r.update(over)
    return r


def _driver(mem, *, isr=None, present=None, supply_input=None, irqs=TIMER_IRQS_PER_FRAME):
    return CPUlessFrameDriver(mem, object(), isr or (lambda *a, **k: None),
                              present=present or (lambda _f: None),
                              supply_input=supply_input, irqs=irqs)


# ---------------------------------------------------------------------------------------------------
# THE GENERATED SPINE OWNS THE YIELD.  This is the point of the whole change: the corpus itself calls
# plat.boundary at the declared address, so nothing has to intercept it from outside.
# ---------------------------------------------------------------------------------------------------

def test_the_generated_body_calls_plat_boundary_at_the_declared_head():
    """`1010:0679` is declared in artifacts/lift_boundary_heads.txt, so its emitted body must carry a
    real `plat.boundary(0x1010, 0x0679, 0x067F, ...)` call.  Without it every head is inert and the
    wait spins to the 20M-iteration guard -- which is exactly what a cold run did before."""
    import inspect

    from overkill.cpuless_recovered.func_1010_0679 import func_1010_0679

    src = inspect.getsource(func_1010_0679)
    assert "plat.boundary(0x1010, 0x0679, 0x067F," in src
    params = inspect.signature(func_1010_0679).parameters
    # `sp` is in the bundle the observer hands the platform, so it must be a parameter.  It was not,
    # and the first arrival at the head raised UnboundLocalError (fixed in dos_re: a boundary head
    # forces sp into the contract).
    assert "sp" in params and "plat" in params


def test_the_wait_terminates_once_the_driver_delivers_the_tick():
    """The end-to-end property the retired override used to assert, now proven against the SPINE.

    The generated body polls `cs:[066B]`; the absent IRQ0 never sets it, so the wait is unsatisfiable
    on its own.  With the driver installed, the park runs the game's recovered ISR, the flag is set,
    and the loop leaves -- no host code intercepting the address."""
    from overkill.cpuless_recovered.func_1010_0679 import func_1010_0679

    mem = _Mem()

    def isr(m, _rt, **_kw):                    # stands in for the recovered 1010:06E5 -> 066C
        m.wb(_CS, _TICK_FLAG, (m.rb(_CS, _TICK_FLAG) + 1) & 0xFF)

    drv = _driver(mem, isr=isr)

    class _Plat:
        def boundary(self, *a):
            return drv.boundary(*a)

    assert mem.rb(_CS, _TICK_FLAG) == 0, "precondition: the tick flag is clear (would block forever)"
    out, compat = func_1010_0679(mem, _Plat(), sp=0x1000, ss=0x2000)
    assert out == {} and "flags" in compat, "the generated contract is preserved"
    assert drv.frame == 1, "an unsatisfiable wait must cut exactly one frame"
    assert mem.rb(_CS, _TICK_FLAG) == TIMER_IRQS_PER_FRAME, "the ticks the absent IRQ0 owed"


def test_an_already_ticked_flag_does_not_cut_a_frame():
    """A wait that would not have blocked on real hardware returns immediately.  Cutting a frame here
    would cost a frame every time the flag is merely polled."""
    from overkill.cpuless_recovered.func_1010_0679 import func_1010_0679

    mem = _Mem()
    mem.wb(_CS, _TICK_FLAG, 3)                 # already ticked
    drv = _driver(mem)

    class _Plat:
        def boundary(self, *a):
            return drv.boundary(*a)

    func_1010_0679(mem, _Plat(), sp=0x1000, ss=0x2000)
    assert drv.frame == 0, "no block -> no frame boundary"
    assert mem.rb(_CS, _TICK_FLAG) == 3, "and no spurious extra tick"


# ---------------------------------------------------------------------------------------------------
# PARK ON RE-ARRIVAL, and the ORDER within a boundary.  Both are silent when wrong.
# ---------------------------------------------------------------------------------------------------

def test_the_first_pass_at_a_head_does_not_cut_a_frame():
    """Pass 1 lets the wait body run to steady state; only pass 2 proves the wait unsatisfied.  The
    observer fires AFTER the poll, so a tick delivered during a pass-1 park is not observed until the
    next trip round the loop -- parking on pass 1 cuts the frame early."""
    drv = _driver(_Mem())
    drv.boundary(*_HEAD, _RESUME, _regs(), 0)
    assert drv.frame == 0 and drv.head is None
    drv.boundary(*_HEAD, _RESUME, _regs(), 0)
    assert drv.frame == 1 and drv.head == _HEAD


def test_each_frame_starts_a_fresh_pass_count():
    """Otherwise the second frame would park on its FIRST arrival and every frame after the first
    would be cut short."""
    drv = _driver(_Mem())
    for _ in range(6):
        drv.boundary(*_HEAD, _RESUME, _regs(), 0)
    assert drv.frame == 3, "3 frames from 6 arrivals: two passes cut one frame"


def test_the_finished_frame_is_presented_before_the_next_frames_input_and_irqs():
    """The fixed order: present frame N, then apply input for N+1, then deliver N+1's timer IRQs.

    A wrong order is invisible except as a one-frame lag in a differential, which is why it is pinned
    here rather than left to the callers."""
    log = []
    mem = _Mem()

    drv = _driver(
        mem,
        isr=lambda *_a, **_k: log.append("irq"),
        present=lambda f: log.append(f"present:{f}"),
        supply_input=lambda f, _r: log.append(f"input:{f}"),
        irqs=2)
    drv.boundary(*_HEAD, _RESUME, _regs(), 0)      # pass 1
    drv.boundary(*_HEAD, _RESUME, _regs(), 0)      # pass 2 -> the boundary
    assert log == ["present:0", "input:1", "irq", "irq"]


def test_every_seam_shares_one_frame_counter():
    """`advance` is the single place a frame ends, so a consumer sees one consistent numbering however
    the game happened to be waiting."""
    seen = []
    drv = _driver(_Mem(), present=seen.append)
    drv.boundary(*_HEAD, _RESUME, _regs(), 0)
    drv.boundary(*_HEAD, _RESUME, _regs(), 0)
    drv.advance(_regs())                            # a different seam, same counter
    assert seen == [0, 1] and drv.frame == 2


def test_two_distinct_heads_each_need_their_own_second_pass():
    """Park-on-re-arrival is per HEAD, not per arrival count: a frame that touches two different waits
    must not be cut by the second wait's first pass."""
    drv = _driver(_Mem())
    other = (0x1010, 0x5160)
    drv.boundary(*_HEAD, _RESUME, _regs(), 0)
    drv.boundary(*other, 0x5170, _regs(), 0)
    assert drv.frame == 0, "two different heads, one pass each: no frame boundary yet"
    drv.boundary(*_HEAD, _RESUME, _regs(), 0)
    assert drv.frame == 1 and drv.head == _HEAD


# ---------------------------------------------------------------------------------------------------
# THE MEASURED PACING CONSTANT.
# ---------------------------------------------------------------------------------------------------

def test_the_irq_rate_is_overkills_measured_two_not_a_copied_constant():
    """2 IRQ0 ticks per displayed frame is MEASURED -- the demo-lockstep gate's recorded INT 08h tick
    distribution over the 8292-frame L1 demo is {0: 2, 1: 1, 2: 8284, 7: 1, 402: 4} -- and it agrees
    with the programmed clock (PIT divisor 0x4000 -> 72.83 Hz IRQ0, 72.83/2 = 36.4 fps).  skyroads'
    driver says 6; copying that number would silently run OVERKILL's sound and timers at 3x."""
    assert TIMER_IRQS_PER_FRAME == 2


def test_the_driver_installs_itself_on_the_frameworks_boundary_protocol():
    """`plat.boundary_cb` is the framework seam.  Nothing in overkill set it before this driver
    existed, so every declared head was inert."""
    class _RT:
        boundary_cb = None

    rt = _RT()
    drv = _driver(_Mem()).install(rt)
    assert rt.boundary_cb == drv.boundary


def test_the_platform_host_yield_no_longer_shadows_the_framework_protocol():
    """`OverkillPlatform.boundary` used to be a one-argument host yield, colliding by NAME with the
    framework's five-argument boundary-head observer.  Now that heads are declared, generated bodies
    really do call `plat.boundary(cs, ip, resume, regs, cost)` on whichever platform they run under,
    so both platforms must answer the same protocol."""
    from overkill.cpuless_runtime import OverkillPlatform

    plat = OverkillPlatform()
    regs = _regs()
    out, flags, cost = plat.boundary(*_HEAD, _RESUME, regs, 7)
    assert out is regs and flags == 2 and cost == 0
    assert plat.boundaries == {"timer": 1}, "the host-yield counter still sees the yield"

    drv = _driver(_Mem()).install(plat)
    plat.boundary(*_HEAD, _RESUME, _regs(), 0)
    plat.boundary(*_HEAD, _RESUME, _regs(), 0)
    assert drv.frame == 1, "an installed driver must receive the pass"


@pytest.mark.parametrize("addr", ["1010:06E5", "1010:0672"])
def test_the_producer_and_the_clear_are_not_declared_as_heads(addr):
    """`overkill/hook_taxonomy.py` groups five addresses under `env_wait`, but only some are waits.
    `1010:06E5` IS the IRQ0 ISR (the PRODUCER of the tick `0679` consumes) and `1010:0672` clears the
    flag.  Declaring either a boundary head would be a category error, so the fact file must not."""
    from pathlib import Path

    heads = (Path(__file__).resolve().parents[1] / "artifacts" / "lift_boundary_heads.txt")
    declared = {ln.strip().upper() for ln in heads.read_text(encoding="utf-8").splitlines()
                if ln.strip() and not ln.lstrip().startswith("#")}
    assert addr.upper() not in declared
