# DOS_RE 2.0 automatic-recovery assessment — OVERKILL

**Date:** 2026-07-17. **Reproduce:** `python scripts/probe_vmless_cpuless.py` (all artifacts
gitignored + regeneratable). **Reference:** [`dos_re/docs/dos_re_2.0.md`](../../dos_re/docs/dos_re_2.0.md),
[`recovery_ir.md`](../../dos_re/docs/recovery_ir.md), [`migration_1.0_to_2.0.md`](../../dos_re/docs/migration_1.0_to_2.0.md).

## TL;DR

The dos_re 2.0 automatic pipeline (irgen → liftemit → cpuless_promote) runs on OVERKILL's binary
**with no hand-lifting**, and the result is strong:

| stage | initial (2026-07-17) | after boundary-head fact + capability |
|---|---|---|
| census entries | 335 | 335 |
| **VMless liftable** (M2 corpus) | 322 / 335 | **332 / 335** |
| **VMless wall** (zero `interp_one` sites) | HOLDS | **HOLDS** |
| **CPUless promotable** (M3) | 204 / 335 | 204 / 335 (see §B′) |

So the machine already recovers the overwhelming majority of OVERKILL automatically. This validates the
manifest's core claim on a *second* game: overkill is now a training/validation corpus for the recovery
machine, not just a hand-port — and it has already **driven one dos_re lifter capability upstream** (§A)
and **surfaced the next one** (§B′).

**Progress this pass (2026-07-17b):** the entire gameplay main loop now lifts (VMless 322 → 332).
overkill's own main loop was refused `no-exit` by a scanner limitation; fixing that in dos_re
(boundary-delimited loops are liftable coroutines, dos_re commit `a2ca7aa`) + declaring one recovery
fact ([`artifacts/lift_boundary_heads.txt`](../../artifacts/lift_boundary_heads.txt)) closed all 10.

This is a completely different track from the existing `native_frame.py` demo-lockstep (which
hand-recovers the 97B2 gameplay frame as one pure function). The 2.0 pipeline is the *automatic* route
to the same VMless/CPUless destination — the manifest's whole thesis is "build the machine that ports
the game," and this measures how close overkill already is to that machine.

## The hard frontier — the actual work-list

### A. Boundary-seam `no-exit` — 10 functions — ✅ RESOLVED (2026-07-17b)

