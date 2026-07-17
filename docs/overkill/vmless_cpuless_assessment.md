# DOS_RE 2.0 automatic-recovery assessment — OVERKILL

**Date:** 2026-07-17. **Reproduce:** `python scripts/probe_vmless_cpuless.py` (all artifacts
gitignored + regeneratable). **Reference:** [`dos_re/docs/dos_re_2.0.md`](../../dos_re/docs/dos_re_2.0.md),
[`recovery_ir.md`](../../dos_re/docs/recovery_ir.md), [`migration_1.0_to_2.0.md`](../../dos_re/docs/migration_1.0_to_2.0.md).

## The endgame (owner-clarified 2026-07-17k) — NOT just the observed closure

The observed demo closure (view A) proves ONE exercised product path is fully CPUless. It is the finite
path to the first hard wall — **not** the completion criterion. The real endgame is a **fully classified,
preferably fully CPUless binary** that materially expands `dos_re` and provides complete evidence for the
memoryless conversion. The desired model:

- every discovered function has a generated CPUless identity; the generated implementation is the DEFAULT;
- a manual body may OVERRIDE at the same address (`impl = manual_overrides.get(addr, generated[addr])`) —
  same identity, recorded reason, generated version kept for differential; NOT a separate carrier-touching
  adapter world;
- generated + manual compose directly in ONE CPUless call graph; never a silent interpreter fallback;
  unsupported functions fail loud and stay measurable work items.

**Two views are maintained** (`scripts/probe_vmless_cpuless.py` + `verify_cpuless.py --demo` = A;
`scripts/cpuless_census_view.py` = B):

- **A. Observed runtime closure** — functions executed by each demo, byte-exact PASS/DIVERGED/INCONCLUSIVE,
  closure completeness, hard CPUless wall. The strongest *behavioral* correctness gate.
- **B. Binary-wide CPUless census** — EVERY discovered function classified (auto-cpuless / manual-override /
  platform-replacement / blocked-shape / blocked-dispatch / blocked-cascade / boundary-loop / likely-data /
  unclassified) with per-fn metadata (exits, direct/indirect callees, refusal, reachability). *Not observed
  ≠ dead.* Next capabilities are chosen by BOTH: observed-closure unblock AND whole-binary unblock +
  `dos_re` reusability, preferring generic emitter/analysis (frame-shape, control-flow, indirect-dispatch,
  register-indirect capture, resume-address closure, call composition) over per-game glue.

Sequence: (1) ✅ dispatch capture↔close fixpoint; (2) ✅ latest `dos_re`; (3) close the observed wall +
`play_cpuless.py` [next]; (4) keep expanding GENERIC CPUless support binary-wide; (5) complete binary-wide
classification; (6) ABI recovery + memory-authority migration (the per-fn metadata is the bridge).

**Latest (dos_re `aa6162b`, converged graph):** census **626** · VMless **622/626** (wall HOLDS) ·
CPUless **561/626** · recovered-purity wall **HOLDS**. **View B:** 561 auto-cpuless · 33 blocked-cascade ·
28 blocked-shape (capability queue: tail-dispatch 16, boundary-head 10, sp-as-data 2) · 4 likely-data;
429/626 reachable from the runtime roots (197 unobserved, not dead).

### Register-indirect resolution promoted into dos_re proper (2026-07-17l)

The near-indirect target resolver — the interpreter-faithful EA computation that turns a trapped
`jmp/call [ea]` **or** register-indirect `call ax` into its concrete `CS:IP` target — now lives in
`dos_re/dos_re/lift/dispatch.py` (`resolve_near_indirect_target(state, mem, inst)`), a PURE function
(no CPU-state mutation, unlike `decode_ea` which fetches the displacement). It is the single source
of truth every port's dispatch-capture probe shares; `scripts/capture_indirect_sites.py` now imports
it instead of a private copy. Covered by `dos_re/tests/test_lift_dispatch.py` — 7 tests that
CROSS-CHECK the resolver against the interpreter (`step()` and require the predicted target to equal
where the CPU lands) across register-indirect, `[disp16]`, `[bx+table]`, BP→SS-default, and
seg-override forms. This is the reusable half of the "capture↔close fixpoint" graph-completeness work.

### The memoryless-bridge metadata (step 6 prep, 2026-07-17l)

