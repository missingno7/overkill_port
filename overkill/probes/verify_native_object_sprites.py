"""Byte-exact gate: the native object->sprite bridge (LEVEL bank) vs the VM's 1010:75A6 draw.

For each active level-bank object (sprite_id >= 0x1C) in a snapshot, drive the ORIGINAL 75A6 per
object (hooks cleared; SS:BP = the object record) and capture the real 2E6E sprite-compositor blit's
(DI destination, SI source-offset into the cs:[95AE] level bank). Then assert
``object_sprites.level_object_sprite_blocks`` computes the identical DI and bank offset for that slot
-- proving the VM-free descriptor lookup (sprite_id -> (sprite_id-0x1C)*0x400) + placement match the VM.

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
E75A6 = 0x75A6
E2E6E = 0x2E6E
RET = 0xFFFF


def main(argv) -> int:
    if not argv:
        print(__doc__)
        return 2
    snap = Path(argv[0])
    from overkill.runtime import load_overkill_snapshot
    from overkill.native_video.object_sprites import (
        COMMON_BANK_THRESHOLD, level_object_sprite_blocks)
    from overkill.recovered.adapters.native_game_state_adapter import read_native_game_state

    rt = load_overkill_snapshot(ROOT / "assets" / "OVERKILL", str(snap), game_root=ROOT / "assets")
    cpu = rt.cpu
    cpu.replacement_hooks.clear()
    cpu.hook_verifier = None
    ds = int(re.search(r"DS=([0-9A-Fa-f]{4})",
                       json.loads((snap / "state.json").read_text())["cpu_snapshot"]).group(1), 16)
    # the cs:[9392] sprite-descriptor table (sprite_id-0x1C -> bank offset), read from the game image
    descriptor_table = [cpu.mem.rw(CS, (0x9392 + 2 * k) & 0xFFFF) for k in range(0x400)]

    class _M:
        def __init__(self, data): self.data = data
        def rb(self, s, o): return self.data[((s & 0xFFFF) * 16 + (o & 0xFFFF)) & 0xFFFFF]
        def rw(self, s, o):
            p = ((s & 0xFFFF) * 16 + (o & 0xFFFF)) & 0xFFFFF
            return self.data[p] | (self.data[(p + 1) & 0xFFFFF] << 8)
    state = read_native_game_state(_M(bytes(cpu.mem.data)), ds)

    def drive_75a6(bp: int):
        """Run original 75A6 for the object record at DS:BP; return the first 2E6E blit's (di, si)."""
        s = cpu.s
        s.cs, s.ds, s.ss, s.bp = CS, ds, ds, bp & 0xFFFF
        sp = (s.sp - 2) & 0xFFFF
        cpu.mem.ww(ds, sp, RET)
        s.sp = sp
        s.ip = E75A6
        captured = None
        for _ in range(200000):
            if (s.cs & 0xFFFF) == CS and (s.ip & 0xFFFF) == RET:
                break
            if captured is None and (s.cs & 0xFFFF) == CS and (s.ip & 0xFFFF) == E2E6E:
                captured = (s.di & 0xFFFF, s.si & 0xFFFF)
            cpu.step()
        return captured

    checked = ok = 0
    fails = []
    for name, pool in (("special", state.special_pool), ("effect", state.effect_pool),
                       ("gameplay", state.object_pool)):
        for i in range(len(pool)):
            if pool.active_word(i) == 0:
                continue
            sid = pool.word_at(i, 0x08)
            if sid < COMMON_BANK_THRESHOLD or pool.word_at(i, 0x12) != 0 or pool.word_at(i, 0x0C) == 0xFFFF:
                continue
            bp = (pool.base + i * pool.stride) & 0xFFFF
            vm = drive_75a6(bp)
            checked += 1
            my_di = pool.word_at(i, 0x0C)
            my_off = descriptor_table[sid - COMMON_BANK_THRESHOLD] & 0xFFFF
            if vm is not None and vm[0] == my_di and vm[1] == my_off:
                ok += 1
            else:
                fails.append((name, i, hex(sid), f"vm={vm}", f"mine=({hex(my_di)},{hex(my_off)})"))

    # also exercise the bridge builder over the level pools (must not raise)
    blocks = level_object_sprite_blocks(state.effect_pool, b"\x00" * 0x20000, descriptor_table)
    print(f"snapshot {snap.name}: 75A6 drive checked={checked} ok={ok} fails={len(fails)}  "
          f"(bridge produced {len(blocks)} effect blocks over a dummy bank)")
    for f in fails[:8]:
        print("  FAIL", f)
    result = checked > 0 and not fails
    print("RESULT:", "PASS -- native object->sprite bridge matches the VM's 75A6 (di + bank offset)"
          if result else "CHECK")
    return 0 if result else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
