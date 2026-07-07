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

DS = 0x25CC
CS = 0x1010


def level_tiles_from_image(mem) -> LevelTileContext:
    """The frame's tile context, read fresh from the image (the plane scrolls in place and the
    class table rebuilds on level transitions)."""
    seg = mem.rw(CS, 0x9592)
    plane = bytes(mem.data[seg * 16:seg * 16 + 0x4000])
    classes = tuple(mem.rb(DS, (0xC3AA + i) & 0xFFFF) for i in range(256))
    return LevelTileContext(origin_x_word=mem.rw(DS, 0x234E),
                            row_base_word=mem.rw(DS, 0x2350),
                            tile_plane=plane, class_table=classes)


def advance_gameplay_frame_97b2(mem) -> None:
    """One 97B2 frame over the image, stage by stage.

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
    # Deferred until frames first COMPLETE (gap frames are never compared); the first completed
    # frame's +0x0C cells will hold it to the oracle at the right position.
    _step_9b2e(mem)


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


def _step_9b2e(mem) -> None:
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
    raise RecoveryGap(
        "the A212 player-record prelude (9B5B: bp=237C, call 1010:A212)",
        "the next 9B2E interior stage -- decode 1010:A212 against the lockstep gate")
