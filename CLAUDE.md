# CLAUDE.md — OVERKILL VM-less source-port

Evidence-driven reverse-engineering + native source port of the DOS game **OVERKILL: The Six-Planet
Mega Blast**. The endgame is a **fully-playable, VM-less, cold-booting** native game (intro → menu →
levels → ending) with the original binary kept only as an optional verification oracle.

## Start here
- **Conventions, layer rules, working principles:** [`AGENTS.md`](AGENTS.md) (read this first).
- **The recovered high-level structure + the native/gap boundary (the SKELETON, read for the map):**
  [`overkill/native_app.py`](overkill/native_app.py) — top-level flow, the `1010:97B2` stage order,
  and every declared fail-loud gap (`describe_gaps()`).
- **What to build next + the cold-boot done-condition (the canonical `/goal` brief):**
  [`docs/overkill/overnight_endgame_execution.md`](docs/overkill/overnight_endgame_execution.md).
- **Latest state / where the last session left off:** [`docs/overkill/run_status.md`](docs/overkill/run_status.md)
  (newest entry on top). Live metrics: `python scripts/source_port_status.py`.
- **Known blockers to skip (verify before trusting; some entries are dated):**
  [`docs/overkill/loop_blockers.md`](docs/overkill/loop_blockers.md).

## Run the autonomous endgame loop
This repo has a `/goal` slash command (`.claude/commands/goal.md`) that launches the long-haul loop
toward the VM-less port. Use `/loop /goal` for an indefinite self-continuing run, or `/goal` once.
It reads the brief above and works one verified slice at a time.

## Non-negotiable invariants (also in the brief §3)
- **Never commit red** — every commit is preceded by a green `python -m pytest -q`
  (~1183 passed / 23 skipped as of 2026-07-04).
- **Check for an existing mechanism before building one.** This repo already ported several pre2
  patterns that later sessions nearly rebuilt. The standing-mechanisms list at the TOP of
  `run_status.md` is the registry — read it before writing any new tooling, harness, or metadata
  system, and add to it when you land one.
- **One verified slice = one focused commit + push to `main`** (this repo commits to `main`; small,
  frequent, self-contained).
- **Never weaken an oracle/test/assertion to make a slice pass.** The byte-exact proof is the value.
- **Failed attempt ⇒ full revert + a repro line in `loop_blockers.md`.** Never leave a half-applied change.
- **Fail loud, never fake a gap.** If the native path needs state the recovered layer lacks, recover it
  at the ASM boundary first (shadow → verified hook → pure system) — do not approximate it in the runtime.
- **`domain/` and `systems/` stay VM-free** (no cpu/mem/dos_re/hooks/offsets); enforced by
  `scripts/audit_recovered_layers.py`, `scripts/audit_architecture.py`, `scripts/lint.py`.

## Where things stand (2026-07-04, evening) — INTEGRATION phase

**Leaf recovery is DRY; the port is an integration project.** The whole movement/collision/decision
surface, the render compose, and the front-end menu LOGIC are pure + verified; what remains is
wiring recovered pieces into the native runtime plus a few unrecovered subsystems. Pure game-logic
mass ≈ 32.9%. **The current, single-authority frontier statement lives at the top of
[`run_status.md`](docs/overkill/run_status.md)** — trust it over any older phrasing (including in
the `/goal` brief's bucket list, which is updated less often).

- **The spine is [`overkill/native_app.py`](overkill/native_app.py)** — the recovered top-level flow,
  `GAMEPLAY_FRAME_STAGES` (the `1010:97B2` call order, each stage tagged native/host/gap/unmonitored),
  and `describe_gaps()`. **Read it first for structure.**
- **`scripts/play_native.py` is the product** (a real VM-less standalone): cold level boot with NO
  snapshot, the real composed frame (byte-exact vs the VM page), movement + firing. It is not yet a
  GAME: no enemies, no level end/death, no HUD, no menu flow.
- **Why no enemies (the key structural fact):** the per-frame object BEHAVIOR WALK
  (`1010:A9DD..AA2A`) dispatches each active record through the type table (`CS:AA36`, key `+0x16`)
  then the 149-entry behavior table (`CS:EFC4`, key `+0x18` = `OFF_LOGIC_ID`) into per-behavior
  state machines (the "zoo") — cold-loadable maps via `adapters/behavior_dispatch_adapter`, handler
  bodies mostly unrecovered. The wave driver is PLANET-KEYED (`B556`): planet 0 (cold boot) = the
  `B4A2` leader-group family; the earlier "formation wave" recovery is planet 3's family only.
- **Genuinely open:** the behavior zoo (start with planet 0's leader group), the `9734/9902/9908`
  transition continuations (mostly compositions of recovered pieces), the level-select cursor render
  + menu-flow wiring, HUD wiring, scene-content, endings, audio.
