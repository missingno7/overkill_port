"""Assemble the frame-0 level-start state ENTIRELY from the recovered cold seeds -- no VM, no snapshot.

This is the VM-free replacement for ``play_native``'s ``--snapshot`` staging: it writes the recovered
level-start sequence into a fresh data image and reads the result back through the existing (VM-verified)
:func:`read_native_game_state` projection.  Every write is a byte-exact recovered seed:

  * session start  -- :func:`new_game_session_init_96ee` (planet 0, lives 3, score 0);
  * new-game setup -- :func:`apply_new_game_setup_c4db` (special + effect pool seed + control reset), via
    the ``DS:0x32CA`` slot table read from the image;
  * gameplay pool  -- :func:`object_pool_seed_c3b5` (the 0x2B5C enemy pool), via ``DS:0x8D12``;
  * control reset  -- :func:`respawn_control_reset_c461`;
  * player spawn   -- :func:`player_spawn_record_c42f` (record 0x237C active at x=0xC0, y=0x58);
  * starfield      -- :func:`load_starfield_state` (cold static stream).

Known omission (marked, not faked): the ``7524`` companion/flame object
(:func:`player_companion_spawn_c453`) needs the runtime allocator, so it is not placed here.
"""
from __future__ import annotations

from overkill.recovered.adapters.native_game_state_adapter import read_native_game_state
from overkill.recovered.adapters.starfield_adapter import DATA_SEGMENT, load_starfield_state
from overkill.recovered.domain.native_game_state import NativeGameState
from overkill.recovered.domain.starfield import StarfieldState
from overkill.recovered.systems.frame_loop import (
    GAMEPLAY_SEED_COUNT,
    GAMEPLAY_SEED_SLOT_TABLE_8D12,
    OBJECT_SEED_COUNT,
    OBJECT_SEED_SLOT_TABLE_32CA,
    PLAYER_SPAWN_RECORD,
    apply_new_game_setup_c4db,
    new_game_session_init_96ee,
    object_pool_seed_c3b5,
    player_spawn_record_c42f,
    respawn_control_reset_c461,
)


class _MutMem:
    """A tiny mutable flat-image reader/writer with the recovered readers' ``rb``/``rw`` shape.

    Plain bytes -- NOT an emulator, no ``dos_re``: it lets the recovered seeds be applied and then read
    back through :func:`read_native_game_state` exactly as if they had run on the real data segment.
    """

    def __init__(self, data: bytes) -> None:
        self.data = bytearray(data)

    def _phys(self, seg: int, off: int) -> int:
        return ((seg & 0xFFFF) * 16 + (off & 0xFFFF)) & 0xFFFFF

    def rb(self, seg: int, off: int) -> int:
        return self.data[self._phys(seg, off)]

    def rw(self, seg: int, off: int) -> int:
        p = self._phys(seg, off)
        return self.data[p] | (self.data[p + 1] << 8)

    def ww(self, seg: int, off: int, val: int) -> None:
        p = self._phys(seg, off)
        self.data[p] = val & 0xFF
        self.data[p + 1] = (val >> 8) & 0xFF


def build_cold_level_start(exe_image: bytes) -> tuple[NativeGameState, StarfieldState]:
    """Assemble the frame-0 level-start ``(NativeGameState, StarfieldState)`` from the recovered seeds.

    ``exe_image`` is the cold runtime data image (its data segment holds the static pool pointer tables
    at ``DS:0x32CA`` / ``DS:0x8D12`` and the starfield stream); this applies the level-start writes on top
    and projects the result.  No VM, no captured snapshot.
    """
    mem = _MutMem(exe_image)
    ds = DATA_SEGMENT

    def write_map(cell_map):
        for off, val in cell_map.items():
            mem.ww(ds, off, val)

    # 1) session start
    write_map(new_game_session_init_96ee())
    # 2) C4DB new-game setup (special + effect seed + control reset) via the DS:0x32CA table
    table_32ca = {cx: mem.rw(ds, OBJECT_SEED_SLOT_TABLE_32CA + cx * 2)
                  for cx in range(1, OBJECT_SEED_COUNT + 1)}
    write_map(apply_new_game_setup_c4db(table_32ca))
    # 3) C3A6 gameplay-pool seed via the DS:0x8D12 table
    table_8d12 = {cx: mem.rw(ds, GAMEPLAY_SEED_SLOT_TABLE_8D12 + cx * 2)
                  for cx in range(1, GAMEPLAY_SEED_COUNT + 1)}
    for rec, fields in object_pool_seed_c3b5(table_8d12).items():
        for fo, val in fields.items():
            mem.ww(ds, rec + fo, val)
    # 4) respawn / level-start control reset
    write_map(respawn_control_reset_c461())
    # 5) player spawn (record 0x237C active at 0xC0/0x58) -- last, over the inactive seed
    for fo, val in player_spawn_record_c42f().items():
        mem.ww(ds, PLAYER_SPAWN_RECORD + fo, val)

    return read_native_game_state(mem, ds), load_starfield_state(exe_image)
