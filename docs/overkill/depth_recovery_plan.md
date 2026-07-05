# Depth Recovery Plan — from "verified at ASM altitude" to human-readable game source

> Written 2026-07-05 after a deep state review. This is a STRATEGIC companion to `run_status.md`
> (which tracks the live per-slice frontier). It answers: what does the code actually look like now,
> what is stale / needs redoing, and how do we recover the MAIN PARTS of the game so they READ like
> reconstructed source — not a verified disassembly.

## 1. Honest state (grounded in metrics, not vibes)

`python scripts/source_port_status.py` (2026-07-05):

| layer | lines | role |
|---|---|---|
| vm | 20544 | emulator / oracle / test harness (not game code) |
| hook_boundary | 4732 | `@registry.replace` glue (`hooks.py` alone = 3265) |
| lifted | 10197 | VM-aware bodies on the original memory layout |
| bridge | 4300 | DOS-memory ↔ portable projection (the adapters/views) |
| backend | 10041 | Tandy/EGA/CGA render + sound + assets (isolated) |
| **source_pure** | **9337** | **PURE VM-free game logic (the future native core)** |
| game_core | 399 | backend-agnostic protocols |

**33.6% of game-logic mass is pure source-like; 239 pure functions in `recovered/systems`.**

The project has strong **breadth** and byte-exact **proof**, but low **altitude** and **readability**:

1. **Recovery is organized by ADDRESS, not by game concept.** `object_update_aed8`,
   `wave_driver_dispatch_b556`, `advance_frame_counters_5f61`, `contact_probe_afd8`. In the
   crystallization pyramid these are Layer-3 names (verified-lifted routines tied to an address), not
   Layer-6 archetypes (`Enemy`, `PlayerShot`, `Wave`, `Score`). We have a *verified disassembly*, not
   *reconstructed source*.

2. **The core data model is half-guessed.** The `0x38` object record is the vocabulary of EVERYTHING
   (player / enemies / shots / effects / pickups). Status: 25/28 words named — but only **10 KNOWN,
   15 GUESSED, 3 unknown**. Every gameplay function reads this record; ~half its fields are guesses.

3. **The newest code is offset-soup.** `recovered/adapters` has **127 raw `+0xNN` offsets vs 62
   `OFF_*` names (67% raw)**; `recovered/systems` is far better (34 raw vs 81 named, ~30% raw). The
   status metric's reassuring "6% raw" measures only the *old* `gameplay/` layer — the adapters
   (`behavior_walk.py` = 514 lines, `level_object_script.py`) are a **blind spot**, and they are the
   milestone code. A reader sees `mem.ww(DS, rec + 0x18, beh)`, not `slot.behavior = beh`.

4. **The confidence manifest is nearly blind.** `@recovered_island` covers **35 of 239 pure
   functions (15%)** and **zero adapters** — so the behavior walk and the level-script walker (the
   biggest recovered subsystems) do not appear in the "what's recovered" map at all.

5. **The spine is documentation-as-code.** `native_app.py`'s `APP_MODE_GRAPH` (boot → title → level
   → death/respawn/game-over) does not EXECUTE; `play_native` drives an ad-hoc loop. 21 declared
   fail-loud gaps.

6. **Scaffolding sprawl.** `hooks.py` is 3265 lines; **318 of 335 hooks are "glue"** (collapse
   targets) that no native path uses but nothing retires.

**Bottom line: we can PROVE the game is correct, but we cannot yet READ it as the game.**

## 2. The four structural problems (what to refactor / clean / redo)

### P1 — The object record is guessed and bypassed  ← highest leverage
It is the shared vocabulary. Until every field is named-with-evidence and read through a struct,
nothing above it can be readable, and every new adapter adds more `rec + 0x18` soup that will have to
be converted later. This is THE foundational debt.

### P2 — The state-view layer exists but is not adopted
`views/object_slots.py` (the `OFF_*` names) and `domain/object_slots.py` (named accessors) already
exist — but the adapters bypass them (127 raw offsets). "Offsets out of the LOGIC" (the pre2
milestone) is unmet in exactly the code that matters most now.

### P3 — Naming altitude: address-tagged, not semantic
239 functions named by address; no `Enemy`/`Player`/`Wave`/`Scoring` concepts. The behavior "zoo" is
a flat set of `_advance_*` / `step_*_<addr>` handlers, not an `Enemy` archetype with named states.

### P4 — Scaffolding sprawl + un-executed spine + manifest blind spot
`hooks.py` (3265 lines), 318 unretired glue hooks, a mode graph that does not run, a manifest that
misses 85% of functions and all adapters.

