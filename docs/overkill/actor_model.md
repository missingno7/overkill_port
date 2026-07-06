# The OVERKILL actor model — toward a verified, data-driven choreography

> Design note (2026-07-05). This is the crystallization target for enemy behaviour: lift the zoo from
> hand-written procedural handlers into a data step-list over a CLOSED primitive vocabulary, verified
> byte-exact by the walk shadow. It guides the [Enemies-L1 campaign](campaigns/enemies_l1.md); it does
> NOT authorise inventing semantics — every primitive is a recovered pure function, every operand is a
> ROM-read field/constant, and the interpreter is only "correct" when it reproduces the walk byte-for-
> byte over the owner's cold-start demo.

## 1. What the ROM actually has (no behaviour bytecode-VM, but a real implicit model)

There is no interpreter walking a per-enemy opcode stream. But the system IS layered, and the layers
get more code-like top to bottom. The top two are already a language; the bottom two are where lifting
happens.

| tier | theatre role | ROM mechanism | nature |
|---|---|---|---|
| cue sheet | stage directions | level script `4A65`, fires a group when scroll-row == `DS:A978` | **DATA** (recovered, shadow-verified) |
| act schedule | stage managers | wave controllers `0x1F`/`8D4F` walk spawn schedules (`A484…`); death re-arms the next (`C054`) | **DATA** |
| cast list | the cast | dispatch table `EFC4`: 149 behaviour-ids → handler, keyed on record `+0x18` | **TABLE** (opcode-like) |
| choreography | each actor's blocking | ~134 hand-written handlers (106 are thin stubs) | **CODE** |
| acting vocab | the craft | a small CLOSED set of shared primitives | **CODE** (recovered) |
| state sheet | the actor's state | the `0x38` object record | **SHARED** |

The behaviour bodies LOOK procedural but are hand-compiled programs in an unwritten language whose
instruction set is the shared-worker library over the one shared record.

## 2. The primitive vocabulary (the "instruction set", quantified from the zoo xref)

`scripts/behavior_zoo_xref.py`: 149 ids → 134 distinct handlers; **106 are thin stubs (<0x20 bytes)**.
The recurring primitives (shared workers) and their reuse counts:

- **tail** — the `BC45`/`BC4B` postmove (drift `A278`, Y clamp, X-bounds death, `BCCB` contact, the
  `62F6` collision scan). Used by **72** handlers. Almost every actor ends here.
- **contact** — `AFD8` contact probe. **21** handlers.
- **animate** — sprite = base + table[clock >> shift]; the table/clock/shift vary per actor
  (`95EA`@`2330`, `96D2`@`233C`, linear@`2338`, …). A pervasive shape, inlined per handler.
- **seek** — `5DB2` and its `B729`/`B2C8` tails. **~9** (seek) + waypoint-setup family.
- **steer** — `5E42` delta-steer (Bresenham axis pick). **3**.
- **shoot** — `7476` enemy-shot stamp into the `7573` gameplay pool. **6**.
- **spawn** — `C237` child spawn (difficulty-throttled `7573` alloc + a parent-keyed jump table). +
  `7420` linked-effect spawn.
- **random** — `4D95` canned RNG ring. **4**.
- **substate** — advance record `+0x1C`, branch per state (the `0x20` wave enemy is the archetype).
- **gate** — a guard on a shared clock/counter/global (`2324` parity, `2328`, `232C`, `232E`, `233C`,
  `2338`, `A7A0` wave clock, `2356` planet, `A47E` live-enemy count).

An actor handler = a short composition of these + per-actor constants (base sprite, target, thresholds).

## 3. The lifting plan (discipline: the schema is DISCOVERED, not imposed)

1. **Keep recovering handlers against the demo frontier** (one behaviour per slice; gate = its
   `verify_native_walk_demo` gap count → 0 with no new divergence, the 200/0 free-run shadow held).
2. **Tag each recovered handler with its decomposition** (§4) — guards, primitives, constants — right
   next to the pure function. Costs nothing now.
3. **Let the schema emerge.** After ~15–20 handlers the recurring `[guard, action]` shape IS the step
   language. Designing it earlier risks unsupported semantics.
4. **Build the interpreter last, shadow-gated.** A behaviour's data step-list is "correct" iff running
   it reproduces the native walk byte-for-byte over the demo. Same oracle we already trust.
5. **Allow an escape hatch.** Irregular handlers (bespoke jump tables — `C237`'s `C2CE`, `0x20`'s dive)
   get a `call <recovered native routine>` primitive rather than being forced declarative. A model
   honest about its ~10% irregular cases beats a falsely-uniform one.

