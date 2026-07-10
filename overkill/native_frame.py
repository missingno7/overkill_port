"""The NATIVE GAMEPLAY FRAME (the demo-lockstep campaign's one frame implementation).

``advance_gameplay_frame_97b2`` advances ONE ``1010:97B2`` gameplay frame on the DGROUP image --
the same boundary ``verify_native_lockstep`` snapshots the VM at.  It executes the REAL stage
order (native_app.GAMEPLAY_FRAME_STAGES) and raises :class:`RecoveryGap` at the first stage whose
DGROUP effects are not natively owned yet -- the gate's per-frame gap report IS the campaign
frontier.  Video-only stages (the draw scan, the present blit, the conditional HUD cell, the
status text) do not mutate DGROUP and are composed separately by the render path; the DGROUP
comparison this frame feeds does not see them.

Discipline (campaigns/demo_lockstep.md): image-only (ADR-1), the real 97B2 stage order, never
mask a divergence, one frame implementation shared by the gate and play_native.
"""
from __future__ import annotations

from overkill.recovered.domain.gaps import RecoveryGap
from overkill.recovered.domain.tilemap import LevelTileContext
from overkill.recovered.systems.input import decode_keyboard_input_flags
from overkill.recovered.adapters.tile_cues import run_tile_cue_row_7948
from overkill.recovered.adapters.level_object_script import (
    SCRIPT_CURSOR_HEADS_0B3E, run_level_object_script_4a65,
)
from overkill.recovered.adapters.behavior_walk import (
    _alloc, _bd17_deactivate, _rotating_pool_scan_b15a, _shot_hit_9e19,
    run_behavior_walk_a9d3, run_level_end_arm_a680,
)
from overkill.recovered.systems.tilemap import compute_tile_probe_5073, lookup_tile_class_byte
from overkill.recovered.domain.tilemap import TileProbeInput
from overkill.recovered.systems.frame_loop import frame_state_update_a940

DS = 0x25CC
CS = 0x1010

#: optional mid-frame observation hook used ONLY by probes (``native_frame._AT_9BCA = fn``);
#: it is None in every normal run and costs one ``is not None`` test per frame.
_AT_9BCA = None


def level_tiles_from_image(mem) -> LevelTileContext:
    """The frame's tile context, read fresh from the image (the plane scrolls in place and the
    class table rebuilds on level transitions)."""
    seg = mem.rw(CS, 0x9592)
    plane = bytes(mem.data[seg * 16:seg * 16 + 0x4000])
    classes = tuple(mem.rb(DS, (0xC3AA + i) & 0xFFFF) for i in range(256))
    return LevelTileContext(origin_x_word=mem.rw(DS, 0x234E),
                            row_base_word=mem.rw(DS, 0x2350),
                            tile_plane=plane, class_table=classes)


def advance_gameplay_frame_97b2(mem, *, isr_ticks: int = 2, level_bytes: bytes | None = None) -> None:
    """One 97B2 frame over the image, stage by stage.

    ``isr_ticks`` is the HOST INPUT for this frame: how many INT8 timer interrupts fired while it
    ran (see :func:`_isr_effects_ticks`).  Steady-state play is 2, which is the default; the lockstep
    gate passes the count it recorded from the original.

    ``level_bytes`` is the OTHER host input: the level map file (``LEV{n}MAP.BIC``) that ``C679``
    fetches with INT 21h when the player dies and the level re-inits.  It is only read on a death
    frame; passing ``None`` there fails loud rather than approximating the reload.

    Stage map (1010:97B2..981D; video-only stages noted, DGROUP-mutating stages executed or
    fail-loud):

    * 0672 timer tick clear -- host pacing; clears CS:[066B] (a CS cell, not DGROUP).
    * 511F page toggle -- video mode 2 (Tandy) is a no-op.
    * A846 sprite draw scan -- VIDEO (the page compose); no DGROUP writes.
    * [A97A]==0 -> 981F HUD cell -- VIDEO.
    * 5BDC present -- VIDEO.
    * A90C present-scan -- DGROUP: every record's +0x0C screen-di projection (native below).
    * 9B2E game-state controller -- DGROUP.  Interior (disasm 2026-07-07): clear A346/A344;
      0162 (input poll -> [98BE] bits); [A47C]!=0 -> 99F6 outro script (native); [A47C]==4 ->
      A344=1 ret; A278=0; A212 (bp=237C prelude); the 9B61 death branch -> 9AFF (native);
      [98BE] bits 8/4/1/2 -> A5D1/A5EA/A607/A5F9 (the four MOVE handlers); [2350]>0xB6 and
      bit 0x20 -> 8546 (FIRE); A66F (scroll); A067 (fire path); [978E]&&[98C8]==1 -> 9D4D (the
      weapon upgrade, native); [A47C]<=1 -> A616; [A47C]==0 -> 9CB6; [2350]>0xB6 -> 9C01; 9CF1;
      9CD9; A031 (the pod-position feeder from the [A33C..] rings); BDAC/2350-gated 9FAF.
      NOT image-native yet: fail loud (the frontier).
    * A344/A342/A346 transition branches -- the frame ENDS at a taken exit.
    * A940 -- frame-state update (recovered pure), then FALLS THROUGH into the OBJECT WALK
      (1010:A9D3..AA25, native + dry for L1-L3) and the far 1F8F:0922 tail.  The walk is stage
      9's interior, NOT 9B2E's (disasm: no ret between A940 and A9D3; A9B8 far-calls 1F8F:081D).
    * 073C service gate / 60A2 status text / 5160 / 0679 -- host/video tails.
    """
    # --- stage 6: A90C present-scan (the +0x0C screen-di projection) ---------------------------
    # DGROUP-visible and BEFORE 9B2E in the frame order; native_walk_frame.sync_screen_projection
    # owns the projection math but was verified as a post-walk sync, not at this stage position.
    _step_9b2e(mem, level_bytes)
    # --- the 97CE transition branches, in the original's order ---------------------------------
    # 97CE: [A344] == 1 -> 9734 (level complete);  97D8: [A342] == 1 -> 9902 (game over);
    # 97E2: [A346] == 1 -> 9908 (DEATH -> respawn).  Only the respawn is wired; the other two still
    # leave the loop here, which is why the gate cannot see past them.
    if mem.rw(DS, 0xA344) == 1 or mem.rw(DS, 0xA342) == 1:
        return
    if mem.rw(DS, 0xA346) == 1:
        # The death frame does NOT run 073C / 60A2 / 0679: 9908's chain re-enters the loop at the
        # 97B2 head, so the frame's tail is the continuation followed by the ordinary present half.
        # The ISR ticks are applied INSIDE the continuation (at the 9921 spin), not here.
        _respawn_continuation_9908(mem, isr_ticks)
        _present_half(mem)
        return
    # --- stage 9: A940 (frame-state update -> the OBJECT WALK -> the 0922 starfield tick) ------
    _a940_walk_stage(mem)
    # --- stage 10: 073C service gate (gated on [9907] == 1; normally an instant ret) -----------
    if mem.rw(DS, 0x9907) & 0xFF == 1:
        raise RecoveryGap("the 073C service body ([9907] == 1)", "unrecovered service path")
    # --- stage 11: the 60A2 stage -- 77C5 (the A97C shield drain) + 5F61 (THE CLOCK TICK) ------
    _shield_charge_77c5(mem)
    _clock_tick_5f61(mem)
    # --- the INT8 ISR's per-frame DGROUP effects (two ticks per frame: the [0054] parity pair) -
    _isr_effects_ticks(mem, isr_ticks)
    # --- the NEXT frame's present half (the 9B2E boundary cut) ---------------------------------
    _present_half(mem)


def _present_half(mem) -> None:
    """The 97B2 loop head's DGROUP-visible work, up to the next 9B2E boundary.

    Runs after the frame tail on the ordinary path and after the respawn continuation on the death
    path -- both re-enter the loop at 97B2."""
    from overkill.native_walk_frame import sync_screen_projection
    # The present half, in the original's order: A846 = SAVE-UNDER loops (32CA cx=0x24, then 8D12
    # cx=0x22) -> 4CED (stars) -> the 7596 sprite draws.  A90C then RESTORES the saved background
    # and 4D64 undraws the stars, so at the next 9B2E boundary the strip is tiles-only again and
    # the ONLY persistent DGROUP effect of the whole present half is the save buffers themselves.
    sync_screen_projection(mem)
    _save_under_a846(mem)
    _star_list_4ced(mem)
    _flash_decay_a846(mem)


#: A846's save loops, in order: the 32CA table (cx = 0x24..1) then the 8D12 table (0x22..1)
_A846_SAVE_ORDER = ((0x32CA, 0x24), (0x8D12, 0x22))
#: the 5AC8 jump table (`word [CS:5AE2 + (draw_type + 3*mode)*2]`, mode 2) selects the saver, and
#: each has its own block geometry (rows, bytes-per-row); the source stride is always 0x68:
#:   type 0 -> 3657: 8 rows x `movsw x2` (+ add si,0x64) =  4 B/row
#:   type 1 -> 35CC: 16 rows x `movsw x4` (+ add si,0x60) =  8 B/row
#:   type 2 -> 356C -> the 35AB helper: 16 rows x `movsw x8` (+ add si,0x58) = 16 B/row, TWO slots,
#:            the second at `[rec+0x0E] + 0x140` (not packed after the first)
SAVE_GEOMETRY = {0: (8, 4), 1: (16, 8), 2: (16, 16)}
SAVE_SLOT2_DEST = 0x140


def _save_under_a846(mem) -> None:
    """``1010:5AC8`` -> ``35CC`` (draw type 1) / ``356C`` (type 2): save the background under each
    drawn record.

    Per slot: ``si`` = the projected ``+0x0C`` screen di (``[234C]``-relative), ``di`` = the
    record's SAVE-BUFFER pointer at ``+0x0E``, ``ds`` = the strip, ``es`` = DGROUP; then 16 rows,
    each ``movsw`` run followed by ``add si,bx`` so the source walks the 0x68 strip stride.  A
    culled slot (``0xFFFF``) saves nothing.  Type 2 (the player) saves TWO slots -- ``+0x0C`` and
    ``+0x10`` -- the second at ``+0x0E + 0x140``.

    The source is simply the STRIP, read as the original reads it.  (An earlier version DERIVED the
    strip from the tile plane, because the lockstep replay cache did not carry the strip's
    above-DGROUP bytes; the cache now records the strip, so the frame no longer has to guess.)
    Gate-verified against the driven original at ``(CS,0xA876)``.
    """
    strip_seg = mem.rw(CS, 0x9598)

    def save_slot(di: int, dest: int, rows: int, row_bytes: int) -> None:
        """35CC/356C/3657: `rep movsw` straight out of the strip, `add si,bx` per row."""
        if di == 0xFFFF:
            return
        for row in range(rows):
            src = (di + row * STRIP_STRIDE) & 0xFFFF
            for j in range(row_bytes):
                mem.wb(DS, (dest + row * row_bytes + j) & 0xFFFF,
                       mem.rb(strip_seg, (src + j) & 0xFFFF))

    for table, count in _A846_SAVE_ORDER:
        for k in range(count, 0, -1):
            rec = mem.rw(DS, (table + k * 2) & 0xFFFF)
            if not rec or mem.rw(DS, rec) == 0:
                continue
            draw_type = mem.rw(DS, rec + 0x14)
            geom = SAVE_GEOMETRY.get(draw_type)
            if geom is None:
                raise RecoveryGap(f"A846 save for draw type {draw_type} (record {rec:04X})",
                                  "only the 3657/35CC/356C savers (draw types 0/1/2) are decoded")
            rows, row_bytes = geom
            dest = mem.rw(DS, rec + 0x0E)
            save_slot(mem.rw(DS, rec + 0x0C), dest, rows, row_bytes)
            if draw_type == 2:
                save_slot(mem.rw(DS, rec + 0x10),
                          (dest + SAVE_SLOT2_DEST) & 0xFFFF, rows, row_bytes)


#: the player view-anchor record (the only record whose +0x24 flash is DGROUP-visible at DS:23A0)
ANCHOR = 0x237C