## 3. The depth plan (phased, reconciled with the L1-playable north star)

Guiding principle (from the sibling pre2_port, which finished this arc): **crystallize meaning UP
from verified low-level facts, and do the big readability pass once the game WORKS** — pre2 moved to
the state-view layer late. BUT nail the DATA MODEL early, because it is the shared vocabulary and
offset-soup compounds daily.

### Track 1 — FINISH L1 PLAYABLE first (do not pause; it's the north star)
Proves ONE level's recovery is complete + correct end-to-end (cold boot → fight → die/win). It's
close (clauses 1–3 done, 4 in progress). **Constraint change: stop adding offset-soup — new code
uses named fields (Track 2's view) from here on.** This is the "boy-scout" entry point for P2.

### Track 2 — NAIL THE OBJECT RECORD (foundational; start NOW, in parallel)
The single highest-leverage depth investment. Steps:
1. **Evidence-name every one of the 28 words.** Drive the field usage across the verified islands
   (each field's writers/readers are already in the recovered functions) to move the 15 GUESSED + 3
   unknown to KNOWN, or mark honestly. Deliverable: a canonical field table with the ASM evidence.
2. **Build one `ObjectRecord` view** over `MutFlatMemory` (mirrors pre2's `dgroup_view`): `rec.x`,
   `rec.behavior`, `rec.sprite`, `rec.active`, `rec.substate`, ... reading/writing the same bytes.
   Byte-backed, so every existing byte-exact gate passes unchanged.
3. **Adopt it in NEW code immediately; convert existing on-touch.** Start with `behavior_walk.py`
   and `level_object_script.py` (the offset-heaviest). Each conversion is gated by the shadow probe
   staying 200/0 — a zero-risk mechanical refactor with a strong net.
4. **Extend the raw-offset metric to the adapters** so the debt is visible and trends down.

### Track 3 — SEMANTIC CRYSTALLIZATION by subsystem (after L1 plays)
Group + rename the address-tagged functions into readable, game-concept modules — but ONLY collapse
where the ORIGINAL call graph supports it (the evidence-based collapse rule; never an invented modern
design). Target shape:
* `player/` — ship move, fire fan-out, death, respawn.
* `enemy/` — the behavior zoo as an `Enemy` archetype: `approach()`, `hold()`, `shoot()`, `dive()`,
  `reshuffle()` (behavior 0x20 already decomposes exactly this way); `WaveController` (0x1F).
* `wave/` — the formation table, the A844 ring, the spawn schedule, the 4A65 scene script.
* `combat/` — the 62F6 overlap scan, damage, the C037 death transition, 5F0D scoring, pickups.
* `frame/` — the 97B2 tick spine, the 5F61 timing cascade, the mode machine.
Each function keeps its `@recovered_island` (now with a semantic name); the address lives in the
metadata, not the identifier. Rename `object_update_aed8` → `enemy.timed_mover_step` / the player
shot's `player_shot.step`, etc.

### Track 4 — STRAND THE SCAFFOLDING (ongoing hygiene, per wired subsystem)
* **Hook-role audit tool** (pre2's `hook_audit`): classify the 335 hooks as probe / verifier /
  replacement / gap-detector and measure which still FIRE per snapshot — the retirement driver.
* **Split `hooks.py`** by subsystem; move registration out of any runtime path into the verify gates.
  End state: hooks load only for oracle comparison. Retire a subsystem's hooks in the same slice it
  goes native.
* **Execute the spine**: promote `APP_MODE_GRAPH` into a `NativeSession` that owns mode + planet +
  lives and walks the edges (the death/respawn/level-end compositions are recovered pieces). The mode
  graph stops being documentation and becomes the program.
* **Extend the manifest to adapters** and raise coverage — it should be the true "what's recovered"
  map, not a 15% sample.

## 4. Sequencing recommendation (the one-paragraph answer)

Keep **Track 1 (finish L1 playable)** as the active north star — it's close and it proves one level
end-to-end. Start **Track 2 (nail the object record)** in parallel *now*, because it is the shared
vocabulary and the longer we build adapters on raw offsets the larger the eventual conversion; it is
also bounded and zero-risk (byte-backed view, shadow-gated). Defer **Track 3 (semantic
crystallization)** until L1 plays — refactoring 239 functions into archetype modules is far safer
against a working, playable reference than mid-recovery. Run **Track 4 (scaffolding hygiene)**
opportunistically, one subsystem at a time, as each goes native. Net: L1 becomes playable, the data
model becomes named, new code becomes readable, and the big rename lands last against a game that
already works — the pre2-proven order.
