# Campaign: DEMO LOCKSTEP — the native frame loop, grown frame-by-frame against a demo

> Opened 2026-07-07 after owner playtest #3 ("play_native is a big pile of stuff glued together;
> start working systematically from the beginning, gradually, with verified steps against demo").
> This campaign SUPERSEDES the seam-wiring approach in play_native: no more dataclass-vs-image
> sync bridges. **THE ACTIVE CAMPAIGN.**

## Tier
Gameplay = **byte-exact** (whole DGROUP, minus the documented async cells); render = **pixel-exact**
(the composed playfield + HUD page vs the VM page).

## Done-condition
`python -m overkill.probes.verify_native_lockstep <demo>` passes for a full recorded L1 demo:
starting from the cold level boot, the NATIVE frame loop — running ONLY on the DGROUP image, in the
real `1010:97B2` stage order, fed the demo's recorded inputs — matches the pure-VM reference at
EVERY frame boundary, state and pixels, with ZERO seams and ZERO gap frames.  `scripts/play_native.py`
then runs THIS SAME loop function with the keyboard in place of the demo — the app and the gate share
one frame implementation by construction.

## Method (the walk-gate discipline, widened to the whole frame)
1. **The instrument first**: `verify_native_lockstep` — replay a demo; snapshot the VM at each
   97B2 frame top; run the native frame ONCE from the same state + inputs; diff whole-DGROUP (and
   the page on present frames).  Reuse `probes/_harness.run_ref_step_probe` (the VM side), the
   walk shadow-cache pattern (record once, replay fast), and the walk gate's verdict shape.
2. **Grow forward from frame 0.** The FIRST divergent cell of the FIRST divergent frame names the
   next stage to recover.  Recover it at the ASM boundary (driven oracle first), wire it into the
   native frame in the REAL stage order, re-run.  Never mask a divergence; never re-order stages
   for convenience.
3. **Image-only.** Every stage reads/writes the ONE `MutFlatMemory` image (ADR-1).  The dataclass
   `NativeGame` is retired from the gameplay path as stages land (it may serve as a render
   projection only).  The existing verified systems (the behavior walk, tile cues, cold level
   boot, HUD/panel compose, the playfield composer, scroll, transitions) are REUSED — wired in
   stage order, not synced across two worlds.
4. **One frame implementation.** The loop lives in ONE importable module function; the gate and
   play_native both call it.  A change that isn't visible to the gate is a change play_native
   doesn't get, by construction.

## Stage map (the 97B2 order — what must run per frame, from native_app.GAMEPLAY_FRAME_STAGES)
timer/pacing (host) → page toggle (native, mode-2 no-op) → sprite draw scan (native) →
conditional HUD cell → present/compose (native) → present-scan projection (native) →
**game_state_controller 9B2E** (input decode → player move/fire → scroll/cues → the OBJECT WALK
(native, dry for L1–L3) → contact/fan-out) → transition flags (native decision) →
frame_state_update A940 (native) → service gate → status text → frame wait (host).
The 9B2E interior is where the seams lived — it must be decomposed against the gate, not assumed.

## Non-goals (until the done-condition holds for L1)
The L4/L5 zoo residue, the planet-0/3/4 wave families, audio, endings, high-score entry.

## REFINED 2026-07-07 (owner reality-check #4)
The owner playtested play_native: no thrusters, wrong fire origin, fire lost after the intro wave,
missing/wrong enemies.  ROOT CAUSE: play_native still runs the OLD hybrid loop -- the gate and the
app are two different programs; nothing verified reaches the player.  The refined order:
1. **One frame, one truth**: play_native's gameplay loop = `advance_gameplay_frame_97b2` on the
   image; the keyboard writes the image's DS:98C4 table; render composes from the image.  The
   dataclass game + sync seams RETIRE.
2. **`play_native --demo <name> [--mirror]`**: replay a recorded demo through the SAME frame fn in
   the app; mirror mode diffs the image per frame vs the recorded VM states (+ pixels vs the VM
   page) and flags divergences live.  Playing demos and checking IS the ongoing reality check.
3. **Drain the named gaps**: the D50E sound-engine DGROUP model (2202 frames; feeds [98C8]
   gameplay reads), the 4CED star-list mid-present occupancy (1702 divergences), 77C5 shield bar
   (266), 9EE4 drain (62), DS:23A0 anchor-variant 1-byte.

## next
- Build `verify_native_lockstep` (frame-top snapshot + native-frame diff, frames 0..N growing).
- First expected divergences: the 9B2E input decode + player step (the dataclass side's logic vs
  the real ASM), the scroll/A66F gate, the fan-out ordering vs the walk.
