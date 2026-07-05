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
