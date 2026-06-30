"""Cold-boot native demo: load an OVERKILL level from the original files and run native frames -- no VM.

Run:  python scripts/native_demo.py [level 0..5]

It loads the level entirely from the two original files (the unpacked OVERKILL.EXE image + the OVERKILL
asset container), decodes every per-level buffer with the recovered codecs, renders the tile map to a PNG,
re-proves the decode is byte-identical to the original game, and then steps the recovered gameplay frame
systems over the cold-loaded level -- all with no emulator in the loop.
"""
from __future__ import annotations

import pathlib
import struct
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from overkill.asset_codecs import load_native_level                          # noqa: E402
from overkill.native_game import NativeGame                                  # noqa: E402
from overkill.recovered.domain.frame_loop import FrameInput                  # noqa: E402
from overkill.recovered.domain.frame_snapshot import CameraState, HudLayer   # noqa: E402
from overkill.recovered.domain.native_game_state import NativeGameState      # noqa: E402
from overkill.recovered.domain.object_slots import ObjectPool                # noqa: E402
from overkill.recovered.systems.input import DEFAULT_CONTROL_MAP, key_state_from_pressed  # noqa: E402

EXE_IMAGE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"
CONTAINER = ROOT / "assets" / "OVERKILL"
MAP_W, MAP_H = 13, 288   # tile-map grid (13-column stride)
STRIDE = 0x38
RIGHT_ARROW, UP_ARROW = 0x4D, 0x48


def _starting_state() -> NativeGameState:
    words = [0] * (STRIDE >> 1)
    words[0x02 >> 1] = 0x60   # view-anchor X
    words[0x04 >> 1] = 0x80   # view-anchor Y
    anchor = ObjectPool(base=0x237C, stride=STRIDE, slots=(tuple(words),))
    empty = lambda base: ObjectPool(base=base, stride=STRIDE, slots=())
    return NativeGameState(anchor, empty(0x2B5C), empty(0x23B4),
                           CameraState(x=0, y=0), HudLayer(counters=(0, 0, 0), score_bcd=(0, 0)))


def _render_map_png(tile_plane: bytes, out_path: pathlib.Path) -> None:
    grid = np.frombuffer(tile_plane, dtype=np.uint8).reshape(MAP_H, MAP_W)
    # per-tile pseudo-colour palette (index 0/background stays dark); distinct, recognisable structure
    idx = np.arange(256, dtype=np.uint32)
    pal = np.stack([(idx * 53) % 256, (idx * 101) % 256, (idx * 151) % 256], axis=1).astype(np.uint8)
    pal[grid.flat[np.argmax(np.bincount(grid.flat))]] = (16, 16, 24)  # mute the most common (open) tile
    rgb = pal[grid]                                  # (288, 13, 3)
    rgb = np.repeat(np.repeat(rgb, 10, axis=0), 10, axis=1)  # scale 10x -> 130 x 2880
    from PIL import Image
    Image.fromarray(rgb, "RGB").save(out_path)


def main() -> int:
    level = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    if not EXE_IMAGE.is_file() or not CONTAINER.is_file():
        print("Missing game data (need %s and %s)" % (EXE_IMAGE, CONTAINER))
        return 1
    exe_image = EXE_IMAGE.read_bytes()
    container = CONTAINER.read_bytes()

    print("=== OVERKILL cold boot (no VM) -- level %d ===" % level)
    print("  inputs: %s  +  %s" % (EXE_IMAGE.name, CONTAINER.name))
    lvl = load_native_level(exe_image, container, level)
    print("  decoded: tile_plane=%d (13x288)  class_table=%d  blocks=%d  graphics=%d"
          % (len(lvl.tile_plane), len(lvl.class_table), len(lvl.blocks), len(lvl.graphics)))

    # Re-prove the cold decode == the original game's live buffer (tile-map body), against a snapshot
    # that actually has this level loaded (the menu-state EXE image carries the constants, not a level).
    snaps = {0: "L6_begin_20260618_225537", 1: "L1_start_20260618_143947", 2: "L2_full_20260617_180221",
             3: "L3_full_20260617_202520", 4: "L4_full_20260618_185155", 5: "L5_start_20260618_185923"}
    snap = ROOT / "artifacts" / "demos" / ("demo_play_tandy_" + snaps.get(level, "")) / "snapshot" / "memory_1mb.bin"
    if snap.is_file():
        gimg = snap.read_bytes()
        cs = struct.unpack_from("<H", gimg, 0x1010 * 16 + 0x9592)[0]
        live = gimg[cs * 16: cs * 16 + len(lvl.tile_plane)]
        body_ok = lvl.tile_plane[12:3682] == live[12:3682]
        print("  verify: cold tile-map body == original game's live buffer (CS:[9592]):  %s"
              % ("OK -- byte-identical" if body_ok else "DIFF"))
    else:
        print("  verify: (gameplay snapshot for level %d not present; decode is byte-verified by tests)" % level)

    out_png = ROOT / ("overkill_level%d_map.png" % level)
    _render_map_png(lvl.tile_plane, out_png)
    print("  rendered level map -> %s" % out_png.name)

    # Run the recovered gameplay frame systems over the cold-loaded level (no VM).
    print("  running native frames over the cold level (player holds RIGHT then UP):")
    game = NativeGame.load_level(exe_image, container, level, _starting_state())
    plan = [RIGHT_ARROW, RIGHT_ARROW, RIGHT_ARROW, UP_ARROW, UP_ARROW]
    for i, key in enumerate(plan):
        game, step = game.step_player(FrameInput(DEFAULT_CONTROL_MAP, key_state_from_pressed((key,))))
        ax, ay = game.state.special_pool.x_word(0), game.state.special_pool.y_word(0)
        print("    frame %d  key=%-5s -> view-anchor (x=%3d, y=%3d)  moved=%s"
              % (i, "RIGHT" if key == RIGHT_ARROW else "UP", ax, ay, step.moved))
    print("=== done: a level loaded + stepped natively, decoded from the original files ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
