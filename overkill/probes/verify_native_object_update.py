"""Native object-update **coverage gate** -- the §1.2/§1.3 scaffold.

This generalises the per-routine ``verify_native_*`` probes into the seed of the
VM-free state producer: it walks a real gameplay demo and, at the per-slot
behaviour dispatch (EFAE, ``1010:EFAE`` -> ``CS:[0xEFC4 + logic_id*2]``), classifies
**every** per-slot object update as either

  * **native** -- a recovered pure whole-slot transform is wired for this
    ``logic_id``, and it is checked byte-exact against the VM at the handler's
    return (the produced-vs-VM gate, same mechanism as the AE09 probe), or
  * **fallback** -- no pure transform yet; counted so the report shows the next
    promotion targets (the hottest fallback ``logic_id`` buckets).

So one run yields three things at once: a live zero-divergence **gate** for the
handlers we have made native, a **coverage %** (how much of the object-update we
can already produce VM-free), and a prioritised **backlog** (which ``logic_id`` to
recover next).  Wire a new pure transform = add one entry to ``NATIVE_HANDLERS``.

Scope today: the EFAE family (AA2B draw-layer-2/4 behaviours -- the bulk of
gameplay/effect objects).  AA2B's other first-level branches are a separate,
smaller dispatch to fold in later.  One native handler is wired: AE09
(``logic_id`` 0Ch), the proven complete per-slot transform.

Usage:
    python -m overkill.probes.verify_native_object_update [demo_name] [max_frames]
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Callable

from overkill.probes._harness import LazyBytes, load_demo, run_ref_step_probe
from overkill.recovered.domain.tilemap import LevelTileContext
from overkill.recovered.systems.objects import object_update_ae09
from overkill.recovered.views.object_slots import (
    OFF_ACTIVE_WORD,
    OFF_DIRECTION_OR_STEP,
    OFF_HAZARD_CLASS,
    OFF_LOGIC_ID,
    OFF_SPRITE_OR_STATE,
    OFF_SUBSTATE,
    OFF_X,
    OFF_Y,
)

CS = 0x1010
EFAE_IP = 0xEFAE              # per-slot behaviour dispatcher
EFC4_TABLE = 0xEFC4          # CS:[EFC4 + logic_id*2] -> handler entry IP
# AE09 tile-probe inputs (see verify_native_object_update_ae09 for the derivation).
AE09_IP = 0xAE09
RENDER_MODE_BDAC = 0xBDAC
TILE_PROBE_ORIGIN_X = 0x234E
TILE_PROBE_ROW_BASE = 0x2350
TILE_CLASS_TABLE = 0xC3AA
TILE_PLANE_SEGMENT_PTR = 0x9592


@dataclass
class _Pending:
    """An armed native prediction awaiting the handler's return."""

    ss: int
    bp: int
    ret_addr: int
    predicted: tuple
    read_post: Callable  # (cpu, ss, bp) -> tuple of post-frame fields
    logic_id: int = -1   # filled in at arm time for clean attribution


@dataclass(frozen=True)
class NativeHandler:
    """A wired pure whole-slot transform for one ``logic_id``.

    ``entry_ip`` is the handler the EFC4 table dispatches to; ``arm`` captures the
    slot pre-state at that IP, predicts the post-state via the pure transform, and
    returns a :class:`_Pending` (or ``None`` to skip an unmodelled sub-path).
    """

    logic_id: int
    label: str
    entry_ip: int
    arm: Callable  # (cpu, class_table_cache) -> _Pending | None