**Recovered vs designed (honesty):** the cue-sheet + schedule tiers are recoverable AS DATA (they
already are data). The behaviour step-list is a RE-REPRESENTATION of hand-written code — legitimate
only because it is shadow-gated. Say so; do not present it as a hidden format we found.

Endgame: the editor edits the cue sheet + the actor step-lists over a verified engine. North star =
**script · schedule · cast · vocabulary · state**.

## 4. Per-handler decomposition log (grows as the zoo is recovered)

Format: `behaviour (handler) — guards → primitives(operands) → tail`.

- **0x27 (`835D`)** — no guard → `animate`(sprite = base[`2356`==5 ? 0x24 : 0x27] + `2338`>>1),
  `drift`(+0x02 += 1) → `BC45` tail. Pure; no shared worker beyond the tail. `step_sprite_scroller_27_835d`.
- **0x2f (`8820`)** — no guard → sprite=0x43, `seek`(mode 2, via `B729`/`5DB2`), `drift`(+0x34 target-x
  += `A278`), `gate`(seek blocked?) → toggle +0x32 target-y `0`↔`0xC0` → `BC45` tail.
  `step_bounce_scanner_2f` + the seek applied by the caller. First actor to reuse the `seek` primitive
  and to branch on a primitive's RESULT (blocked) — the "gate on an action outcome" shape.
- **0x25 (`8265`)** — `gate`(`232C`==0x1F) → `spawn`(child via `C237`) → set child sprite 0x1A → `BC45`.
  First actor to use the `spawn` primitive. The `spawn` primitive itself (`C237`,
  `child_spawn_*_c237`) is now recovered: a shared difficulty throttle (`BEDC`/shared `A956`), the 7573
  alloc + field stamp (child = behaviour 0x04), and a per-parent-nibble SFX. Note the recovered
  primitive vocabulary now includes `spawn(C237)` alongside `spawn(7420)` / `shoot(7476)`.
- **0x30 (`8851`)** — `animate`(sprite = table[`96D2` + `233C`*2] + 0x44) → `gate`(`232A`==0xF) →
  `spawn`(C237) + `sound`(BEFF=0x0E) → `BC45`. `step_spawner_anim_30`. First composition of
  `animate` + `spawn` + `sound`; the `animate`-from-a-DATA-table shape (vs 0x27's inline) recurs
  (also 0x90/0x91's `95EA` table). Planet-5 has an extra anchor-proximity freeze (modelled, untested
  by the L1 demo).
- **0x90 / 0x91 (`8282` / `8291`)** — `animate`(base[`2356`] + `95EA`[`2330`>>5]) → `gate`(`232C`==0x1F)
  → the `95EA` value ALSO selects a `spawn`(C237) at `X±4` (value 0→-4, 2→+4, 1→none) → `BC45`.
  `step_animated_spawner_90_91` (one fn, two bases). Note the recurring pattern: a table value that is
  BOTH a sprite delta and a dispatch selector — a compact "phase table" idiom worth a first-class slot
  in the eventual step language.
- **0x04 (`AEBF`→`AF60`)** — the spawned CHILD's own behaviour, not a moving-object actor: type 2 (not
  6), so it's SELF-CONTAINED (like 0x02/0x0B) and never reaches the shared `BC45` tail. `step(2px) ×2`
  (fixed direction, no substate timer) → the same `contact`(B250, the `237E`/`2380` player box) →
  `drift`(AD5A, `+A278`) or `death-sentinel`(ADC9, `X=FFFF`) → `bounds`(AD60) → on contact, the single
  `9E19` damage beat (same primitive 0x0B's shot-hit uses). `object_update_af60` — the third member of
  the AED8/B24D/AF60 "EFAE per-object update" family (all share `contact`+`AD60`, differ only in the
  movement clause). This closes the C237 spawn chain: `0x25`/`0x30`/`0x90`/`0x91` now produce zero
  residual gaps. Landing it caught two REAL bugs via the demo shadow (not modelling artifacts): `DS:
  A956` is a byte counter, not a word (a word write clobbered the adjacent `A957`); and `DS:215A` is
  promiscuous IRQ/sound/menu scratch (400+ writes traced from unrelated addresses in a few thousand
  boundaries) — added to `EXCLUDED_CELLS`, the same class as the `230A`/`230C` steer scratch. Both are
  exactly the kind of finding this crystallization discipline is meant to surface early.
- **0x11 / 0x12 (`B2C3`→`B2CD`)** — the first STATEFUL actor: `+0x36` (a per-record pointer field)
  holds a cursor into the COLD `A43C` waypoint table. `0x11` is a one-shot morph (`seed`(ptr=A43C),
  `retag`(behaviour:=0x12)) that falls straight into `0x12`'s body. `0x12`: `seek`(mode 2 iff planet
  0 or `BDAC`==1, else mode 1) toward `waypoint[ptr]+0x20,waypoint[ptr+2]`; on `blocked`, `advance`
  (ptr+=4) and `retry` with the next pair — the first primitive with an internal RETRY LOOP, not a
  single decision; `gate`(the final direction) selects the sprite from a `planet`×`BDAC` bias table
  (the fully-decoded `B2C3..B3BC` cascade) → `BC4B` (no drift). `step_waypoint_follower_11_12`.
  Reuses `seek` (5DB2) exactly as recovered elsewhere — no new movement primitive, just a new
  CONTROL shape (loop-until-non-blocked over cold data) worth a first-class "follow a path" verb in
  the step language, alongside the existing decision-per-frame verbs. Wiring this ALSO caught a
  missing `DS:2304/2306` global write (the seek's own target-position side effect, re-stamped every
  retry) AND unmasked a genuine field-offset bug in the shared `bounds`(AD60) primitive itself:
  every wired caller passed the WRONG record field (`+0x0A` instead of `+0x16`) to its tile-probe
  gate — silent until a real hazard_class=2/logic_id=4 object (a C237 child) crossed a class-1 tile.
  Fixed at the primitive level (all 6 `object_bounds_tile_decision_ad60` callers), see run_status.md.
  Lesson for the model: a shared primitive's CORRECTNESS is only as strong as its weakest caller's
  wiring — the primitive itself was fine, evidence just never reached the buggy branch before.
