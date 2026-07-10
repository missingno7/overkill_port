# Campaign: DEMO LOCKSTEP — the native frame loop, grown frame-by-frame against a demo

> Opened 2026-07-07 after owner playtest #3 ("play_native is a big pile of stuff glued together;
> start working systematically from the beginning, gradually, with verified steps against demo").
> This campaign SUPERSEDES the seam-wiring approach in play_native: no more dataclass-vs-image
> sync bridges. **THE ACTIVE CAMPAIGN.**

## THE DEATH CONTINUATION — the lockstep gate's entire remaining residue (decoded 2026-07-10)

The gate is at **8285 / 8292 byte-exact, 0 gapped**. All 7 diverging frames are death/respawn
windows: `4636, 4821, 5018, 5379, 6495, 7143, 7595`. `advance_gameplay_frame_97b2` returns at the
`97CE` exit; the original runs 418626 more instructions before the next `9B2E`.

Iterate with `pypy -m overkill.probes.inspect_death_windows` (~16 s, 7 windows, byte counts +
region breakdown). Prove with `pypy -m overkill.probes.verify_native_lockstep "" 20000`.
Re-derive the call map any time with `pypy -m overkill.probes.map_frame_window 5018`.

### The three `97CE` exits (hand-decoded, verified against the driven map)

    97CE  cmp word [A344],1 ; jnz         -> jmp 9734      (level complete)
    97D8  cmp word [A342],1 ; jnz         -> jmp 9902      (game over)
    97E2  cmp word [A346],1 ; jnz         -> jmp 9908      (DEATH -> respawn)
    97EC  call A940 / 073C / 60A2         (the normal frame tail)

`9902` is `mov word [2358],0` and falls straight into `9908`, so game-over and death share the
continuation and differ only in `[2358]`.

### `9908` — the respawn continuation

    9908  call C4DB                       ; object/status reset  (recovered: apply_respawn_seeds)
    990B  dec byte [2358]
    990F  cmp byte [978D],0 ; jz 991A ; inc word [2358]
    991A  cmp byte [98C0],0 ; jz 9928
    9921  cmp byte [BEFE],0 ; jnz 9921    ; SPIN until the death jingle drains  <-- the 402 ticks
    9928  cmp byte [98C0],0 ; jz 9934
    992F  mov byte [BEFF],2               ; queue sound 2
    9934  jmp 9773

    9773  cmp word [2358],FFFF ; jz 98EB  ; (game over proper)
    977D  call C3A6   (the gameplay-pool seed; its tail is C42F/C461)
    9780  call 77C5   (the shield/bar tick -- already native: _shield_charge_77c5)
    9783  call 99BF
    9786  call 6176
    9789  mov bp,237C                     ; the player anchor
    978C  call 9BE2                       ; (-> 9CD9, A031, 9FAF -- all already in _step_9b2e)
    978F  call A940                       ; + the object walk + the far 1F8F:0922 starfield
    9792  mov word [20A6],20A8
    9798  call C57C
    979B  call B5A9
    979E  mov word [A8C2],0
    97A4  call 5F43
    97A7  cmp word [2350],9C ; jnz 97B2 ; call D305
    97B2  the ordinary loop head (0672 / 511F / A846 / 981F / 5BDC / A90C) -> next 9B2E

### `4DBF` — the LEVEL RE-INIT, called from the death tail at `9B16` (before `[A346] = 1`)

Not "the death jingle" — an earlier note in `native_frame.py` guessed that and was wrong.

    4DAF  lodsw / mov di,ax               ; a 4-word checkpoint record:
          lodsw / mov dx,ax               ;   di = row base, dx = script ptr,
          lodsw / mov [20C8],ax           ;   [20C8] = w2,
          lodsw / cmp [2350],ax           ;   CF = ([2350] < w3)   <- the `jb` below
          ret

    4DBF  mov bx,[2356] ; shl bx,1 ; add bx,C601 ; mov si,[bx]    ; per-planet checkpoint table
    4DCB  mov cx,3
    4DCE  call 4DAF ; jb 4DD8 ; loop 4DCE ; call 4DAF             ; find the checkpoint for [2350]
    4DD8  mov si,dx
    4DDA  push si / push di / push word [A978]
    4DE0  call 0B3E                       ; THE LEVEL-DATA INIT (see below)
    4DE3  pop word [A978]                 ; ...restored, so 0B3E's own A978 write is discarded
    4DE7  pop di / mov [2350],di          ; scroll back to the checkpoint row
    4DEC  push di / call 4E26 / mov word [2350],0E93 / pop di / pop si
    4DF8  call 4E0D
    4DFB  mov bx,[2356] ; shl bx,1 ; add bx,20CA ; mov bx,[bx] ; mov ax,[20C8] ; mov [bx],ax
    4E0C  ret

    4E0D  push di / push si / call A781 / pop si / pop di         ; pull rows until...
    4E14  cmp [2350],di ; ja 4E0D
    4E1A  cmp word [234E],0 ; jnz 4E0D                            ; ...aligned at the checkpoint
    4E21  mov [A978],si ; ret

    4E26  push ax/bx/cx/dx/di/si/bp/es/ds ; ... (the save-all row render)