def _arm_ae09(cpu, class_table_cache: dict) -> _Pending | None:
    """Capture + predict AE09 (logic_id 0Ch) -- identical to the AE09 probe."""
    ss = cpu.s.ss & 0xFFFF
    ds = cpu.s.ds & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    substate = cpu.mem.rw(ss, (bp + OFF_SUBSTATE) & 0xFFFF)
    direction = cpu.mem.rw(ss, (bp + OFF_DIRECTION_OR_STEP) & 0xFFFF)
    x = cpu.mem.rw(ss, (bp + OFF_X) & 0xFFFF)
    y = cpu.mem.rw(ss, (bp + OFF_Y) & 0xFFFF)
    active = cpu.mem.rw(ss, (bp + OFF_ACTIVE_WORD) & 0xFFFF)
    draw_layer = cpu.mem.rw(ss, (bp + OFF_HAZARD_CLASS) & 0xFFFF)
    logic_id = cpu.mem.rw(ss, (bp + OFF_LOGIC_ID) & 0xFFFF)
    bdac = cpu.mem.rw(ds, RENDER_MODE_BDAC)
    class_table = class_table_cache.get(ds)
    if class_table is None:
        class_table = tuple(cpu.mem.rb(ds, (TILE_CLASS_TABLE + i) & 0xFFFF) for i in range(0x100))
        class_table_cache[ds] = class_table
    tiles = LevelTileContext(
        origin_x_word=cpu.mem.rw(ds, TILE_PROBE_ORIGIN_X),
        row_base_word=cpu.mem.rw(ds, TILE_PROBE_ROW_BASE),
        tile_plane=LazyBytes(cpu.mem, cpu.mem.rw(cpu.s.cs & 0xFFFF, TILE_PLANE_SEGMENT_PTR), 0, 0x10000),
        class_table=class_table,
    )
    p = object_update_ae09(substate, direction, x, y, active, draw_layer, logic_id, bdac == 0x0001, tiles)
    predicted = (p.substate, p.direction_or_step, p.sprite_or_state, p.x_word, p.y_word, p.active_word)
    ret_addr = cpu.mem.rw(ss, cpu.s.sp & 0xFFFF)

    def read_post(c, ss_, bp_):
        return (
            c.mem.rw(ss_, (bp_ + OFF_SUBSTATE) & 0xFFFF),
            c.mem.rw(ss_, (bp_ + OFF_DIRECTION_OR_STEP) & 0xFFFF),
            c.mem.rw(ss_, (bp_ + OFF_SPRITE_OR_STATE) & 0xFFFF),
            c.mem.rw(ss_, (bp_ + OFF_X) & 0xFFFF),
            c.mem.rw(ss_, (bp_ + OFF_Y) & 0xFFFF),
            c.mem.rw(ss_, (bp_ + OFF_ACTIVE_WORD) & 0xFFFF),
        )

    return _Pending(ss=ss, bp=bp, ret_addr=ret_addr, predicted=predicted, read_post=read_post)


# The registry: one entry per recovered pure whole-slot transform.  Grow this as
# handlers are promoted; everything not here is counted as a fallback.
NATIVE_HANDLERS: tuple[NativeHandler, ...] = (
    NativeHandler(logic_id=0x0C, label="AE09", entry_ip=AE09_IP, arm=_arm_ae09),
)
_HANDLER_BY_IP = {(CS, h.entry_ip): h for h in NATIVE_HANDLERS}


