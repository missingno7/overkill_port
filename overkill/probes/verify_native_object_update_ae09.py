"""Verify the native AE09 WHOLE slot transform (object_update_ae09) is byte-exact vs the VM's
1010:AE09 behavior across a gameplay demo -- the §1.2 produced-vs-VM gate for a COMPLETE per-slot
object-update (movement + the AD60 bounds/tile -> active), including the tile-collision path.

AE09 (the EFAE logic_id=0Ch behavior) decrements the slot's substate timer, steps it 3px in its
direction (AF22), then tails into AD60: out of play bounds -> deactivate (BD17 -> active=0); else for
the tile-probe family (draw_layer 2) it samples the tile one map row below (5073 +13 -> 505B) and
deactivates when that tile has class 1; else it survives.  ``object_update_ae09`` composes the recovered
movement (``object_movement_step_ae09``), the AD60 bounds decision, and the tile-probe deactivation
(``object_tile_probe_deactivates_ad60`` over a :class:`LevelTileContext`), predicting the slot's six
post-frame fields: substate +1C, direction +06, sprite +08, x +02, y +04, active +00.  (The BD17 global
counter/spawn writes are separate state, out of scope.)

Step-hook AE09 on the pure-VM (oracle) side: at entry capture the slot fields + draw_layer/logic_id/
DS:BDAC + the level tile context (DS:234E origin, DS:2350 row base, the CS:[9592] tile plane, the
DS:C3AA class table) + the return address; predict; when control returns (the AD60 tail RETs to AE09's
caller) read the slot's six post fields and assert they equal the prediction -- for every AE09 object.

Usage:
    python -m overkill.probes.verify_native_object_update_ae09 [demo_name] [max_frames]
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
from overkill.recovered.domain.tilemap import LevelTileContext  # noqa: E402
from overkill.recovered.systems.objects import object_update_ae09  # noqa: E402
from overkill.recovered.views.object_slots import (  # noqa: E402
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
AE09_IP = 0xAE09
RENDER_MODE_BDAC = 0xBDAC       # DS:BDAC; AD60 suppresses the tile-probe when this == 1
TILE_PROBE_ORIGIN_X = 0x234E    # DS:234E
TILE_PROBE_ROW_BASE = 0x2350    # DS:2350
TILE_CLASS_TABLE = 0xC3AA       # DS:C3AA, 256 entries
TILE_PLANE_SEGMENT_PTR = 0x9592  # CS:[9592] -> the raw tile-plane segment


class _Bytes:
    """Lazy byte Sequence over a VM segment:base region (for the pure tile probe inputs)."""

    def __init__(self, mem, seg: int, base: int, length: int) -> None:
        self._mem, self._seg, self._base, self._length = mem, seg & 0xFFFF, base & 0xFFFF, length

    def __len__(self) -> int:
        return self._length

    def __getitem__(self, index: int) -> int:
        return self._mem.rb(self._seg, (self._base + index) & 0xFFFF)


def main(argv) -> int:
    demo_name = argv[0] if argv else "demo_play_tandy_L2_full_20260617_180221"
    max_frames = int(argv[1]) if len(argv) > 1 else 1200
    demo = InputDemoPlayback.load(ROOT / "artifacts" / "demos" / demo_name)
    snapshot = demo.snapshot_path()
    video = str(demo.manifest.get("metadata", {}).get("video", "tandy"))

    res = {"calls": 0, "ok": 0, "fail": []}
    pending: dict[int, tuple] = {}
    class_table_cache: dict[int, tuple] = {}  # DS:C3AA is static; snapshot once (avoid 256 reads/call)
    orig_step = CPU8086.step

    def step(self):
        if getattr(self, "_side", "") == "ref":
            cs = self.s.cs & 0xFFFF
            ip = self.s.ip & 0xFFFF
            key = id(self)
            if cs == CS and ip == AE09_IP and key not in pending:
                ss = self.s.ss & 0xFFFF
                ds = self.s.ds & 0xFFFF
                bp = self.s.bp & 0xFFFF
                substate = self.mem.rw(ss, (bp + OFF_SUBSTATE) & 0xFFFF)
                direction = self.mem.rw(ss, (bp + OFF_DIRECTION_OR_STEP) & 0xFFFF)
                x = self.mem.rw(ss, (bp + OFF_X) & 0xFFFF)
                y = self.mem.rw(ss, (bp + OFF_Y) & 0xFFFF)
                active = self.mem.rw(ss, (bp + OFF_ACTIVE_WORD) & 0xFFFF)
                draw_layer = self.mem.rw(ss, (bp + OFF_HAZARD_CLASS) & 0xFFFF)
                logic_id = self.mem.rw(ss, (bp + OFF_LOGIC_ID) & 0xFFFF)
                bdac = self.mem.rw(ds, RENDER_MODE_BDAC)
                class_table = class_table_cache.get(ds)
                if class_table is None:
                    class_table = tuple(self.mem.rb(ds, (TILE_CLASS_TABLE + i) & 0xFFFF) for i in range(0x100))
                    class_table_cache[ds] = class_table
                tiles = LevelTileContext(
                    origin_x_word=self.mem.rw(ds, TILE_PROBE_ORIGIN_X),
                    row_base_word=self.mem.rw(ds, TILE_PROBE_ROW_BASE),
                    tile_plane=_Bytes(self.mem, self.mem.rw(cs, TILE_PLANE_SEGMENT_PTR), 0, 0x10000),
                    class_table=class_table,
                )
                predicted = object_update_ae09(
                    substate, direction, x, y, active, draw_layer, logic_id, bdac == 0x0001, tiles
                )
                ret_addr = self.mem.rw(ss, self.s.sp & 0xFFFF)
                pending[key] = (ss, bp, ret_addr, predicted)
            elif key in pending and cs == CS and ip == pending[key][2]:
                ss, bp, _ret, predicted = pending.pop(key)
                post = (
                    self.mem.rw(ss, (bp + OFF_SUBSTATE) & 0xFFFF),
                    self.mem.rw(ss, (bp + OFF_DIRECTION_OR_STEP) & 0xFFFF),
                    self.mem.rw(ss, (bp + OFF_SPRITE_OR_STATE) & 0xFFFF),
                    self.mem.rw(ss, (bp + OFF_X) & 0xFFFF),
                    self.mem.rw(ss, (bp + OFF_Y) & 0xFFFF),
                    self.mem.rw(ss, (bp + OFF_ACTIVE_WORD) & 0xFFFF),
                )
                pred = (predicted.substate, predicted.direction_or_step, predicted.sprite_or_state,
                        predicted.x_word, predicted.y_word, predicted.active_word)
                res["calls"] += 1
                if pred == post:
                    res["ok"] += 1
                else:
                    res["fail"].append((pred, post))
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

    print(f"demo {demo_name} ({max_frames} frames): native object_update_ae09 vs VM AE09 (movement+active): "
          f"calls={res['calls']} ok={res['ok']} fail={len(res['fail'])}")
    for pred, post in res["fail"][:8]:
        print(f"  FAIL predicted={tuple(hex(v) for v in pred)} actual={tuple(hex(v) for v in post)}")
    ok = res["calls"] > 0 and not res["fail"]
    print("RESULT:", "PASS -- native AE09 whole slot transform byte-exact vs the VM across the demo"
          if ok else "CHECK -- no AE09 reached, or a divergence")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
