# Next Engineering Steps

> **Status (updated 2026-06-30):** the live "what to work on next" is the single `/goal` brief
> **[`docs/overkill/overnight_endgame_execution.md`](overnight_endgame_execution.md)** (the
> cold-boot endgame), with **`docs/overkill/loop_blockers.md`** for open blockers. This file is
> now a **durable methodology + island reference**: the
> observe→classify→boundary→oracle→hook loop, verification modes, mature-island
> list, and semantic-crystallization discipline below all still hold. The dated
> "Current next candidates after …" sections near the bottom are a **historical
> record** of past frontiers, not a live TODO — most of those hooks are long
> since lifted. Don't pick work from them; use `refactor_plan.md`.

Use the current methodology loop for every item:

```text
observe -> classify -> choose boundary -> build ASM oracle -> implement hook -> verify -> document -> move to island
```

The detailed OVERKILL playbook is in `docs/overkill/source_port_methodology.md`.

Keep the bootstrap/static-runtime boundary explicit when startup issues appear:

```bash
python -m overkill.cli bootstrap-boundary --video tandy --sound adlib --out artifacts/static_runtime_boundary.json
```

Use `docs/overkill/bootstrap_static_boundary.md` to decide whether a new regression belongs
to startup extraction/materialization or to the target runtime/source-port layer.

## Current Priorities

0. **Use the static runtime bundle as the canonical inner-runtime checkpoint.**
   - Generate it from original files, not from `OVERKILL.UNLZEXE.EXE`:

     ```bash
     python -m overkill.cli static-runtime-bundle assets/OVERKILL \
       --game-root assets \
       --video tandy \
       --sound adlib \
       --out-dir artifacts/static_runtime_bundle
     ```

   - Treat `static_runtime_bundle.json` as the review surface for bootstrap
     regressions: PSP tail, `1010:*` hash, optional `2032:*` driver hash, and
     materialized globals.
   - The next extraction frontier is splitting derived screens/tables/sound blobs
     out of the initialized image into named deterministic assets.

1. **Keep shrinking meaningful `unknown` coverage.**
   - Prefer stable game-module boundaries over transient bootstrap code.
   - Good candidates are repeated fail-fast paths, renderer/setup table builders,
     object/collision tails, and file/overlay orchestration parents.
   - Treat `32FF:*`-style dynamically loaded bootstrap/relocation code as the
     `bootstrap` coverage island. It is classified, but not a source-port game
     island to hook unless boot performance itself becomes a blocker.

2. **Keep `overkill/hooks.py` as staging, not the final game source.**
   - New hooks may start there.
   - Once their island is clear, move behavior into
     `overkill/<island>/` and keep only the exact address
     wrapper in `overkill/hooks.py`.
   - Current cleanup priority:

     ```text
     1. EGA rendering module
     2. packed/CGA/shared blitter modules
     3. object_runtime module
     4. asm_helpers / hook_bridge module
     5. present/timing/input module
     ```

3. **Prevent duplicate lifted logic.**
   - Before adding a hook, search for the same original tail, continuation IP,
     field offsets, and table addresses.
   - Factor shared tails into helpers named after original addresses.
   - Reuse existing helpers such as the AC97 scan, AD60 bounds/tile tail, 0FA3
     table builder, asset stream helpers, and shared coordinate helpers.

4. **Use verification modes intentionally.**
   - Direct oracle tests for small routines.
   - Snapshot oracle tests for stateful paths.
   - Live hook verifier for real startup/gameplay calls.
   - Frame verifier for video paths and intro/menu regressions.
   - Runtime smoke with fail-fast enabled for newly exposed branches.

5. **Maintain island truth tables.**
   - `symbols.json`: address name/status/island.
   - `docs/overkill/runtime_findings.md`: durable facts and weird side effects.
   - `docs/overkill/island_truth_tables.md`: what is known/verified/guessed/unknown per
     island, plus staged routines and test/snapshot coverage.
   - `docs/overkill/run_status.md`: current checkpoint and commands run.
   - `artifacts/hook_coverage_cache.json`: verified/cached cost when useful.

## Active Frontiers

- gameplay object behavior and collision/postmove branches found by fail-fast
  reports;
- remaining shared layer/sprite scans or presenter tails that still appear as
  unknown in representative gameplay coverage;
- sound/timer behavior beyond the verified PC speaker/timer ISR path;
- EGA-specific rendering correctness, which should be approached with frame
  verification rather than broad renderer guesses.

## Object Runtime And Semantic Crystallization

Do not start with `Enemy`. Start with runtime evidence:

```text
slot id
active flag
x/y
sprite ref
behavior id
spawn source
collision partner
state changes
sound triggers
deactivation reason
```

Then introduce candidates, not hardcoded semantic behavior:

```python
class ObjectClassification:
    kind_candidate: str
    confidence: float
    evidence: list[str]
```

Example:

```text
slot 12 -> candidate: enemy_projectile, confidence 0.72
evidence:
- spawned from enemy behavior AED8
- damages player
- deactivates on collision
- uses small moving sprite
```

Only after repeated patterns converge should higher semantic definitions appear:

```text
ProjectileDefinition
EnemyDefinition
PickupDefinition
BossDefinition
```

## Mature Or Closed-Candidate Islands

- `asset_codecs`: checksum, packed reads, RLE/LZ, and decoded-asset table
  search. Startup graphics and overlay helpers are separate islands.
- `overlay`: overlay directory/signature/name/path/XOR helpers.
- `file_io`: overlay/container open/read/seek orchestration around asset loading.
- `startup_graphics`: renderer table/materialization helpers used during startup.
- `rendering`: Tandy/CGA/EGA renderer primitives, shared coordinates, layer sprites.