def _flash_decay_a846(mem) -> None:
    """The A846 draw scan's HIT-FLASH decay: each compositor prologue (1010:25AE / 30FF / 4227)
    runs ``cmp [bp+24h],0 ; jz .. ; dec [bp+24h]`` -- i.e. a drawn record's +0x24 flash counter
    ticks down ONCE PER DRAWN SLOT, not once per frame.  The player anchor (0x237C, draw type 2)
    issues TWO slots, so DS:23A0 (= 0x237C + 0x24) decays by 2 per frame while it is on screen;
    a culled slot (its di cell holds the 0xFFFF off-screen sentinel) issues no compositor call and
    so does not tick."""
    flash = mem.rw(DS, ANCHOR + 0x24)
    if flash == 0:
        return
    slots = 0
    if mem.rw(DS, ANCHOR + 0x0C) != 0xFFFF:
        slots += 1
    if mem.rw(DS, ANCHOR + 0x10) != 0xFFFF:
        slots += 1
    for _ in range(slots):
        if flash == 0:
            break
        flash -= 1
    mem.ww(DS, ANCHOR + 0x24, flash)


def _star_list_4ced(mem) -> None:
    """``1010:4CED`` -- the star pass, called from A846 (at A876) right after its per-object loop.

    GATE-PROVEN SHAPE (``verify_native_star_strip``: 10/10 strip windows and 10/10 produced lists
    byte-exact vs the driven VM):

    * the occupancy the pass tests (``cmp es:[bx],0``, ``es = CS:[9598]``) is the **terrain window
      and nothing else** -- at 4CED the sprites have been erased by A846's own loop and the previous
      frame's stars were undrawn by ``4D64`` (called from A90C, after the blit).  So it is a pure
      function of DGROUP: ``compose_tile_window`` packed 2 px/byte at the 0x68 stride.
    * per ring star (three parallax layers of 20/10/10 at ``DS:C6C1``, 6 bytes each): the cell is
      ``bx = tick*0x68 + [234C] + xoff``; an OCCUPIED cell skips the star, a free one plots it (so
      later stars see it) and appends ``bx`` to the ``DS:C7B1`` list, which is FFFF-terminated.

    Only the LIST is persistent state: the star pixels this pass writes into the strip are undrawn
    again by ``4D64`` before the next 9B2E boundary, so within one lockstep frame their net effect
    is nil -- writing them here is what made the earlier attempt *add* ~2700 divergences.
    """
    if mem.rw(CS, 0x95BC) == 1:
        raise RecoveryGap("4CED's video-mode-1 star pass", "Tandy is mode 2")

    window = _terrain_window(mem)
    scroll = mem.rw(DS, 0x234C)
    di = 0xC7B1
    si = 0xC6C1
    for count in (0x14, 0x0A, 0x0A):
        for _ in range(count):
            tick = mem.rw(DS, si)
            xoff = mem.rw(DS, (si + 2) & 0xFFFF)
            px = mem.rb(DS, (si + 4) & 0xFFFF)
            si = (si + 6) & 0xFFFF
            bx = (tick * STRIP_STRIDE + scroll + xoff) & 0xFFFF
            t, c = divmod(bx - scroll, STRIP_STRIDE)
            if not (0 <= t < STRIP_ROWS and 0 <= c < STRIP_STRIDE):
                continue
            if window[t][c]:
                continue                       # 4D28: occupied -> skip
            window[t][c] = px                  # 4D59: plot (later stars see it)
            mem.ww(DS, di, bx)                 # 4D5C: append
            di = (di + 2) & 0xFFFF
    mem.ww(DS, di, 0xFFFF)                     # 4D10: terminate


STRIP_STRIDE = 0x68        # 104 bytes per scanline (208 px, 2 px/byte)
STRIP_ROWS = 192
STRIP_TOP_Y = 4


def _terrain_stack(mem):
    """The WHOLE packed terrain strip stack, and the visible window's offset into it.

    ``compose_tile_window`` renders 14 bands of 16 scanlines (``row_base``, ``row_base - 0x0D``,
    ...) and slices the visible 192 rows starting ``16 + phase`` in.  The star pass only needs that
    window, but A846's save-under reads 16 rows starting at a sprite's own di, which can straddle
    the window's top or bottom -- and those rows ARE in the stack.  So build the stack once and let
    callers index it by window-relative row ``t`` (``stack[start + t]``).

    Returns ``(packed_stack, start)`` where ``packed_stack[r][c]`` is the strip byte (2 px) of
    absolute stack row ``r``.
    """
    import numpy as np

    from overkill.native_video.tile_row import (
        BANK2_ROW_BASE, PLANE_ROW_STRIDE, TILE_ROWS, WINDOW_BANDS, render_tile_row,
    )

    row_base = mem.rw(DS, 0x2350)
    mem_np = np.frombuffer(bytes(mem.data), dtype=np.uint8)
    plane_seg = mem.rw(CS, 0x9592)
    plane = mem_np[plane_seg * 16: plane_seg * 16 + 0x10000]
    table = [mem.rw(CS, (0x8D92 + 2 * k) & 0xFFFF) for k in range(0x100)]
    bank_ptr = 0x959C if row_base >= BANK2_ROW_BASE else 0x959A
    bank = mem.rw(CS, bank_ptr)
    graphics = mem_np[bank * 16: bank * 16 + 0x10000]
    strips = [render_tile_row(plane, (row_base - s * PLANE_ROW_STRIDE) & 0xFFFF, table, graphics)
              for s in range(WINDOW_BANDS + 2)]
    stack = np.concatenate(strips, axis=0)[:, :STRIP_STRIDE * 2]
    pairs = stack.reshape(stack.shape[0], STRIP_STRIDE, 2)
    packed = ((pairs[:, :, 0] << 4) | pairs[:, :, 1]).tolist()
    return packed, TILE_ROWS + (mem.rw(DS, 0x234E) & 0x0F)


def _terrain_window(mem) -> "list[list[int]]":
    """The (192, 104) packed terrain bytes 4CED probes -- the visible slice of the stack."""
    packed, start = _terrain_stack(mem)
    return packed[start: start + STRIP_ROWS]


def _a940_walk_stage(mem) -> None:
    """Stage 9: ``1010:A940`` (the recovered pure frame-state update), falling through into the
    OBJECT WALK (A9D3..AA25, native) and the far ``1F8F:0922`` STARFIELD tick (the C6C1 ring:
    20 + 10 + 10 star words at stride 6, wrap 0xC0, three parity-gated layers; skipped while the
    player anchor state is FFFF)."""
    u = frame_state_update_a940(
        mem.rw(DS, 0xA8CE), mem.rw(DS, 0xA8C8), mem.rw(DS, 0xA8CC),
        mem.rw(DS, 0x2356), mem.rb(DS, 0x98A8), mem.rw(DS, 0xA8C2))
    mem.ww(DS, 0xA8CE, u.counter_a8ce)
    mem.ww(DS, 0xA8C6, u.prev_a8c6)
    mem.ww(DS, 0xA8CA, u.prev_a8ca)
    mem.ww(DS, 0xA8CC, u.a8cc_reset)
    mem.wb(DS, 0x98A8, u.flag_98a8)
    mem.wb(DS, 0x98A9, u.flag_98a9)
    run_behavior_walk_a9d3(mem, level_tiles_from_image(mem))
    # 1F8F:0922 -- the starfield tick
    if mem.rw(DS, 0xA95A) == 0xFFFF:
        return
    parity = (mem.rw(DS, 0xC812) + 1) & 1
    mem.ww(DS, 0xC812, parity)
    if parity:
        return
    si = 0xC6C1
    for layer_cells, gate in ((0x14, None), (0x0A, 0xC814), (0x0A, 0xC816)):
        if gate is not None:
            g = (mem.rw(DS, gate) + 1) & 1
            mem.ww(DS, gate, g)
            if g:
                return
        for _ in range(layer_cells):
            v = (mem.rw(DS, si) + 1) & 0xFFFF
            mem.ww(DS, si, 0 if v == 0x00C0 else v)
            si = (si + 6) & 0xFFFF


def _clock_tick_5f61(mem) -> None:
    """``1010:5F61`` (called from the 60A2 stage) -- THE FRAME CLOCK: the A480 countdown's CB1C
    music beat, the [2328]==7 vertical-delta flip machinery (2342/2344/2346/2348), the [2332]
    quarter-gated slow clocks (2334/2338/233A/233E/233C/2336 + the A7A0 wave phase), the fast
    2324..2330 cascade, and the 606F difficulty-paced 9EE4 drain beats."""
    if mem.rw(DS, 0xA47E) == 0 and mem.rw(DS, 0xA480) != 0:
        v = (mem.rw(DS, 0xA480) - 1) & 0xFFFF
        mem.ww(DS, 0xA480, v)
        if v == 0:                                   # 5F75: the planet-keyed CB1C music beat
            al = mem.rb(DS, (0x231E + (mem.rb(DS, 0x2356))) & 0xFFFF)
            if mem.rw(DS, 0x2350) >= 0x0750:
                al = 6
            mem.wb(DS, 0x98C2, al)                   # CB1C ([98C1]-gated sound-seg writes: host)
    if mem.rw(DS, 0x2328) == 7:                      # 5F89
        if mem.rw(DS, 0x2342) == 0xFFFF:             # 5F90
            v = (mem.rw(DS, 0x2344) - 1) & 0xFFFF    # 5FAC
            mem.ww(DS, 0x2344, v)
            if v == 0:
                mem.ww(DS, 0x2342, (-mem.rw(DS, 0x2342)) & 0xFFFF)
                mem.ww(DS, 0x2348, (mem.rw(DS, 0x2348) + 1) & 0xFFFF)
        else:
            v = (mem.rw(DS, 0x2344) + 1) & 0xFFFF    # 5F97
            mem.ww(DS, 0x2344, v)
            if v == 2:
                mem.ww(DS, 0x2342, (-mem.rw(DS, 0x2342)) & 0xFFFF)
                mem.ww(DS, 0x2348, (mem.rw(DS, 0x2348) + 1) & 0xFFFF)
    mem.ww(DS, 0x2348, mem.rw(DS, 0x2348) & 0x000F)  # 5FBA
    if mem.rw(DS, 0x2348) == 0:
        mem.ww(DS, 0x2346, 8)
        mem.ww(DS, 0x2348, (mem.rw(DS, 0x2348) + 1) & 0xFFFF)
    quarter = (mem.rw(DS, 0x2332) + 1) & 0x0003      # 5FCB
    mem.ww(DS, 0x2332, quarter)
    if quarter == 0:                                 # the slow group + the A7A0 wave phase
        v = (mem.rw(DS, 0x2334) + 1) & 0xFFFF        # 5FD6 (cmp 0xA reset)
        mem.ww(DS, 0x2334, 0 if v >= 0x0A else v)
        v = (mem.rw(DS, 0x2338) + 1) & 0xFFFF
        mem.ww(DS, 0x2338, 0 if v >= 6 else v)
        v = (mem.rw(DS, 0x233A) + 1) & 0xFFFF
        mem.ww(DS, 0x233A, 0 if v >= 5 else v)
        v = (mem.rw(DS, 0x233E) + 1) & 0xFFFF
        mem.ww(DS, 0x233E, 0 if v >= 3 else v)
        mem.ww(DS, 0x233C, (mem.rw(DS, 0x233C) + 1) & 3)
        mem.ww(DS, 0x2336, (mem.rw(DS, 0x2336) + 1) & 7)
        mem.ww(DS, 0xA7A0, (mem.rw(DS, 0xA7A0) + 1) & 0xFFFF)   # 602C
    mem.ww(DS, 0x2324, mem.rw(DS, 0x2324) ^ 1)       # 6030
    mem.ww(DS, 0x2326, (mem.rw(DS, 0x2326) + 1) & 0x0003)
    mem.ww(DS, 0x2328, (mem.rw(DS, 0x2328) + 1) & 0x0007)
    mem.ww(DS, 0x232A, (mem.rw(DS, 0x232A) + 1) & 0x000F)
    mem.ww(DS, 0x232C, (mem.rw(DS, 0x232C) + 1) & 0x001F)
    mem.ww(DS, 0x232E, (mem.rw(DS, 0x232E) + 1) & 0x003F)
    mem.ww(DS, 0x2330, (mem.rw(DS, 0x2330) + 1) & 0x007F)
    # 606F: the difficulty-paced drain beats
    gate_hit = (mem.rw(DS, 0x2330) == 0x007F if mem.rw(DS, 0xBEDC) <= 1
                else mem.rw(DS, 0x232E) == 0x003F)
    if gate_hit:
        _energy_drain_9ee4(mem)                      # 6084
    if (mem.rw(DS, 0x2384) == 2 and mem.rw(DS, 0x232C) == 0x001F):
        v = mem.rw(DS, 0x234A) ^ 1                   # 6097
        mem.ww(DS, 0x234A, v)
        if v == 0:
            _energy_drain_9ee4(mem)                  # 609F: jmp 9EE4


