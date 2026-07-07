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
from overkill.recovered.adapters.level_object_script import run_level_object_script_4a65
from overkill.recovered.adapters.behavior_walk import (
    run_behavior_walk_a9d3, run_level_end_arm_a680,
)
from overkill.recovered.systems.frame_loop import frame_state_update_a940

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
    # verify_native_screen_di-proven; wired at the REAL stage position (before 9B2E).
    from overkill.native_walk_frame import sync_screen_projection
    sync_screen_projection(mem)
    _step_9b2e(mem)
    # --- the 97CE transition branches: a taken exit leaves the loop (no next 97B2 boundary) ----
    if mem.rw(DS, 0xA344) == 1 or mem.rw(DS, 0xA342) == 1 or mem.rw(DS, 0xA346) == 1:
        return
    # --- stage 9: A940 (frame-state update -> the OBJECT WALK -> the 0922 starfield tick) ------
    _a940_walk_stage(mem)
    # --- stage 10: 073C service gate (gated on [9907] == 1; normally an instant ret) -----------
    if mem.rw(DS, 0x9907) & 0xFF == 1:
        raise RecoveryGap("the 073C service body ([9907] == 1)", "unrecovered service path")
    # --- stage 11: the 60A2 stage -- 77C5 (the A97C shield drain) + 5F61 (THE CLOCK TICK) ------
    if mem.rw(DS, 0xA97C) == 1:
        raise RecoveryGap("the 77C5 A97C shield-bar body ([A97C] == 1)",
                          "unrecovered; fires only after a kind-4 pickup")
    _clock_tick_5f61(mem)
    # --- the INT8 ISR's per-frame DGROUP effects (two ticks per frame: the [0054] parity pair) -
    _isr_effects_two_ticks(mem)


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
        raise RecoveryGap("the 9EE4 difficulty drain beat (6084)",
                          "unrecovered; fires every 128 (or 64 on difficulty 2+) frames")
    if (mem.rw(DS, 0x2384) == 2 and mem.rw(DS, 0x232C) == 0x001F):
        v = mem.rw(DS, 0x234A) ^ 1                   # 6097
        mem.ww(DS, 0x234A, v)
        if v == 0:
            raise RecoveryGap("the pose-2 9EE4 drain beat (609F)", "unrecovered")


def _isr_effects_two_ticks(mem) -> None:
    """The INT8 ISR's per-frame DGROUP effects.  The game paces on CS:[066B], which the ISR sets
    every OTHER fire ([0054] parity) -- TWO ISR ticks per frame: [0054] += 2 (mod 4) and two D50E
    sound-engine steps ([BF00] += 1 & 3 each; the [BEFF] effect-queue consume and the BFAA/BFBA
    channel steppers are the AUDIO campaign -- fail loud when a sound is actually queued so the
    gate names the cells)."""
    mem.wb(DS, 0x0054, (mem.rb(DS, 0x0054) + 2) & 0x03)
    for _ in range(2):
        mem.ww(DS, 0xBF00, (mem.rw(DS, 0xBF00) + 1) & 0x0003)
        if mem.rb(DS, 0xBEFF):
            raise RecoveryGap("the D566 sound-effect start ([BEFF] queued)",
                              "the D50E channel machinery is the audio campaign's; fail loud")
        if mem.rb(DS, 0xBEFE):
            raise RecoveryGap("the D50E active-channel step ([BEFE] != 0)",
                              "the BFAA/BFBA channel steppers are the audio campaign's")


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
    # 9B5B: bp = 237C; A212 -- the sibling-snake mover, gated on the A3B4 list being populated
    # ([A972] != 0); an empty list is an immediate ret (the normal-L1 path).
    if mem.rw(DS, 0xA972) != 0:
        raise RecoveryGap("the A212 sibling-snake mover ([A972] != 0)",
                          "only the empty-list early-out is wired; decode A212's body when a demo"
                          " populates the A3B4 list")
    anchor = 0x237C
    # 9B61: the death branch -- anchor state absent -> the 9AFF death tail INSTEAD of the whole
    # player flow.  9AFF: on [2326] == 3 the anchor +08 explosion counter ticks; at 0x0F the
    # anchor deactivates, 4DBF runs (the death jingle -- a host boundary whose DGROUP effects, if
    # any, will surface as a divergence on the first death frame), [A346] = 1, and an empty
    # [A97A] bar also raises [A342] = 1 (game over).
    if mem.rw(DS, 0xA95A) == 0xFFFF or mem.rw(DS, 0xA97A) == 0:
        if mem.rw(DS, 0x2326) == 3:
            counter = (mem.rw(DS, anchor + 0x08) + 1) & 0xFFFF
            mem.ww(DS, anchor + 0x08, counter)
            if counter == 0x000F:
                mem.ww(DS, anchor + 0x00, 0)        # 9B11
                mem.ww(DS, 0xA346, 1)               # 9B19 (4DBF: host jingle boundary)
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
    raise RecoveryGap(
        "the A067 fire-path stage (9BAC)",
        "the next 9B2E interior stage -- decode/wire 1010:A067 against the lockstep gate "
        "(a067_fire_path exists in systems/action_spawns)")


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
        raise RecoveryGap("the reverse-scroll row pull ([2352] == 1, A81B's bx-0xA9 path)",
                          "only the forward path is wired")
    mem.ww(DS, 0xA408, row)                         # A82D
    if row <= 0x0E52:
        run_tile_cue_row_7948(mem, row)             # A839
        run_level_object_script_4a65(mem)           # A83C
    if row <= 0x00B6 and mem.rb(DS, 0x98C0):        # A751
        mem.wb(DS, 0xBEFF, 0x07)
    mem.ww(DS, 0x2350, (row + 0x000D) & 0xFFFF)     # A765
    mem.ww(DS, 0xA978, (mem.rw(DS, 0xA978) - 1) & 0xFFFF)
    if mem.rw(DS, 0xA978) == 4:                     # A770 -> CB1C (al = 5)
        mem.wb(DS, 0x98C2, 0x05)
    mem.ww(DS, 0x2354, 0)                           # A77A


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
