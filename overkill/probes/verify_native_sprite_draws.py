"""Verify the native sprite draw list (native_sprite_draws, from NativeGameState) reproduces the
VM's complete draw list byte-exact across a gameplay demo -- the §1.2 RenderState-mirror gate for
the composed draw list (sprite identity + draw order + on-screen set + screen di).

The present scan 1010:A90C walks the special view-anchor slot (DS:237C), then the gameplay
(DS:8D12 -> 2B5C), then the effect (DS:32CA -> 23B4) slots, drawing each active one and writing its
screen di to ``+0C`` (FFFFh = off-screen).  At A90C's return every drawn slot's ``+0C`` is fresh and
the slots' X/Y are still the draw-time values, so this samples there: it builds the native draw list
from a NativeGameState read out of the same VM memory (``native_sprite_draws`` over the live DS:99C8
column table + DS:234C scroll) and the VM reference list directly from the slots (sprite ``+08``, di
``+0C``, active ``+00``, on-screen ``+0C != FFFF``), in the same special-then-gameplay-then-effect
order, and asserts they are equal.

An all-match run means the native composition produces exactly the VM's draws from recovered state
-- so the backend can build the FrameSnapshot sprite list with no VM read.

Usage:
    python -m overkill.probes.verify_native_sprite_draws [demo_name] [max_frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import overkill.frame_verify as fv  # noqa: E402
from dos_re.cpu import CPU8086  # noqa: E402
from dos_re.input_demo import InputDemoPlayback  # noqa: E402
from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier  # noqa: E402
from overkill.input_waits import pump_demo_frame  # noqa: E402
from overkill.native_video.sprite_compose import native_sprite_draws  # noqa: E402
from overkill.recovered.adapters.native_game_state_adapter import read_native_game_state  # noqa: E402
from overkill.recovered.views.object_slots import (  # noqa: E402
    EFFECT_OBJECT_TABLE_BASE,
    EFFECT_OBJECT_TABLE_COUNT,
    GAMEPLAY_OBJECT_TABLE_BASE,
    GAMEPLAY_OBJECT_TABLE_COUNT,
    OBJECT_SLOT_STRIDE,
    OFF_ACTIVE_WORD,
    OFF_DRAW_SCRATCH_OR_DI,
    OFF_SPRITE_OR_STATE,
    SPECIAL_DRAW_SLOT_BASE,
    SPECIAL_DRAW_SLOT_COUNT,
)

CS = 0x1010
SCAN_IP = 0xA90C           # the gameplay+effect present scan parent
COLUMN_TABLE = 0x99C8      # DS:99C8 per-column base table (word per X)
SCROLL_CURSOR = 0x234C     # DS:234C present source cursor
OFFSCREEN = 0xFFFF


def _vm_draw_list(mem, ds: int) -> tuple:
    """The VM's draw list straight from the slots: special, then gameplay, then effect (the
    witnessed-exact present order); active and on-screen (``+0C != FFFF``), each as
    ``(sprite +08, di +0C)``."""
    out = []
    for base, count in (
        (SPECIAL_DRAW_SLOT_BASE, SPECIAL_DRAW_SLOT_COUNT),
        (GAMEPLAY_OBJECT_TABLE_BASE, GAMEPLAY_OBJECT_TABLE_COUNT),
        (EFFECT_OBJECT_TABLE_BASE, EFFECT_OBJECT_TABLE_COUNT),
    ):
        for i in range(count):
            slot = (base + i * OBJECT_SLOT_STRIDE) & 0xFFFF
            if mem.rw(ds, (slot + OFF_ACTIVE_WORD) & 0xFFFF) == 0:
                continue
            di = mem.rw(ds, (slot + OFF_DRAW_SCRATCH_OR_DI) & 0xFFFF)
            if di != OFFSCREEN:
                out.append((mem.rw(ds, (slot + OFF_SPRITE_OR_STATE) & 0xFFFF), di))
    return tuple(out)


def main(argv) -> int:
    demo_name = argv[0] if argv else "demo_play_tandy_L2_full_20260617_180221"
    max_frames = int(argv[1]) if len(argv) > 1 else 1200
    demo = InputDemoPlayback.load(ROOT / "artifacts" / "demos" / demo_name)
    snapshot = demo.snapshot_path()
    video = str(demo.manifest.get("metadata", {}).get("video", "tandy"))

    res = {"calls": 0, "ok": 0, "fail": []}
    pending: dict[int, int] = {}
    orig_step = CPU8086.step

    def step(self):
        if getattr(self, "_side", "") == "ref":
            cs = self.s.cs & 0xFFFF
            ip = self.s.ip & 0xFFFF
            key = id(self)
            if cs == CS and ip == SCAN_IP:
                pending[key] = self.mem.rw(self.s.ss & 0xFFFF, self.s.sp & 0xFFFF)  # the CALL ret addr
            elif key in pending and cs == CS and ip == pending[key]:
                pending.pop(key)
                ds = self.s.ds & 0xFFFF
                state = read_native_game_state(self.mem, ds)
                col = [self.mem.rw(ds, (COLUMN_TABLE + ((x * 2) & 0xFFFF)) & 0xFFFF) for x in range(0x100)]
                scroll = self.mem.rw(ds, SCROLL_CURSOR)
                native = native_sprite_draws(state, col, scroll)
                vm = _vm_draw_list(self.mem, ds)
                res["calls"] += 1
                if native == vm:
                    res["ok"] += 1
                else:
                    res["fail"].append((native, vm))
        return orig_step(self)

    CPU8086.step = step
    orig_load = fv._load_runtime
    sides = iter(("ref", "cand"))

    def patched_load(exe, assets, snap, tail):
        rt = orig_load(exe, assets, snap, tail)
        rt.cpu._side = next(sides)
        return rt

    fv._load_runtime = patched_load
    boundary = {"n": 0}

    def pump_inputs(ref_rt, cand_rt):
        boundary["n"], _ = pump_demo_frame(demo, boundary["n"], (ref_rt, cand_rt), ref_rt.cpu)
        boundary["n"] += 1

    cfg = FrameVerifyConfig(video=video, source="candidate", max_frames=max_frames,
                            semantic_state_check=False, stop_on_diff=False, log_every=0)
    try:
        run_frame_verifier(exe=ROOT / "assets" / "OVERKILL", assets=ROOT / "assets",
                           snapshot=str(snapshot), command_tail=b"", config=cfg, pump_inputs=pump_inputs)
    finally:
        fv._load_runtime = orig_load
        CPU8086.step = orig_step

    print(f"demo {demo_name} ({max_frames} frames): native native_sprite_draws vs VM draw list: "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])}")
    for native, vm in res["fail"][:4]:
        print(f"  FAIL native={native}")
        print(f"       vm    ={vm}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native draw list byte-exact vs the VM across the demo"
          if ok else "CHECK -- no scans reached, or a divergence")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
