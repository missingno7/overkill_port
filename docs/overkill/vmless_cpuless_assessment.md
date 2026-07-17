# DOS_RE 2.0 automatic-recovery assessment — OVERKILL

**Date:** 2026-07-17. **Reproduce:** `python scripts/probe_vmless_cpuless.py` (all artifacts
gitignored + regeneratable). **Reference:** [`dos_re/docs/dos_re_2.0.md`](../../dos_re/docs/dos_re_2.0.md),
[`recovery_ir.md`](../../dos_re/docs/recovery_ir.md), [`migration_1.0_to_2.0.md`](../../dos_re/docs/migration_1.0_to_2.0.md).

## TL;DR

The dos_re 2.0 automatic pipeline runs on OVERKILL's binary **with no hand-lifting**. Three passes so
far, each driving a real dos_re capability and/or a recovery fact:

| stage | initial (07-17) | + boundary-head (07-17b) | + census closure (07-17c) |
|---|---|---|---|
| census entries | 335 | 335 | **512** (static closure) |
| **VMless liftable** (M2) | 322 / 335 | 332 / 335 | **508 / 512** |
| **VMless wall** | HOLDS | HOLDS | 1 violation (`5F0D`, DAA — §D) |
| **CPUless promotable** (M3) | 204 / 335 | 204 / 335 | **438 / 512** |

The **census closure** (pass 3) is the dominant lever: the observed-execution entry list missed 177
statically-reachable functions, and every caller of a missing callee refused `contains-call`. Closing
the static call graph to a fixpoint ([`scripts/close_census.py`](../../scripts/close_census.py)) took
CPUless from 204 to **438** and collapsed the cascade from 114 to 44 — and honestly surfaced the real
remaining gaps (a DAA opcode, more tail-dispatch variants) that observation coverage had hidden.

This validates the manifest's core claim on a *second* game: overkill is a training/validation corpus
for the recovery machine, and has already driven **two dos_re lifter capabilities upstream** (§A, §B′)
plus the census-closure pipeline step, with the next gaps (§B, §D) precisely characterized.

**Reproduce the whole thing:** `python scripts/probe_vmless_cpuless.py` (closes the census, emits the
VMless corpus, runs the CPUless promoter, prints the scorecard). All artifacts gitignored + regenerated.

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

### B′. Boundary-head-on-transfer — ✅ RESOLVED as a capability (2026-07-17c)

The CPUless de-carrier refused a boundary head on anything but a `SEQ` (`boundary-head-on-transfer`),
while the VMless emitter accepts a head on a `CALL`. Fixed upstream (dos_re `13ce724`): a head on a
*composed* near/far `CALL` now promotes — the observer fires after the recovered callee returns; an
uncomposed call or a bare transfer still refuses. Three regression tests. **But** the frame loop is
*top-of-DAG* — its boundary is `call 9B2E`, and `9B2E`'s own subtree is still blocked deeper (see §B),
so the 10 frame-loop functions stay `boundary-head-on-transfer`-refused until `9B2E` promotes. The
capability is done; the demonstration waits on the cascade below it.

### D. Census closure — ✅ the dominant CPUless lever (2026-07-17c)

The single biggest finding. The observed-execution census (335 entries) missed **177 statically-
reachable functions** (e.g. `50C9` calls `C9F1`/`CA02`, neither ever listed), so every caller of a
missing callee refused `contains-call` — that, not any single opcode, was ~110 of the 114 cascade.
[`scripts/close_census.py`](../../scripts/close_census.py) closes the static call graph to a fixpoint
(seed → irgen → add every near/far call target → repeat; 335 → 431 → 478 → 503 → 509 → **512**). Result:
**VMless 332 → 508 liftable, CPUless 204 → 438 promotable, cascade 114 → 44.** This is the 2.0 principle
in action — *discover the reachable graph, don't depend on observation coverage.* Candidate to promote
into dos_re proper (generic, like `codemap`); lives as a port script for now.

### B. Tail-dispatch (nonzero-depth + unbalanced-stack) — 12 functions (the deepest CPUless gap)