#: 77F6's only DGROUP write: `mov [95DC],di`, with di from the `call 5A00` at 77FA (the rel16 is
#: relative to the NEXT instruction, 0x77FD).  Driven on the original with `ax = 0x5F1D`:
#: di = 0x6ED4 -- the energy bar's page origin, and exactly the value the VM holds.  Everything else
#: 77F6 does is pixels into the visible page (`es = CS:[95A4]` = B800), outside DGROUP.
BAR_PAGE_DI = 0x6ED4


def _bar_draw_77f6(mem) -> None:
    """``1010:77F6`` -- redraw the energy bar.  DGROUP-visible part only."""
    mem.ww(DS, 0x95DC, BAR_PAGE_DI)
    if mem.rw(CS, 0x95BC) == 1:
        raise RecoveryGap("77E3's mode-1 dual-page bar redraw (511F)", "Tandy is mode 2")


def _shield_charge_77c5(mem) -> None:
    """``1010:77C5`` (the 60A2 stage): while the shield pickup is held (``[A97C] == 1``) and the
    player is not dying (``[2384] < 3``), the energy bar CHARGES one step per frame.  At full
    (``[A97A] == 0x58``) the 77B2 tail fires sound 0x0C and clears ``[A97C]`` (the shield is spent);
    otherwise ``[A97A]`` increments and the bar is redrawn (77DF -> 77F6)."""
    if mem.rw(DS, 0xA97C) != 1:                      # 77C5
        return
    if mem.rw(DS, 0x2384) >= 3:                      # 77CD: dying -> nothing
        return
    if mem.rw(DS, 0xA97A) == 0x0058:                 # 77D4 -> 77B2: full
        if mem.rb(DS, 0x98C0):
            mem.wb(DS, 0xBEFF, 0x0C)
        mem.ww(DS, 0xA97C, 0)
        return
    mem.ww(DS, 0xA97A, (mem.rw(DS, 0xA97A) + 1) & 0xFFFF)   # 77DB
    _bar_draw_77f6(mem)                              # 77DF


def _energy_drain_9ee4(mem) -> None:
    """``1010:9EE4`` -- the periodic energy DRAIN (the 606F beats).  An empty bar is a no-op; else
    ``[A97A]`` decrements.  Still non-zero -> just redraw.  Emptied: the ``[978C]`` cheat refills it
    to 0x58, otherwise the player enters the dying pose (``[2384] = 3``) with sound 0x19.  All paths
    tail into the 77DF bar redraw."""
    a97a = mem.rw(DS, 0xA97A)
    if a97a == 0:                                    # 9EE4
        return
    a97a = (a97a - 1) & 0xFFFF
    mem.ww(DS, 0xA97A, a97a)
    if a97a != 0:                                    # 9EF0 -> 77DF
        _bar_draw_77f6(mem)
        return
    if mem.rb(DS, 0x978C) == 1:                      # 9EF5 -> 9F11: the cheat refill
        mem.ww(DS, 0xA97A, 0x0058)
        _bar_draw_77f6(mem)
        return
    mem.ww(DS, 0x2384, 0x0003)                       # 9EFC: the dying pose
    if mem.rb(DS, 0x98C0):
        mem.wb(DS, 0xBEFF, 0x19)
    _bar_draw_77f6(mem)


def _isr_effects_ticks(mem, ticks: int) -> None:
    """The INT8 ISR's per-frame DGROUP effects: ``ticks`` fires of the timer interrupt.

    Each fire bumps ``[0054]`` (mod 4 -- the parity the game paces on via CS:[066B], which the ISR
    sets every OTHER fire) and runs one D50E sound-engine step (``[BF00] += 1 & 3``; the [BEFF]
    effect-queue consume and the BFAA/BFBA channel steppers are the AUDIO campaign -- fail loud when
    a sound is actually queued so the gate names the cells).

    HOW MANY TICKS is not game state: it is how many timer interrupts the HOST delivered while the
    frame ran, exactly as the key table is what the HOST's keyboard delivered.  Steady-state play is
    2 (the frame-wait at 0679 blocks for the pair), and that is the default the native game uses --
    but driving the original over the cold-start demo shows the true distribution is
    ``{0: 2, 1: 1, 2: 8284, 7: 1, 402: 4}`` windows: the four 402s are the death/respawn frames,
    whose 418626-instruction level reload outruns the timer by two hundred ticks.  So the lockstep
    gate RECORDS the count per window (it traps the INT8 vector 1010:06E5) and passes it here.
    ``[0054]``/``[BF00]`` are only 2-bit counters, so the count cannot be recovered from DGROUP
    after the fact -- an earlier hard-coded 2 put frame 4637 (a genuine one-tick window) into
    divergence, one sound-engine step ahead of the original.
    """
    for _ in range(ticks):
        mem.wb(DS, 0x0054, (mem.rb(DS, 0x0054) + 1) & 0x03)
        _sound_engine_tick_d50e(mem)


def _sound_period_d61f(mem, ch: int) -> None:
    """``1010:D61F``: the channel's PIT period (+6) from the DS:BF01 note table (note*2)."""
    note = mem.rb(DS, ch + 4)
    mem.ww(DS, ch + 6, mem.rw(DS, (0xBF01 + ((note << 1) & 0xFF)) & 0xFFFF))


def _sound_channel_step_d5ac(mem, ch: int) -> None:
    """``1010:D5AC`` -- one channel's per-tick step of the two-channel SOUND BYTECODE interpreter
    (channel blocks at DS:BFAA / DS:BFBA: +2 script ptr, +4 note, +5 default duration, +6 PIT
    period, +8 countdown, +9 status, +0xB note-slide delta, +0xC pitch-slide delta word, +0xE
    pitch-slide count).  A non-expired countdown runs the two slides; expiry fetches bytecode:
    notes (< 0x80) commit note+period+status 2; 0xE0+ sets the default duration; 0x80..0x85
    dispatch the DS:BEF0 op table {stop, rest, slide-down, slide-up, pitch-params, hold}.  The
    PIT/speaker port writes are host I/O -- DGROUP only here."""
    bx = mem.rw(DS, ch + 2)
    cnt = (mem.rb(DS, ch + 8) - 1) & 0xFF
    mem.wb(DS, ch + 8, cnt)
    if cnt != 0:
        delta = mem.rb(DS, ch + 0x0B)               # D612: the note slide
        if delta:
            mem.wb(DS, ch + 4, (mem.rb(DS, ch + 4) + delta) & 0xFF)
            _sound_period_d61f(mem, ch)
        if mem.rb(DS, ch + 0x0E):                   # D602: the pitch slide
            mem.wb(DS, ch + 0x0E, (mem.rb(DS, ch + 0x0E) - 1) & 0xFF)
            mem.ww(DS, ch + 6, (mem.rw(DS, ch + 6) + mem.rw(DS, ch + 0x0C)) & 0xFFFF)
        return
    while True:                                     # D5BB: the fetch loop
        al = mem.rb(DS, bx & 0xFFFF)
        bx = (bx + 1) & 0xFFFF
        if al < 0x80:                               # a NOTE
            mem.wb(DS, ch + 4, al)
            _sound_period_d61f(mem, ch)
            mem.wb(DS, ch + 9, 2)
            break
        if al >= 0xE0:                              # D5FB: the duration prefix
            mem.wb(DS, ch + 5, (al - 0xDF) & 0xFF)
            continue
        op = al - 0x80                              # the BEF0 op table
        if op == 0:                                 # D62F: STOP (kills the whole effect; no commit)
            mem.wb(DS, 0xBEFE, 0)
            mem.wb(DS, 0xBFB3, 0)
            mem.wb(DS, 0xBFC3, 0)
            return
        if op == 1:                                 # D5D6: REST
            mem.wb(DS, ch + 9, 0)
            break
        if op == 2:                                 # D641: slide down
            mem.wb(DS, ch + 0x0B, 0xFF)
            continue
        if op == 3:                                 # D648: slide up
            mem.wb(DS, ch + 0x0B, 0x01)
            continue
        if op == 4:                                 # D64F: pitch-slide params
            mem.ww(DS, ch + 0x0C, mem.rw(DS, bx & 0xFFFF))
            bx = (bx + 2) & 0xFFFF
            mem.wb(DS, ch + 0x0E, mem.rb(DS, bx & 0xFFFF))
            bx = (bx + 1) & 0xFFFF
            continue
        if op == 5:                                 # D5CC: hold (straight to the commit)
            break
        raise RecoveryGap(f"sound opcode {al:#04x} (channel {ch:04X})",
                          "the BEF0 table's entries 6/7 are unused/garbage in the shipped data")
    mem.ww(DS, ch + 2, bx)                          # D5CC: commit + reload the countdown
    mem.wb(DS, ch + 8, mem.rb(DS, ch + 5))


def _sound_engine_tick_d50e(mem) -> None:
    """``1010:D50E`` -- ONE ISR sound tick (DGROUP only; the PIT/speaker port writes are host):
    the [BF00] beat, the [BEFF] queue -> D566 effect start (priority: a LOWER id preempts, equal
    restarts, higher is ignored WITHOUT consuming the queue; id >= 0x20 is the STOP command),
    then both channel steps while an effect is live."""
    mem.wb(DS, 0xBF00, (mem.rb(DS, 0xBF00) + 1) & 0x03)   # fe 06: a BYTE inc
    al = mem.rb(DS, 0xBEFF)
    if al:
        if al >= 0x20:                              # D62F via D568: the stop command
            mem.wb(DS, 0xBEFE, 0)
            mem.wb(DS, 0xBFB3, 0)
            mem.wb(DS, 0xBFC3, 0)
        else:
            cur = mem.rb(DS, 0xBEFE)
            if not (cur != 0 and al != cur and al > cur):
                mem.wb(DS, 0xBEFE, al)              # D57C: start the effect
                si = (0xBFCA + ((al << 2) & 0xFFFF)) & 0xFFFF
                mem.ww(DS, 0xBFAC, mem.rw(DS, si))
                mem.ww(DS, 0xBFBC, mem.rw(DS, (si + 2) & 0xFFFF))
                for cell in (0xBFB5, 0xBFC5, 0xBFB8, 0xBFC8, 0xBEFF):
                    mem.wb(DS, cell, 0)
                mem.wb(DS, 0xBFB2, 1)
                mem.wb(DS, 0xBFC2, 1)
    if mem.rb(DS, 0xBEFE) != 0:                     # D521 -> the two channel steps
        _sound_channel_step_d5ac(mem, 0xBFAA)
        _sound_channel_step_d5ac(mem, 0xBFBA)


def _input_poll_0162(mem) -> None:
    """``1010:0162`` -- the per-frame input poll: the eight-scancode control map (DS:213E, or
    DS:2146 when [0010] == 2) packs MSB-first from the DS:98C4 INT9 key-state table, then the six
    fixed keys OR in -- the DS:98BE button byte (the recovered, verified
    ``decode_keyboard_input_flags``).  The key-state table is IRQ-written INTO THE IMAGE, so the
    lockstep frame decodes input purely from the image -- no external input channel."""
    if mem.rw(DS, 0x0010) == 1:
        raise RecoveryGap("0162's non-keyboard input mode ([0010] == 1)",
                          "only the keyboard paths ([0010] == 0/2) are wired")
    map_base = 0x2146 if mem.rw(DS, 0x0010) == 2 else 0x213E
    control_map = tuple(mem.rb(DS, (map_base + i) & 0xFFFF) for i in range(8))
    key_state = tuple(mem.rb(DS, (0x98C4 + i) & 0xFFFF) for i in range(256))
    mem.wb(DS, 0x98BE, decode_keyboard_input_flags(control_map, key_state))


