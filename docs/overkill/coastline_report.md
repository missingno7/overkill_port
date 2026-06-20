# OVERKILL coastline report

The **coastline** is the active boundary between original ASM (run on the `dos_re`
oracle) and recovered native code. This report inventories it so the rescue
refactor can shorten/raise it over time. See `rescue_refactor.md` for the plan.

Regenerate the metrics with `PYTHONPATH=. python scripts/source_port_status.py`.

## Layer inventory (2026-06-19)

| Layer | mods | lines | role | direction |
|---|---|---|---|---|
| `vm` (overkill top-level) | 18 | 5091 | emulator harness / oracle / verification | keep |
| `hook_boundary` (hooks.py + hook_wrappers) | 9 | 5581 | `@registry.replace` glue | **keep thin; shrink** |
| `lifted` (gameplay/) | 17 | 10293 | VM-aware bodies on the original layout | **the coastline; push down** |
| `bridge` (recovered/{adapters,views}) | 16 | 2511 | DOS-mem ⇄ domain projection | grow as needed |
| `backend` (rendering/sounds/asset_codecs/file_io) | 24 | 8760 | platform-specific, isolated | keep isolated |
| `source_pure` (recovered/{domain,systems}+islands) | 18 | 1793 | **pure VM-free game logic** | **grow** |
| `game_core` | 4 | 399 | backend-agnostic protocols/types | grow |

**Headline:** 10.7% of game-logic mass is pure source-like (2192 / 20577 lines).
The rescue raises this by moving logic from `lifted` down into `source_pure`.

## Coastline metrics

- **Registered VM hooks: 336** — taxonomy: 12 checkpoint, 5 env_wait, 0 debug_probe,
  **319 glue**. The 319 glue hooks are the coastline's length; the rescue converts
  these toward verified pure functions called by *thin* adapters.
- **`hooks.py` = 4106 lines** — the single oversized hook-boundary file (the
  dashboard flags >1500). Registration glue should stay thin; fat bodies belong in
  islands. Do not grow it.
- **Largest lifted files** (push-down candidates, by lines): `object_movement`
  (1391), `game_state` (1255), `frame_orchestration` (1253), `action_spawns`
  (1247), `object_behaviors` (1231), `object_runtime` (1095).
- **Object-record map:** 25/28 words named; gameplay record access 50 named / 3
  raw (the deliberate `OFF_SUBSTATE_1E` alias). Typed-view migration is complete.
- **Recovered islands (self-describing): 13** (all VERIFIED, MovementSystem) — the
  first annotated slice. The pure layer has 44 functions total; annotating the rest
  is ongoing.

## Classification of the broad frame hooks (maps, not source)

`run_main_frame_loop_d007` and `run_frame_controller_9b2e` are **frame maps /
call-order evidence / oracle-composition scaffolds** — they record *which* islands
run in *what order* per frame. **Do not add recovered gameplay logic inside them.**
New gameplay logic goes into pure systems; the frame map only composes them.

## Where the coupling concentrates

1. **`lifted` (gameplay/) ↔ VM** — the bulk of the coastline. Every function takes
   `cpu` and mutates `cpu.s`/`cpu.mem`. Target: each becomes a thin adapter (read
   view → call pure system → write/check), with logic in `source_pure`.
2. **`hooks.py` fat bodies** — registration glue mixed with behaviour. Target:
   thin registration only.
3. **`object_runtime.py` re-export facade** — 183 imports re-exported to hooks/
   hook_wrappers. Not dead (verified), but a sign of the tight lifted↔hook weave;
   it shrinks as islands move down.

## Reduction targets (priority order)

1. Object/movement slice → `MovementSystem` / `ObjectSystem` (in progress).
2. Collision predicates → pure `recovered/systems/collision.py` (partly exists).
3. Frame timers / status display → pure systems (partly exists).
4. Thin the per-behaviour hook adapters as their logic lands in pure systems.
5. Stop the broad frame hooks growing; reclassify as maps (done in docs).

## What is NOT coastline (already clean)

- `recovered/systems`, `recovered/domain`, `game_core` — verified pure (0 VM
  imports). These are the destination, not the problem.
- `backend` — isolated; must not import gameplay.
- Typed views — the memory-translation layer is in place.
