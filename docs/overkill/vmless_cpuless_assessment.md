# DOS_RE 2.0 automatic-recovery assessment — OVERKILL

**Date:** 2026-07-17. **Reproduce:** `python scripts/probe_vmless_cpuless.py` (all artifacts
gitignored + regeneratable). **Reference:** [`dos_re/docs/dos_re_2.0.md`](../../dos_re/docs/dos_re_2.0.md),
[`recovery_ir.md`](../../dos_re/docs/recovery_ir.md), [`migration_1.0_to_2.0.md`](../../dos_re/docs/migration_1.0_to_2.0.md).

## TL;DR

The dos_re 2.0 automatic pipeline (irgen → liftemit → cpuless_promote) runs on OVERKILL's binary
**with no hand-lifting**, and the result is strong:

| stage | result |
|---|---|
| census entries | 335 |
| **VMless liftable** (M2 corpus) | **322 / 335** |
| **VMless wall** (zero `interp_one` sites) | **HOLDS** |
| **CPUless promotable** (M3) | **204 / 335** (fixpoint, 4 rounds) |

So the machine already recovers the overwhelming majority of OVERKILL automatically. What remains is a
**17-function hard frontier** (real capability/fact gaps) plus a **114-function cascade** that the
promotion fixpoint sweeps in as the 17 close. This validates the manifest's core claim on a *second*
game: overkill is now a training/validation corpus for the recovery machine, not just a hand-port.

This is a completely different track from the existing `native_frame.py` demo-lockstep (which
hand-recovers the 97B2 gameplay frame as one pure function). The 2.0 pipeline is the *automatic* route
to the same VMless/CPUless destination — the manifest's whole thesis is "build the machine that ports
the game," and this measures how close overkill already is to that machine.

## The hard frontier (17) — the actual work-list

### A. Boundary-seam `no-exit` — 10 functions (the biggest, most tractable bucket)

`1010:96C5 96C8 9720 97B2 986E 989E 98D8 9908 9921 9928` — the entire **gameplay-frame-loop region**.
irgen refuses them `no-exit`: CFG recovery finds no `ret`/`retf`/`iret` because they run until a
**boundary/wait seam** (the 9B2E frame boundary, input waits) and jump into each other, not back to a
caller. This is *exactly* the VMless frontier the manifest predicts (§3a: "environment-wait loops,
scheduler/boundary seams").

**The fix is a recovery FACT overkill already owns, not a capability gap.** irgen/liftemit/promote all
take `--boundary-heads @FILE`: each listed address emits a boundary event + a RESUME entry, giving the
function a modelled exit. overkill already knows every one of these boundaries — they are encoded today
in [`overkill/input_waits.py`](../../overkill/input_waits.py) and the 9B2E frame boundary the
lockstep gate snapshots at. **Next step:** distil those into a `boundary_heads.txt` recovery fact and
re-run; the 10 should move into the VMless graph, and much of the 114 cascade with them.

### B. Tail-dispatch-at-nonzero-depth — 4 functions (the one genuine dos_re CAPABILITY gap)

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

### C. Misdecode / census-hygiene — 3 entries

`1010:3EFC` (decodes as garbage from that offset — a jump-table target or mid-function address wrongly
listed as an entry), `1C43:0069` and `23AD:0069` (**foreign segments** — overlay/relocated stubs that
don't decode as valid code in a gameplay snapshot). These are stale census entries, not capability
gaps. **Fix:** prune them from the entry census, or record them as `code_as_data` / overlay recovery
facts with the right snapshot.

## The 114-function cascade

`refused: contains-call` = a function that would promote except one of its (transitive) callees is
still unpromoted. It is *not* an independent gap: it is the DAG shadow of the 17. As the boundary-head
fact (A) and the tail-dispatch capability (B) land and the census is cleaned (C), the promotion
fixpoint re-runs and sweeps most of the 114 into `promotable`. The honest unknown is *how much* of the
114 is downstream of A/B/C vs. surfacing a further gap only reachable once these clear — that is
measured by re-running `scripts/probe_vmless_cpuless.py` after each fix, not predicted.

## Recommended order (each step is one gitignored regen + a scorecard delta)

1. **Census hygiene (C)** — cheapest; prune/annotate the 3 misdecodes, re-run, confirm the number.
2. **Boundary-head fact (A)** — distil `input_waits.py` + the 9B2E boundary into `boundary_heads.txt`,
   feed all three tools, re-run; expect the 10 no-exits + a chunk of the 114 to promote.
3. **Tail-dispatch capability (B)** — the upstream dos_re contribution; unblocks the 4 dispatchers and
   their cascade.
4. **Re-measure**, then wire the standalone CPUless runtime against the demo oracle
   (`acceptance_cpuless` pattern) — the byte-exact gate that makes M3 real, the same instrument as the
   existing lockstep but with the CPU carrier removed.

## What this does NOT change today

The shipped runtime is untouched — this is a measurement track. `play_native` still runs the
hand-recovered `native_frame.py` lockstep frame. The 2.0 pipeline is the *parallel automatic route*;
adopting it as the runtime is a later decision (the manifest even allows keeping the hand-recovered
frame as a verified projection). Nothing here hand-edits generated output or weakens an oracle.
