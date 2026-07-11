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
- **0x01 latch-9 morph (`BE5A/BE60`) + 0x26 (`8302`)** — the first RESPAWN-CYCLE pair: the dying
  handler's key-1 latch, at exactly 9, MORPHS the record (`+0x1A` previous-id keyed: 0x24→up/0x97,
  0x25→down/0x91, else `BD17`) into behavior 0x26, snapshotting the position into `+0x32`/`+0x34` and
  `ret`-ing PAST the shared BC45 tail — the first actor path where "skip the postmove this frame" is
  semantic, not incidental (the BD17 deactivate tails also `ret`). 0x26 then `step`(AFD8+BDD0, the
  morphed direction) until `blocked ∨ y≥0xC0` → `animate`(+1 ramp to a FINISHED sprite) + `sound`(0x1E)
  → `gate`(`2326`==3) → RESET (y from `+0x32`, sprite back) — a scenery object that dies, floats away,
  and respawns. New vocabulary: the morph (an actor rewriting its own cast entry mid-walk) and the
  postmove-skip `ret`; both matter for the eventual step-language schema.
- **0x89 (`B2A6`)** — `animate`(sprite = `233C` + 0x1C) → `gate`(`232C`==0x1F) → `spawn`(C237 via the
  shared `BAE1` dir-4 emit) → the shared `BB03` bounce. A pure re-parameterization of 0x19 (different
  clock/bias/gate, same shape) — the first actor recovered by constants-only diff against an existing
  handler. Its landing also PROVED the wired `BDD0` contact predicate (its BB03 bounce hits contact
  frames 0x19/0x1A never reach).