def _step_9b2e(mem, level_bytes: bytes | None = None) -> None:
    """``1010:9B2E`` -- the game-state controller, decomposed stage by stage against the lockstep
    gate (the interior map is in :func:`advance_gameplay_frame_97b2`'s docstring)."""
    mem.ww(DS, 0xA346, 0)                       # 9B2E
    mem.ww(DS, 0xA344, 0)                       # 9B34
    _input_poll_0162(mem)                       # 9B3A
    if mem.rw(DS, 0xA47C) != 0:                 # 9B3D -> 99F6: the outro scripted input
        raise RecoveryGap("the 99F6 outro path inside the lockstep frame ([A47C] != 0)",
                          "run_outro_script_99f6 exists (adapters/behavior_walk) but its exact "
                          "in-frame composition here is unverified -- wire when a demo reaches it")
    mem.ww(DS, 0xA278, 0)                       # 9B55
    # 9B5B: bp = 237C; A212 -- the sibling-snake mover, gated on the A3B4 list being populated
    # ([A972] != 0); an empty list is an immediate ret (the normal-L1 path).
    if mem.rw(DS, 0xA972) != 0:
        raise RecoveryGap("the A212 sibling-snake mover ([A972] != 0)",
                          "only the empty-list early-out is wired; decode A212's body when a demo"
                          " populates the A3B4 list")
    anchor = 0x237C
    # 9B61: the death branch -- anchor state absent -> the 9AFF death tail INSTEAD of the whole
    # player flow.  9AFF: on [2326] == 3 the anchor +08 explosion counter ticks; at 0x0F the
    # anchor deactivates, 4DBF runs, [A346] = 1, and an empty [A97A] bar also raises [A342] = 1
    # (game over).
    #
    # 4DBF IS THE LEVEL RE-INIT, NOT A JINGLE.  (An earlier note here guessed "the death jingle --
    # a host boundary"; a coverage map of the death window disproved it.)  Driven at the 5018th
    # 9B2E boundary of the cold-start demo, the window runs 418626 instructions:
    #   9B16 -> 4DBF   -> 4DAF, -> 0B3E (the level-data initializer: C679 -> C7B2/C80B/C85B, the
    #                    far 254A:04D7 asset decode, 0248 -> 0624/065C), -> 4E26, -> 4E0D -> A781
    #                    (the row-pull chain -> A7EB -> A81B)
    #   9908  -> C4DB  -> 8517 -> 5A00, 85B5 -> 85D5 -> 613E/5A6C, ...   (the respawn seed)
    #   978F  -> A940 (+ the object walk + 1F8F:0922), 9798 -> C57C, 979B -> B5A9, 97A4 -> 5F43
    #   then the ordinary present half (0672/511F/A846/5BDC/A90C) up to the next 9B2E.
    # So the 7 'death/respawn' frames the lockstep gate still reports are that whole continuation,
    # which this frame fn returns before by design.  recovered/adapters/cold_level_start.py's
    # apply_respawn_seeds() already models the 9908 -> C4DB/C3A6/C461/C42F half of it.
    # Repro: scratch death_window.py, or trap (1010,9B2E) and swap in a full-step logger.
    if mem.rw(DS, 0xA95A) == 0xFFFF or mem.rw(DS, 0xA97A) == 0:
        if mem.rw(DS, 0x2326) == 3:
            counter = (mem.rw(DS, anchor + 0x08) + 1) & 0xFFFF
            mem.ww(DS, anchor + 0x08, counter)
            if counter == 0x000F:
                mem.ww(DS, anchor + 0x00, 0)        # 9B11
                if level_bytes is None:             # 9B16: 4DBF needs the level file (a host input)
                    raise RecoveryGap("the 4DBF level re-init needs the level map file",
                                      "pass level_bytes= to advance_gameplay_frame_97b2")
                _level_reinit_4dbf(mem, level_bytes)   # 9B16
                mem.ww(DS, 0xA346, 1)               # 9B19
                if mem.rw(DS, 0xA97A) == 0:
                    mem.ww(DS, 0xA342, 1)           # 9B27
        return
    # 9B6F..9B94: the four bit-gated MOVE handlers over the anchor (bp = 237C).  Each body is the
    # call-$+3 DOUBLING trick (2px/frame); A5D1's [A47C] != 0 alternative is a single unclamped
    # 1px step.  Clamps: +02 in [0x20, 0xC0]; +04 in [0, 0xB0).
    bits = mem.rb(DS, 0x98BE)
    if bits & 0x08:                                 # A5D1
        if mem.rw(DS, 0xA47C) == 0:
            for _ in range(2):
                if mem.rw(DS, anchor + 2) != 0x0020:
                    mem.ww(DS, anchor + 2, (mem.rw(DS, anchor + 2) - 1) & 0xFFFF)
        else:
            mem.ww(DS, anchor + 2, (mem.rw(DS, anchor + 2) - 1) & 0xFFFF)
    if bits & 0x04:                                 # A5EA
        for _ in range(2):
            if mem.rw(DS, anchor + 2) != 0x00C0:
                mem.ww(DS, anchor + 2, (mem.rw(DS, anchor + 2) + 1) & 0xFFFF)
    if bits & 0x01:                                 # A607
        for _ in range(2):
            if mem.rw(DS, anchor + 4) < 0x00B0:
                mem.ww(DS, anchor + 4, (mem.rw(DS, anchor + 4) + 1) & 0xFFFF)
    if bits & 0x02:                                 # A5F9
        for _ in range(2):
            if mem.rw(DS, anchor + 4) != 0:
                mem.ww(DS, anchor + 4, (mem.rw(DS, anchor + 4) - 1) & 0xFFFF)
    # 9B97: FIRE ([2350] > 0xB6 with bit 0x20) -> 8546
    if mem.rw(DS, 0x2350) > 0x00B6 and (bits & 0x20):
        raise RecoveryGap("the 8546 FIRE handler (9B97)",
                          "decode 1010:8546 against the lockstep gate")
    _scroll_a66f(mem)                               # 9BA9
    _fire_fanout_a067(mem)                          # 9BAC
    # 9BAF: the [978E]/[98C8] weapon-upgrade apply (9D4D -- native via the walk adapter)
    if mem.rb(DS, 0x978E) and mem.rb(DS, 0x98C8) == 1:
        raise RecoveryGap("the 9BAF 9D4D upgrade beat ([978E] with [98C8]==1)",
                          "the sound-busy-gated apply; wire when a demo exercises it")
    # 9BC0: [A47C] <= 1 -> A616 (the ship tilt/bank counters)
    if mem.rw(DS, 0xA47C) <= 1:
        _tilt_a616(mem)
    if _AT_9BCA is not None:                         # debug observation point (default: disabled)
        _AT_9BCA(mem)
    # 9BCA: [A47C] == 0 -> 9CB6 (the terrain crash -> the difficulty-scaled 9E19 damage).
    # 9CB6 is a fall-through CALL CHAIN of four 9E19s (9CCB/9CCE/9CD1/9CD4) entered by difficulty:
    # BEDC == 0 jumps to 9CD1 (2 calls), == 1 to 9CCE (3 calls), else starts at 9CCB (4 calls).
    # Oracle: the lockstep gate's DS:A95C family -- the VM drains 2/frame on difficulty 0, not 1.
    if mem.rw(DS, 0xA47C) == 0:
        if _terrain_crash_4ff9(mem):
            bedc = mem.rw(DS, 0xBEDC)
            for _ in range(2 if bedc == 0 else (3 if bedc == 1 else 4)):
                _shot_hit_9e19(mem)
    # 9BD4: [2350] > 0xB6 -> 9C01 (the edge-assist + the pod axis dispatch)
    if mem.rw(DS, 0x2350) > 0x00B6:
        _axis_assist_9c01(mem)
    _ring_advance_9cf1(mem)                         # 9BDF
    _frame_9be2(mem)                                # 9BE2


def _frame_9be2(mem) -> None:
    """``1010:9BE2`` -- the player's post-move tail: the 9CD9 history-ring write, the A031 pod feed,
    and the 9FAF pod tilt (gated on [BDAC] or a scrolled-in [2350]).

    Called from two places: the ordinary 9B2E player flow, and the 978C step of the respawn
    continuation (which is why it lives in its own function rather than inline)."""
    anchor = _ANCHOR
    di = mem.rw(DS, 0xA33A)                         # 9BE2 -> 9CD9: the history-ring write
    mem.ww(DS, di, (mem.rw(DS, anchor + 2) + 8) & 0xFFFF)
    mem.ww(DS, (di + 2) & 0xFFFF, (mem.rw(DS, anchor + 4) + 8) & 0xFFFF)
    _pod_feed_a031(mem)                             # 9BE5
    if mem.rw(DS, 0xBDAC) != 0 or mem.rw(DS, 0x2350) > 0x00B6:   # 9BE8
        _pod_tilt_9faf(mem)


def _terrain_crash_4ff9(mem) -> bool:
    """``1010:4FF9`` -- the PLAYER terrain-crash predicate: a dying pose (>= 3) is stc; else the
    pose-indexed 214E hitbox offset shifts the probe point, the 5073 probe's column (+0xD) --
    and a second column left when the [215A] sub-tile phase & 0xF > 0xA -- is class-checked
    (both rows on an unaligned Y).  Pure carry: the anchor's cells are pushed/restored."""
    pose = mem.rw(DS, _ANCHOR + 8)
    if pose >= 3:
        return True
    si = (0x214E + pose * 4) & 0xFFFF
    x = (mem.rw(DS, _ANCHOR + 2) + mem.rw(DS, si)) & 0xFFFF
    y = (mem.rw(DS, _ANCHOR + 4) + mem.rw(DS, (si + 2) & 0xFFFF)) & 0xFFFF
    tiles = level_tiles_from_image(mem)
    probe = compute_tile_probe_5073(TileProbeInput(
        origin_x_word=tiles.origin_x_word, row_base_word=tiles.row_base_word,
        object_x_word=x, object_y_word=y))
    bx = (probe.tile_offset_word + 0x0D) & 0xFFFF
    # 5073 STORES its adjusted x (origin_x + object_x) into DS:215A, and 4FF9's next instruction
    # (`mov ax,[215A]`) reads THAT FRESH VALUE, not the one standing at entry.  Reading the stale
    # cell made the two-column widening never fire.  Oracle: cold-start frame 3577 -- 215A goes
    # 0x0070 -> 0x00AF across the 5073 call, and 0xF > 0xA selects cx = 2, which finds the solid
    # tile the VM crashes on.
    mem.ww(DS, 0x215A, probe.adjusted_x_word)
    cols = 1 if (probe.adjusted_x_word & 0x000F) <= 0x000A else 2
    for _ in range(cols):
        if lookup_tile_class_byte(tiles.tile_plane[bx & 0x3FFF], tiles.class_table) != 0:
            return True
        if (y & 0x000F) and lookup_tile_class_byte(
                tiles.tile_plane[(bx + 1) & 0x3FFF], tiles.class_table) != 0:
            return True
        bx = (bx - 0x000D) & 0xFFFF
    return False


def _axis_assist_9c01(mem) -> None:
    """``1010:9C01`` -- the edge-assist + pod axis dispatch: [A360] = 0; the A39E/A39F edge flags
    (set by the 9FEA pod clamps) auto-nudge the anchor via the doubled A607/A5F9 movers when the
    matching input bit is released; then the pod counts feed the CS:9C70 axis jump table -- the
    (0,0) no-pods case is the 44AF ret; live-pod cases are undecoded (fail loud)."""
    anchor = _ANCHOR
    mem.ww(DS, 0xA360, 0)
    bits = mem.rb(DS, 0x98BE)
    if not (bits & 0x02) and mem.rb(DS, 0xA39E) == 1:
        for _ in range(2):                          # A607 (the doubled +04 inc, clamp < 0xB0)
            if mem.rw(DS, anchor + 4) < 0x00B0:
                mem.ww(DS, anchor + 4, (mem.rw(DS, anchor + 4) + 1) & 0xFFFF)
        mem.ww(DS, 0xA360, 1)
    if not (bits & 0x01) and mem.rb(DS, 0xA39F) == 1:
        for _ in range(2):                          # A5F9 (the doubled +04 dec, clamp != 0)
            if mem.rw(DS, anchor + 4) != 0:
                mem.ww(DS, anchor + 4, (mem.rw(DS, anchor + 4) - 1) & 0xFFFF)
        mem.ww(DS, 0xA360, 1)
    ah = (mem.rw(DS, 0xA966) != 0xFFFF) + (mem.rw(DS, 0xA96A) != 0xFFFF)
    al = (mem.rw(DS, 0xA968) != 0xFFFF) + (mem.rw(DS, 0xA96C) != 0xFFFF)
    if ah or al:
        raise RecoveryGap(f"the 9C70 axis case (ah={ah}, al={al})",
                          "the live-pod delayed-coordinate bodies (9C8A..) are undecoded")


