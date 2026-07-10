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
- **THE OPERATING MODEL — campaigns (pick ONE, drive it to done):**
  [`docs/overkill/campaigns/README.md`](docs/overkill/campaigns/README.md) — the roadmap, the rules
  (done includes hook retirement; no re-banking plans), and ADR-1 (the DGROUP image IS the game
  state; `NativeGameState` is a render projection).
- **The journal (what happened, newest on top):** [`docs/overkill/run_status.md`](docs/overkill/run_status.md).
  Live metrics: `python scripts/source_port_status.py`.
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

## Where things stand (2026-07-07) — the DEMO-LOCKSTEP phase

**The operating truth lives in [`campaigns/demo_lockstep.md`](docs/overkill/campaigns/demo_lockstep.md)
(THE active campaign) and the TOP HEADER of [`run_status.md`](docs/overkill/run_status.md) — trust
those over anything below or in older docs.**

- **The method** (= `D:\Games\DOS\dos_re`'s canonical done-definition): the native port must replay
  the demo corpus with the VM disabled and match frame-and-state, byte-exact, every frame.  The
  instrument is `overkill/probes/verify_native_lockstep.py`: the pure VM is snapshotted at every
  `1010:9B2E` frame boundary of a recorded demo; the ONE native frame implementation
  (`overkill/native_frame.py: advance_gameplay_frame_97b2`) runs over the same pre-state; the whole
  DGROUP is diffed.  The first divergent cell names the next recovery.  No seams, no approximations:
  unrecovered stages fail loud and are the reported frontier.
- **The OBJECT WALK (every enemy/actor/pickup state machine) is fully native and dry** for the L1,
  L2 and L3 demos (zero divergence, zero gaps); L4 has a small named residue.  The lockstep frame
  additionally owns: input (from the image's own INT9 key table), the player move handlers, the
  death tail, the A66F scroll (tile cues + the level script run INSIDE the row pull), the A067 fire
  path, the A940 state update, the 5F61 frame clock, the 0922 starfield and the D50E sound engine.
- **`scripts/play_native.py` runs the gate-verified frame fn over the image** (2026-07-10: the old
  hybrid loop — dataclass game + sync bridges — is DELETED, see deprecated_or_quarantined.md; never
  rebuild it).  Charter step 2 is still open: `--demo <name> --mirror` (replay a recorded demo in
  the app with live state/pixel divergence flagging).  The lockstep gate remains the byte-exact
  evidence; `verify_play_native_frame` gates the app wiring.
- **Genuinely open** (ordered in the charter): the 4CED star-list mid-present occupancy, the 23A0
  flash decay (recipe journaled), the 77C5 shield body, the 9EE4 drain, the app unification, then
  the L4/L5 walk residue, transitions/menu/endings, audio (the D50E DGROUP model is done; the host
  sound output isn't).
