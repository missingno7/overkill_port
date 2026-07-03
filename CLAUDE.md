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
  (~1132 passed / 23 skipped as of 2026-07-04).
- **One verified slice = one focused commit + push to `main`** (this repo commits to `main`; small,
  frequent, self-contained).
- **Never weaken an oracle/test/assertion to make a slice pass.** The byte-exact proof is the value.
- **Failed attempt ⇒ full revert + a repro line in `loop_blockers.md`.** Never leave a half-applied change.
- **Fail loud, never fake a gap.** If the native path needs state the recovered layer lacks, recover it
  at the ASM boundary first (shadow → verified hook → pure system) — do not approximate it in the runtime.
- **`domain/` and `systems/` stay VM-free** (no cpu/mem/dos_re/hooks/offsets); enforced by
  `scripts/audit_recovered_layers.py`, `scripts/audit_architecture.py`, `scripts/lint.py`.

## Where things stand (2026-07-04) — STRUCTURE-FIRST phase

**The phase has shifted from "hook individual routines" to "recover the game's high-level design."**
The decision-leaf well is essentially dry: the whole movement/collision/behavior *decision* surface is
already pure and byte-exact; what remains VM-coupled is *orchestration* (frame flow, mode transitions,
scene machine), and that only shrinks by growing the **native runtime**, not by more leaf extraction.
Pure game-logic mass ≈ 30.5%.

- **The spine is [`overkill/native_app.py`](overkill/native_app.py)** — the VM-less application
  skeleton: the recovered top-level flow (boot → title → attract → level → gameplay → transitions),
  `GAMEPLAY_FRAME_STAGES` (the real `1010:97B2` call order, each stage tagged native/host/gap/
  unmonitored), and the fail-loud gap markers `RecoveryGap`/`UnmonitoredGap`
  ([`recovered/domain/gaps.py`](overkill/recovered/domain/gaps.py)). `describe_gaps()` lists every
  declared gap. **This is the map of what's recovered vs missing — read it first for structure.**
- **Native + verified:** input decode, player movement, world-scroll (`A66F`/`A6FE`), the whole object
  pass; the **full object→sprite draw** (all 3 routines/compositors/banks, byte-exact vs the VM page,
  0 diff) and the **parallax starfield** are wired into `play_native.py` — it renders the **real
  gameplay frame** (ship+flames+enemies+starfield), NOT a placeholder. The **attract scene machine**
  (`1010:D007`) is demo-witnessed end-to-end. `scripts/play.py`'s old hybrid `--backend native` is
  removed.
- **Recovered-not-yet-wired:** the HUD panel composers (chrome/counters/score exist + verified, not
  folded into the standalone); the **gameplay-exit transition rules** (`A344`/`A346`/`A342` — scripted
  transition / death tail / game-over, pure in `systems/frame_loop.py`) — the native loop can't yet
  *end a level* because `NativeGameState` doesn't carry `A47C`/`2326`/`A97A`.
- **Genuinely open (fail-loud gaps):** native level-start state (Bucket F — gameplay still needs
  `--snapshot`), `99F6` scripted-input, `A212` view-anchor chain, the `A067` full fan-out / `A970`
  counters, front-end menu logic, scene-content (the `DS:BE18` descriptor table + scene-entry actions),
  and audio drivers.

The next structural slices are in the brief §6 (Bucket C — native runtime); the immediate one is
threading the transition state into `NativeGameState` so the native loop ends a level fail-loudly.