def _ring_advance_9cf1(mem) -> None:
    """``1010:9CF1`` -- advance the four A27A..A339 position-history ring cursors
    ([A33A]/[A33C]/[A33E]/[A340], +4 each, wrapping A33A -> A27A) -- only while the player is
    MOVING (any direction bit) or the A360 edge-assist nudged."""
    if not (mem.rb(DS, 0x98BE) & 0x0F) and mem.rw(DS, 0xA360) == 0:
        return
    for cell in (0xA33A, 0xA33C, 0xA33E, 0xA340):
        v = (mem.rw(DS, cell) + 4) & 0xFFFF
        if v == 0xA33A:
            v = 0xA27A
        mem.ww(DS, cell, v)


def _pod_feed_a031(mem) -> None:
    """``1010:A031`` -- the A962/A964 pods take their position from the history ring (the
    [A33C]/[A33E] delayed cursors) -- the classic trailing-option movement."""
    for pod_cell, cur_cell in ((0xA962, 0xA33C), (0xA964, 0xA33E)):
        pod = mem.rw(DS, pod_cell)
        if pod == 0xFFFF:
            continue
        si = mem.rw(DS, cur_cell)
        mem.ww(DS, pod + 2, mem.rw(DS, si))
        mem.ww(DS, pod + 4, mem.rw(DS, (si + 2) & 0xFFFF))


def _pod_tilt_9faf(mem) -> None:
    """``1010:9FAF`` -- the A966..A96C pods' tilt-table positions: A39E/A39F cleared, then per
    pod the pose-indexed offset table (A38C/A374 with [A39A]; A380/A368 with [A39C]) places the
    pod at anchor + offset (+ 2*the tilt counter on the +04 axis), clamped to [0, 0xC0] with the
    edge flags set (9FEA)."""
    mem.wb(DS, 0xA39E, 0)
    mem.wb(DS, 0xA39F, 0)
    mem.ww(DS, 0xA398, mem.rw(DS, 0xA39A))
    _pod_place_9fea(mem, 0xA38C, mem.rw(DS, 0xA96C))
    _pod_place_9fea(mem, 0xA374, mem.rw(DS, 0xA968))
    mem.ww(DS, 0xA398, mem.rw(DS, 0xA39C))
    _pod_place_9fea(mem, 0xA380, mem.rw(DS, 0xA96A))
    _pod_place_9fea(mem, 0xA368, mem.rw(DS, 0xA966))


def _pod_place_9fea(mem, si: int, pod: int) -> None:
    if pod == 0xFFFF:
        return
    si = (si + ((mem.rw(DS, _ANCHOR + 8) << 2) & 0xFFFF)) & 0xFFFF
    mem.ww(DS, pod + 2, (mem.rw(DS, si) + mem.rw(DS, _ANCHOR + 2)) & 0xFFFF)
    y = (mem.rw(DS, (si + 2) & 0xFFFF) + mem.rw(DS, _ANCHOR + 4)
         + 2 * mem.rw(DS, 0xA398)) & 0xFFFF
    mem.ww(DS, pod + 4, y)
    if _s16(y) < 0:                                  # A00F (signed)
        mem.ww(DS, pod + 4, 0)
        mem.wb(DS, 0xA39E, 1)
    elif _s16(y) > 0x00C0:                           # A01F (signed)
        mem.ww(DS, pod + 4, 0x00C0)
        mem.wb(DS, 0xA39F, 1)


def _s16(v: int) -> int:
    return v - 0x10000 if v & 0x8000 else v


def _tilt_a616(mem) -> None:
    """``1010:A616`` -- the ship TILT counters: only past scroll 0xB6.  A648: at y (+04-axis) == 0
    with the LEFT bit (&2), [A39A] decs to the -8 floor... (the top-edge tilt); then at +04 ==
    0xB0 with the RIGHT bit (&1), [A39C] incs to 8; else [A39C] decays to 0."""
    if mem.rw(DS, 0x2350) <= 0x00B6:
        return
    anchor = 0x237C
    bits = mem.rb(DS, 0x98BE)
    # A648: the top-edge counter [A39A]
    if mem.rw(DS, anchor + 4) == 0 and (bits & 0x02):
        if mem.rw(DS, 0xA39A) != 0xFFF8:
            mem.ww(DS, 0xA39A, (mem.rw(DS, 0xA39A) - 1) & 0xFFFF)
    else:
        if mem.rw(DS, 0xA39A) != 0:
            mem.ww(DS, 0xA39A, (mem.rw(DS, 0xA39A) + 1) & 0xFFFF)
    # A622: the bottom-edge counter [A39C]
    if mem.rw(DS, anchor + 4) == 0x00B0 and (bits & 0x01):
        if mem.rw(DS, 0xA39C) != 8:
            mem.ww(DS, 0xA39C, (mem.rw(DS, 0xA39C) + 1) & 0xFFFF)
    else:
        if mem.rw(DS, 0xA39C) != 0:
            mem.ww(DS, 0xA39C, (mem.rw(DS, 0xA39C) - 1) & 0xFFFF)


# ---------------------------------------------------------------------------------------------
# The A067 FIRE FAN-OUT (decoded 2026-07-07; the journal carries the per-address map)
# ---------------------------------------------------------------------------------------------

_GAMEPLAY_POOL_BASE = 0x2B5C
_GAMEPLAY_POOL_WRAP = 0x32CC
_GAMEPLAY_SLOTS = 0x22
_ANCHOR = 0x237C


def _alloc_7547(mem) -> int:
    """``1010:7547`` -- the gameplay alloc WITH the 7550 kill-and-reuse recycle: the plain
    [95DA]-cursor scan; a full pool takes the first 2B5C record whose type (+0x16) != 1 (pods are
    never recycled), skipping behaviors 9/0xA, falling back to record 0 -- BD0D-killed, then
    reused."""
    slot = _alloc(mem, 0x95DA, _GAMEPLAY_POOL_BASE, _GAMEPLAY_POOL_WRAP, _GAMEPLAY_SLOTS)
    if slot != 0xFFFF:
        return slot
    bx = _GAMEPLAY_POOL_BASE
    for _ in range(_GAMEPLAY_SLOTS):
        if (mem.rw(DS, bx + 0x18) not in (9, 0x0A)
                and mem.rw(DS, bx + 0x16) != 1):
            break
        bx += 0x38
    else:
        bx = _GAMEPLAY_POOL_BASE
    _bd17_deactivate(mem, bx)                       # BD0D
    return bx


def _spawn_seed_a4ea(mem) -> int:
    """``1010:A4EA`` -- the player-shot spawn seed: 7547 alloc + the stamps (active=1, +1E=1,
    dir 0, sprite 0x32, +14=0, type 2, behavior 2, +1C=FFFF)."""
    slot = _alloc_7547(mem)
    mem.ww(DS, slot + 0x00, 1)
    mem.ww(DS, slot + 0x1E, 1)
    mem.ww(DS, slot + 0x06, 0)
    mem.ww(DS, slot + 0x08, 0x0032)
    mem.ww(DS, slot + 0x14, 0)
    mem.ww(DS, slot + 0x16, 2)
    mem.ww(DS, slot + 0x18, 2)
    mem.ww(DS, slot + 0x1C, 0xFFFF)
    return slot


def _muzzle_project_a1ae(mem, slot: int) -> None:
    """``1010:A1AE`` -- the anchor muzzle projection: the anchor SPRITE indexes the A3A8 offset
    pairs; the shot's +02/+04 = offset + the anchor's +02/+04."""
    si = (0xA3A8 + ((mem.rw(DS, _ANCHOR + 8) << 2) & 0xFFFF)) & 0xFFFF
    mem.ww(DS, slot + 2, (mem.rw(DS, si) + mem.rw(DS, _ANCHOR + 2)) & 0xFFFF)
    mem.ww(DS, slot + 4, (mem.rw(DS, (si + 2) & 0xFFFF) + mem.rw(DS, _ANCHOR + 4)) & 0xFFFF)


def _anchor_shot_a19f(mem) -> None:
    """``1010:A19F`` -- one seeded shot at the muzzle, preceded by the [98C0]-gated sound 0x13.

    The routine opens with `cmp [98C0],0 ; jz +5 ; mov [BEFF],13h` (bytes at A19F) before it seeds
    the shot; we were dropping that queue write, which showed up as DS:BEFF divergence on the
    frames where the player fires from the early-level anchor path.
    """
    if mem.rb(DS, 0x98C0):
        mem.wb(DS, 0xBEFF, 0x13)
    slot = _spawn_seed_a4ea(mem)
    _muzzle_project_a1ae(mem, slot)


def _anchor_shot_a18a(mem) -> None:
    """``1010:A18A`` -- the mode-1 anchor shot: A1AB (seed + muzzle) + sprite 0x33 + sound 0x14."""
    slot = _spawn_seed_a4ea(mem)
    _muzzle_project_a1ae(mem, slot)
    mem.ww(DS, slot + 8, 0x0033)
    if mem.rb(DS, 0x98C0):
        mem.wb(DS, 0xBEFF, 0x14)


def _anchor_shot_a1c8(mem) -> None:
    """``1010:A1C8`` -- the mode-2 DOUBLE shot: sound 0x15; shot 1 sprite 0x18; shot 2's
    direction/sprite from the input bits (&2 -> 7/0x1F, else &1 -> 1/0x19, else 0/0x18)."""
    if mem.rb(DS, 0x98C0):
        mem.wb(DS, 0xBEFF, 0x15)
    slot = _spawn_seed_a4ea(mem)
    mem.ww(DS, slot + 8, 0x0018)
    _muzzle_project_a1ae(mem, slot)
    slot = _spawn_seed_a4ea(mem)
    _muzzle_project_a1ae(mem, slot)
    bits = mem.rb(DS, 0x98BE)
    mem.ww(DS, slot + 6, 7)
    mem.ww(DS, slot + 8, 0x001F)
    if not (bits & 0x02):
        mem.ww(DS, slot + 6, 1)
        mem.ww(DS, slot + 8, 0x0019)
        if not (bits & 0x01):
            mem.ww(DS, slot + 6, 0)
            mem.ww(DS, slot + 8, 0x0018)


def _pod_shot_a4d7(mem, si: int) -> int:
    """``1010:A4D7`` -- the mode-0 pod shot: a seed at the pod's +02 / +04 + 4."""
    slot = _spawn_seed_a4ea(mem)
    mem.ww(DS, slot + 2, mem.rw(DS, si + 2))
    mem.ww(DS, slot + 4, (mem.rw(DS, si + 4) + 4) & 0xFFFF)
    return slot


def _pod_weapon_dispatch_a41a(mem, si: int) -> None:
    """``1010:A41A`` -- per-pod weapon dispatch: si == FFFF is a no-op; else the [A958] mode
    through the CS:A42C table."""
    if si == 0xFFFF:
        return
    mode = mem.rw(DS, 0xA958)
    if mode == 0:
        _pod_shot_a4d7(mem, si)
    elif mode == 1:                                 # A490
        slot = _pod_shot_a4d7(mem, si)
        mem.ww(DS, slot + 8, 0x0033)
    elif mode == 2:                                 # A499: the angled shot
        slot = _spawn_seed_a4ea(mem)
        mem.ww(DS, slot + 2, mem.rw(DS, si + 2))
        mem.ww(DS, slot + 4, (mem.rw(DS, si + 4) + 4) & 0xFFFF)
        d = mem.rw(DS, 0xA3EC)
        if d == 0xFFFF:
            d = 7
            if mem.rw(DS, si + 4) > 0x0058:
                d = 1
        mem.ww(DS, slot + 6, d)
        mem.ww(DS, slot + 8, 0x0019 if d == 1 else 0x001F)
    elif mode in (3, 4):                            # A464 / A438: the missile PAIR
        if mem.rw(DS, 0xA3A0) != 0:
            return
        mem.ww(DS, 0xA970, (mem.rw(DS, 0xA970) + 2) & 0xFFFF)
        beh, spr = (7, 0x0037) if mode == 3 else (8, 0x0035)
        slot = _pod_shot_a4d7(mem, si)
        mem.ww(DS, slot + 0x18, beh)
        mem.ww(DS, slot + 8, spr)
        slot = _pod_shot_a4d7(mem, si)
        mem.ww(DS, slot + 0x18, beh)
        mem.ww(DS, slot + 8, spr)
        mem.ww(DS, slot + 2, (mem.rw(DS, slot + 2) + 8) & 0xFFFF)
    else:
        raise RecoveryGap(f"the pod weapon mode {mode} (A42C[{mode}] = 44AF)",
                          "mode 5's table entry is 44AF -- undecoded")


