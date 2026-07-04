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
                         [native]; the level-START STATE (player spawn, object-table seed, starfield
                         init -- "Bucket F")                              [GAP: needs --snapshot]
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
               "draws panel cell 0x29 at (4,0x58)+cursor; DS:A97A not in the native model"),
    FrameStage("present_blit", "1010:5BDC", NATIVE,
               "playfield compose + present; native form = compose_playfield_indices (byte-exact)"),
    FrameStage("present_object_scan", "1010:A90C", NATIVE,
               "projection/culling of object screen_di; folded into the native object pass"),
    FrameStage("game_state_controller", "1010:9B2E", NATIVE,
               "NativeGame.step: input decode + player move + scroll + fan-out (EARLY) + object pass;"
               " gaps INSIDE it: 99F6 scripted input, A212 chain, FULL fan-out/A970, 9CB6 probe"),
    FrameStage("transition_flags", "1010:97CE..97E9: A344->9734, A342->9902, A346->9908", GAP,
               "the gameplay-exit boundary; the DECISION is recovered + demo-witnessed"
               " (systems/frame_loop.detect_gameplay_transition -> GameplayTransition; A344 scripted /"
               " A346 death / A342 game-over in 97B2 priority; matched the live verdict incl. 4 real"
               " DEATH frames) and is now WIRED into play_native -- each frame it fails loud if an exit"
               " fires (the 9734/9902/9908 targets are unrecovered). PARTIAL: the anchor +08 death"
               " counter is live, but the other trigger cells (A47C/A95A/A97A/2326) are seeded-static"
               " because the native loop doesn't run the stages that mutate them yet -- so a REAL death"
               " isn't detected from native gameplay until that upstream state is native (next slice)"),
    FrameStage("frame_state_update", "1010:A940", NATIVE,
               "the gameplay path (DS:2356 != 5) is composed + produced-vs-VM verified as"
               " systems/frame_loop.frame_state_update_a940 (accumulator shift + scan-entry fork;"
               " 750/750 A940 frames byte-exact, verify_native_a940). The DS:2356 == 5 attract-mode"
               " middle is ALSO recovered now (step_a940_attract_middle, driven-oracle 8/8) though not"
               " composed into the gameplay-path signature. Output cells not threaded into the loop yet"),
    FrameStage("service_gate", "1010:073C", GAP, "sound/timer service gate; not recovered -- not run"),
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
               "level-0 story-intro splash (far-call text 1F8F:0980 + fire-wait) -- not recovered;"
               " only on the level-end transition entry, not on a fresh new game"),
    # --- converged per-level setup -> 97B2 ---
    FrameStage("level_advance", "1010:9744", NATIVE,
               "six-planet level-index advance; native form = frame_loop.advance_level_index_9744"
               " (DS:2356 0->1->..5->0, driven-oracle 9/9)"),
    FrameStage("setup_tail", "1010:9755..97B2", GAP,
               "the remaining per-level setup calls (the 98C0->BEFF gate + 5145/5BCA/0B3E/0E9C/60AC/"
               "C3A6/77C5/99BF/9BE2/A940/C57C/B5A9/5F43) that lead into the 97B2 gameplay frame loop --"
               " mostly init/presentation glue, not recovered"),
)


def describe_gaps() -> list[str]:
    """Every declared gap in the skeleton, one line each (for reports/tests -- keep it honest)."""
    out = [f"{s.name}: [{s.status}] {s.asm} -- {s.note}"
           for s in GAMEPLAY_FRAME_STAGES if s.status in (GAP, UNMONITORED)]
    out += [f"new_game_setup.{s.name}: [{s.status}] {s.asm} -- {s.note}"
            for s in NEW_GAME_SETUP_STAGES if s.status in (GAP, UNMONITORED)]
    out.append("attract scene 0: [gap] 1010:D0D1 -> D160 -- special branch not recovered (fail-loud)")
    out.append("attract scene advance: [gap] 1010:D0DB.. -- next-scene entry actions not recovered")
    out.append("level start state: [gap] Bucket F -- C4DB new-game setup is native"
               " (apply_new_game_setup_c4db) + level advance (advance_level_index_9744); still GAP:"
               " the player spawn/starfield init + wiring these into a native cold level-start")
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
    "FrameStage", "GAMEPLAY_FRAME_STAGES", "NEW_GAME_SETUP_STAGES", "describe_gaps",
    "GameplayFrameSkeleton", "AttractSequencer",
    "NATIVE", "HOST", "GAP", "UNMONITORED",
    "RecoveryGap", "UnmonitoredGap",
]
