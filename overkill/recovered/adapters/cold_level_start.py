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

The ``7524`` companion/flame object (:func:`player_companion_spawn_c453`) IS placed: the allocator is
recovered (``behavior_walk._alloc``), and without it a cold-started level has no ship thrusters.
"""
from __future__ import annotations

from overkill.recovered.adapters.flat_memory import MutFlatMemory
from overkill.recovered.adapters.level_object_script import rewind_level_scripts_0b3e
from overkill.recovered.adapters.native_game_state_adapter import read_native_game_state
from overkill.recovered.adapters.starfield_adapter import DATA_SEGMENT, load_starfield_state
from overkill.recovered.domain.native_game_state import NativeGameState
from overkill.recovered.domain.starfield import StarfieldState
from overkill.recovered.systems.frame_loop import (
    PLAYER_SPAWN_RECORD,
    apply_new_game_setup_c4db,
    gameplay_seed_slot_table_8d12,
    new_game_session_init_96ee,
    object_pool_seed_c3b5,
    object_seed_slot_table_32ca,
    player_companion_spawn_c453,
    player_spawn_record_c42f,
    respawn_control_reset_c461,
)


#  The play order is planets 1->2->3->4->5->0 (planet 0 is the FINAL boss level); play_native's
#  0-based --level argument names the Nth level a player plays, so level 0 -> planet 1, ..., level 4
#  -> planet 5, level 5 -> planet 0.
LEVEL_INDEX_TO_PLANET = (1, 2, 3, 4, 5, 0)


def build_cold_level_start_image(exe_image: bytes, level_index: int = 0,
                                 container: "bytes | None" = None) -> MutFlatMemory:
    """Build the raw seeded DGROUP image (the level-start writes, no projection).

    This is the same write sequence :func:`build_cold_level_start` projects through
    :func:`read_native_game_state`; exposed separately so callers that need the LIVE image itself (e.g.
    ``play_native``'s object-behaviour-walk DGROUP, which the level-object-script walker and the
    behaviour walk both mutate in place) can seed it identically instead of re-deriving the writes.

    With ``container`` (the ``assets/OVERKILL`` bytes) the PLANET's level data is decoded INTO the
    image's own segments -- the tile-map body into ``CS:[9592]`` (keeping the bundle's post-init
    border rows), the LEV{planet}BLX tile bank into ``CS:[959A]``, the G{planet}.BIC SPRITE bank into
    ``CS:[95AE]`` (both verbatim: proven byte-equal to the VM's runtime banks), and the planet's class
    table into ``DS:C3AA``.  Without it the image
    keeps the STATIC BUNDLE's captured level data -- which belongs to whatever level the bundle
    snapshot had loaded, NOT ``level_index``.
    """
    mem = MutFlatMemory(exe_image)
    # 1) session start (a fresh SESSION only -- the respawn flow re-runs everything BUT this)
    for off, val in new_game_session_init_96ee().items():
        mem.ww(DATA_SEGMENT, off, val)
    planet = LEVEL_INDEX_TO_PLANET[level_index % len(LEVEL_INDEX_TO_PLANET)]
    mem.ww(DATA_SEGMENT, 0x2356, planet)
    if container is not None:
        _load_planet_level_data(mem, exe_image, container, planet)
    # 2..6) the level-start / respawn re-init (shared with the 9908 death->respawn composition)
    apply_respawn_seeds(mem)
    # 7) the SCROLL CURSOR.  The static bundle's capture holds whatever the snapshot's level had;
    # a seeded cold image must start where a real level load leaves the cursor, or the first A6FE
    # scroll step wraps DS:234C negative.  These are the values 1010:60AC's warm-up leaves -- MEASURED against the VM (it sets
    # [234C] = CS:[95A2] = 0x680, [2350] = 0EA0, then runs `16 x A781` until [2350] == 9C, then
    # [A978] -= 3).  An earlier version of this seed asserted 234C = 0x5B00 / A978 = 0x110; 0x5B00
    # is CS:[95C0], the wrap-TOP, not the band base, and 0x110 was off by one.  The 98EB game-over
    # composition proved both wrong: every downstream cell (the star draw list, the sprites'
    # +0x0C screen-di, [A278]) is computed from [234C].
    mem.ww(DATA_SEGMENT, 0x234C, 0x1A00)     # the row-source cursor, post-warm-up
    mem.ww(DATA_SEGMENT, 0x234E, 0x0000)     # the origin-x phase
    mem.ww(DATA_SEGMENT, 0x2350, 0x009C)     # the view row base
    mem.ww(DATA_SEGMENT, 0x2352, 0x0000)     # forward scroll
    mem.ww(DATA_SEGMENT, 0xA978, 0x0111)     # rows to the first level-script trigger
    # 8) [BDAC] = 0 -- the render/weapon mode.  The ATTRACT flow sets it to 1 (1010:CF9C) and the
    # attract-exit-into-a-game clears it (1010:D040, `mov word [BDAC],0`); the static bundle's
    # snapshot was captured with the attract value, so a seeded image inherited BDAC = 1 and the
    # first held FIRE walked A067 into its BDAC==1 branch (a genuine gap, but not one a fresh game
    # can reach).  Every mid-play snapshot holds 0.
    mem.ww(DATA_SEGMENT, 0xBDAC, 0x0000)
    return mem


#: the decoded-map body region NOT rewritten by the post-load border init (0BB9..0BD2) -- the
#: border rows outside it are level-independent and stay as the bundle's post-init capture.
_MAP_BODY = (12, 3682)


def _load_planet_level_data(mem: MutFlatMemory, exe_image: bytes, container: bytes,
                            planet: int) -> None:
    """Decode the PLANET's level data into the image's own segments (the 0E9C/0B3E load, natively).

    LEV{n} asset names are PLANET-keyed (pinned by tests/test_level_map_placement.py's fresh-load
    snapshots, which assert ``DS:2356 == n``); the pre-existing bundle capture is overwritten."""
    from overkill.asset_codecs.level_assets import (decode_level_blocks, decode_level_graphics,
                                                    decode_level_tile_map)
    from overkill.asset_codecs.native_level import build_level_class_table
    from overkill.recovered.adapters.level_rom import class_override_pairs_from_rom, extract_level_rom

    cs = 0x1010
    plane_base = mem.rw(cs, 0x9592) * 16
    tile_map = decode_level_tile_map(container, planet)
    b0, b1 = _MAP_BODY
    mem.data[plane_base + b0: plane_base + b1] = tile_map[b0:b1]
    # 0E9C loads TWO per-level files, from the (graphics, blocks) pairs at DS:14E8 + planet*4:
    #   LEV{n}BLX.BIC -> CS:[959A]  (the TILE-BLOCK bank)
    #   G{n}.BIC      -> CS:[95AE]  (the level SPRITE bank)
    # Only the first was being placed.  The sprite bank is what object_sprite_blocks_a846 indexes,
    # so a level's enemies were drawn out of the tile-block bank.
    bank_base = mem.rw(cs, 0x959A) * 16
    blocks = decode_level_blocks(container, planet)
    mem.data[bank_base: bank_base + len(blocks)] = blocks
    gfx_base = mem.rw(cs, 0x95AE) * 16
    graphics = decode_level_graphics(container, planet)
    mem.data[gfx_base: gfx_base + len(graphics)] = graphics
    # CONVERGENCE slice B (docs/overkill/campaigns/convergence.md): the class-override read is the
    # pure level_rom decoder over the 384-byte extracted ROM, not a raw exe_image byte-read -- proven
    # byte-identical to the old exe-based path for every level (tests/test_level_rom.py).
    level_rom = extract_level_rom(exe_image)
    classes = build_level_class_table(class_override_pairs_from_rom(level_rom, planet))
    base = DATA_SEGMENT * 16 + 0xC3AA
    mem.data[base: base + len(classes)] = classes


def apply_respawn_seeds(mem) -> None:
    """The level-start / RESPAWN re-init over a live DGROUP image (in place) -- the seed sequence
    both the cold level start and the ``9908`` death continuation run: C4DB (special + effect pool
    seed + frame-control reset), the C3A6 gameplay-pool seed, the C461 control reset, the C42F
    player spawn, and the post-intro health bar.

    This is exactly what the real ``9908 -> 9773`` respawn re-runs after a death (C4DB at 9908,
    C3A6 -- whose own tail is C42F/C461 -- at 977D), minus the session-scoped ``96EE`` init (score/
    lives/planet persist across deaths).  The health-bar reseed models the post-intro fixed point:
    the real intro script refills DS:A97A 0 -> 0x58 via the per-frame 77C5 tick (gated on
    DS:A97C == 1) before handing over to normal play (the 9A16 script-advance requires A97A==0x58
    AND A95A==3 AND A95C==0x18); an EMPTY bar IS the 9B61 death condition, so leaving it unseeded
    would start (re)play dying the moment the counter bank cycles.
    """
    ds = DATA_SEGMENT

    def write_map(cell_map):
        for off, val in cell_map.items():
            mem.ww(ds, off, val)

    # C4DB new-game setup (special + effect seed + control reset) via the DS:0x32CA table
    # CONVERGENCE slice B (docs/overkill/campaigns/convergence.md): both slot tables are computed
    # arithmetically, not read from the image -- verified byte-identical to the exe's stored tables
    # for every entry (tests/test_seed_slot_tables.py).  Zero exe bytes needed for either.
    write_map(apply_new_game_setup_c4db(object_seed_slot_table_32ca()))
    # C3A6 gameplay-pool seed via the (computed) DS:0x8D12 table
    for rec, fields in object_pool_seed_c3b5(gameplay_seed_slot_table_8d12()).items():
        for fo, val in fields.items():
            mem.ww(ds, rec + fo, val)
    # respawn / level-start control reset
    write_map(respawn_control_reset_c461())
    # player spawn (record 0x237C active at 0xC0/0x58) -- last, over the inactive seed
    for fo, val in player_spawn_record_c42f().items():
        mem.ww(ds, PLAYER_SPAWN_RECORD + fo, val)
    # C450: the 7524-allocated COMPANION object -- the ship's flame/exhaust anchor.  This used to be
    # the file's "known omission (marked, not faked): needs the runtime allocator".  It does not: the
    # allocator is recovered (behavior_walk._alloc, the 7524/7573 cursor scan), and the 9908 respawn
    # continuation already spawns it this way.  Without it a COLD-started level has NO THRUSTERS,
    # while any snapshot does -- exactly the difference the owner saw.
    from overkill.recovered.adapters.behavior_walk import (
        EFFECT_POOL_BASE, EFFECT_POOL_WRAP, EFFECT_SLOTS, _alloc,
    )
    slot = _alloc(mem, 0x95D8, EFFECT_POOL_BASE, EFFECT_POOL_WRAP, EFFECT_SLOTS)
    if slot != 0xFFFF:
        for fo, val in player_companion_spawn_c453().items():
            mem.ww(ds, (slot + fo) & 0xFFFF, val)
    # the health BAR at its post-intro fixed point (AFTER C4DB/C461, which zero it -- see docstring)
    mem.ww(ds, 0xA97A, 0x0058)
    mem.ww(ds, 0xA97C, 0x0001)
    # the 0B3E script-cursor rewind + the wave-state clear: the real death moment runs 4DBF -> 0B3E
    # (the level-data initializer -- traced live: the demo's respawns land with the scroll back at
    # the level start, the six script cursors at their heads, and A47E/A480 zeroed), so a respawned
    # level REPLAYS its spawn script from the top.  On the cold path these are no-ops (the raw
    # bundle already holds the heads and zeros).
    rewind_level_scripts_0b3e(mem)
    mem.ww(ds, 0xA47E, 0x0000)
    mem.ww(ds, 0xA480, 0x0000)


def build_cold_level_start(exe_image: bytes, level_index: int = 0) -> tuple[NativeGameState, StarfieldState]:
    """Assemble the frame-0 level-start ``(NativeGameState, StarfieldState)`` from the recovered seeds.

    ``exe_image`` is the cold runtime data image (its data segment holds the static pool pointer tables
    at ``DS:0x32CA`` / ``DS:0x8D12`` and the starfield stream); this applies the level-start writes on top
    (:func:`build_cold_level_start_image`) and projects the result.  No VM, no captured snapshot.
    ``level_index`` is play_native's 0-based level argument, mapped to the planet number via
    :data:`LEVEL_INDEX_TO_PLANET` (``DS:2356``) -- :func:`new_game_session_init_96ee` alone always seeds
    planet 0 (a fresh SESSION, not a chosen level), so this overrides it afterward, matching how
    :func:`native_new_game_data_setup` (the level-select entry point) sets the SAME cell from a chosen
    level index.
    """
    mem = build_cold_level_start_image(exe_image, level_index)
    ds = DATA_SEGMENT
    return read_native_game_state(mem, ds), load_starfield_state(exe_image)