def _fire_fanout_a067(mem) -> None:
    """``1010:A067`` -- the FIRE fan-out (the journal's decode map, wired image-native)."""
    if not (mem.rb(DS, 0x98BE) & 0x10):
        mem.ww(DS, 0xA980, 0)                       # A060: the release latch
        return
    if mem.rw(DS, 0xA980) != 0:                     # held: the autofire gates
        if not (mem.rb(DS, 0x9790) == 1 or mem.rw(DS, 0x232A) == 0x000F):
            return
    mem.ww(DS, 0xA980, 1)                           # A084
    if mem.rw(DS, 0x2350) <= 0x00B6 and mem.rw(DS, 0xBDAC) == 0:
        if mem.rw(DS, 0xA958) == 2:                 # the EARLY anchor tails
            _anchor_shot_a1c8(mem)
        else:
            _anchor_shot_a19f(mem)
        return
    # the FULL fan-out: the held-action counter copy
    mem.ww(DS, 0xA3A0, mem.rw(DS, 0xA970))
    mem.ww(DS, 0xA3A2, mem.rw(DS, 0xA972))
    mem.ww(DS, 0xA3A4, mem.rw(DS, 0xA976))
    mem.ww(DS, 0xA3A6, mem.rw(DS, 0xA974))
    if mem.rw(DS, 0xBDAC) == 1:
        raise RecoveryGap("A067's BDAC==1 render-mode branches (A114-only / A515-only)",
                          "never taken in gameplay demos")
    # A515: the tractor-drone launcher
    if mem.rw(DS, 0xA960) != 0 and mem.rw(DS, 0xA97E) != 1:
        slot = _alloc_7547(mem)
        mem.ww(DS, slot + 4, (mem.rw(DS, _ANCHOR + 4) + 0x0A) & 0xFFFF)   # A571
        mem.ww(DS, slot + 2, (mem.rw(DS, _ANCHOR + 2) + 0x0A) & 0xFFFF)
        victim = _rotating_pool_scan_b15a(mem)
        if victim != 0xFFFF:
            mem.ww(DS, slot + 0x30, victim)
            mem.ww(DS, slot + 0x00, 1)
            mem.ww(DS, slot + 0x1E, 1)
            mem.ww(DS, slot + 0x14, 0)
            mem.ww(DS, slot + 0x16, 2)
            mem.ww(DS, slot + 0x18, 0x000A)
            mem.ww(DS, slot + 0x1C, 1)
            if mem.rb(DS, 0x98C0):
                mem.wb(DS, 0xBEFF, 0x11)
            mem.ww(DS, 0xA97E, (mem.rw(DS, 0xA97E) + 1) & 0xFFFF)
            mem.ww(DS, 0xA960, (mem.rw(DS, 0xA960) - 1) & 0xFFFF)
    # A584: the ground-bomb pair (behaviors 0x05 / 0x06)
    if mem.rw(DS, 0xA95E) != 0 and mem.rw(DS, 0xA3A4) == 0:
        mem.ww(DS, 0xA976, (mem.rw(DS, 0xA976) + 1) & 0xFFFF)
        if mem.rb(DS, 0x98C0):
            mem.wb(DS, 0xBEFF, 0x12)
        for beh in (5, 6):
            slot = _spawn_seed_a4ea(mem)
            mem.ww(DS, slot + 4, (mem.rw(DS, _ANCHOR + 4) + 0x0A) & 0xFFFF)   # A571
            mem.ww(DS, slot + 2, (mem.rw(DS, _ANCHOR + 2) + 0x0A) & 0xFFFF)
            mem.ww(DS, slot + 4, mem.rw(DS, slot + 4) & 0xFFFC)
            mem.ww(DS, slot + 8, 8)
            mem.ww(DS, slot + 0x18, beh)
            if beh == 5:
                mem.ww(DS, 0xA976, (mem.rw(DS, 0xA976) + 1) & 0xFFFF)
    # A3FF: the A962/A964 pods ([A3EC] = FFFF, with the A378 tail)
    mem.ww(DS, 0xA3EC, 0xFFFF)
    for slot_cell in (0xA962, 0xA964):
        si = mem.rw(DS, slot_cell)
        _pod_weapon_dispatch_a41a(mem, si)
        if si != 0xFFFF:
            raise RecoveryGap("the A378 tail after a live A962/A964 pod fire",
                              "1010:A378 is undecoded")
    # A3CA: the A966..A96C pods with alternating [A3EC] bias
    for slot_cell, bias in ((0xA966, 7), (0xA968, 1), (0xA96A, 7), (0xA96C, 1)):
        mem.ww(DS, 0xA3EC, bias)
        _pod_weapon_dispatch_a41a(mem, mem.rw(DS, slot_cell))
    # A0E8: the anchor-fire dispatcher
    mode = mem.rw(DS, 0xA958)
    if mode == 5:
        raise RecoveryGap("A0E8's mode-5 A2A0 body", "1010:A2A0 is undecoded")
    if mem.rw(DS, 0xA96E) != 0xFFFF:                # A114: the tracker pod's triple spread
        if mem.rw(DS, 0xA3A6) == 0:
            if mem.rb(DS, 0x98C0):
                mem.wb(DS, 0xBEFF, 0x18)
            pod = mem.rw(DS, 0xA96E)
            for dx, dy, d in ((-6, 4, None), (-2, -4, 7), (-2, 0x0C, 1)):
                mem.ww(DS, 0xA974, (mem.rw(DS, 0xA974) + 1) & 0xFFFF)
                slot = _spawn_seed_a4ea(mem)        # A175
                mem.ww(DS, slot + 0x18, 0x000C)
                mem.ww(DS, slot + 0x1C, 7)
                mem.ww(DS, slot + 2, (mem.rw(DS, pod + 2) + dx) & 0xFFFF)
                mem.ww(DS, slot + 4, (mem.rw(DS, pod + 4) + dy) & 0xFFFF)
                if d is not None:
                    mem.ww(DS, slot + 6, d)
    if mode == 0:
        _anchor_shot_a19f(mem)
    elif mode == 1:
        _anchor_shot_a18a(mem)
    elif mode == 2:
        _anchor_shot_a1c8(mem)
    else:
        raise RecoveryGap(f"the A108 anchor-shot mode {mode} (A337/A2F6)",
                          "modes 3/4's bodies are undecoded")


def _row_pull_a74e(mem) -> None:
    """``1010:A74E`` -- the scroll ROW PULL.  A7EB's render half (the 5A7E tile-row strip render
    and the CS:[9598]-segment strip copy) is VIDEO-side; the DGROUP/logic half is A81B: stash the
    pulled row in [A408], then for rows <= 0xE52 run THE TILE CUES (7948, native) and THE LEVEL
    OBJECT SCRIPT (4A65, native -- triggered on the PRE-decrement [A978], which is exactly this
    call's position in the order).  Back in A74E: the [2350] <= 0xB6 scroll-beat sound, the row
    advance ([2350] += 0xD, [A978] -= 1), the [A978] == 4 CB1C music beat ([98C2] = 5; the 2032
    sound-segment writes are a host boundary), and [2354] = 0."""
    row = mem.rw(DS, 0x2350)
    if mem.rw(DS, 0x2352) == 1:
        # [2352] == 1 is set by A781, the REVERSE row pull, which only the DEATH RE-INIT (4DBF ->
        # 4E0D) runs: it rewinds the level from row 0x0E93 back to the checkpoint, rendering every
        # row on the way.  A781 is decoded in campaigns/demo_lockstep.md; it is blocked only on
        # C679 (the level decompressor 0B3E calls).  This gap is that continuation, not a stray flag.
        raise RecoveryGap("the reverse-scroll row pull ([2352] == 1, A781 via the 4DBF death "
                          "re-init)", "only the forward path is wired")
    mem.ww(DS, 0xA408, row)                         # A82D
    if row <= 0x0E52:
        # 8209's "+32/+34 caller-frame leak" is not a leak at all: at the A839 call site bp is
        # still 0x237C (the anchor record set at 9B5B), so ss:[bp+2] / ss:[bp+4] ARE the player's
        # x and y.  Measured by trapping (CS,0x7948): bp=237C on every hit.  Passing zeros here
        # left every cue-spawned record with +0x32/+0x34 = 0.
        run_tile_cue_row_7948(mem, row,             # A839
                              leak_32=mem.rw(DS, 0x2380), leak_34=mem.rw(DS, 0x237E))
        run_level_object_script_4a65(mem)           # A83C
    _render_strip_row_a7eb(mem, row)                # A7EB: 5A7E's render + the ring mirror
    if row <= 0x00B6 and mem.rb(DS, 0x98C0):        # A751
        mem.wb(DS, 0xBEFF, 0x07)
    mem.ww(DS, 0x2350, (row + 0x000D) & 0xFFFF)     # A765
    mem.ww(DS, 0xA978, (mem.rw(DS, 0xA978) - 1) & 0xFFFF)
    if mem.rw(DS, 0xA978) == 4:                     # A770 -> CB1C (al = 5)
        mem.wb(DS, 0x98C2, 0x05)
    mem.ww(DS, 0x2354, 0)                           # A77A


#: A7EB's geometry, from CS: [95BE] = 0x680 (one 16-row band = 16 * 0x68 bytes, contiguous),
#: [95C2] = 0x5480 (the ring-duplicate offset the band is mirrored to)
STRIP_BAND_BYTES = 0x0680
STRIP_MIRROR_OFF = 0x5480
#: the mirror offset in ROWS: 0x5480 / 0x68 = 208
STRIP_RING_ROWS = STRIP_MIRROR_OFF // 0x68


def _render_strip_row_a7eb(mem, row_base: int) -> None:
    """``1010:A7EB``: render the freshly pulled tile row into the STRIP, then mirror it.

    ``di = [234C] - CS:[95BE]`` addresses the band; ``A81B`` runs the cue/script beats and tails
    into ``5A7E`` -> (video mode 2) ``36A2``, whose pixels are ``render_tile_row``.  Rows are
    contiguous: the 0x68 stride equals the 104-byte row, so the band is 16 * 0x68 = 0x680 bytes.
    Then ``rep movsw`` copies that whole band to ``di + CS:[95C2]`` -- the ring duplicate that lets
    the scroll window slide without wrapping.
    """
    import numpy as np

    from overkill.native_video.tile_row import BANK2_ROW_BASE, render_tile_row

    strip_seg = mem.rw(CS, 0x9598)
    di0 = (mem.rw(DS, 0x234C) - mem.rw(CS, 0x95BE)) & 0xFFFF
    mem_np = np.frombuffer(bytes(mem.data), dtype=np.uint8)
    plane_seg = mem.rw(CS, 0x9592)
    plane = mem_np[plane_seg * 16: plane_seg * 16 + 0x10000]
    table = [mem.rw(CS, (0x8D92 + 2 * k) & 0xFFFF) for k in range(0x100)]
    bank_ptr = 0x959C if row_base >= BANK2_ROW_BASE else 0x959A
    bank = mem.rw(CS, bank_ptr)
    graphics = mem_np[bank * 16: bank * 16 + 0x10000]

    px = render_tile_row(plane, row_base, table, graphics)[:, :STRIP_STRIDE * 2]
    pairs = px.reshape(px.shape[0], STRIP_STRIDE, 2)
    packed = ((pairs[:, :, 0] << 4) | pairs[:, :, 1]).tolist()
    for r, line in enumerate(packed):                       # 36A2: the band, rows contiguous
        base = (di0 + r * STRIP_STRIDE) & 0xFFFF
        for c, b in enumerate(line):
            mem.wb(strip_seg, (base + c) & 0xFFFF, b)
    mirror = mem.rw(CS, 0x95C2)                             # A807/A813: the ring duplicate
    for k in range(STRIP_BAND_BYTES):
        mem.wb(strip_seg, (di0 + mirror + k) & 0xFFFF,
               mem.rb(strip_seg, (di0 + k) & 0xFFFF))


