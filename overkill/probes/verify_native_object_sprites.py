"""Byte-exact gate: the native object->sprite bridge vs the VM's real draw-type dispatch 1010:7596.

For each active, anim-0, non-variant object in a snapshot, drive the ORIGINAL draw-type dispatcher
``7596`` (hooks cleared; SS:BP = the object record).  ``7596`` selects the real routine via
``obj[+14] -> cs:[75A0]`` (7746/768E/75A6) and runs it; capture every Tandy masked-compositor blit
(2E6E/2F81/2FB6) as (compositor IP, DI destination, SI source-offset).  Then assert
``object_sprites.object_slots`` predicts the SAME sequence of slot starts -- same compositor, same DI,
and same source offset into the same bank -- proving the VM-free bank/table/threshold/two-slot logic
matches the live draw for every routine.

Usage:
    python -m overkill.probes.verify_native_object_sprites <snapshot_dir>
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CS = 0x1010
E7596 = 0x7596
RET = 0xFFFF
# Recovered compositor geometry: {ip: (words_per_row, row_add, fixed_rows|None)}.  The per-row DI
# advance is ``words_per_row*2`` (bytes written) + ``row_add`` (the ADD DI,BX to the next scanline);
# 2E6E/2F81 loop once per row (fixed_rows None), while 2FB6 is a fully unrolled 8-row block that
# enters its leaf exactly once.
from overkill.recovered.systems.sprite_textures import MASKED_COMPOSITORS
COMPOSITORS = set(MASKED_COMPOSITORS)


def _expected_blits(slots):
    """Reconstruct the full ordered (comp_ip, di, si) blit sequence a bridge slot list yields.

    Row-loop leaves (2E6E/2F81) advance di by ``words_per_row*2 + row_add`` and si by
    ``words_per_row*4`` each of ``rows`` rows; the unrolled 2FB6 leaf issues one blit for the block.
    """
    out = []
    for s in slots:
        words, row_add, fixed = MASKED_COMPOSITORS[s.comp_ip]
        n = 1 if fixed is not None else s.rows          # 2FB6 unrolled -> single leaf entry
        di_step = words * 2 + row_add
        si_step = words * 4
        for r in range(n):
            out.append((s.comp_ip, (s.di + r * di_step) & 0xFFFF, (s.src_off + r * si_step) & 0xFFFF))
    return out


def main(argv) -> int:
    if not argv:
        print(__doc__)
        return 2
    snap = Path(argv[0])
    from overkill.runtime import load_overkill_snapshot
    from overkill.asset_codecs.native_level import load_native_level
    from overkill.asset_codecs.shared_assets import load_shared_startup_assets
    from overkill.native_video.object_sprites import (
        OFFSCREEN, SpriteDrawContext, object_slots)
    from overkill.recovered.adapters.native_game_state_adapter import read_native_game_state

    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None
    ds = int(re.search(r"DS=([0-9A-Fa-f]{4})",
                       json.loads((snap / "state.json").read_text())["cpu_snapshot"]).group(1), 16)
    mem = bytes(cpu.mem.data)

    def rw(seg, off):
        p = ((seg & 0xFFFF) * 16 + (off & 0xFFFF)) & 0xFFFFF
        return mem[p] | (mem[(p + 1) & 0xFFFFF] << 8)

    # The VM keeps the four global sprite banks at these segments; the level bank comes from the
    # graphics var.  Locate the level whose recovered graphics matches the live level bank.
    exe = (ROOT / "assets" / "OVERKILL").read_bytes()
    level_base = (rw(CS, 0x95AE) << 4) & 0xFFFFF
    level = None
    for lv in range(6):
        g = load_native_level(exe, exe, lv).graphics
        if mem[level_base:level_base + len(g)] == g:
            level = lv
            break
    if level is None:
        print("could not identify the live level bank")
        return 1
    shared = load_shared_startup_assets(exe)
    ctx = SpriteDrawContext(
        common_bank=shared["MANEXPL.BIC"],
        level_bank=load_native_level(exe, exe, level).graphics,
        wide_bank=shared["2X2.BIC"],
        wide_bank_hi=shared["2X2C.BIC"],
        compact_bank=shared["1X1.BIC"],
        table_75a6=[rw(CS, 0x9392 + 2 * k) for k in range(0x400)],
        table_768e=[rw(CS, 0x9192 + 2 * k) for k in range(0x100)],
        table_7746=[rw(CS, 0x8F92 + 2 * k) for k in range(0x100)],
        half_stride=(rw(ds, 0x1028) >> 1) & 0xFFFF,
    )

    class _M:
        def __init__(self, data): self.data = data
        def rb(self, s, o): return self.data[((s & 0xFFFF) * 16 + (o & 0xFFFF)) & 0xFFFFF]
        def rw(self, s, o):
            p = ((s & 0xFFFF) * 16 + (o & 0xFFFF)) & 0xFFFFF
            return self.data[p] | (self.data[(p + 1) & 0xFFFFF] << 8)
    state = read_native_game_state(_M(mem), ds)

    def drive_7596(bp: int):
        """Run the original 7596 dispatch for the record at DS:BP; return the ordered slot-start blits."""
        s = cpu.s
        s.cs, s.ds, s.ss, s.bp = CS, ds, ds, bp & 0xFFFF
        sp = (s.sp - 2) & 0xFFFF
        cpu.mem.ww(ds, sp, RET)
        s.sp = sp
        s.ip = E7596
        blits = []
        for _ in range(300000):
            if (s.cs & 0xFFFF) == CS and (s.ip & 0xFFFF) == RET:
                break
            ip = s.ip & 0xFFFF
            if (s.cs & 0xFFFF) == CS and ip in COMPOSITORS:
                blits.append((ip, s.di & 0xFFFF, s.si & 0xFFFF))
            cpu.step()
        return blits

    checked = ok = 0
    fails = []
    for name, pool in (("special", state.special_pool), ("effect", state.effect_pool),
                       ("gameplay", state.object_pool)):
        for i in range(len(pool)):
            if pool.active_word(i) == 0:
                continue
            if pool.word_at(i, 0x12) != 0 or pool.word_at(i, 0x24) != 0:
                continue  # anim / OR-inverted variant -> different compositor, out of scope
            sid = pool.word_at(i, 0x08)
            dtype = pool.word_at(i, 0x14)
            c0, c1 = pool.word_at(i, 0x0C), pool.word_at(i, 0x10)
            if c0 == OFFSCREEN and c1 == OFFSCREEN:
                continue
            bp = (pool.base + i * pool.stride) & 0xFFFF
            vm = drive_7596(bp)
            if not vm:
                continue  # object routed to a non-sprite draw-type (dtype not 0/1/2)
            mine = _expected_blits(object_slots(sid, dtype, c0, c1, ctx))
            checked += 1
            if mine == vm:
                ok += 1
            else:
                fails.append((name, i, hex(sid), f"dtype={hex(dtype)}",
                              f"vm={[(hex(a),hex(b),hex(c)) for a,b,c in vm]}",
                              f"mine={[(hex(a),hex(b),hex(c)) for a,b,c in mine]}"))

    print(f"snapshot {snap.name} (level {level}): 7596 dispatch checked={checked} ok={ok} "
          f"fails={len(fails)}")
    for f in fails[:8]:
        print("  FAIL", f)
    result = checked > 0 and not fails
    print("RESULT:", "PASS -- native object->sprite bridge matches the VM's 7596 draw-type dispatch"
          if result else "CHECK")
    return 0 if result else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