- **0x24 (`8248`)** — byte-identical to `0x25` apart from the sprite constant (0x1E vs 0x1A):
  `gate`(`232C`==0x1F) → `spawn`(child via `C237`) → set child sprite → `BC45`. Generalised
  `_step_spawn_25` into `_step_spawn_child_sprite(parent_beh, sprite)`, the first case of two
  actors converging on ONE parameterised adapter — exactly the shape the eventual step-language
  should capture as one template with per-actor constants, not two near-duplicate functions.
- **0x29 (`8721`)** — a sprite RAMP-then-retarget-then-steer: `gate`(`2328`==7) → `animate`
  (sprite += 1, once per gated frame) → on reaching the ramp target (0xA4), `retarget`(the NEW
  `74E2` primitive: `move_delta = record_pos - anchor_pos`, Y-biased +9 — the SAME formula
  `formation_spawn_seed_7476` already uses for a fresh spawn) → `steer`(5E42, mode 2 during the
  call, restored to 3 after) → `gate`(steered Y out of `[0,0xC0]`, SIGNED) → `death`(BFC7) → `BC45`
  regardless. First reuse of `steer`(5E42) outside a spawn seed, and first actor whose OWN
  death-gate (not the shared BC45 tail's) triggers BFC7 directly. `step_ramp_steer_29` +
  `retarget_delta_toward_anchor_74e2`.

**Landing 0x24/0x29 surfaced TWO deep, pre-existing bugs the demo shadow's full-frame comparison was
built to catch** (see run_status.md for the full forensics):
1. **`GAMEPLAY_POOL_WRAP` was mistranscribed** (`0x2CA4`, not slot-aligned to
   `base + slots*stride`) — the allocator's `cur == wrap` check could never fire, letting the
   cursor drift into adjacent memory once a scan needed more than ~5 tries. Fixed by reusing the
   ALREADY-CORRECT, canonical `GAMEPLAY_OBJECT_ALLOCATOR_WRAP_SENTINEL` from `views/object_slots.py`
   instead of a second, drifted copy — a "check for an existing mechanism" lesson.
2. **`x_word == 0xFFFF` is an AMBIGUOUS proxy for "contact happened."** The real ASM branches
   DETERMINISTICALLY at detection time (contact -> ADC9 stamps FFFF; no-contact -> AD5A drifts by
   `+A278`) — but ordinary drift arithmetic can ALSO wrap X to exactly 0xFFFF with no contact at all
   (an off-screen-spawned child's own step+drift). The 3 pure `*SlotUpdate` dataclasses now expose
   the ACTUAL `contact: bool` the B250 selector computed, so the 9E19 fan-out gates on the real
   decision, not a coincidental byte value.

Fixing both took the demo from 3 unexplained divergences (614/6037/6897, open since early this
session) to **zero divergence across all 8294 walk frames** — proof that this crystallization
discipline (recover an actor → run the FULL demo → chase every divergence to its root, never explain
it away) surfaces real bugs that a narrower gate would leave latent indefinitely.