### What already exists

* `recovered/adapters/cold_level_start.py: apply_respawn_seeds()` models `C4DB` + `C3A6` +
  `C461` + `C42F` + the bar reseed + `rewind_level_scripts_0b3e` + `A47E/A480 = 0`. That is the
  `9908 -> 9773 -> C3A6` half.
* `_shield_charge_77c5`, `_a940_walk_stage` (A940 + walk + starfield), `_step_9b2e`'s `9BE2`
  interior (`9CD9`/`A031`/`9FAF`), and the whole present half are already native.
* `_row_pull_a74e` / `_render_strip_row_a7eb` cover the `A781` row-pull family.

### What is NOT modelled (the actual work, in order)

1. **`0B3E`** — the level-data initializer. Its call map is `0B7F -> C679 -> C7B2/C80B/C85B`, the
   far `254A:04D7` asset decode, and `C6F9 -> 0248 -> 0624/065C`. **Only its DGROUP effects need to
   match**: the gate does not diff the tile-plane segment (the cache re-supplies the plane per
   frame), and the asset decode's bulk lands there.

   **MEASURED (2026-07-10, driven at the 0B3E call inside death window 5018, entry `si=00D2`
   `di=03CF`): the whole of 0B3E touches exactly 24 DGROUP bytes.**

       DS:990C      01 -> 00
       DS:9911      01 -> 00
       DS:A256..A259  00 00 03 00 -> D9 05 4A 25     ; a FAR POINTER: 254A:05D9 (the asset overlay)
       DS:A25B..A269  (15 B, e.g. 06 16 07 00 -> 32 CC 25 02)   ; more far pointers; 25CC = DGROUP
       DS:A26B      AA -> C3
       DS:C5F7..C5F8  06 C9 -> D6 C8                 ; the planet's script cursor -> its head C8D6

   So 0B3E is NOT the obstacle it looked like. The A256..A26B block is a small table of far pointers
   into the decoded level data; `_load_planet_level_data` already performs the equivalent decode, so
   the work is to make it also publish these pointers. `990C`/`9911` are flags. The C5F7 write is
   the cursor rewind `rewind_level_scripts_0b3e` already does (only ONE cursor differs here because
   the other five already stood at their heads — the write-set is a diff, not a write log).

   **4DBF as a whole touches 3457 DGROUP bytes in 498 runs**, the first being `DS:234C..234E`
   (the scroll). The bulk is the `4E0D` row-pull loop's effects — `A781` re-pulling every row from
   the checkpoint, which re-runs the level script and re-spawns the objects. Those spawns are why
   the object pools dominate the diff. `_row_pull_a74e` + the native level-script spawner already
   own that machinery; wiring them into the `4E0D` loop shape is the slice.
2. **`4DBF`'s frame** around it (checkpoint search, `[2350]`, `4E0D`'s row-pull loop, `[20CA]`).
3. **`9908`**'s own body: `[2358]`, the `[BEFE]` spin (the recorded `isr_ticks` already supplies the
   right number of sound steps, so the spin is a no-op natively — the sound state converges either
   way), `[BEFF] = 2`.
4. **`99BF`, `6176`, `C57C`, `B5A9`, `5F43`, `D305`** — undecoded. `5F43` is near the `5F61` clock
   tick already native; `C57C`/`B5A9` are called on the normal level-start path too.

Do them as separate gated commits; `inspect_death_windows` gives a 16-second signal, and the frame
count in `verify_native_lockstep` only moves when a window becomes byte-exact.

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