#: the per-planet CHECKPOINT table pointer (`[C601 + planet*2]` -> four 4-word records) and the
#: per-planet SCRIPT-CURSOR cell pointer (`[20CA + planet*2]` -> one of C5F5..C5FF)
CHECKPOINT_TABLE_C601 = 0xC601
SCRIPT_CURSOR_CELL_TABLE_20CA = 0x20CA
#: `[14C0 + planet*2]` -> a DS offset holding the level's filename ("LEV1MAP.BIC" for planet 1)
LEVEL_FILENAME_TABLE_14C0 = 0x14C0
#: 4DBF's checkpoint search: up to 3 records inside the `loop`, then one more if none matched
CHECKPOINT_LOOP_COUNT = 3
#: the level rewinds from this row (4DF0) back to the checkpoint
LEVEL_LAST_ROW = 0x0E93
#: the level file is 0x0EA0 bytes; only this slice is level data (see cold_level_start._MAP_BODY)
LEVEL_MAP_BODY = (12, 3682)


def _level_data_init_0b3e(mem, level_bytes: bytes) -> None:
    """``1010:0B3E`` -- the LEVEL-DATA INITIALIZER.

    Rewinds the six spawn-script cursors to their heads, republishes the level-file pointers, and
    loads the level map.

    ``C679``, which it calls, is NOT a decompressor: it is a DOS file load (``mov dx,[21AA]`` = the
    filename, ``ah=3Dh`` open through the far 254A:04D7 wrapper, ``[21AC]`` = the handle, ``0248``
    reads, ``[21A8] = cs:[0244]`` = the byte count, ``ah=3Eh`` close).  That is a HOST BOUNDARY, so
    ``level_bytes`` is supplied by the caller exactly as the key table and the INT8 tick count are,
    rather than emulating INT 21h.  The bytes land at ``[21A4]:[21A6]`` -- the tile plane, offset 0.

    ``[21AC]`` (the DOS handle) is left alone: the original always gets 5 back and never changes it.
    The trailing ``rep stosb`` clear of the INT9 key table at 98C4..9943 (via 1010:50AB) is replayed
    for faithfulness even though the lockstep gate excludes that range as the input channel.
    """
    for cell, head in SCRIPT_CURSOR_HEADS_0B3E:            # 0B3E..0B61
        mem.ww(DS, cell, head)
    planet = mem.rw(DS, 0x2356)
    mem.ww(DS, 0x21AA, mem.rw(DS, (LEVEL_FILENAME_TABLE_14C0 + planet * 2) & 0xFFFF))   # 0B62
    plane = mem.rw(CS, 0x9592)
    mem.ww(DS, 0x21A4, plane)                              # 0B72
    mem.ww(DS, 0x21A6, 0)                                  # 0B79
    mem.ww(DS, 0xBB80, 0)                                  # C679
    mem.ww(DS, 0xBB82, 0)                                  # C685
    # 0248 reads the whole 0x0EA0-byte file to plane:0.  We copy only the MAP BODY: the bytes
    # outside [12, 3682) are the level-independent border rows, and cold_level_start's own loader
    # (test-pinned by tests/test_level_map_placement.py) does not trust the decoder there either.
    # Writing them corrupted row 0, which only the checkpoints that rewind to the top (di = 0x9C)
    # ever render -- the 4DBF gate failed on exactly those three windows and no others.
    body_start, body_end = LEVEL_MAP_BODY
    for off in range(body_start, min(body_end, len(level_bytes))):
        mem.wb(plane, off & 0xFFFF, level_bytes[off])
    mem.ww(DS, 0x21A8, len(level_bytes))                   # C6FC: [21A8] = cs:[0244]
    for i in range(0x80):                                  # 50AB: rep stosb over the INT9 key table
        mem.wb(DS, (0x98C4 + i) & 0xFFFF, 0)


def _level_reinit_4dbf(mem, level_bytes: bytes) -> None:
    """``1010:4DBF`` -- the LEVEL RE-INIT the 9AFF death tail calls at ``9B16``.

    (An older note in this file called it "the death jingle -- a host boundary".  It is not: it is
    418626 instructions of level reload, and it is why the lockstep gate's last 7 frames diverge.)

    ``[C601 + planet*2]`` names a table of four 4-word records ``(row_base, script_ptr, cursor_value,
    row_threshold)``.  ``4DAF`` reads one and sets CF from ``cmp [2350], row_threshold``; 4DBF calls
    it up to three times inside a ``loop`` and once more if none matched, so the chosen checkpoint is
    the first whose threshold exceeds the current scroll row.  Then: reload the level (``0B3E``, with
    ``[A978]`` saved across it), drop the scroll to the checkpoint, repaint its tiles (``4E26``),
    jump to the level's last row and rewind all the way back rendering every row (``4E0D``), and
    finally re-point the planet's spawn-script cursor at the checkpoint.
    """
    planet = mem.rw(DS, 0x2356)
    si = mem.rw(DS, (CHECKPOINT_TABLE_C601 + planet * 2) & 0xFFFF)
    row_base = script_ptr = 0
    for attempt in range(CHECKPOINT_LOOP_COUNT + 1):       # 4DCE: `loop`, then the 4DD5 fall-through
        row_base = mem.rw(DS, si)                          # 4DAF: four `lodsw`
        script_ptr = mem.rw(DS, (si + 2) & 0xFFFF)
        mem.ww(DS, 0x20C8, mem.rw(DS, (si + 4) & 0xFFFF))
        threshold = mem.rw(DS, (si + 6) & 0xFFFF)
        si = (si + 8) & 0xFFFF
        if mem.rw(DS, 0x2350) < threshold:                 # 4DD1: `jb`
            break

    saved_a978 = mem.rw(DS, 0xA978)                        # 4DDC: push [A978]
    _level_data_init_0b3e(mem, level_bytes)                # 4DE0
    mem.ww(DS, 0xA978, saved_a978)                         # 4DE3: pop [A978]

    mem.ww(DS, 0x2350, row_base)                           # 4DE8
    _plane_repaint_4e26(mem)                               # 4DED
    mem.ww(DS, 0x2350, LEVEL_LAST_ROW)                     # 4DF0
    _row_rewind_loop_4e0d(mem, row_base, script_ptr)       # 4DF8

    cursor_cell = mem.rw(DS, (SCRIPT_CURSOR_CELL_TABLE_20CA + planet * 2) & 0xFFFF)
    mem.ww(DS, cursor_cell, mem.rw(DS, 0x20C8))            # 4DFB..4E0A


#: 99BF seeds the pod history ring at A27A with 0x30 (x, y) pairs and re-heads its four pointers
POD_RING_BASE = 0xA27A
POD_RING_PAIRS = 0x30
POD_RING_HEADS = ((0xA33A, 0xA27A), (0xA33C, 0xA2FE), (0xA33E, 0xA2BE), (0xA340, 0xA27E))
#: 6176's DGROUP effect, measured over every death window: these six words go to zero
HUD_RESET_CELLS_6176 = (0x2368, 0x236A, 0x236C, 0x236E, 0x2370, 0x2372)
#: 5F43 picks a music id by scroll row, else the planet's own from the 231E table
MUSIC_ROW_TOP, MUSIC_ROW_END = 0x009C, 0x0EA0
MUSIC_TABLE_231E = 0x231E
MUSIC_BEAT_CELL = 0x98C2


def _new_game_setup_c4db(mem) -> None:
    """``1010:C4DB`` -- the object/status reset the respawn runs first (9908)."""
    from overkill.recovered.adapters.cold_level_start import (
        OBJECT_SEED_COUNT, OBJECT_SEED_SLOT_TABLE_32CA,
    )
    from overkill.recovered.systems.frame_loop import apply_new_game_setup_c4db

    table = {cx: mem.rw(DS, (OBJECT_SEED_SLOT_TABLE_32CA + cx * 2) & 0xFFFF)
             for cx in range(1, OBJECT_SEED_COUNT + 1)}
    for off, val in apply_new_game_setup_c4db(table).items():
        mem.ww(DS, off, val)


#: C3A6's own head, BEFORE the C3B5 pool loop the recovered systems model: `mov di,2078 ;
#: mov cx,10 ; xor ax,ax ; rep stosw` -- the 16-word completion-counter table goes to zero.
COMPLETION_COUNTER_TABLE_2078 = 0x2078
COMPLETION_COUNTER_WORDS = 0x10
#: C42F allocates an effect slot through 7524 and stamps it; C461's tail zeroes [2340].
RESPAWN_EFFECT_FIELDS = ((0x00, 1), (0x14, 1), (0x16, 6))


def _gameplay_pool_seed_c3a6(mem) -> None:
    """``1010:C3A6`` -- the gameplay-pool seed (977D); it falls through C42F into C461.

    Three pieces the recovered systems maps do NOT cover, each measured at the call site:

    * C3A6's own head is a ``rep stosw`` over the 16-word completion-counter table at 2078.  The
      recovered ``object_pool_seed_c3b5`` starts at the C3B5 label, one instruction later.
    * ``C42F`` calls the 7524 allocator and stamps the slot it gets (``+0 = 1``, ``+0x14 = 1``,
      ``+0x16 = 6``) -- the player's respawn effect.  Its slot rotates with the allocator cursor
      (10, 21, 32 across the demo's three non-D305 deaths), so it cannot be a constant.
    * ``C461``'s tail zeroes ``[2340]``.
    """
    from overkill.recovered.adapters.behavior_walk import (
        EFFECT_POOL_BASE, EFFECT_POOL_WRAP, EFFECT_SLOTS, _alloc,
    )
    from overkill.recovered.adapters.cold_level_start import (
        GAMEPLAY_SEED_COUNT, GAMEPLAY_SEED_SLOT_TABLE_8D12, PLAYER_SPAWN_RECORD,
    )
    from overkill.recovered.systems.frame_loop import (
        object_pool_seed_c3b5, player_spawn_record_c42f, respawn_control_reset_c461,
    )

    for k in range(COMPLETION_COUNTER_WORDS):                       # C3AB: rep stosw
        mem.ww(DS, (COMPLETION_COUNTER_TABLE_2078 + k * 2) & 0xFFFF, 0)
    table = {cx: mem.rw(DS, (GAMEPLAY_SEED_SLOT_TABLE_8D12 + cx * 2) & 0xFFFF)
             for cx in range(1, GAMEPLAY_SEED_COUNT + 1)}
    for rec, fields in object_pool_seed_c3b5(table).items():        # C3B5
        for fo, val in fields.items():
            mem.ww(DS, (rec + fo) & 0xFFFF, val)
    for fo, val in player_spawn_record_c42f().items():              # C42F
        mem.ww(DS, (PLAYER_SPAWN_RECORD + fo) & 0xFFFF, val)
    slot = _alloc(mem, 0x95D8, EFFECT_POOL_BASE, EFFECT_POOL_WRAP, EFFECT_SLOTS)   # C450 -> 7524
    if slot != 0xFFFF:
        for fo, val in RESPAWN_EFFECT_FIELDS:
            mem.ww(DS, (slot + fo) & 0xFFFF, val)
    for off, val in respawn_control_reset_c461().items():           # C462
        mem.ww(DS, off, val)
    # Two more cells the recovered C461 map omits, both measured at the call site over every death
    # window.  [A97C] = 1 ARMS the shield bar, which is why the very next call (77C5, at 9780) ticks
    # [A97A] from 0 to 1 -- without it the bar stays empty and the respawned player dies instantly.
    mem.ww(DS, 0xA97C, 1)
    mem.wb(DS, 0xBEFF, 0x0D)                                        # C4B2 -> 9DB8: the respawn sound
    mem.ww(DS, 0x2340, 0)                                           # C4D4


def _pod_ring_seed_99bf(mem) -> None:
    """``1010:99BF`` -- fill the pod history ring with the spawned player's position, re-head it.

    ``mov bp,237C`` then 0x30 iterations of ``stosw`` pairs: ``[bp+2] + 8`` and ``[bp+4] + 9``.
    Note the +9 on Y -- the 9CD9 ring write that follows uses +8, which is why exactly one cell
    (A27C) changes again in the 9BE2 step.
    """
    x = (mem.rw(DS, _ANCHOR + 2) + 8) & 0xFFFF
    y = (mem.rw(DS, _ANCHOR + 4) + 9) & 0xFFFF
    di = POD_RING_BASE
    for _ in range(POD_RING_PAIRS):
        mem.ww(DS, di, x)
        mem.ww(DS, (di + 2) & 0xFFFF, y)
        di = (di + 4) & 0xFFFF
    for cell, head in POD_RING_HEADS:
        mem.ww(DS, cell, head)


