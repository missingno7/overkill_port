"""VM-free unit tests for the recovered 1010:9FEA child-coordinate decision.

The adapter ``overkill.gameplay.object_movement.run_object_child_coord_update_9fea`` is
verified against the ASM by the hook verifier + demo replay; these pin the pure gameplay
decision (base + table delta + 2x vertical scroll bias, Y clamped into 0..0x00C0) headlessly.
"""
from __future__ import annotations

from dos_re.cpu import CPU8086, CPUState
from dos_re.memory import Memory

from overkill.gameplay.object_movement import run_object_child_coord_update_9fea
from overkill.recovered.domain.movement import ChildCoordUpdate
from overkill.recovered.systems.movement import object_child_coord_update_9fea

_OFF_X = 0x02
_OFF_Y = 0x04
_OFF_SPRITE_OR_STATE = 0x08


def _u(**kw):
    return object_child_coord_update_9fea(**kw)


def _no_self_disable(cpu, addr, sig, name):
    return False


def _run_adapter(*, bx, x_delta, y_delta, src_x, src_y, scroll_bias, sprite_state=0):
    """Run the real 9FEA hook on a controlled CPU/memory; return observable end-state.

    Layout: DS=0x2000, SS=0x3000. Motion table at DS:SI (x_delta, y_delta); source slot at
    SS:BP (+02 X, +04 Y, +08 sprite/state); child object at DS:BX; scroll bias at DS:A398;
    a return IP on the stack for the near-ret. Mirrors the ASM's addressing exactly.
    """
    ds, ss, bp, si, sp = 0x2000, 0x3000, 0x0100, 0x0400, 0x0FF0
    mem = Memory()
    cpu = CPU8086(mem, CPUState(ds=ds, ss=ss, bp=bp, si=si, sp=sp, bx=bx & 0xFFFF))
    mem.ww(ss, sp, 0xBEEF)                       # near-ret target
    mem.ww(ds, si, x_delta & 0xFFFF)
    mem.ww(ds, (si + 2) & 0xFFFF, y_delta & 0xFFFF)
    mem.ww(ss, (bp + _OFF_X) & 0xFFFF, src_x & 0xFFFF)
    mem.ww(ss, (bp + _OFF_Y) & 0xFFFF, src_y & 0xFFFF)
    mem.ww(ss, (bp + _OFF_SPRITE_OR_STATE) & 0xFFFF, sprite_state & 0xFFFF)
    mem.ww(ds, 0xA398, scroll_bias & 0xFFFF)
    run_object_child_coord_update_9fea(cpu, _no_self_disable)
    return {
        "ip": cpu.s.ip & 0xFFFF,
        "ax": cpu.s.ax & 0xFFFF,
        "si": cpu.s.si & 0xFFFF,
        "child_x": mem.rw(ds, (bx + _OFF_X) & 0xFFFF),
        "child_y": mem.rw(ds, (bx + _OFF_Y) & 0xFFFF),
        "a39e": mem.rb(ds, 0xA39E),
        "a39f": mem.rb(ds, 0xA39F),
    }


def test_adapter_null_link_bx_ffff_is_a_noop_return():
    ds, ss, bp, sp = 0x2000, 0x3000, 0x0100, 0x0FF0
    mem = Memory()
    cpu = CPU8086(mem, CPUState(ds=ds, ss=ss, bp=bp, sp=sp, bx=0xFFFF))
    mem.ww(ss, sp, 0xBEEF)
    mem.wb(ds, 0xA39E, 0x00)
    run_object_child_coord_update_9fea(cpu, _no_self_disable)
    assert cpu.s.ip == 0xBEEF          # near-ret taken
    assert mem.rb(ds, 0xA39E) == 0     # no clamp flags written


def test_adapter_no_clamp_writes_child_and_leaves_preclamp_ax():
    r = _run_adapter(bx=0x0500, x_delta=0x000A, y_delta=0x0014, src_x=0x0064, src_y=0x0032, scroll_bias=0x0005)
    assert r["child_x"] == 0x006E                 # 0x0A + 0x64
    assert r["child_y"] == 0x0050                 # 0x14 + 0x32 + 2*5, in range
    assert r["ax"] == 0x0050                       # AX = pre-clamp Y
    assert r["si"] == 0x0404                        # SI advanced by 4 (sprite_state 0)
    assert r["a39e"] == 0 and r["a39f"] == 0
    assert r["ip"] == 0xBEEF


def test_adapter_upper_clamp_sets_a39f():
    r = _run_adapter(bx=0x0500, x_delta=0, y_delta=0x0010, src_x=0, src_y=0x00C0, scroll_bias=0)
    assert r["child_y"] == 0x00C0
    assert r["a39f"] == 0x01 and r["a39e"] == 0
    assert r["ax"] == 0x00D0                        # AX keeps the pre-clamp Y (0xD0)


def test_adapter_lower_clamp_sets_a39e():
    r = _run_adapter(bx=0x0500, x_delta=0, y_delta=0xFFF0, src_x=0, src_y=0x0000, scroll_bias=0)
    assert r["child_y"] == 0x0000
    assert r["a39e"] == 0x01 and r["a39f"] == 0
    assert r["ax"] == 0xFFF0                        # AX keeps the pre-clamp (negative) Y


def test_no_clamp_adds_base_delta_and_double_scroll_bias():
    r = _u(source_x=100, source_y=50, x_delta=10, y_delta=20, scroll_bias=5)
    # x = 10+100 = 110; y = 20+50+2*5 = 80, in range -> no clamp
    assert r == ChildCoordUpdate(x_word=110, y_word=80, lower_clamped=False, upper_clamped=False)


def test_scroll_bias_is_applied_twice():
    r = _u(source_x=0, source_y=0, x_delta=0, y_delta=0, scroll_bias=7)
    assert r.y_word == 14 and not r.lower_clamped and not r.upper_clamped


def test_upper_clamp_when_y_exceeds_00c0():
    r = _u(source_x=0, source_y=0x00C0, x_delta=0, y_delta=0x10, scroll_bias=0)
    # y = 0xC0 + 0x10 = 0xD0 > 0xC0 -> upper clamp
    assert r.y_word == 0x00C0 and r.upper_clamped and not r.lower_clamped


def test_y_exactly_00c0_is_not_clamped():
    r = _u(source_x=0, source_y=0x00C0, x_delta=0, y_delta=0, scroll_bias=0)
    assert r.y_word == 0x00C0 and not r.upper_clamped and not r.lower_clamped


def test_y_just_above_00c0_is_upper_clamped():
    r = _u(source_x=0, source_y=0x00C1, x_delta=0, y_delta=0, scroll_bias=0)
    assert r.y_word == 0x00C0 and r.upper_clamped


def test_lower_clamp_when_y_goes_negative_via_delta():
    # y_delta = 0xFFF0 (= -16 signed), source_y small -> sum has bit 15 set -> clamp to 0
    r = _u(source_x=0, source_y=0x0000, x_delta=0, y_delta=0xFFF0, scroll_bias=0)
    assert r.y_word == 0x0000 and r.lower_clamped and not r.upper_clamped


def test_lower_clamp_via_scroll_bias_sign_bit():
    # 2 * 0xC000 = 0x18000, masked to 0x8000 -> bit 15 set -> lower clamp
    r = _u(source_x=0, source_y=0, x_delta=0, y_delta=0, scroll_bias=0xC000)
    assert r.y_word == 0x0000 and r.lower_clamped


def test_x_word_wraps_mod_16bits():
    r = _u(source_x=0xFFFF, source_y=0, x_delta=2, y_delta=0, scroll_bias=0)
    assert r.x_word == 0x0001