- **0x8C / 0x8B (`BB80`/`BB88` → the shared `BB8E` body)** — the GROUND CRAWLER, the first
  TERRAIN-FOLLOWING actor: `flag`(`A952` = ±1, the two behaviors differ ONLY in this sign) →
  `terrain-probe`(`BBED`: 5073 over X+`A278`-0x10, then tile `[bx + A952 (-0xD on the left path)]`
  via 505B — class-0 = no ground = blocked) → `step`(AFD8 **with the BDD0 contact predicate**, dir
  0/4 picked by X vs the view anchor) → `animate`(sprite = 0x61 + 4*`A952` + `233C`-only-when-moved
  + dir) → `gate`(`2330` ∈ {0x7F,0x6B,0x57}) → `shoot`(7476 + sprite/X/Y patch). New vocabulary:
  `terrain-probe` (sampling the plane AHEAD of the step, distinct from the step's own collision) and
  the anim-term-gated-on-motion idiom. Landing it unmasked the B2CD seek-mode global
  (`WaypointFollowerStep.seek_mode_2308`) — the 0x12 follower's `[2308]` write the adapter had
  never persisted (write-scratch omissions surface only when a later-walked actor's frame is diffed).
- **0x28 / 0x2A (`8676` + its `8654` helper)** — an animated spawner whose `spawn` fires a SELF-COUNTED
  child: `animate`(sprite = `96AA`[+0x06 counter] + 0x1C, the counter a per-record clock that advances
  only when `2332`==0, wrapping mod 0x18) → `gate`(`A47E`==0 AND counter==7, i.e. once per cycle while
  no enemies live) → `spawn`(`81F4` = `alloc(7524)` + the recovered `enemy_spawn_stamp_8209`) with a
  per-planet CHILD-BEHAVIOUR OVERRIDE (planet 1/4→0x29, 2→0x2B, 5→0x7A; the 8209 stamp's default 0x14
  survives only on planets 3/0). `step_spawner_28`. New idiom: `spawn` where the child's behaviour is a
  DATA-selected field-patch over a shared stamp template — the same "phase table" compression as
  0x90/0x91 but applied to the spawned actor's TYPE, not the parent's sprite. The counter-in-`+0x06`
  (a field usually holding direction) is a reminder the record schema is behaviour-overloaded.
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

---

## 5. Where the zoo stands (2026-07-10) — the evidence-based map, refreshed

The §4 log above stopped at ~12 handlers; the zoo is now **~90 of 146 behaviour ids recovered across
75 `_step_*`/`step_*` handlers** in `behavior_walk.py`. The model in §1–3 held up — nothing below
revises it, this section is the CURRENT map an actor-refactor would start from.

### 5.1 The dispatch is TWO levels, both data tables (confirmed)
- **Level 1 — TYPE / draw-layer** (`1010:AA2B`, jump table `CS:AA36`, keyed on record **`+0x16`**):
  8 logic handlers. `_dispatch` (`behavior_walk.py:2620`) mirrors it: type 0 nop, 1 special-pod,
  5 pickup, 6 companion, and **types 2 & 4 → the EFAE enemy-behaviour dispatch**. (Layer 2/4 → `EFAE`;
  0 → `BC45` no-op; 3 → `44AF` no-op; 1/5/6/7 → their own logic.)
- **Level 2 — BEHAVIOUR** (`EFAE` → jump table `CS:EFC4`, keyed on record **`+0x18`**): 146 ids → 134
  handlers, **6 alias families** (one body, several ids): `8D4F`←{13,15,1C,1F,7D,7E} (waypoint
  controllers), `BC45`←{00,0D,0E,82} (pure drift), `8676`←{28,2A}, `AED8`←{02,03}, `B3DF`←{22,35},
  `B930`←{16,17}, `F201`←{57,58}.
- **Level 3 — MODE sub-machine** (some families): the waypoint controllers far-call `1F8F:027A`, which
  after the seek dispatches on the record's **`+0x24` mode** (0x13→0432, 0x15→03E6, 0x1C→03A6,
  0x1F→0368, 0x7D→0309, else→02CB) to an arrival action. This IS a third dispatch level — the closest
  thing in the ROM to a per-actor "opcode" beyond the cast-list id.

Handlers live in three code regions: **`8xxx`** (65 ids — the generic behaviour segment), **`Axxx–
Bxxx`** (41 — the movement/seek/collision segment: `AED8`/`AE09`/`B1B0`/`B556`/`BC45`…), **`Fxxx`**
(39 — the level-specific zoo, mostly L3/L5). Region is a coarse cluster proxy.

### 5.2 The recovered "instruction set" (the true surface — ~20 workers, not 146 handlers)
`behavior_zoo_xref.py` (re-run 2026-07-10): **76/134 handlers are thin stubs (<0x20 bytes)**. The
shared workers every handler composes, now all recovered pure functions in `behavior_walk.py`:

| verb | worker(s) | fn | reuse |
|---|---|---|---|
| **tail** | BC45 / BC4B postmove (drift, Y-clamp, X-bounds death, 62F6 collision) | `_postmove_bc45` :2523 | ~72 |
| **contact-step** | AFD8 one contact-step (+ BDD0 predicate) | `_afd8_step` :824 / `_bdd0_contact_at` :254 | 21 |
| **seek** | 5DB2 toward a target, mode-gated | `_apply_seek` :166 / `_b729_seek` :356 | ~9 |
| **steer** | 5E42 Bresenham delta-steer | `_steer_5e42_inplace` :811 / `_steer_missile_tail_8744` :1457 | 3+ |
| **shoot** | 7476 enemy-shot stamp | `_spawn_enemy_shot_7476` :602 | 6 |
| **spawn(child)** | C237 difficulty-throttled child | `_spawn_child_c237` :1347 | ~10 |
| **spawn(alloc)** | 7524/81F4 alloc + 8209 stamp | `_alloc` :153 + `enemy_spawn_stamp_8209` | ~8 |
| **retarget** | 74E2 delta toward anchor (Y+9) | `retarget_delta_toward_anchor_74e2` | 5 |
| **bounce** | BB03 vertical bounce | `_bb03_bounce` :281 | 6 |
| **death** | BFC7 touch-death / BD17 deactivate | `_bfc7_touch_death` :2471 / `_bd17_deactivate` :2393 | many |
| **animate** | sprite = base + table[clock>>shift] | inlined (tables 96D2/96C2/95EA/96AA/96DA/96EC) | pervasive |
| **gate** | guard on a shared clock/counter/planet | inlined (2324/2328/232C/232E/233C/2356/A7A0/A47E) | pervasive |
| **substate** | advance +0x1C, branch per state | inlined (0x20 archetype) | few |

An actor handler = `guards → primitive(operands) → tail`. This is already the step language of §2; it
is now EVIDENCED across 75 handlers, not hypothesised.

### 5.3 Behaviour clusters (for a refactor's grouping)
**A movement-only** (0x27/0x31/0x4F/0x64/0x3B/0x42/0x52/0x53/0x5C/0x5D) · **B seek/steer movers**
(0x2F/0x2E/0x3A/0x29/0x3E/0x3F/0x60/0x2B/0x2C/0x0A/0x1E/0x1D) · **C spawn/shoot emitters**
(0x24/0x25/0x30/0x40/0x68/0x2D/0x46/0x34/0x8F/0x87/0x48/0x49/0x28/0x2A/0x86/0x21/0x1F/0x13/0x1C) ·
**D contact-reactive** (0x33/0x3D/0x3C/0x4B/0x4E/0x19/0x1A/0x83/0x89/0x8A/0x47/0x54/0x56/0x57/0x58/
0x59/0x5A/0x5E/0x5F/0x8B/0x8C/0x26) · **E anim/morph state machines** (0x01/0x26 respawn cycle; the
one-frame morphs 0x3C→3D, 0x4B→33, 0x4D→39, 0x54→56, 0x59→5A, 0x3E→3F, 0x23→2C; 0x63 hatcher) ·
**F waypoint/formation controllers** (the 8D4F/1F8F:027A family + 0x11/0x12 A43C follower + 0x14
formation + the seed group 0x41/0x43/0x44/0x45/0x4A/0x51) · **G level/boss special cases** (0x21 boss
transform, 0x22/0x35 boss riser, planet-gated 0x48/0x59/0x34/…, final-boss A8C2) · **H dispatchers**
(the AA36/EFC4 tables, the AF22 8-way move table, C237's own jump table, the 837A weapon scheduler).

## 6. The proposal — an Overkill actor architecture (emerge, don't impose)

The recovery has ALREADY produced 4 of the 5 pieces; the proposal is to formalise them, not invent.

### 6.1 The `Actor` (the 0x38 record — already a shared view)
`views/object_slots.py:ObjectSlotView` is the Actor. Its fields, as a dataclass the interpreter would
carry: `active(+0), x(+2), y(+4), dir_or_step(+6), sprite(+8), gate_or_layer(+0xA), draw_di(+0xC),
link_key(+0xE), row_or_phase(+0x12), object_type(+0x16→L1 dispatch), behavior(+0x18→L2 dispatch),
prev_behavior(+0x1A), substate(+0x1C), solid(+0x1E), counter(+0x20), transition_latch(+0x22),
mode/variant(+0x24→L3 dispatch), linked_counter(+0x28), move_dx(+0x2A), move_dy(+0x2C),
step_error(+0x2E), target_ptr(+0x30), target_y(+0x32), target_x(+0x34), waypoint_ptr(+0x36)`.
**Open field gaps** a full Actor must still name: `+0x10`, `+0x26` (unnamed), and `+0x36` (the
waypoint cursor — used but unnamed). No new recovery needed, just naming.

### 6.2 The `Behavior` = a step-list over the closed verb set (§5.2)
Represent each behaviour as an ordered `[Guard? , Action(operands) …] + Tail` — where Action ∈ the
recovered verbs and operands are ROM-read constants/fields. Irregular handlers (bosses, C237's own
jump table, the 0x20 dive) keep a `Call(recovered_native_fn)` escape verb (§3.5). The step-list is a
RE-REPRESENTATION of the recovered handler, legal ONLY because a shadow gate proves it reproduces the
walk byte-for-byte. Do NOT build the interpreter until ~all handlers carry their §4-style
decomposition tag — the schema is still emerging (the +0x24 mode sub-machine and the retry-loop of
0x12 are two control shapes the current verb set doesn't yet name).

### 6.3 Per-level data (already data — just externalise it)
- **spawn**: the per-planet tile-cue tables (`tile_cues.py:_PLANETn_STAMPS`, tile id → behavior/sprite/
  dir) — the level's "who appears where."
- **schedules**: `CONTROLLER_SPAWN_SCHEDULES` / `A482` waypoint streams (`(x,y)` pairs, `(x,y,tx,ty)`
  quads, FFFF-terminated) — the movement scripts; `_DEATH_NEXT_SCHEDULE` the death re-arm.
- **anim**: the sprite tables 96D2/96C2/95EA/96AA/96DA/96EC (base + table[clock>>shift]).
These are the editable "cue sheet + choreography data" of the endgame editor.

### 6.4 What stays special-case (honesty)
The boss transforms (0x21/0x22/0x35, `boss_transform_stamp_b58a`, final-boss `A8C2`), the C237 parent
jump table, and the `Fxxx` level-5/L3 zoo tail (0x5B–0x63) are irregular enough to keep as recovered
native fns behind the `Call` verb rather than forcing them declarative.

## 7. Using the LIFTER to accelerate the remaining zoo (the owner's ask)

The remaining ~56 unrecovered behaviours (and the overlay bodies like `1F8F:027A`) should be lifted,
not hand-decoded — hand-reading just cost a wrong `0x7D` arrival stamp this session (the lifter's
literal transcription would not have). The standing pipeline:
1. **`scripts/capture_demo_snapshot.py --demo <D> --stop-at 1010:<HANDLER> --min-boundary N`** — writes
   a full `memory_1mb.bin`+`state.json` snapshot the first time the demo REACHES the handler (pick a
   demo that plays that handler's planet; `L4_full` for the 8D4F waypoint family, `L3_full`/`L5_*` for
   the Fxxx zoo). liftverify runs FORWARD from the snapshot, so it must be captured where the routine
   is already live (a start snapshot run idle never reaches it — verified this session).
2. **`python dos_re/tools/liftverify.py --exe assets/OVERKILL --snapshot <SNAP> --entry 1010:<H>
   [--entry 1F8F:027A …] --samples 16`** — emits a literal ASM→Python hook per entry and differentially
   verifies each call against the interpreted original (ORACLE_PASSING / DIVERGED / NOT_REACHED). A
   PASS is a SAMPLE, not a whole-run proof (retires at `--samples`).
3. **Read the verified hook as authoritative, refactor into a §5.2 verb composition**, then gate with a
   per-behaviour driven oracle (below). The lifted hook is scaffolding; the recovered-source island is
   the deliverable.

## 7.5 SPIKE LANDED (2026-07-11): the step-list interpreter, proven on the bounce cluster

The §6.2 interpreter now has a first CONCRETE, verified realization -- not the production engine, a
scoped spike to validate the verb set + the equivalence-gate method before committing to the zoo:

- `overkill/recovered/adapters/actor_steps.py`: a `Step` verb set (`SetSprite`, `SetSpriteAnim`,
  `GuardXEq`, `SoundGated`, `MorphBehavior`, `SetDir`, `TripleBounce`) -- each a thin wrapper over an
  already-recovered worker, no new semantics -- and `run_actor_steps` (stop early on a failed guard).
- The 88CF triple-AFD8 bouncer cluster expressed as DATA step-lists (`BOUNCE_BEHAVIORS`): `0x33 =
  [TripleBounce]`, `0x3D = [Anim, TripleBounce]`, `0x3C = [SetSprite, Guard(x==0xB0), Sound, Morph,
  SetDir, Anim, TripleBounce]` -- exactly the "guards -> primitive -> tail" shape of §5.2.
- `tests/test_actor_steps.py`: the EQUIVALENCE GATE -- each step-list vs its native `_step_*` handler
  over a spread of record pre-states (the guard boundary, sound gate on/off, anim phases, directions),
  whole-DGROUP diff = 0.  18/18 green.

This demonstrates the model's core claim end to end: a behaviour as data over a shared interpreter is
byte-identical to the hand-written handler.  It does NOT yet touch the walk (the handlers keep their
bodies); promoting a behaviour to its step-list still waits on §6.2 step 4 (the whole zoo tagged) +
the demo-level shadow gate, so the schema keeps emerging rather than being frozen on 3 handlers.

## 7.6 QUANTIZATION COVERAGE (2026-07-11) — the exact ledger

`scripts/actor_quantization_report.py` statically decomposes every recovered `_step_*` handler into
the §5.2 verb set and classifies how it quantizes.  Over the **86 recovered handlers**:

| class | count | % | meaning |
|---|---|---|---|
| STUB | 1 | 1% | tiny body -> a one-verb step-list |
| PURE | 40 | 47% | all callees are verbs + simple control -> a step-list TODAY |
| CHAIN | 23 | 27% | also calls another handler (morph / fall-through) -> compose two step-lists |
| CONTROL | 14 | 16% | verbs known but heavy inline control the vocab doesn't NAME yet |
| ESCAPE | 8 | 9% | bespoke -- keep behind a `Call` verb |

- **Quantizable TODAY (STUB+PURE+CHAIN): 64/86 = 74%.**
- **After 1–2 CONTROL verbs (a `substate`/`+0x24 mode`/retry-loop verb): 78/86 = 91%.**  The CONTROL
  set is almost entirely the waypoint/formation family (`_step_controller_1c/15/7d`, `_step_waypoint_18`,
  `_step_diver_16_17`, `_step_formation_14`, `_step_marcher_0c`, `_step_dropper_34`, `_step_child_04`,
  `_step_stepper_93`, `_step_glider_5a`, `_step_turner_5f`, `_step_hatcher_63`, `_step_yseeker_6b6c6d`)
  — exactly the `1F8F:027A` `+0x24` mode sub-machine §5.1/§6.2 already flagged.  Add that one control
  verb and the whole family quantizes.
- **Genuine `Call` ESCAPE floor: 8/86 = 9%** — the bosses (`_step_wave_driver_21`, `boss_transform_
  stamp_b58a`, `wave_driver_dispatch_b556`), the pods/pickups (`_step_special_pod_1`, `_step_pickup_5`,
  the `_pod_*` sweeps), the `0x26` morph state machine, and `_step_dying_01`.  These stay recovered
  native fns behind the escape verb — the honest irregular tail, matching §6.4.

**Verb reuse** (handlers touching each verb): spawn 30, death 15, seek 14, shoot 10, contact 10,
steer 8, guard 7, move 7, bounce 6, random 5, retarget 5, update 4, sprite 3, tile-gate 3, reflect 1.
So the answer to "can we quantize the zoo": **~74% is a step-list today, ~91% with one control verb,
with a deliberate ~9% `Call` escape** — a measured reduction, every promotion shadow-gated (§7.5).

**Control-verb slice landed (2026-07-11):** the "one control verb" is now demonstrated.
`actor_steps.py` adds the seek->arrival->substate primitives the CONTROL bucket named —
`SetSeekMode2308`, `SeekB729` (records `arrived`), `SpriteFromDir`, `WhenArrived` (the shared
on-arrival gate), and the generic field/branch verbs `IfFieldZero` / `DecFieldThen` /
`GuardGlobalEq` / `GuardFieldNe` / `SetField` / `MorphTo` (all reused across the family).  The
0x16/0x17 diver (`_step_diver_16_17`, a CONTROL-class handler) is expressed as a step-list with them
(`CONTROLLER_BEHAVIORS`) and gated byte-exact vs the native handler over arrival / substate-countdown /
0x16-vs-0x17 / planet states (`tests/test_actor_steps.py`, 30/30).  So the control verbs are proven,
not hypothesised — the waypoint/formation family's remaining members are now mechanical step-list
transcriptions over this same vocabulary, each shadow-gated.

**Projectiles = actors; shoot = the spawn verb, shot TYPE = its operand (2026-07-11).**  A shot is
another object record with its own behaviour/sprite/velocity, so it is already in the model.  The base
`7476` bullet is one template (type 2, behaviour `0x0B`, sprite `0x31`, player-aimed via the `74E2`
deltas); variants re-stamp the spawned slot (the 0x49 burster = an 8-shot RADIAL of behaviour-`0x04`
bullets; the 0x86 launcher = a homing behaviour-`0x60`; the crawler = a sprite override).  The emit
verbs `Shoot` (single aimed `0x0B`) and `ShootRadial(behavior, count)` capture this; `_step_burster_49`
is a step-list (`SHOOTER_BEHAVIORS`, `[SetSprite, AddX, OnClockBeat(232A==F, ShootRadial(0x04, 8))]`)
gated byte-exact (32/32).  So the projectile TYPE is a data operand, and *which enemy fires what* is
step-list data + the `C237` parent-keyed child table (the enemy->child map -- data, kept behind the
`Call` escape for now).  Movement-only actors simply carry no emit verb.

**C237 child spawn folded to data (2026-07-11).**  The last escape-classified emitter is now
declarative.  `_spawn_child_c237` produces a default child (type 2, behaviour `0x04`, sprite `0x30`,
parent+4px) with a parent-nibble spawn-sound table (already recovered data); callers only override the
child sprite.  The `SpawnChild(sprite)` verb captures that (including the throttled stale-bx artifact),
so the child spawners are `[OnClockBeat(232C==0x1F, SpawnChild(sprite))]` differing only by the sprite
operand -- the enemy->child map as data: `SPAWNER_BEHAVIORS` 0x24 -> 0x1E, 0x25 -> 0x1A, gated
byte-exact across fire/off-beat and the difficulty-throttle paths (`tests/test_actor_steps.py`, 42/42).
The verb set now has FOUR families proven end to end -- action, control, emit(shoot), emit(spawn-child).

## 8. First refactor candidates + the verifier plan

**Best first clusters** (biggest sharing, lowest risk): the **waypoint controller family** (one body
`8D4F`/`1F8F:027A` serves 6 behaviours 0x13/0x15/0x1C/0x1F/0x7D/0x7E — recover the mode sub-machine
once, get 6) and the **contact-reactive bouncers** (0x33/0x3D/0x3C/0x4B/0x4E all = `_afd8_step` +
`_bb03_bounce` + a morph gate — pure re-parameterisation). The **spawn emitters** (C237 family) are
already largely done.

**Verifiers (the equivalence proofs — never weaken them):**
- the **walk shadow** `verify_native_lockstep` / `verify_native_walk_demo` (byte-exact whole-DGROUP per
  frame) remains the ground truth;
- **per-behaviour driven oracles** for paths the corpus under-exercises — the pattern proven this
  session (`verify_native_flash_decay`, `verify_native_special_weapon_apply`): inject the precondition
  into BOTH the pure VM and the native handler at a 9B2E boundary and diff (the driven-oracle pattern
  in `loop_blockers.md`);
- a NEW **step-list interpreter equivalence gate** (build only in §6.2's step 4): run the declarative
  step-list vs the recovered native handler over the demo, require zero divergence before a behaviour
  is allowed to drop its procedural body.

**North star, unchanged:** script · schedule · cast · vocabulary · state — an editor over a
byte-exact engine, every layer recovered as data or shadow-gated code, never guessed.