def _hud_reset_6176(mem) -> None:
    """``1010:6176`` -- the score/lives HUD redraw (5EDB + 60F3; its cs:[95BC]==1 branches are the
    non-Tandy modes).  The drawing is video; its whole DGROUP effect, MEASURED at the call site over
    every death window (probes/attribute_death_continuation), is that these six words go to zero."""
    for cell in HUD_RESET_CELLS_6176:
        mem.ww(DS, cell, 0)


def _music_beat_5f43(mem) -> None:
    """``1010:5F43`` -- choose the music id by scroll row, then fall into CB1C's beat ([98C2])."""
    row = mem.rw(DS, 0x2350)
    if row == MUSIC_ROW_TOP:
        track = 4
    elif row == MUSIC_ROW_END:
        track = 5
    else:
        track = mem.rb(DS, (MUSIC_TABLE_231E + mem.rb(DS, 0x2356)) & 0xFFFF)
    mem.wb(DS, MUSIC_BEAT_CELL, track)


def _respawn_continuation_9908(mem, isr_ticks: int) -> None:
    """``1010:9908`` -> ``9773`` -> ``978F`` -- everything the original runs after the 97CE death
    exit, up to the ordinary 97B2 loop head.

    THE TICK PLACEMENT MATTERS.  ``9921`` spins on ``[BEFE]`` until the death jingle drains, so the
    frame's timer interrupts fire THERE, and only afterwards does ``992F`` queue sound 2 into
    ``[BEFF]``.  Running the ticks at the end of the frame instead (where the ordinary path puts
    them) would let the ISR consume the sound we had just queued.

    ``C57C`` (9798) and ``B5A9`` (979B) are skipped: attribute_death_continuation measured zero
    DGROUP bytes for both across all seven death windows.  They are video.
    """
    _new_game_setup_c4db(mem)                                  # 9908
    mem.wb(DS, 0x2358, (mem.rb(DS, 0x2358) - 1) & 0xFF)        # 990B: dec BYTE
    if mem.rb(DS, 0x978D):                                     # 990F
        mem.ww(DS, 0x2358, (mem.rw(DS, 0x2358) + 1) & 0xFFFF)  # 9916: inc WORD
    _isr_effects_ticks(mem, isr_ticks)                         # 9921: the spin is where time passes
    if mem.rb(DS, 0x98C0):                                     # 9928
        mem.wb(DS, 0xBEFF, 2)                                  # 992F
    if mem.rw(DS, 0x2358) == 0xFFFF:                           # 9773
        raise RecoveryGap("the 98EB game-over continuation ([2358] == FFFF)",
                          "only the respawn path is wired")
    _gameplay_pool_seed_c3a6(mem)                              # 977D
    _shield_charge_77c5(mem)                                   # 9780
    _pod_ring_seed_99bf(mem)                                   # 9783
    _hud_reset_6176(mem)                                       # 9786
    _frame_9be2(mem)                                           # 978C (bp = 237C, already the anchor)
    _a940_walk_stage(mem)                                      # 978F
    mem.ww(DS, 0x20A6, 0x20A8)                                 # 9792
    mem.ww(DS, 0xA8C2, 0)                                      # 979E
    _music_beat_5f43(mem)                                      # 97A4
    if mem.rw(DS, 0x2350) == MUSIC_ROW_TOP:                    # 97A7 -> D305
        raise RecoveryGap("the D305 respawn wait loop ([2350] == 0x9C)",
                          "200 nested mini-frames ([BED8] counts to 0xC8) -- 159 DGROUP bytes")


#: A81B's reverse-scroll row offset: `sub bx,0A9` -- 0xA9 == 13 * 0x0D, i.e. thirteen tile rows
#: back.  The forward path renders `[2350]`; the reverse path renders the row THIRTEEN behind it,
#: because the band it is filling is the one about to scroll into view from the other side.
REVERSE_ROW_LOOKBACK = 0x00A9


def _row_render_back_a7d0(mem) -> None:
    """``1010:A7D0`` -- A781's render half: draw a row into the band, step [2350] BACK, latch [2354].

    The row is NOT ``[2350]``.  ``A7EB`` tails into ``A81B``, which branches on ``[2352]``: the
    forward path stashes ``[A408]`` and runs the tile cues + level script, but the reverse path
    (``[2352] == 1``, which only this rewind sets) does ``sub bx,0A9`` and jumps straight to the
    ``5A7E`` render -- no cue, no script, no ``[A408]``.  Getting this wrong leaves every non-strip
    cell exact and the rendered bands wrong, which is precisely what the 4DBF gate first reported.
    """
    row = (mem.rw(DS, 0x2350) - REVERSE_ROW_LOOKBACK) & 0xFFFF     # A826
    _render_strip_row_a7eb(mem, row)
    mem.ww(DS, 0x2350, (mem.rw(DS, 0x2350) - 0x000D) & 0xFFFF)
    mem.ww(DS, 0xA978, (mem.rw(DS, 0xA978) + 1) & 0xFFFF)
    mem.ww(DS, 0x2354, 1)


def _row_pull_reverse_a781(mem) -> None:
    """``1010:A781`` -- the REVERSE row pull: A6FE's mirror image, run only by the death re-init.

    It sets ``[2352] = 1`` (the flag :func:`_row_pull_a74e` fails loud on -- the forward pull must
    never see it), biases ``[A278]`` DOWN, renders + steps the row base back every 16th call, and
    walks the strip's row source FORWARD (wrapping at CS:[95C0] = 0x5B00 back to CS:[95BE] = 0x680,
    stride CS:[959E] = 0x68).  Note the ``[2354]`` polarity is inverted vs A6FE: here the extra
    row-base step is skipped when the latch is 1, because A7D0 has already taken it."""
    mem.ww(DS, 0x2352, 1)
    if mem.rw(DS, 0x2350) == 0:                     # A788: nothing left to rewind
        return
    mem.ww(DS, 0xA278, (mem.rw(DS, 0xA278) - 1) & 0xFFFF)
    if mem.rw(DS, 0x234E) == 0:                     # A794
        _row_render_back_a7d0(mem)
    phase = (mem.rw(DS, 0x234E) + 1) & 0x000F       # A79E/A7A2
    mem.ww(DS, 0x234E, phase)
    if phase == 0 and mem.rw(DS, 0x2354) != 1:      # A7A7/A7AE
        mem.ww(DS, 0x2350, (mem.rw(DS, 0x2350) - 0x000D) & 0xFFFF)
        mem.ww(DS, 0xA978, (mem.rw(DS, 0xA978) + 1) & 0xFFFF)
    if mem.rw(DS, 0x234C) == mem.rw(CS, 0x95C0):    # A7B9 -> A7E3: the row-source wrap
        mem.ww(DS, 0x234C, mem.rw(CS, 0x95BE))
    mem.ww(DS, 0x234C, (mem.rw(DS, 0x234C) + mem.rw(CS, 0x959E)) & 0xFFFF)


#: 4E0D rewinds at most one level's worth of rows; a runaway means the loop condition is wrong.
_REWIND_STEP_LIMIT = 0x8000


def _row_rewind_loop_4e0d(mem, row_stop: int, script_ptr: int) -> None:
    """``1010:4E0D`` -- pull rows backwards until the level sits at ``row_stop``, then re-point
    the scroll's script cursor.  The exit test is ``[2350] <= row_stop AND [234E] == 0``."""
    for _ in range(_REWIND_STEP_LIMIT):
        _row_pull_reverse_a781(mem)
        if mem.rw(DS, 0x2350) <= row_stop and mem.rw(DS, 0x234E) == 0:
            mem.ww(DS, 0xA978, script_ptr)          # 4E21
            return
    raise RecoveryGap("the 4E0D row-rewind loop did not converge",
                      f"row_stop={row_stop:#06x} [2350]={mem.rw(DS, 0x2350):#06x} "
                      f"[234E]={mem.rw(DS, 0x234E):#06x}")


#: 4E26's two tile-rewrite handlers, by the CS address `jmp cs:[bx+2]` dispatches to:
#: 4E5F = `mov byte es:[si],28`, 4E65 = `mov byte es:[si],01`.  (Hand-decoding put these at
#: 4E5D/4E63; the driven gate rejected 4E5F on the first run.  Count the bytes, then check.)
_REPAINT_HANDLERS = {0x4E5F: 0x28, 0x4E65: 0x01}
TILE_REPAINT_TABLE_20D6 = 0x20D6
REPAINT_SPAN = 0x9C


def _plane_repaint_4e26(mem) -> None:
    """``1010:4E26`` -- rewrite the checkpoint's tiles in the PLANE (``es = CS:[9592]``).

    Walks ``0x9C`` plane bytes down from ``[2350] - 1``; each byte is matched against the planet's
    ``(tile, handler)`` pair list at ``CS:[[20D6 + planet*2]]`` (FFFF-terminated), and a match jumps
    to a handler that stores 0x28 or 1.  DGROUP is untouched -- but the plane is what the row renders
    that follow read, so this must run."""
    plane = mem.rw(CS, 0x9592)
    planet = mem.rw(DS, 0x2356)
    table = mem.rw(DS, (TILE_REPAINT_TABLE_20D6 + planet * 2) & 0xFFFF)
    si = (mem.rw(DS, 0x2350) - 1) & 0xFFFF
    for _ in range(REPAINT_SPAN):
        bx = table
        while True:
            want = mem.rw(CS, bx)
            if want == 0xFFFF:
                break
            if want == mem.rb(plane, si):
                handler = mem.rw(CS, (bx + 2) & 0xFFFF)
                value = _REPAINT_HANDLERS.get(handler)
                if value is None:
                    raise RecoveryGap(f"4E26 tile handler CS:{handler:04X}",
                                      "only the 4E5D (0x28) and 4E63 (0x01) stores are recovered")
                mem.wb(plane, si, value)
                break
            bx = (bx + 4) & 0xFFFF
        si = (si - 1) & 0xFFFF


def _scroll_step_a6fe(mem) -> None:
    """``1010:A6FE`` -- the forward world-scroll step: the [A278] +1 drift bias, [2352] = 0, the
    row pull when the [234E] phase is at 0, the phase dec (mod 16) with the [2354]-mode row-base
    advance, and the [234C] row-source step-back (wrapping at CS:[95BE] to CS:[95C0], stride
    CS:[959E])."""
    mem.ww(DS, 0xA278, (mem.rw(DS, 0xA278) + 1) & 0xFFFF)
    mem.ww(DS, 0x2352, 0)
    if mem.rw(DS, 0x234E) == 0:
        _row_pull_a74e(mem)
    phase = (mem.rw(DS, 0x234E) - 1) & 0x000F       # A714/A718
    mem.ww(DS, 0x234E, phase)
    if phase == 0 and mem.rw(DS, 0x2354) != 0:      # A71D/A71F
        mem.ww(DS, 0x2350, (mem.rw(DS, 0x2350) + 0x000D) & 0xFFFF)
        mem.ww(DS, 0xA978, (mem.rw(DS, 0xA978) - 1) & 0xFFFF)
    if mem.rw(DS, 0x234C) == mem.rw(CS, 0x95BE):    # A72F -> A746: the row-source wrap
        mem.ww(DS, 0x234C, mem.rw(CS, 0x95C0))
    mem.ww(DS, 0x234C, (mem.rw(DS, 0x234C) - mem.rw(CS, 0x959E)) & 0xFFFF)


def _scroll_a66f(mem) -> None:
    """``1010:A66F`` -- the world-scroll stage: gated on [A47C]/[A47E]/[A480] ALL zero (the outro
    arm / live-wave / countdown holds), one A6FE step; on the [234E] wrap frame, the row-0xE52
    C591 beat (unrecovered, fail loud) and the row-0xEA0 LEVEL-END ARM (native:
    run_level_end_arm_a680 -- A47C = 1, the 62AA sweep, the four A3EE outro spawns)."""
    if mem.rw(DS, 0xA47C) or mem.rw(DS, 0xA47E) or mem.rw(DS, 0xA480):
        return
    _scroll_step_a6fe(mem)
    if mem.rw(DS, 0x234E) != 0:                     # A68A
        return
    if mem.rw(DS, 0x2350) == 0x0E52:                # A69D
        raise RecoveryGap("the C591 row-0xE52 beat (si = A982)",
                          "unrecovered; fires once per level at the bank-2 boundary row")
    if mem.rw(DS, 0x2350) == 0x0EA0:                # A6B1
        run_level_end_arm_a680(mem)
