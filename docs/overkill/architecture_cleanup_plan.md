# Architecture cleanup plan — one game core, two hosts

Target shape (the binding direction):

```text
        thin hooks ──► recovered adapters ──► recovered domain + recovered systems ◄── native runtime
                                                  (the canonical game)
```

The recovered **systems** are the game. **Hooks** are only entry points from original
`CS:IP` addresses. **Adapters** only translate DOS/VM memory ↔ recovered records. The
**native runtime** is only a modern host that drives the *same* recovered systems from
native state. The VM stays alive as oracle/verifier/gap-executor and shrinks over time.

This is a **staged migration, not a rewrite** — the project stays runnable at every step.

## 1. Honest scorecard — where we actually are

The architecture is already ~70–80% of the way to the target. The work is collapsing the
*remainder*, not rebuilding.

| Concern | Status | Evidence / notes |
|---|---|---|
| Dependency direction enforced | **strong** | `audit_architecture.py` (layers vm/hook_boundary/lifted/backend/**native_render**/bridge/source_pure/game_core) + `audit_recovered_layers.py` (no cpu/mem/CPU/Memory/layout-consts in pure). Both green. |
| Pure systems are VM-free & canonical | **strong** | 26 `source_pure` modules; collision island, movement primitives, spawn seeds, score, timers, AE09 transform, action gates all pure + single-owner. |
| Adapters translate, don't decide | **strong** | 49 `…disagrees…` cross-check asserts; adapters call the pure system and assert agreement (the sanctioned pattern), not a 2nd implementation. |
| Native runtime hosts recovered systems | **partial** | `native_video` now imports only `recovered.{domain,systems}` (+self); `game_core` imports nothing external. The coverage gate proves the native path runs recovered code (AE09 byte-exact). |
| Hooks are thin | **partial** | `hooks.py` = 202 registrations / 251 defs (mostly registration), but 3203 lines with nested runtime factories — the one real structural smell. |
| Object-update logic is canonical & native | **early** | Coverage gate: **1** of ~dozens handlers native (AE09). The hot handlers (B86D 46%, AED8…) are still lifted cpu-hooks, not pure transforms. |
| Render from recovered state | **partial** | `native_video/` composes playfield+sprites+HUD from `NativeGameState`; starfield parallax is the hard blocker. |
| Audio from recovered events | **missing** | `sounds/` are VM-side drivers; no native audio engine consuming recovered events. |
| State model completeness (§1.2) | **partial** | `NativeGameState` = pools+camera+hud only; no Projectile/Combat/Level/Rng/Scene mirrors yet. |
| Duplicate logic | **mostly collapsed** | Audit found no unguarded duplicate gameplay decisions. The real duplication was the **probe harness** (19× scaffolding) — now unified in `probes/_harness.py`. |

## 2. The canonical-systems principle (what "one place" means here)

A gameplay rule is *canonical* when exactly one `recovered/systems` function owns it and every
other layer **calls** it. Already canonical: collision predicates, movement clamps/steps, the
AE09 whole-slot transform, BCD score, frame timers, the A067 action gates. The lifted handlers
still inline their movement/tail composition — that is the main remaining duplication to collapse,
and it collapses *by promotion*, not by deleting copies blindly (each promotion is gated produced-vs-VM).

## 3. Staged migration recipe (per rule)

```text
lifted/hook behaviour works
  → isolate the pure rule (inputs/outputs as ordinary values)
  → add/extend a recovered DOMAIN record for its inputs
  → add the recovered SYSTEM function (the canonical rule)
  → adapter: project DOS state → record → call system → write back + assert agreement
  → native runtime: register the system in the object-update / frame driver
  → delete the duplicate inline copy
  → verify (per-routine ASM oracle + demo-replay + the coverage gate)
  → document remaining gaps
```

## 4. Priority order (high-impact first — measured, not guessed)

The coverage gate (`overkill/probes/verify_native_object_update.py`) turns this into a measured
backlog. Current order on L2_full:

1. **B86D (logic_id 0x1D) — 46% of per-slot updates.** Promote to a pure whole-slot transform
   (AE09 pattern); near-calls already composed. Biggest single coverage win.
2. **AED8 (0x02), BE3C (0x01), 8C1F (0x8A), 8D4F (0x1C)…** — the next buckets.
3. **EFC4 dispatch** → pure routing fn (the per-logic dispatch the native pool-walk needs).
4. **Frame orchestration** → a native frame driver that calls the object-update + render systems.
5. **HUD/status, input cadence, timing** — mostly pure already; wire into the native frame.
6. **Render from recovered state** (close the starfield gap with off-screen trace tooling).
7. **Audio engine** (recovered events → native mixer) — the largest greenfield subsystem.

## 5. Guardrails (enforced now)

- `scripts/audit_architecture.py` — layer import rules. **New this pass:** the `native_render`
  layer (`overkill/native_video/*`) must not import vm/hooks/lifted/bridge — the native host
  cannot reach back into the VM world. (`source_pure`/`game_core` already locked.)
- `scripts/audit_recovered_layers.py` — pure layers free of cpu/mem, VM/CPU *types*, and
  memory-layout constants (`# layout-justified` escape hatch).
- `tests/test_architecture_layers.py` / `tests/test_audit_recovered_layers.py` — non-vacuous
  (prove the rules catch real violations).
- `overkill/probes/_harness.py` + the coverage gate — one verify framework; a new native rule
  is one registry entry, gated produced-vs-VM.

**Guardrail gaps to add:** a "hook body too large" check (thin-hooks); an advisory
duplicate-predicate lister; a `source_port_status` line for native-ready vs VM-bound per subsystem.

## 6. Remaining VM-bound gaps & missing recovered systems (deliverable #8)

**VM-bound (still lifted cpu-hooks; promote via §3):**
- Object behaviour handlers: B86D/AED8/BE3C/8C1F/8D4F/8A23/B24D/B909/… (see coverage gate).
- Frame orchestration spine (`frame_orchestration.py`) — phase decisions still VM-shaped.
- `hooks.py` nested runtime factories (`_tandy_render_runtime`, `_layer_sprite_runtime`) — move out.
- Bounded-original tails: A7EB display copy, D2A4+, drift branches AE45/AE91, A958→44AF dispatch.

**Missing recovered systems (greenfield):**
- EFC4 per-logic dispatch as a pure routing fn.
- ProjectileState / CombatState / LevelState / RngState / Scene-mode domain records + their systems.
- Native audio engine (recovered audio events → mixer); starfield parallax render system.
- Level load / trigger (3721) / transition / mode-flow systems.

**Genuinely hard (need new tooling, not just labour):** starfield parallax (off-screen trace);
native audio subsystem.

## 7. Definition of done

`--backend native` replays every demo with **no VM**; native state mirrors the VM at every
checkpoint with zero divergence; the runtime path is VM-free; duplicate gameplay logic is collapsed
and the dependency shape is guarded. The repo then reads as **one recovered game core with two hosts**
(VM/oracle host + native host) converging on the same `recovered/systems`.
