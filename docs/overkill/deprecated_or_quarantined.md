# Deprecated / quarantined

Tracks code, data, and docs that are obsolete, speculative, historical, or mixing
layers — to be deleted or moved to an explicit evidence/quarantine area rather
than left mixed with current recovered logic. See `rescue_refactor.md`.

## 2026-07-10 — the play_native HYBRID LOOP is deleted (the owner's deep-cleanup directive)

**What was deleted.**  `scripts/play_native.py`'s entire gameplay machinery: the dataclass
`NativeGame` authority, `_advance`'s `g.step(...)` call with its hand-fed globals
(`_object_update_globals`, `scroll_gate`, `source_x/source_y`), the per-tick sync bridges
(`sync_player_anchor`, `sync_new_gameplay_records`, manual `234C/234E/2350/A978` writes), the
separate dataclass starfield simulation (`advance_starfield` — the image's C6C1 ring is the real
one and the frame fn ticks it), the death/respawn glue (`apply_respawn_seeds` + hand-rolled B5A9/
A8C2/20A6 resets at the exit), the `_load_next_level`/`_restart_session` dataclass reloads, and the
fake game-over banner→title flow.  Also deleted: the five probes that GATED that wiring —
`verify_play_native_cold/death/respawn/levelend/render` — replaced by ONE probe of the real wiring,
`verify_play_native_frame`.

**Why.**  The hybrid mirrored fragments of state into the image and back; everything the mirrors
missed was silently wrong.  The owner's playtests kept finding exactly those gaps (no thrusters,
wrong fire origin, dead waves, lost fire after the intro), and the follow-up fixes were being
glued onto the same scaffolding.  The project's whole point is that the ONE lockstep-verified frame
(`advance_gameplay_frame_97b2`, byte-exact on 8291/8292 L1 demo frames) IS the game; the app is a
host shell (window, keyboard→INT9 table, palette blit, pacing) plus an image-only renderer.

**What remains quarantined (not deleted this pass).**  `overkill/native_game.py`'s `NativeGame.step`
path and `native_walk_frame`'s sync bridges still exist because tests and older probes pin recovered
systems THROUGH them.  They are DEPRECATED FOR GAMEPLAY: no new caller may drive a game with them.
Retiring them (moving the pinned tests onto image-level checks) is follow-up work.

**Do not resurrect** a dataclass game authority, a second starfield sim, or an exit-time respawn
glue path.  If play_native misbehaves, the bug is in the frame fn or the seed — fix it there, under
the lockstep gate.

## Doc sweep (2026-07-07, owner-directed)

Eighteen historical plan/report/audit docs were stamped with a SUPERSEDED banner (content kept,
links intact): next_steps, loop_plan, native_recovery_goal, native_game_endgame, refactor_plan,
rescue_refactor, architecture_cleanup_plan, render_completion_plan, enhanced_renderer_plan,
native_background_interpolation_plan, semantic_crystallization_plan, high_level_refactor_audit,
coastline_report, performance_investigation, hook_naming_audit, native_video_plan,
render_completeness, runtime_code_staticization (depth_recovery_plan was already marked).
The live authorities are `campaigns/README.md` -> `campaigns/demo_lockstep.md` (the ACTIVE
campaign) -> the `run_status.md` TOP HEADER.  Reference docs (design, source_port_methodology,
game_recovery_lifecycle, recovered_islands, island_truth_tables, hook_inventory, actor_model,
bootstrap_static_boundary, runtime_findings) stay unbannered -- they document mechanisms, not
plans.  The clean-process reference this sweep was checked against: `D:\Games\DOS\dos_re`
(START_HERE/lifecycle/charter) -- its done-definition ("replay the demo corpus with the VM
disabled; frame-and-state equivalence") IS the demo-lockstep campaign.

## Status of the inventory (2026-06-19)

A repo-wide mess sweep (this rescue pass + the earlier cleanup) found the code
itself **remarkably clean**: 0 unreferenced modules, 0 backup/`.bak`/`_old`
files, 0 tracked `.pyc`, 1 TODO marker. So there is little *dead code* to delete.
The quarantine work is mostly about **heavy evidence artifacts** and **historical
doc sections**, plus **future** layer separation (probes/evidence dirs).

## To quarantine — heavy evidence artifacts (not test fixtures)

Move these to a future `overkill/evidence/` (or drop them; git history keeps them):

- `artifacts/world_write_trace_demo_20260616_000527_enriched_20000.json` (~1.39 MB)
- `artifacts/world_write_trace_demo_20260616_000527_enriched_2000.json` (~0.33 MB)
- `artifacts/world_write_trace_demo_start_1000.json` (~0.46 MB)
- `artifacts/world_write_summary_*.json`, `artifacts/world_dump_*.json`

These are one-off investigation dumps from a past trace; **no test loads them**
(only `recovered_source_layer.md` / `run_status.md` cite them as evidence). Keep
them only as archived evidence, not in the live artifacts root.

## Already neutralised (no action needed)

- **`.idea/` IDE config** — was tracked (11 files, two folders); untracked +
  gitignored.
- **`next_steps.md` dated "current next candidates" sections** — marked historical
  (banner added); not a live TODO.
- **`loop_plan.md` / `loop_blockers.md`** — reframed: loop_plan is now only the
  divergence-fix procedure; resolved blockers compressed to an index.

## Pending verification, NOT deprecated (do not delete)

- `_run_object_behavior_8d4f` and the `7476` formation-spawn flag scaffolding —
  analyzed-dead de-transliteration that was **reverted** because the bounded demo
  window never exercises them and they have no per-hook oracle. A full-demo
  (`OVERKILL_FULL_DEMO_VERIFY=1`) pass would unblock them. They are correct as-is.

## Watch list — coupling to reduce, not delete

- **`hooks.py` (4106 lines)** — keep thin; move fat bodies into islands over time.
  Not deprecated, but must not grow.
- **`object_runtime.py` re-export facade** — load-bearing (verified), but a symptom
  of the tight lifted↔hook weave; shrinks as islands move to pure systems.

## To create (layer separation)

- `overkill/probes/` — temporary investigation tools (currently `scripts/trace.py`
  and ad-hoc probes live outside a clear home).
- `overkill/evidence/` — archived pilot evidence, traces, old maps.