View B now carries, for **every** discovered function, the machine-readable ABI record the
DOS-layout-less stage consumes (`abi` in `cpuless_census_view.json`, from `register_effects` over the
reconstructed scan): `regs_read` / `regs_written` (MAY sets — the promoter computes the strict live-in
for auto-cpuless fns; this covers all 626 uniformly), `reads_mem`/`writes_mem`/`port_io`,
`global_reads`/`global_writes` (the **fixed DGROUP cells** each function depends on — `seg:offset` of
every direct `mod0/rm6` + moffs operand, the discrete global-state edges the memory-authority migration
must bind), `uses_bp_frame`, and `callees_indirect` (observed-dispatch targets). **622/626** carry a
clean record (the 4 gaps are the non-liftable `likely-data` — they fail loud with the decode reason,
never a silent zero); **480** touch fixed global cells. Spot-checks confirm fidelity: `5827` reads
`cs:95BC` (the video-mode selector) with indirect callee `587E`; `C85B` flags ints 13h+21h; `5F61`
names its frame-clock cells (`ds:2324‥2342`).

### Tail-dispatch capability — evidence-backed design (the next generic pass, step 4)

The 16 tail-dispatch refusals are **two distinct compiler shapes**, not one, and the fix differs. The
evidence key is the *jmp IP* (`indirect_sites.json`), not the function entry:

