# CLAUDE.md — OVERKILL VM-less source-port

Evidence-driven reverse-engineering + native source port of the DOS game **OVERKILL: The Six-Planet
Mega Blast**. The endgame is a **fully-playable, VM-less, cold-booting** native game (intro → menu →
levels → ending) with the original binary kept only as an optional verification oracle.

## Start here
- **Conventions, layer rules, working principles:** [`AGENTS.md`](AGENTS.md) (read this first).
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
  (~1057 passed / 23 skipped as of 2026-07-03).
- **One verified slice = one focused commit + push to `main`** (this repo commits to `main`; small,
  frequent, self-contained).
- **Never weaken an oracle/test/assertion to make a slice pass.** The byte-exact proof is the value.
- **Failed attempt ⇒ full revert + a repro line in `loop_blockers.md`.** Never leave a half-applied change.
- **Fail loud, never fake a gap.** If the native path needs state the recovered layer lacks, recover it
  at the ASM boundary first (shadow → verified hook → pure system) — do not approximate it in the runtime.
- **`domain/` and `systems/` stay VM-free** (no cpu/mem/dos_re/hooks/offsets); enforced by
  `scripts/audit_recovered_layers.py`, `scripts/audit_architecture.py`, `scripts/lint.py`.

## Where things stand (2026-07-03)
Gameplay-frame mechanics are native + produced-vs-VM verified: input decode, player movement,
world-scroll (`A66F`/`A6FE`), the whole object pass. Pure game-logic mass ≈ 30.2% and climbing. The
`B73E`/logic-id-0x20 wall and the object-behavior/collision veins are recovered. Genuinely still open:
`99F6` scripted-input, `A212` view-anchor, the render-layer **backend wiring** (starfield + HUD are
recovered but not yet composed into `--backend native`), front-end flow, native asset/level load, and
audio drivers. See the brief §6 for the prioritized queue.