def main(argv) -> int:
    default_demo = "demo_play_tandy_L2_full_20260617_180221"
    demo_name = argv[0] if argv else default_demo
    max_frames = int(argv[1]) if len(argv) > 1 else 1200
    demo = load_demo(demo_name, default_demo)

    coverage: dict[int, int] = {}          # logic_id -> per-slot EFAE dispatches
    handler_ip: dict[int, int] = {}        # logic_id -> EFC4 dispatch target IP (the routine to recover)
    native_ok: dict[int, int] = {}         # logic_id -> verified-exact native updates
    native_fail: dict[int, list] = {}      # logic_id -> [(predicted, actual), ...]
    pending: dict[int, _Pending] = {}      # id(cpu) -> armed prediction (no nesting in the walk)
    class_table_cache: dict[int, tuple] = {}

    def on_ref_step(cpu):
        cs = cpu.s.cs & 0xFFFF
        ip = cpu.s.ip & 0xFFFF
        if cs == CS and ip == EFAE_IP:
            ss = cpu.s.ss & 0xFFFF
            bp = cpu.s.bp & 0xFFFF
            logic_id = cpu.mem.rw(ss, (bp + OFF_LOGIC_ID) & 0xFFFF)
            coverage[logic_id] = coverage.get(logic_id, 0) + 1
            if logic_id not in handler_ip:
                handler_ip[logic_id] = cpu.mem.rw(cs, (EFC4_TABLE + ((logic_id << 1) & 0xFFFF)) & 0xFFFF)
        else:
            key = id(cpu)
            handler = _HANDLER_BY_IP.get((cs, ip))
            if handler is not None and key not in pending:
                armed = handler.arm(cpu, class_table_cache)
                if armed is not None:
                    armed.logic_id = handler.logic_id
                    pending[key] = armed
            else:
                armed = pending.get(key)
                if armed is not None and cs == CS and ip == armed.ret_addr:
                    pending.pop(key)
                    actual = armed.read_post(cpu, armed.ss, armed.bp)
                    if actual == armed.predicted:
                        native_ok[armed.logic_id] = native_ok.get(armed.logic_id, 0) + 1
                    else:
                        native_fail.setdefault(armed.logic_id, []).append((armed.predicted, actual))

    run_ref_step_probe(demo, max_frames, on_ref_step)
    return _report(demo_name, max_frames, coverage, native_ok, native_fail, handler_ip)


def _report(demo_name, max_frames, coverage, native_ok, native_fail, handler_ip=None) -> int:
    handler_ip = handler_ip or {}
    total = sum(coverage.values())
    native_total = sum(native_ok.values())
    native_logic_ids = {h.logic_id for h in NATIVE_HANDLERS}
    any_fail = any(native_fail.values())

    print(f"demo {demo_name} ({max_frames} frames): native object-update coverage (EFAE family)")
    print(f"  total per-slot EFAE updates: {total}")
    for lid in sorted(coverage, key=lambda k: -coverage[k]):
        seen = coverage[lid]
        if lid in native_logic_ids:
            ok = native_ok.get(lid, 0)
            fails = native_fail.get(lid, [])
            tag = f"native OK  ok={ok}/{seen} fail={len(fails)}" if not fails else f"native FAIL fail={len(fails)}"
        else:
            tag = "fallback (VM)"
        label = next((h.label for h in NATIVE_HANDLERS if h.logic_id == lid), "----")
        ip = handler_ip.get(lid)
        ip_s = f"->{ip:04X}" if ip is not None else "->????"
        print(f"  logic_id {lid:#06x} {ip_s}  {label:<6} {tag:<28} slots={seen}")
    pct = (100.0 * native_total / total) if total else 0.0
    print(f"  NATIVE COVERAGE: {native_total}/{total} per-slot updates ({pct:.1f}%), "
          f"{len(native_logic_ids)} logic_id(s) wired")
    for lid, fails in native_fail.items():
        for pred, actual in fails[:4]:
            print(f"  FAIL logic_id {lid:#06x} predicted={tuple(hex(v) for v in pred)} "
                  f"actual={tuple(hex(v) for v in actual)}")

    # Gate semantics: only an actual divergence fails.  A demo that never spawns a
    # wired handler is NO-EVENTS (not a failure) -- the rare-event convention used by
    # scripts/verify_native_producers.py -- so this is safe in a cross-demo sweep.
    if any_fail:
        result, code = "FAIL -- a wired native handler diverged from the VM", 1
    elif native_total == 0:
        result, code = "NO-EVENTS -- no wired native handler reached in this demo (not a failure)", 0
    else:
        result, code = "PASS -- wired native handlers byte-exact vs VM; coverage measured", 0
    print("RESULT:", result)
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