The census closure widened this family: **`tail-dispatch-at-nonzero-depth`** (`4E26 580B 5827 AED8
CC4F CC7F CD68`) and **`tail-dispatch-with-unbalanced-stack`** (`CCAA CCC4 CCF0 CD8D CDAA`) — all
**video-mode jump-table dispatchers** (`JMP [table + mode*2]`) reached with a non-empty / unbalanced
stack. The de-carrier resolves an indirect tail dispatch only at statically-provable depth 0. Notable:
`CC7F`/`CD68` are the dirty-cell presenter loop; `4E26` the loading tile-remap. **The contribution:**
teach `lift/cpuless.py`+`lift/emit_cpuless.py` to model a jump-table tail dispatch at statically-known
nonzero depth (it is stack discipline — the depth is known — not `sp`-as-data). This is the deepest of
the remaining gaps and gates `9B2E` → the frame loop; a focused capability + test, all games inherit it.

### D2. Unhandled BCD/misc opcodes — `5F0D` (DAA), the one VMless-WALL violation

The closure surfaced `1010:5F0D`, which uses `0x27` **DAA** (decimal-adjust after BCD add — score/BCD
code). The interpreter implements it (`cpu.py:1323`) and the decoder names it, but neither emitter
lifts it: VMless falls back to `interp_one` (**the sole wall violation on the closed graph, 4 sites**)
and CPUless refuses `unanalyzed-opcode-27`. Clean, well-scoped fix: port the interpreter's flag-exact
DAA into `register_effects` + both emitters (and its siblings DAS/AAA/AAS while there), with an
emitted-vs-interpreter test. Restores the wall AND promotes `5F0D`.

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

### C. Census-hygiene — the 4 `ir-not-liftable` (identified, each explained)

`1010:0248 3EFC`, `1C43:0069`, `23AD:0069`:
- **`1C43:0069`, `23AD:0069`** = `overkill_bootstrap_lzexe_main_loop_*` — the **LZEXE self-decompressor**
  loops, in *temporary* segments that only exist during cold-boot self-extraction. Outside the runtime
  graph by design (the 2.0 EXE-independence model runs the loader at *recovery time*). **Fix:** exclude.
- **`1010:3EFC`** (`overkill_strided_row_copy_3efc`) + **`1010:0248`** — **runtime-patched (SMC)**; the
  hooks guard on `_code_matches`, so the snapshot bytes are one patched variant. **Fix:** `desmc-candidate`
  emit or hand-hook, not a frozen lift.

## The 44-function cascade

`refused: contains-call` = would promote but a (transitive) callee is still unpromoted. It is the DAG
shadow of the hard frontier, not an independent gap. The census closure already swept it from 114 to
44; the rest bottoms out on §B tail-dispatch (which gates `9B2E` → the frame loop), §D2 DAA, and the
handful of `sp-as-data` / `vectored-int-call` roots. Re-run `scripts/probe_vmless_cpuless.py` after each
capability lands to watch it shrink — measured, not predicted.

## Current scorecard & remaining order

VMless **508 / 512** (1 wall violation: `5F0D`) · CPUless **438 / 512**. Remaining, each = one regen +
a scorecard delta:

1. ✅ **Boundary-head loop capability (A)** — dos_re `a2ca7aa` + the boundary-head fact.
2. ✅ **Boundary-head-on-transfer (B′)** — dos_re `13ce724` (waits on §B to demonstrate on the frame loop).
3. ✅ **Census closure (D)** — `scripts/close_census.py`; the dominant lever (204 → 438 CPUless).
4. **DAA/BCD opcodes (D2)** — port flag-exact DAA (+DAS/AAA/AAS) into both emitters + `register_effects`.
   Restores the VMless wall and promotes `5F0D`. Smallest next win.
5. **Tail-dispatch nonzero-depth / unbalanced-stack (B)** — the deepest gap; gates `9B2E` → the frame
   loop. Model a jump-table tail dispatch at statically-known nonzero depth.
6. **`sp-as-data` (0111/065C), `vectored-int-call` (C85B), the SMC/LZEXE census entries (C)** — smaller
   focused items.
7. **Re-measure**, then stand up the standalone CPUless runtime against the demo oracle
   (`acceptance_cpuless` pattern) — the byte-exact gate that makes M3 real (the lockstep, CPU-carrier
   removed).

## What this does NOT change today

The shipped runtime is untouched — this is a measurement track. `play_native` still runs the
hand-recovered `native_frame.py` lockstep frame. The 2.0 pipeline is the *parallel automatic route*;
adopting it as the runtime is a later decision (the manifest even allows keeping the hand-recovered
frame as a verified projection). Nothing here hand-edits generated output or weakens an oracle.