These can still receive fixes if new evidence appears, but they should not be
rewritten speculatively.

## Current Next Frontier After The 2026-06-13 Input/Collision Pass

- `1010:AB77` / `1010:ABCA` object-behaviour driver family.
- `1010:A940` gameplay-state update cluster.
- Refresh hook coverage cache for newly verified hooks.
- Add an object-slot evidence trace/dump tool before introducing semantic enemy
  or projectile classes.

## Semantic Crystallization Rule

For object/gameplay work, keep accepting the current low-level model until the
evidence supports a higher one. A slot can remain "object with sprite/layer/logic
id/movement/collision fields" until multiple verified routines prove that it is
the player, a projectile, a pickup, or a specific enemy archetype.

Useful evidence for promoting a concept upward:

- stable logic-id dispatch target;
- stable sprite/animation table;
- unique collision/postmove behavior;
- unique owner/link fields;
- repeated level-state or score/resource side effects;
- renderer/presence behavior that matches the same object family.

Avoid introducing modern semantic names in island modules too early; keep address
anchoring in helper names until the archetype is proven.

## Task Layer Discipline

Every AI/Codex/Claude task should say the layer:

```text
Work only in the verified lifted routine layer.
```

or:

```text
Work in the runtime object model layer. Do not classify enemies yet.
```

or:

```text
Work in the semantic classification layer. Do not change runtime behavior.
```

Do not combine these accidentally. A refactor task is not a fix task; a fix task
is not a semantic model task; a semantic task is not renderer cleanup.

## Current next candidates after 2026-06-13 unknown cleanup

1. Hook `1010:4CED` as a small presence-list parent by composing the existing
   `4D15` helper three times.  Do not duplicate `4D15` internals.
2. Hook the `1010:A846/A85E/A876` layer-scan parents only if they can be cleanly
   composed from existing `A849`, `A861`, `A87C`, `5AC8`, `7746`, and `4CED`
   helpers.
3. `1010:9B2E` is now lifted as a parent, `9CB6` is split as a contact
   fanout, and `A067` is split as raw action/object-spawn fanout. Continue with
   the remaining out-of-range `A067/A958` child (`44AF`); `9E19` is already lifted as post-contact/status fanout. Do not add semantic player/enemy/weapon names yet.
4. Keep `1010:A940` classified as `game_state` frontier until child calls such as
   `1F8F:081D`, `F797`, and the object scan tails are sufficiently understood.
5. Treat `1010:D007` as a main-loop orchestration boundary, not an early hook
   target.  It should be lifted late, after children are exhausted.

## Current next candidates after A90C/A93C/4D64 cleanup

1. `1010:A846/A85E/A876` can be approached as scan-parent composition only after
   verifying they reuse existing scan helpers cleanly.
2. `1010:D04D..D072` is now classified as `game_state` frontier.  Treat it like
   the `D007` parent: document and split child calls first; do not hook it as one
   monolith unless the children are exhausted.
3. Keep object semantic work candidate-based.  The A90C pass is renderer/list
   orchestration, not evidence for a concrete enemy/projectile class.

## Current next candidates after 96C5/BC45/4E0D/61CA cleanup

1. `1010:9FEA` is the most interesting gameplay-runtime candidate.  It appears
   to update object/table coordinates and flag bytes, but it needs a direct ASM
   oracle before being assigned to `movement` or `gameplay_objects`.
2. `1010:4D95` is likely a presence-list parent.  If lifted, it should compose
   the existing `4D15` presence stamper and avoid copying its loop.
3. `1010:780E` is a Tandy/layer draw sub-loop candidate; use frame/pixel evidence
   before broadening its boundary.
4. `1010:8A7E` is object-behavior frontier.  Keep technical naming and avoid
   `Enemy`/`Projectile` semantics until spawn/collision/death/asset evidence
   converges.

## Recent cleanup of init-phase ASM

## 2026-06-14 - Bootstrap LZEXE and AdLib probe lifting

Reduced pure-original Tandy+AdLib cold-start ASM in the dynamic/init layer.

- Added `overkill/bootstrap_lzexe.py` and hooks for the
  observed temporary nested LZEXE/self-relocation stubs at `1B65:0069`,
  `1C43:0069`, and `23AD:0069`. These hooks lift only the hot bitstream copy
  loop and stop at the original relocation/final-transfer tail (`00FC`), keeping
  the bootstrap/runtime boundary explicit.
- Classified the observed temporary unpacker segments as `bootstrap` rather than
  `unknown`; they are not source-port runtime islands.
- Added `overkill/sounds/adlib_driver.py` and a
  `2032:04E9` hook for the loaded Sound Images AdLib/YM3812 hardware probe.
  The hook preserves the original register writes and synthesized status reads
  but skips PIT-delay busy loops.
- `scripts/profile_hotspots.py` now accepts `--sound pc|adlib|roland` and uses
  the canonical compact PSP tail builder, so profiling can match `play.py
  --video tandy --sound adlib`.

Validation:

```text
python -m overkill.cli static-runtime-bundle assets/OVERKILL --game-root assets --video tandy --sound adlib --out-dir /tmp/static_after_hooks_final
# reached 1010:D007; steps=21,499
# memory_1mb.bin SHA256 is unchanged: c9bad83826f22bd144a7dcb3d98d84aaaf732b03527f8702dd4d2b68da57a476
# CPU snapshot is byte-equivalent to the previous interpreted canonical bundle

python scripts/lint.py
# passed

python -m pytest -q
# 225 passed
```

Before this pass, the canonical static bundle reached `1010:D007` in 1,245,977
steps before the LZEXE lift and 95,846 steps after the LZEXE lift alone. With
the AdLib probe lift as well it now reaches the same runtime image in 21,499
steps.

