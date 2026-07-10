"""The VM-less OVERKILL application skeleton -- the game's recovered HIGH-LEVEL structure.

This module is the native runtime's spine: the top-level flow, the frame-loop stage orders, and the
scene machine, each transcribed from the ORIGINAL dispatchers (ASM anchors cited inline) as explicit
Python structure.  Every piece is one of three kinds, and the boundary is machine-readable:

* **native** -- recovered + running VM-free (the callable is wired here);
* **gap (fail-loud)** -- the trigger IS detectable natively and raises :class:`RecoveryGap` when hit;
* **unmonitored gap** -- the trigger state is not represented in the native model yet, so the runtime
  cannot even notice it; declared as :class:`UnmonitoredGap` in the stage map (greppable, reported by
  :func:`describe_gaps`) instead of silently absent.

NO silent fallbacks, NO guessed behaviour, NO compatibility shims -- per the project invariant, a gap
must stay visible until a targeted demo/probe recovers it.

RECOVERED TOP-LEVEL FLOW (the game's actual design, from the dispatchers):

    boot/init            LZEXE unpack -> container open (254A:04D7) -> video mode (command tail) ->
                         shared startup assets (1010:0D42..0E0E: 1X1/2X2/2X2C/MANEXPL/THEND/PANEL/
                         BLUEBITS/SHIP)                                   [assets native; init GAP]
    title/options        OKMENU.ENC full-screen (native_video.front_end)  [image native; menu logic GAP]
    attract/story        the 1010:D007 scene loop -- scene id DS:BE06 indexes a 6-byte descriptor
                         table at DS:BE18 -> CS:0BE4 panel directory; countdown DS:BE08 auto-advances
                         scenes; DS:BE0A injects demo auto-fire and drives A067 (the attract mode
                         plays itself); exits on FIRE / any key / terminal scene 0x13
                                                        [structure native (systems/attract); scene-0
                                                         D160 + scene-entry actions GAP]
    level load           per-level assets (1010:0E9C: LEV{n}MAP/BLX + G{n} -> native_level)
                         [native]; the level-START STATE -- object-table seed (C4DB) + player spawn
                         (C42F: 237C active at x=0xC0,y=0x58) + starfield (cold-load load_starfield_state
                         + advance_starfield; NOT re-seeded per level -- proven) are all NATIVE
                                                                          [Bucket F now cold-loadable]
    gameplay frame loop  1010:97B2 -- the stage order in GAMEPLAY_FRAME_STAGES below; exits via three
                         transition flags: A344 -> jmp 9734, A342 -> jmp 9902, A346 -> jmp 9908
                         (death / level-end / game-over family -- setters live in 9B2E's children)
                                                                          [stages: see map; the
                                                                           transitions UNMONITORED]
    game-state ctrl      1010:9B2E (called by 97B2): input poll (0162/017E) -> player movement bits ->
                         A067 action fan-out -> optional 9CB6 contact probe -> coordinate rings ->
                         linked-child propagation (9FAF/9FEA)             [core native via
                         NativeGame.step; scripted-input 99F6 + A212 + full fan-out GAPs]
    render/present       A846 draw scan -> 5BDC present -> A90C present scan; playfield = starfield
                         plate + object sprite blocks (byte-exact); HUD panel drawn at level load +
                         61DC counters + 5F05 score                       [playfield native; HUD
                                                                           composers native, NOT
                                                                           wired into the standalone]

The runnable pieces below (GameplayFrameSkeleton, AttractSequencer) are hosts for that structure;
``scripts/play_native.py`` is the entrypoint that drives them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from overkill.recovered.domain.gaps import RecoveryGap, UnmonitoredGap
from overkill.recovered.domain.attract import AttractSceneState
from overkill.recovered.systems.attract import attract_frame_step, attract_loop_exits

# ---------------------------------------------------------------------------------------------------
# The gameplay frame loop (1010:97B2) -- the stage order, one entry per original call site.
# ---------------------------------------------------------------------------------------------------

#: Stage ownership states (the machine-readable boundary).
NATIVE = "native"            # recovered + wired VM-free
HOST = "host"                # owned by the host runtime by design (timing, window, input device)
GAP = "gap"                  # not recovered; fail-loud when its trigger is reached
UNMONITORED = "unmonitored"  # not recovered AND its trigger state is absent from the native model


@dataclass(frozen=True)
class FrameStage:
    """One original frame-loop call site: where it lives in the ASM and who owns it natively."""

    name: str
    asm: str
    status: str
    note: str


GAMEPLAY_FRAME_STAGES: tuple[FrameStage, ...] = (
    FrameStage("timer_tick_clear", "1010:0672", HOST,
               "frame pacing; the host clock owns cadence (recovered stub clears CS:[066B])"),
    FrameStage("video_page_toggle", "1010:511F", NATIVE,
               "recovered: only video mode 1 flips pages; Tandy (mode 2) is a no-op"),
    FrameStage("sprite_draw_scan", "1010:A846", NATIVE,
               "the object->sprite draw; native form = object_sprite_blocks (byte-exact vs 7596)"),
    FrameStage("conditional_hud_cell", "1010:981F (if DS:A97A == 0)", UNMONITORED,
               "draws panel cell 0x29 at (4,0x58)+cursor when the energy bar is empty.  MEASURED: "
               "[A97A] == 0 fires on 0 of the L1 demo's 8292 frames -- the L1 playthrough never "
               "reaches it (VIDEO-only when it does)"),
    FrameStage("present_blit", "1010:5BDC", NATIVE,
               "playfield compose + present; native form = compose_playfield_indices (byte-exact)"),
    FrameStage("present_object_scan", "1010:A90C", NATIVE,
               "projection/culling of object screen_di; folded into the native object pass"),
    FrameStage("game_state_controller", "1010:9B2E", NATIVE,
               "native_frame._step_9b2e (the lockstep frame): the 0162 input poll from the image's"
               " own INT9 key table, the A212 prelude, the 9AFF death tail, the four move handlers,"
               " the 8546/A067 fire paths, the A66F scroll (tile cues + the 4A65 level script run"
               " INSIDE the row pull), the 9D4D upgrade apply, the pod feeder + the walk-adjacent"
               " stages. The OBJECT BEHAVIOR WALK itself is stage A940's interior (A940 falls"
               " through into A9D3) and is FULLY NATIVE + demo-dry for L1/L2/L3 (run_behavior_"
               " walk_a9d3). NOTE: scripts/play_native.py still runs an OLDER hybrid loop -- the"
               " lockstep charter step 1 swaps it onto this frame."),
    FrameStage("transition_flags", "1010:97CE..97E9: A344->9734, A342->9902, A346->9908", NATIVE,
               "the gameplay-exit boundary, COMPOSED into the native frame (2026-07-10): A346 death ->"
               " the 9908 respawn continuation (or 98EB game-over on lives exhausted); A344 ->"
               " the 9734 level advance.  All byte-exact vs the VM (verify_native_level_reinit_4dbf,"
               " verify_native_level_advance_9734, and the whole lockstep gate at 8292/8292, 0 gapped)."
               " Remaining: A342 game-over-flag entry converges into the same 98EB path"),
    FrameStage("frame_state_update", "1010:A940", NATIVE,
               "the gameplay path (DS:2356 != 5) is composed + produced-vs-VM verified as"
               " systems/frame_loop.frame_state_update_a940 (accumulator shift + scan-entry fork;"
               " 750/750 A940 frames byte-exact, verify_native_a940). The DS:2356 == 5 attract-mode"
               " middle is ALSO recovered now (step_a940_attract_middle, driven-oracle 8/8) though not"
               " composed into the gameplay-path signature. Output cells not threaded into the loop yet"),
    FrameStage("service_gate", "1010:073C (if DS:9907 == 1)", GAP,
               "an INSTANT ret unless [9907] == 1, when it does a video re-init (mode 3 int10, font/"
               "palette).  MEASURED: [9907] == 1 fires on 0 of the L1 demo's 8292 frames -- correctly "
               "guarded, never reached in the L1 playthrough (fail-loud if it ever is)"),
    FrameStage("status_text", "1010:60A2", GAP,
               "per-frame status text; hud_text composers exist but are not wired into the standalone"),
    FrameStage("frame_wait", "1010:0679", HOST, "wait-for-timer-tick; the host clock owns cadence"),
)


#: The new-game / level-start setup that bridges the front-end to the gameplay frame loop.
#: TWO entry points converge at the level-advance (1010:9744):
#:   * 1010:971A -- NEW GAME (fresh start): runs the new-game prologue, then ``jmp 9744``.
#:   * 1010:9734 -- LEVEL-END TRANSITION (the A344 scripted-exit target of detect_gameplay_transition):
#:     runs the level-transition prologue (the level-0 story branch), then falls into 9744.
#: Both then run the converged per-level setup tail into 1010:97B2 (GAMEPLAY_FRAME_STAGES).
NEW_GAME_SETUP_STAGES: tuple[FrameStage, ...] = (
    # --- new-game prologue (1010:971A) ---
    FrameStage("level_select", "1010:D390", GAP,
               "level-select-family setup call; the grid direction/confirm DECISIONS are recovered"
               " (systems/menu + native_front_end), but the screen loop itself is host/presentation --"
               " not composed into this bridge yet"),
    FrameStage("screen_load", "1010:5C9A", HOST,
               "full-screen VGA plane blit (rep movsb 0x1F40 + 03CE register writes) -- presentation"),
    FrameStage("new_game_setup", "1010:C4DB", NATIVE,
               "object-pool seed + frame-control reset; native form = frame_loop.apply_new_game_setup_c4db"
               " (263 DGROUP cells, correct AND complete vs the VM -- verify_native_new_game_setup_c4db)"),
    FrameStage("countdown_init", "1010:9723", NATIVE,
               "DS:A95A := 3, DS:A95C := 0x18 -- the A47C-script counters' new-game init (constants)"),
    FrameStage("panel_draw", "1010:6176", HOST,
               "HUD/panel draw composite (dual-page gated on CS:95BC) -- presentation"),
    # --- level-end transition prologue (1010:9734, alternate entry) ---
    FrameStage("level0_intro", "1010:9844 (via 9734, if DS:2356 == 0)", GAP,
               "the mothership story splash: an INTERACTIVE text screen (5BEE setup, the far text"
               " renderer 1F8F:0980, 50C9 delays, a 0163 fire-wait) shown only when 9734 re-enters"
               " with DS:2356 == 0 -- i.e. AFTER the mothership (planet 0) is beaten, then it converges"
               " at 9744.  NOT on the six-level playthrough path (all six planets play + advance;"
               " verify_native_level_progression).  Blocked on 1F8F:0980, an unrecovered text renderer"
               " -- a front-end campaign task"),
    # --- converged per-level setup -> 97B2 ---
    FrameStage("level_advance", "1010:9744", NATIVE,
               "six-planet level-index advance; native form = frame_loop.advance_level_index_9744"
               " (DS:2356 0->1->..5->0, driven-oracle 9/9)"),
    FrameStage("setup_tail", "1010:9755..97B2", NATIVE,
               "the per-level setup, RECOVERED and composed (2026-07-10) as native_frame's shared"
               " _level_setup_tail_9773 + the 0B3E/0E9C level loads + 60AC scroll warm-up + D305:"
               " C3A6/77C5/99BF/6176/9BE2/A940/[20A6]/[A8C2]/5F43.  C57C and B5A9 are video (measured"
               " zero DGROUP; attribute_death_continuation).  Byte-exact vs the VM"),
)

#: The DS:2356 per-planet video/palette dispatch (``1010:C565``: ``jmp cs:[2356*2 + 0xC570]``).
#:
#: Level-load RENDERING config -- NOT the top-level game-mode machine (an earlier hypothesis; corrected
#: after disassembly).  For the six planets (``DS:2356 = 0..5``, the range ``advance_level_index_9744``
#: produces) it selects one of THREE handlers that set the CGA/Tandy colour mode (port ``0x3D8`` bit 2)
#: + BIOS palette (``int10 AH=0Bh``).  Dispatch drive-verified in ``verify_native_planet_video_dispatch``.
#: Scenes 6+ (``832E``/``BC3E``/...) are DISTINCT special-scene handlers -- a separate GAP, not bounded
#: or recovered here.
PLANET_VIDEO_DISPATCH: dict[int, int] = {0: 0x4F37, 1: 0x4FC3, 2: 0x4F57, 3: 0x4FC3, 4: 0x4F37, 5: 0x4F57}

#: What each of the three distinct per-planet video/palette handlers does (from disassembly).
PLANET_VIDEO_HANDLERS: dict[int, str] = {
    0x4F37: "config A (planets 0,4): CGA/Tandy mode port 0x3D8 bit 2 SET",
    0x4FC3: "config B (planets 1,3): BIOS palette 1 (int10 AH=0Bh BL=1) + 0x3D8 bit 2 clear",
    0x4F57: "config C (planets 2,5): BIOS palette 0 (int10 AH=0Bh BL=0) + 0x3D8 bit 2 clear",
}

#: The mode-transition EDGES out of the 97B2 gameplay loop -- where each exit flag
#: (``detect_gameplay_transition``, the 1010:97CE..97E9 dispatch) jumps.  Grounded by disassembly of the
#: targets.  These are the level/death/game-over transitions of the top-level mode machine.
GAMEPLAY_EXIT_TARGETS: tuple[FrameStage, ...] = (
    FrameStage("level_end", "1010:9734 (flag A344)", NATIVE,
               "level complete, RECOVERED (2026-07-10) as native_frame._level_advance_9734: advance the"
               " planet (wrap 5->0), load the new planet's map/tile/sprite banks (0B3E/0E9C), the 60AC"
               " scroll warm-up, and the shared setup tail.  Byte-exact (verify_native_level_advance_9734)."
               " The DS:2356==0 story branch (9844) is a separate front-end GAP -- see level0_intro"),
    FrameStage("game_over", "1010:9902 -> 98EB (flag A342)", NATIVE,
               "out of lives: 990B's `dec WORD [2358]` wraps 0->FFFF and 9773 branches to 98EB, the"
               " game-over -> title -> fresh-game chain, RECOVERED (2026-07-10) as"
               " native_frame._game_over_continuation_98eb.  Byte-exact vs the VM (the whole lockstep"
               " gate; the last-life frame 5379 is now 0-diverged)"),
    FrameStage("death", "1010:9908 (flag A346)", NATIVE,
               "death respawn, RECOVERED (2026-07-10) as native_frame._respawn_continuation_9908:"
               " C4DB reseed, the 4DBF level re-init, the shared 9773 setup tail, and D305 the"
               " post-respawn wait.  Byte-exact vs the VM (verify_native_level_reinit_4dbf 7/7 +"
               " the lockstep gate; all seven death windows 0-diverged)"),
)


@dataclass(frozen=True)
class ModeEdge:
    """A transition out of an :class:`AppMode` -- where it goes, on what trigger, and who owns it."""

    to: str
    on: str
    status: str


@dataclass(frozen=True)
class AppMode:
    """One node of the top-level game-session mode machine: an ASM anchor + its outgoing edges."""

    name: str
    asm: str
    status: str
    note: str
    edges: tuple[ModeEdge, ...]


#: The top-level game-session MODE MACHINE -- the recovered high-level control graph, one node per mode,
#: each with its outgoing transition edges.  This is the spine the per-mode structures hang off
#: (AttractSequencer, NEW_GAME_SETUP_STAGES, GAMEPLAY_FRAME_STAGES, GAMEPLAY_EXIT_TARGETS).  Every node
#: and edge is tagged native/gap so the boundary between recovered flow and unknown flow is explicit.
APP_MODE_GRAPH: tuple[AppMode, ...] = (
    AppMode("boot", "254A:04D7 -> 1010:0D42", GAP,
            "LZEXE unpack -> container open -> video mode -> shared startup assets",
            (ModeEdge("title_menu", "after init", GAP),)),
    AppMode("title_menu", "OKMENU.ENC (native_video.front_end)", GAP,
            "title/options full-screen image is native; the menu/key-redefine LOGIC + the exit to a game"
            " is a GAP",
            (ModeEdge("attract", "idle timeout", GAP), ModeEdge("new_game", "start", GAP))),
    AppMode("attract", "1010:D007", NATIVE,
            "the D007 scene machine is native + demo-witnessed (systems/attract); WHERE its fire/any-key"
            " exit transfers (back to title vs into a game) is not yet pinned",
            (ModeEdge("title_menu", "fire / any key / terminal scene 0x13", GAP),)),
    AppMode("new_game", "1010:96E0 / 96EE", NATIVE,
            "session init: planet=0, lives=3, score=0, game-over flag cleared "
            "(frame_loop.new_game_session_init_96ee, byte-exact + complete); the 96E0..96EB video init is"
            " host presentation. Reached at first-start (front-end, GAP) AND game-over restart (98FF)",
            (ModeEdge("level_setup", "fall-through -> 971A", NATIVE),)),
    AppMode("level_setup", "1010:971A", NATIVE,
            "new-game / level-start setup (apply_new_game_setup_c4db complete + advance_level_index_9744);"
            " per-stage detail + gaps in NEW_GAME_SETUP_STAGES",
            (ModeEdge("level_play", "-> 97B2", NATIVE),)),
    AppMode("level_play", "1010:97B2", NATIVE,
            "gameplay frame loop (GAMEPLAY_FRAME_STAGES); exits via detect_gameplay_transition",
            (ModeEdge("level_end", "flag A344", NATIVE),
             ModeEdge("death", "flag A346", NATIVE),
             ModeEdge("game_over", "flag A342", NATIVE))),
    AppMode("level_end", "1010:9734", NATIVE,
            "scripted / level-end: advance to the next planet",
            (ModeEdge("level_setup", "2356++ -> 9744 converge", NATIVE),)),
    AppMode("death", "1010:9908", NATIVE,
            "re-seed (C4DB) + DS:2358 lives-- (death_continue_counter_update); branch at 9773 on the lives"
            " sentinel.  The respawn continuation is RECOVERED (native_frame._respawn_continuation_9908),"
            " byte-exact vs the VM",
            (ModeEdge("game_over_seq", "2358 == 0xFFFF", NATIVE),
             ModeEdge("level_play", "else: the 9773 respawn re-init -> 97B2", NATIVE))),
    AppMode("game_over", "1010:9902", NATIVE,
            "force DS:2358 := 0 (death_continue_counter_update) then fall into the death handler",
            (ModeEdge("death", "-> 9908", NATIVE),)),
    AppMode("game_over_seq", "1010:98EB", NATIVE,
            "the game-over -> title -> fresh-game chain, RECOVERED (native_frame._game_over_continuation"
            "_98eb): 96EE session init, the new-planet load, the setup tail, D305.  Byte-exact vs the VM"
            " (the last-life frame is 0-diverged).  The front-end SCREENS it composes into scratch"
            " (game-over banner, high-score, title) are cleared before the boundary -- their pixels are"
            " a front-end-renderer gap, not a state gap",
            (ModeEdge("new_game", "jmp 96E0 (restart)", NATIVE),)),
)


def describe_gaps() -> list[str]:
    """Every declared gap in the skeleton, one line each (for reports/tests -- keep it honest)."""
    out = [f"{s.name}: [{s.status}] {s.asm} -- {s.note}"
           for s in GAMEPLAY_FRAME_STAGES if s.status in (GAP, UNMONITORED)]
    out += [f"mode.{mode.name}: [{mode.status}] {mode.asm} -- {mode.note}"
            for mode in APP_MODE_GRAPH if mode.status in (GAP, UNMONITORED)]
    out += [f"mode.{mode.name} -> {e.to}: [{e.status}] on {e.on}"
            for mode in APP_MODE_GRAPH for e in mode.edges if e.status in (GAP, UNMONITORED)]
    out += [f"new_game_setup.{s.name}: [{s.status}] {s.asm} -- {s.note}"
            for s in NEW_GAME_SETUP_STAGES if s.status in (GAP, UNMONITORED)]
    out += [f"gameplay_exit.{s.name}: [{s.status}] {s.asm} -- {s.note}"
            for s in GAMEPLAY_EXIT_TARGETS if s.status in (GAP, UNMONITORED)]
    out.append("attract scene 0: [gap] 1010:D0D1 -> D160 -- special branch not recovered (fail-loud)")
    out.append("attract scene advance: [gap] 1010:D0DB.. -- next-scene entry actions not recovered")
    # (level start state -- RECOVERED 2026-07-10: build_cold_level_start_image seeds a complete,
    #  playable cold level 0..5 -- session init, C4DB, the pool seeds, the player spawn, the companion
    #  (thrusters), both level banks, the scroll warm-up; verify_native_level_progression plays all six.)
    out.append("front-end menu logic: [gap] key-redefine/joystick/menu branches -- title image only")
    return out


# ---------------------------------------------------------------------------------------------------
# The gameplay frame skeleton -- runs the NATIVE stages in the original 97B2 order.
# ---------------------------------------------------------------------------------------------------

class GameplayFrameSkeleton:
    """One gameplay frame in the original 97B2 stage order, over the native state.

    ``render`` and ``advance`` are the two native composites the entrypoint supplies (the render half
    draws the CURRENT state -- the original presents before 9B2E runs -- and the advance half is the
    9B2E-family step).  Stages marked GAP/UNMONITORED in the map are NOT run -- they are declared,
    reported by :func:`describe_gaps`, and (where detectable) fail loud inside the composites
    themselves.  This class owns only the ORDER; it deliberately has no behaviour of its own.
    """

    def __init__(self, *, render: Callable[[], object], advance: Callable[[], None]) -> None:
        self._render = render
        self._advance = advance

    def tick(self):
        """Run one frame in the original order: present the current state, then advance it.

        Returns the presented frame.  Any :class:`RecoveryGap` (or other divergence) from the advance
        half propagates -- the caller decides how to stop visibly (play_native holds the last frame).
        """
        frame = self._render()   # A846/5BDC/A90C: present the state 9B2E produced last tick
        self._advance()          # 9B2E family: input -> player -> scroll -> fan-out -> objects
        return frame


# ---------------------------------------------------------------------------------------------------
# The attract/story sequencer -- the 1010:D007 scene loop's native host.
# ---------------------------------------------------------------------------------------------------

class AttractSequencer:
    """The D007 scene machine over :mod:`overkill.recovered.systems.attract`.

    VERIFICATION: the rules are disassembly-grounded (D007..D0EF) with unit tests; NOT yet
    demo-witnessed, and the per-scene content (descriptor table DS:BE18, scene graphics, scene-entry
    actions) is not recovered -- so this sequencer is NOT wired into ``play_native`` yet.  It exists
    so the structure is explicit; wiring it up requires the scene-content recovery first (targeted
    cold-start demo), not a guess.
    """

    def __init__(self, state: AttractSceneState) -> None:
        self.state = state

    def frame(self, *, real_input_98be: int, any_key_98c3: int) -> Optional[int]:
        """Advance one frame; return the input the demo's fan-out consumed, or None when the loop exits.

        Mirrors D007's per-frame order exactly: the scene machine steps first (``D04D`` at the
        ``D016`` call site -- the auto-fire's injected input is consumed by the ``A067`` drive INSIDE
        that step), and only then does the loop poll the REAL input (``0162`` at ``D02F`` overwrites
        ``98BE``) and run the exit test on it -- so a demo auto-fire never exits the attract loop;
        only a real FIRE, a real key, or the terminal scene does.  Scene 0 and scene advances fail
        loud inside :func:`attract_frame_step` / here, exactly where the original would do
        unrecovered work.
        """
        step = attract_frame_step(self.state)
        self.state = step.state
        if step.scene_advanced:
            raise RecoveryGap("1010:D0DB.. (attract next-scene entry actions)",
                              f"scene advanced to {self.state.scene:#x}; entry actions not recovered")
        if attract_loop_exits(self.state.scene, real_input_98be, any_key_98c3):
            return None
        return step.injected_input


__all__ = [
    "FrameStage", "GAMEPLAY_FRAME_STAGES", "NEW_GAME_SETUP_STAGES", "GAMEPLAY_EXIT_TARGETS",
    "AppMode", "ModeEdge", "APP_MODE_GRAPH",
    "PLANET_VIDEO_DISPATCH", "PLANET_VIDEO_HANDLERS", "describe_gaps",
    "GameplayFrameSkeleton", "AttractSequencer",
    "NATIVE", "HOST", "GAP", "UNMONITORED",
    "RecoveryGap", "UnmonitoredGap",
]