1. **Intra-function computed goto** (e.g. `4E26` @ `4E56`: a `jmp rm16` inside a loop, with a normal
   `ret` tail). The refusal `tail-dispatch-at-nonzero-depth` misfires because `_check_stack_depths`
   treats *any* `JMP_IND` as a tail exit demanding depth 0. Correct model: when the jmp's evidence
   targets are all **within the function's own IP range**, it is an internal multi-way branch at the
   jmp's depth — follow the landings as internal edges, don't refuse. **Gating rule (non-negotiable,
   per the manifest's no-guess-on-indirect-tables law):** only with *observed* targets. `4E56` has
   **no evidence** (demos never hit it) → it MUST stay refused (fail-loud, a coverage work item), never
   statically guessed.
2. **Tail-call to a separate stack-arg-consuming function** (`5827` @ `582F`: `push cx; mov bx,cs:[95BC];
   jmp cs:[bx+table]` → `587E`, a *separate* function that pops the pushed `cx` and rets to `5827`'s
   caller). Refusal `tail-dispatch-with-unbalanced-stack`. Correct model: a `JMP_IND` at depth *d* whose
   evidence callees each consume *d* bytes composes as a tail call — the dispatcher's live-out is the
   callee's, and the pushed args are the callee's stack parameters (the manifest's stack-arg ABI). The
   handlers (`587E`, …) themselves promote as stack-arg functions.

Both need the per-site targets threaded from `indirect_sites.json` through `cfg`/promoter/emitter (a
multi-part `dos_re` change spanning cfg-scan, depth-walk, flag-pass, emit) and validation via the
demo-driven differential (`verify_cpuless.py --demo`). **9 of 16 are observed-reachable**, so this
serves BOTH criteria. Scoped as its own focused pass; not attempted blind. Functions without dispatch
evidence stay measurable coverage items.

## TL;DR (historical passes)

The dos_re 2.0 automatic pipeline runs on OVERKILL's binary **with no hand-lifting**. Three passes so
far, each driving a real dos_re capability and/or a recovery fact:

| stage | initial (07-17) | + closure (07-17c) | + DAA (07-17d) | + dispatch-closure (07-17g) |
|---|---|---|---|---|
| census entries | 335 | 512 | 512 | **619** |
| **VMless liftable** (M2) | 322 / 335 | 508 / 512 | 508 / 512 | **615 / 619** |
| **VMless wall** | HOLDS | 1 violation | HOLDS | **HOLDS** |
| **CPUless recovered-purity wall** | — | — | — | **HOLDS** (AST-proven) |
| **CPUless promotable** (M3) | 204 / 335 | 438 / 512 | 451 / 512 | **554 / 619** |
| **recovered fns proven byte-exact** | — | — | — | **29 PASS / 0 DIVERGED** |

The **census closure** (pass 3) is the dominant lever: the observed-execution entry list missed 177
statically-reachable functions, and every caller of a missing callee refused `contains-call`. Closing
the static call graph to a fixpoint ([`scripts/close_census.py`](../../scripts/close_census.py)) took
CPUless from 204 to **438** and collapsed the cascade from 114 to 44 — and honestly surfaced the real
remaining gaps (a DAA opcode, more tail-dispatch variants) that observation coverage had hidden.

**The real M3 metric is the RUNTIME CLOSURE from the gameplay root, not the whole-census count**
(manifest M3). From `1010:97B2`: **250 functions reachable, 228 promoted, a 22-function frontier**
gated on just **~6 real root gaps** — most tail-dispatch functions (presenter/loader) aren't even on
the gameplay path. **And the automatic lift is now oracle-VALIDATED, not just structural:** `liftverify`
proved a slice of hot gameplay functions (input poll `0162`, coord helper `5A00`, …) **byte-exact vs the
interpreted oracle**, and caught `0679` (the frame timer wait) DIVERGING — correctly, it's an env-wait
(§E), which matches overkill's own `input_waits.py`.

This validates the manifest's core claim on a *second* game: overkill is a training/validation corpus
for the recovery machine, has driven **three dos_re lifter capabilities upstream** (§A, §B′, §D2) plus
the census-closure pipeline step, and now has an oracle-validation loop.

**Reproduce the whole thing:** `python scripts/probe_vmless_cpuless.py` (closes the census, emits the
VMless corpus, runs the CPUless promoter, measures the gameplay runtime closure, prints the scorecard).
All artifacts gitignored + regenerated.

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

### D2. DAA opcode — ✅ RESOLVED (2026-07-17d)

`1010:5F0D` uses `0x27` **DAA** (decimal-adjust after BCD add — score/BCD code). It was decoded +
interpreted but not lifted: VMless fell back to `interp_one` (the sole wall violation) and CPUless
refused `unanalyzed-opcode-27`. Fixed upstream (dos_re `ca50aee`): `CPU8086.daa()` is the single source
of truth (interpreter calls it, VMless emits `cpu.daa()`); CPUless gets `register_effects` (reads/writes
AX), the flag-def + flag-read tables, and an inline flag-exact `_translate` — tested against the
interpreter across **all 1024 (AL, CF, AF) inputs**. **Result: VMless wall HOLDS again; CPUless 438 →
451.** (Only DAA was needed; DAS/AAA/AAS aren't in the interpreter — the game doesn't use them, so they
stay fail-loud.)

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

### E. Env-wait spin loops — `0679` / `50C9` (oracle-caught; recovery fact recorded, 2026-07-17e)

`liftverify` (the M2 byte-exact gate) proved a hot-gameplay slice correct against the oracle AND flagged
`1010:0679` **DIVERGED** — the gameplay frame timer wait (`cmp cs:[066B],0; jz 0679; ret`, spins until
the timer ISR sets `066B`). A plain lift freezes a timing-dependent iteration count; this is the
manifest's env-wait FRONTIER, not a lifter bug. Recorded as a recovery fact
([`artifacts/lift_keep_interpreted.txt`](../../artifacts/lift_keep_interpreted.txt): `0679` + the `50C9`
retrace wait, matching `input_waits.py`), threaded through irgen as `platform_effect=env_wait`. The
runtime installer keeps them interpreted (the enumerated fail-loud frontier) until they are modelled as
explicit scheduler-yield boundaries in the standalone runtime.

## The cascade & the GAMEPLAY closure

`refused: contains-call` = would promote but a (transitive) callee is still unpromoted — the DAG shadow
of the hard frontier. Whole-census: 114 → 44 (closure) → **31** (DAA). But the metric that matters is the
**gameplay runtime closure** (`scripts/probe_vmless_cpuless.py` stage 4, root `1010:97B2`): **228 / 250
reached-and-promoted**, a **22-function frontier**, of which the real root gaps are only:
`tail-dispatch` ×3 (`4E26 580B CC4F`), `sp-as-data` ×1 (`0111`), `ir-not-liftable` ×1 (`0248`, SMC),
`vectored-int-call` ×1 (`C85B`) — plus `97B2`/`9B2E` waiting on them and a 15-fn cascade below.

## Oracle validation (the M2 down-payment) — 2026-07-17f

`liftverify` (the byte-exact M2 gate) over a 40-function hot-gameplay slice from the L1 snapshot:
**12 ORACLE_PASSING** (byte-exact vs the interpreted oracle: `0162 0672 073C 4CED 4D15 4D64 4FF9 505B
5073 511F 5160 518C`), **1 DIVERGED** (`0679`, the env-wait — §E, correctly), 0 INCONCLUSIVE, the rest
`notreach` (an idle level-start forward run doesn't exercise event-driven paths — unproven, not
disproven). **Finding: every gameplay function that actually executes verifies byte-exact — the
automatic lift is provably correct on real running code, not just structurally emittable.** Reaching the
`notreach` set needs a demo-DRIVEN run (the standalone/acceptance harness), not a static snapshot.

## The remaining gaps are all deep — the enabler is the acceptance harness

Every one of the ~6 gameplay-frontier root gaps was investigated this pass and is genuinely
non-trivial; none is a clean drop-in, and — critically — **none can be validated correct without a
standalone demo-oracle run**, so rushing any of them risks a silently-wrong de-carrier:

- **Tail-dispatch `4E26 580B CC4F` (intra-function jump tables).** Confirmed by reading the table:
  `5827`'s `jmp cs:[bx+5834]` (bx = `CS:[95BC]`*2, the video mode) lands at `583A`/`5852`/`587E` — three
  mode-specific blocks *inside the function*, each popping the pushed param. `_gate_dyn_evidence`
  already accepts intra-function jump-table landings, **but `_check_stack_depths` seeds every dispatch
  target at depth 0 (the external-arrival model) and refuses the `JMP_IND` at nonzero depth** — the
  landings are actually reached at the jmp's depth *d*. The fix must thread per-site evidence through
  the depth walk + flag pass + seeding to follow intra-function landings at depth *d* (distinct from
  external depth-0 arrivals). Deep; correctness needs the standalone.
- **`sp-as-data 0111`** — a `ret` function whose `jnz;jmp 0001` tail makes its scan span a *second*
  function (`0001`); the shared-tail depth is what trips `sp-as-data`.
- **`vectored-int-call C85B`** — ✅ RESOLVED (dos_re `489188a`): `int 13h` (disk BIOS, a dead
  copy-protection path) now joins `PLATFORM_INT`; the function promotes on its live paths and
  `plat.intr(0x13)` fails loud if ever reached (matching the interpreter, which can't run it either).
  Generic — every DOS game with disk save/load/copy-protection inherits it. +1 test.
- **`ir-not-liftable 0248 / 3EFC`** — runtime-patched (SMC): the snapshot bytes decode to different
  *lengths* than the interpreter executes (`decoder-mismatch`, not operand-immediate patches), so the
  de-SMC promotion (`268eea9`) doesn't apply. Needs a **pre-patch code-authority snapshot** for these
  regions or a hand-hook — an overkill-specific recovery-facts issue, not a generic capability.

### GAMEPLAY-FRONTIER LEVERAGE (2026-07-17h) — why the frame loop needs 3 gaps at once

Per-function dependency analysis of the 21-fn gameplay frontier (each `contains-call` fn unblocks only
when ALL its real-gap deps clear): **`9B2E` (→ the frame loop, via `4DBF` level re-init → the file/disk
I/O cluster) depends on ALL THREE of SMC `0248` + tail-dispatch + vectored-int `C85B`**; the 7-fn
`0Bxx/0Cxx/C679/D390` I/O cluster depends on `0248` + `C85B`. So no single fix opens the frame loop —
`C85B` (done) is one of three. Remaining for `9B2E`: the `0248` SMC snapshot + the tail-dispatch
depth-walk capability + the `97B2` boundary-head (which itself waits on `9B2E`).

## Current scorecard & remaining order

VMless **615 / 619** (wall HOLDS) · CPUless whole-census **555 / 619** · **gameplay closure 229 / 250**
(frontier 21) · recovered-purity wall HOLDS · 29 hot fns proven byte-exact (0 DIVERGED). Landed dos_re
capabilities: **(A)** boundary-head loop `a2ca7aa` · **(B′)** boundary-head-on-call `13ce724` · **(D2)**
DAA `ca50aee` · **(INT13)** disk-int platform effect `489188a`; plus the census closure, dispatch
closure, env-wait fact, the CPUless wall + the `verify_cpuless` differential.

**Next = the standalone `acceptance_cpuless` demo-oracle gate**, not more isolated de-carrier surgery.
It is the enabler, not just the finish line: it (1) validates the 228 promoted gameplay functions
byte-exact *together* over the demo (reaching the `notreach` set), and (2) gives the correctness gate
needed to land the deep tail-dispatch/sp-as-data capabilities *safely*. Build order: platform runtime +
boundary scheduler → dispatch/HANDLERS registries + per-site dyn-evidence → replay the demo standalone
vs the oracle, masked byte-exact per boundary. Then the deep gaps land with a real gate under them.

**Broad demo-driven validation + REGISTER-indirect dispatch capture (2026-07-17j).**
Running the demo-driven differential over the whole plat-free set: **L1 gameplay 161 PASS / 0 DIVERGED**;
**cold-start 286 PASS / 1 DIVERGED**.  The one divergence was another graph-completeness gap:
`837A`'s `call ax` (a REGISTER-indirect computed function pointer) dispatched to `83D7`, which was never
in the graph — `scripts/capture_indirect_sites.py` only computed MEMORY-indirect targets and skipped
register-indirect ones.  Fixed: the capture now reads the register value for a `mod==3` indirect
(`call ax` → the target IS `ax`).  Re-capture → re-close: census **619 → 625**, CPUless **555 → 560**,
`83D7` promoted.  The demo-driven differential is proving itself the right gate — each pass either
validates byte-exact or names a concrete completeness gap.

**DEMO-DRIVEN differential caught a real codegen bug in the object walk (2026-07-17i).**
`scripts/verify_cpuless.py --demo` validates each fn from its REAL execution state (replays the demo,
captures each fn's live pre-state, diffs the adapter vs the ref VM's actual run) — no random wandering,
so it exercises the dynamic-dispatch fns the random mode filtered out. It immediately caught **13
object-walk/behavior dispatchers** (`A940` & callees) raising `NameError: name 'cs' is not defined`:
the dispatch-SELECTOR read `mov reg, cs:[bx+disp]` bypasses the ABI input pass, so `cs` was neither
param nor local. **Fixed upstream (dos_re `300c24d`):** CS is the function's fixed code segment — a
compile-time constant, never a runtime input; `register_effects` never adds it, `emit_recovered` always
materialises `cs = 0x<seg>` as a local. **After: 58 PASS / 0 DIVERGED byte-exact from real states.** A
silent correctness bug that "555 promotable" hid — exactly what the function differential is for. The
demo-driven differential is now the primary correctness gate (candidate to generalize into dos_re).

**The CPUless HARD WALL + the correctness gate + graph completion (2026-07-17g).**
- **CPUless recovered-purity wall INSTALLED + HOLDS** (`dos_re/tools/lint_cpuless.py`, wired as probe
  stage 5): a static AST proof that **every** recovered module imports nothing but sibling recovered
  modules — never the CPU carrier, the interpreter, the lifted graph, or the adapters. The recovered
  *code* is provably cpuless. (The *runner-closure* half of the wall waits on a `play_cpuless.py`.)
- **Correctness gate built: the per-function DIFFERENTIAL** ([`scripts/verify_cpuless.py`](../../scripts/verify_cpuless.py)) —
  the manifest's "function differential" dos_re lacked. It runs the generated CPU-ABI adapter (which calls
  the pure recovered body) vs INTERPRETING the original bytes, over randomized state, and diffs the full
  register file + memory. **29 PASS byte-exact / 0 DIVERGED** on the pure-compute set — the first proof
  the recovered functions *compute* what the CPU does, not merely emit. (Random state → many INCONCLUSIVE
  wanderings; reaching those needs demo-captured pre-states, i.e. the standalone. Candidate to generalize
  into dos_re.)
- **Graph completed via DYNAMIC-DISPATCH closure.** The differential exposed that `close_census.py`
  followed only near/far CALL targets, so dispatch-only targets (`5A00 → 3103`, the whole `AFxx`
  handler cluster) were missing from the graph entirely. Feeding the captured `indirect_sites.json`
  targets into the closure took the census **512 → 619**, VMless **508 → 615**, CPUless **451 → 554**,
  and the Tandy coordinate/handler targets (`3103`, `30D2`, …) are now promoted (the EGA-only `32AC` is
  dead in Tandy, never observed — correctly absent).

**Groundwork landed (2026-07-17f): per-site dynamic-dispatch evidence.**
[`scripts/capture_indirect_sites.py`](../../scripts/capture_indirect_sites.py) runs the demo(s) through
the ref VM, traps all 87 near-indirect sites in the graph, and records each resolved target →
`indirect_sites.json` (the `--dyn-evidence` input the promoter's DISPATCH registry *and* the future
standalone runtime consume; wired into the probe's promote stage, used when present). Two findings:
(1) it lifted the resolved dispatch registry 393 → 406 selectors; (2) it **empirically confirmed the
tail-dispatch gap is a depth-walk CAPABILITY, not an evidence gap** — feeding the evidence left the
count at 451 (the `tail-dispatch-at-nonzero-depth` refusal fires in `_check_stack_depths` *before*
dispatch resolution). It also showed several dispatch sites (e.g. `5827`'s EGA path) are **never taken
in Tandy gameplay** — dead selectors that promote optimistically.

## What this does NOT change today

The shipped runtime is untouched — this is a measurement track. `play_native` still runs the
hand-recovered `native_frame.py` lockstep frame. The 2.0 pipeline is the *parallel automatic route*;
adopting it as the runtime is a later decision (the manifest even allows keeping the hand-recovered
frame as a verified projection). Nothing here hand-edits generated output or weakens an oracle.