`1010:96C5 96C8 9720 97B2 986E 989E 98D8 9908 9921 9928` — the entire **gameplay-frame-loop region**.
irgen refused them `no-exit`: CFG recovery found no `ret`/`retf`/`iret` because they are the top-level
gameplay loop — an infinite `jmp` cycle that yields one frame at a boundary instead of returning. This
is *exactly* the VMless frontier the manifest predicts (§3a: "environment-wait loops, scheduler/boundary
seams").

**Root cause was a dos_re SCANNER limitation, not just a missing fact.** The boundary-head machinery in
`emit.py` was already present, but `cfg.scan_function` refused `no-exit` *before* it ever ran, so a
game's own main loop was structurally unliftable. Fixed upstream (dos_re `a2ca7aa`): a function whose
only terminating construct is a declared boundary head is a liftable coroutine, not a dead end — with
regression tests, opt-in and byte-identical when no heads are declared. Two-line follow-through in the
IR re-elaborator so `liftemit --from-ir` re-scans identically (heads recovered from the record's own
`boundary_effect` marks — the IR stays the single source of truth).

**The recovery fact** ([`artifacts/lift_boundary_heads.txt`](../../artifacts/lift_boundary_heads.txt)):
one head, `1010:97CB` (the `call 9B2E` per-frame boundary — the same boundary the demo-lockstep gate
snapshots at). Verified: all 10 entries scan into one strongly-connected loop and every one reaches
that call. **Result: VMless 322 → 332, wall still HOLDS**; the emitted `1010:97B2` module is a proper
coroutine (`cpu.boundary_hook(cpu, 0x1010, 0x97CB, 0x97CE)` + exported `RESUME_ENTRIES`).

### B′. Boundary-head-on-transfer — the NEXT dos_re CPUless capability (surfaced 2026-07-17b)

With the frame loop now VMless-liftable, the CPUless de-carrier refuses the same 10 with a *new*
reason: `boundary-head-on-transfer` (`emit_cpuless.py:846`). The VMless emitter accepts a boundary head
on a `SEQ`, `CALL`, `CALL_FAR`, `CALL_IND`, or `INT`; the CPUless emitter accepts it only on a `SEQ`.
Our head is on the frame-boundary `CALL` (`97CB`), which is the *semantically correct* placement (it
matches the lockstep's 9B2E boundary), so the fix is to teach the CPUless emitter to model a boundary
observer + resume around a CALL head — not to relocate the head to dodge the check. This is the next
upstream contribution; until it lands the 10 frame-loop functions stay VMless-only.

### B. Tail-dispatch-at-nonzero-depth — 4 functions (a genuine dos_re CAPABILITY gap)

`1010:4E26 5827 CC7F CD68` — all **video-mode jump-table dispatchers** (`JMP [table + mode*2]` with a
non-empty stack, i.e. a tail dispatch that isn't at a call boundary). The CPUless emitter can already
resolve a near indirect call/jmp through the generated DISPATCH registry when depth is zero, but
refuses when the tail dispatch sits at nonzero stack depth. Notable members: **`CC7F`/`CD68` are the
dirty-cell presenter loop** hand-recovered last session for the blueprint reveal, and **`4E26` is the
loading tile-remap scan** (historically the "hand-decode got the jump table wrong by two bytes" case —
precisely why the automatic dispatch-registry route is preferable).

**This is the contribution to make upstream to dos_re** ("improve the machine with our code"): teach
`lift/cpuless.py` + `lift/emit_cpuless.py` to model a jump-table tail dispatch at nonzero depth (the
depth is statically known; it is stack discipline, not sp-as-data — the same reasoning that already
handles the frameless Borland idiom). A focused dos_re capability + test, and all future games inherit
it. overkill is the corpus that surfaced it.

### C. Census-hygiene — 3 entries (identified, each explained)

Cross-referenced against overkill's own hooks:
- **`1C43:0069`, `23AD:0069`** = `overkill_bootstrap_lzexe_main_loop_*` — the **LZEXE self-decompressor**
  bitstream loops, in *temporary* segments that only exist during cold-boot self-extraction. In a
  gameplay snapshot those segments hold decompressed data, so they decode as garbage. By design they
  are **outside the runtime graph**: the 2.0 EXE-independence model (§1a′) runs the loader at *recovery
  time* to build the data-only boot image. **Fix:** exclude from the runtime census.
- **`1010:3EFC`** = `overkill_strided_row_copy_3efc`, a **runtime-patched (SMC)** row copier — its hook
  guards on `_code_matches`, so the snapshot bytes are one patched variant. **Fix:** a `desmc-candidate`
  (operand-field patch) emit, or keep it a hand-hook — not a plain frozen lift.

## The 114-function cascade

`refused: contains-call` = a function that would promote except one of its (transitive) callees is
still unpromoted. It is *not* an independent gap: it is the DAG shadow of the hard frontier. As the
remaining CPUless capabilities (§B′ boundary-head-on-transfer, §B tail-dispatch) land and the census is
cleaned (§C), the promotion fixpoint re-runs and sweeps the downstream ones into `promotable`. The
honest unknown is *how much* of the 114 is downstream of B′/B/C vs. surfacing a further gap only
reachable once these clear — measured by re-running `scripts/probe_vmless_cpuless.py`, not predicted.

## Current scorecard & remaining order

VMless **332 / 335** (wall HOLDS) · CPUless **204 / 335**. Remaining, each = one regen + a scorecard
delta:

1. ✅ **Boundary-head loop capability (A)** — DONE: dos_re `a2ca7aa` + the boundary-head fact; the
   whole gameplay main loop now VMless-lifts (322 → 332).
2. **Boundary-head-on-transfer (B′)** — the next CPUless capability: model a boundary observer + resume
   around a `CALL` head in `emit_cpuless.py` (the VMless emitter already does). Unblocks the 10
   frame-loop functions for CPUless.
3. **Tail-dispatch-at-nonzero-depth (B)** — model a jump-table tail dispatch at statically-known nonzero
   depth. Unblocks `4E26 5827 CC7F CD68` and their cascade.
4. **Census hygiene (C)** — annotate/exclude the 3: `1C43:0069`/`23AD:0069` are LZEXE boot-loader loops
   (built at recovery time into the data-only boot image, §1a′ — not runtime graph); `1010:3EFC` is
   runtime-patched (SMC) — a `desmc-candidate` or hand-hook, not a plain lift.
5. **Re-measure**, then wire the standalone CPUless runtime against the demo oracle
   (`acceptance_cpuless` pattern) — the byte-exact gate that makes M3 real, the same instrument as the
   existing lockstep but with the CPU carrier removed.

## What this does NOT change today

The shipped runtime is untouched — this is a measurement track. `play_native` still runs the
hand-recovered `native_frame.py` lockstep frame. The 2.0 pipeline is the *parallel automatic route*;
adopting it as the runtime is a later decision (the manifest even allows keeping the hand-recovered
frame as a verified projection). Nothing here hand-edits generated output or weakens an oracle.
