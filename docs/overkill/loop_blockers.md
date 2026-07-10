# Loop blockers — divergences/targets that need the user (or better tooling)

Open items the autonomous loop attempted but could not finish byte-exact. Do NOT
re-attempt these in the loop; they need a reproduction trace and/or gameplay
context. Each has the analysis already done so a human can pick up fast.

## 2026-07-10 — behavior 0x7D / 0x7E: the overlay WAYPOINT-FOLLOWER (1F8F:027A) — reproduced, open

Owner hit `behavior 0x7d (record 23EC) -- no native handler registered` on planet 4 (tick 16, a
common early enemy).  REPRODUCES from a cold planet-4 seed: `build_cold_level_start_image(bundle, 3,
container)` then run `advance_gameplay_frame_97b2` -> gap at tick 16.  EFC4[0x7D] = EFC4[0x7E] = the
step handler `1010:8D4F` = `call far 1F8F:027A ; jmp BC4B` (the postmove BC4B is already recovered via
`_postmove_bc45(with_drift=True)`).  So the body IS the overlay routine `1F8F:027A` + the postmove.

`1F8F:027A` (disasm) is a MULTI-MODE waypoint/formation follower: reads the waypoint pointer si=[A482],
lodsw the next point, sets the seek targets [2306]=pt.x+0x20 / [2304]=pt.y / [2308]=3, calls the 5DB2
seek (via the 8D8B far trampoline, `object_target_seek_step_5db2` -- recovered), checks [230A]
(blocked), then branches on the record's +0x24 MODE (0x13/0x15/0x1C/0x1F/0x7D) -- each mode advances
[A482] by 8 and spawns/handles the next waypoint (0x81F4 alloc via 8D8B, stamp +0x34/+0x32 from the
waypoint list, FFFF-terminated).  It is a whole overlay state machine, not a one-liner.

RECIPE: drive the reproducing planet-4 state one VM frame, trap 8D4F entry + the far-call return 8D54
and the BC4B postmove for record 23EC, capture the DGROUP delta per mode, implement mode-by-mode in
behavior_walk's dispatch (add `elif beh in (0x7D, 0x7E):`), gate each mode.  The overlay far-calls
(1F8F) mean the driven oracle must run the interpreter with the overlay loaded (a demo snapshot that
reaches planet 4, or load the gap-snapshot image into a dos_re runtime).  A multi-slice recovery.

## 2026-07-10 — the 8546 SPECIAL-WEAPON apply families — 6 of 7 FILLED; only 849D open

FILLED byte-exact (commits 779d171, 58ec714, +): 44AF (no-op ret), 84C3 (9F1A deploy -> [A962]/
[A964]), 8463 (9D91 deploy -> [A96E]), 84D6/84FD (flag/sound weapons, [2384]=1/2), 843D/844E (single-
cell flag weapons [A95E]=1 / [A960]=4).  All gated by `verify_native_special_weapon_apply` (14/14, 0
diverging) -- the handlers are LEVELS of the two special weapons (the ladder dispatches on [desc+8]),
so forcing the level in the pure VM's descriptor reaches each.  **STILL OPEN: 849D (9F5F)** -- a
4-slot orbital deploy: `[A364]=2; for bx in [A966,A968,A96A,A96C]: 9F82(bx)` where 9F82 = alloc 74FE +
the 9F41 stamp + `[bx+8]=0x18 [bx+0x0A]=1`, stores the slot into the [A966..] tracker, calls 9FAF
([A39E]=0 ...), and `dec [A364]`.  Reachable as marker 1 lvl 6 / marker 2 lvl 2 in the L6 demo; fill
with the same level-forced oracle (add `(2, 2, "849D")` to `verify_native_special_weapon_apply.CASES`).

## OLD (superseded) — the 8546 families characterization

`native_frame._apply_upgrade_8546` handles the `[A958]` gun-LEVEL stubs (mov [A958],imm; jmp 8430)
but fails loud on the five NON-gun weapon handlers the 95FC descriptors also reach.  Owner hit CS:8463
in play (collected a special weapon, pressed Z).  Disassembled (lindis, static bundle):

* **8463**: `call 9D91 ; jmp 8430`.  9D91 = if `[A96E]==FFFF`: alloc a record via `74FE` (-> bx),
  `[A96E]=bx`, stamp `[bx]=1 [bx+20]=1 [bx+22]=1 [bx+8]=0x0F ...` (deploy a persistent weapon module).
* **849D**: `call 9F5F ; jmp 8430`  (same alloc+stamp shape, different tracker/stamps).
* **84C3**: `call 9F1A ; jmp 8430`.  9F1A -> 9F20 = alloc into the first free of `[A962]`/`[A964]`,
  stamp `[bx]=1 [bx+20]=1 [bx+22]=1 [bx+8]=0x14 [bx+32]=0x50 ...`.
* **84D6**: `mov [BEFE],0 ; if [98C0]: [BEFF]=6 ; [2384]=1 ; jmp 8430`  (a flag/sound weapon, no alloc).
* **44AF**: bare `ret` -- the apply does NOTHING (marker is NOT cleared, so it persists); only 8546's
  own 837A tick + tail run.

The `jmp 8430` tail clears the marker ([95FA]=FFFF) so 8546's tail then fires the [BEFF]=9 apply sound;
44AF (no jmp) leaves the marker set (no sound).  The deploy machinery (74FE alloc + the A962/A964/A96E
trackers) is ALREADY modelled VM-era in `overkill/gameplay/action_spawns.py` (the A067/A3FF anchor
spawn) -- reuse that shape.  RECIPE: play to each weapon (or reuse a reaching snapshot) -> the new
`play_native` gap-snapshot auto-dumps the pre-frame seed -> driven oracle (inject Z at a 9B2E
boundary, run one VM frame, diff DGROUP) -> implement per-target in `_apply_upgrade_8546` -> gate.
Reachable markers in `demo_play_tandy_L6_different_weapons_20260618_225615`: 0->8412 (done), 1/3->44AF,
2->84C3; 8463/849D/84D6 need a snapshot whose descriptors reach them.

## 2026-07-10 (late) — boot-lift coverage is recursion-bounded at 25/54, not stack-bounded

`scripts/verify_boot_lifts.py` verifies 25 of 54 emitted boot hooks byte-exact over a fresh boot and
stops on a Python `RecursionError` (a lifted hook calling a nested lifted hook — the emitted body
Python-calls sub-hooks, so the Python stack mirrors the ASM call depth, which is unbounded in the
boot's asset-load loop).  Raising `sys.setrecursionlimit` to 200000 on a 250 MiB-stack CPython thread
(the max valid `threading.stack_size` is <256 MiB) ran **4× more instructions (9437 → 37865) but
verified the SAME 25 routines** — the extra depth is loop re-entry of already-counted routines, then
the same recursion blow-up.  So the ceiling is the harness's hook-nesting design, NOT the recursion
limit.  The real fix is to stop Python-recursing on nested hooks: run only the OUTERMOST hooked
routine as a Python hook and let its nested CALLs fall through to the interpreter (they were already
verified on their own first top-level hit earlier in the boot).  That is a `verify_boot_lifts` /
dos_re verifier change, deferred — 25/54 stands as the current gated coverage.  Scratch repro:
`sys.setrecursionlimit(200_000); threading.stack_size(250*1024*1024)` then `verify_boot_lifts.main([])`
in a thread.  No repo change was made.

## 2026-07-10 — COLD-BOOT CHAIN scoped: ~19K-instruction init (72 routines, 74% liftable), nothing static-relocatable

OVERKILL is a PLAIN MZ executable (no LZEXE -- no LZ09/LZ91/LZEXE signature; entry cs:ip = C22:000E,
0 relocations, load module 50043 bytes).  The "bootstrap" the static bundle captures is the game's
own INIT, run from the MZ entry to the frontier `1010:D007` (the attract/mode-machine top) --
**CORRECTED (traced, not from the manifest): the init REACHES `1010:D007` in ~18770 instructions
across 72 distinct 1010: call targets** -- not 1.25M.  (The manifest's 1245977 `steps` counts the
attract loop spinning at the D007 frontier afterwards; D007 is re-entered many times.)  So the boot
INIT is small and tractable.

**And 74% of it is AUTOMATICALLY LIFTABLE**: `liftgen` over the 72 init routines reports 53 LIFTABLE,
19 refused (17 indirect-jump -- jump tables; 6 region-budget -- large; 3 decoder-mismatch).  Many are
already recovered (C679 the file loader, 0248/0624/065C the read path, 5145).  This is a bounded
lifter campaign, not a 1.2M-instruction mystery.

**PROVEN (2026-07-10): the lift loop WORKS on OVERKILL boot code -- 6 ORACLE_PASSING, 0 DIVERGED** on
the first liftverify pass (e.g. 1010:CE40 verified 12 calls byte-exact vs the interpreted original).
Every boot routine reached-and-lifted verified exact; none diverged.  Recipe:
`scripts/make_boot_snapshots.py` writes `boot_entry_snapshot` (1C32:000E, pre-init, for the phase-1
segment setup that BUILDS the 1010 code segment) and `boot_1010_entry` (first 1010 execution, ~8134
instr, for the phase-2 table builders); then liftverify replays FORWARD to D007 with the hooks
installed.  The boot is linear, so one snapshot only reaches routines AFTER it -- full coverage needs
a snapshot at each routine's entry, or a cold-boot harness that installs all hooks and verifies each
on first hit (the remaining harness work).  Acceptance test: the CS tables (8D92/9592/9598/C570)
byte-equal to the bundle.  Snapshots are gitignored (regenerable).

A bespoke decoupled harness was ATTEMPTED (emit from the bundle, install + verify over a fresh boot)
and reverted -- it hit a KeyError inside dos_re's _probe/clone when scanning from a non-live runtime.
The right home is liftverify gaining a separate --emit-snapshot vs --run-from (a small dos_re change),
not a script here.  The proof already stands via the direct liftverify run (6 ORACLE_PASSING, 0
DIVERGED); full coverage is a mechanics follow-up, not a correctness question.

**DONE (2026-07-10, after the dos_re bump to 58a1a51's pluggable cloner): scripts/verify_boot_lifts.py
is that decoupled harness, and it PASSES -- 54 of 72 boot routines emitted, 25 verified BYTE-EXACT
over a FRESH boot (MZ entry -> D007), ZERO real divergences.**  1 retired on ASM-oracle timeout
(too deep to re-interpret), then a clean stop when one lifted hook hit Python recursion depth.  So
half the boot init is proven native byte-exact end to end.  Remaining to reach 100%: the ~18 refused
(indirect-jump / region-budget -- need the lifter's jump-table + larger-region support), the 1 deep-
recursion routine, and lifting the top-level boot orchestration (main from 1C32) so the boot runs
with NO interpreter at all.  The CS-table acceptance test (8D92/9592/9598/C570 byte-equal to the
bundle) is the finish line.

BOOT STRUCTURE (traced): the init is a `1010 <-> 254A:04D7` loop -- the game's 1010 code repeatedly
far-calls the DOS int-21 file-read wrapper at 254A:04D7 (returning to 1010:026F / C6A0) to load its
assets, then builds the CS tables.  The 6-of-53 verified-in-one-pass is a SNAPSHOT-TIMING artifact,
not a lifter failure (0 diverged): a single forward run from one snapshot only exercises the routines
called after that point, and boot routines are one-shot.  The next slice is a cold-boot harness that
EMITS from a post-init snapshot (correct bytes) but INSTALLS + verifies while running from boot ENTRY,
so every routine is checked on its own first hit.  liftverify emits+runs from one snapshot, so this
needs either per-routine snapshots or a small decoupled harness (emit-dir reuse + install_hook_
verifier from boot entry).

**The cold boot cannot shortcut via static relocation.**  Checked the CS runtime tables the gameplay
depends on -- 8D92/9192/9392/8F92 (sprite-frame), 9592 (plane seg ptr), 9598 (strip seg), 95A2,
C570 (the video dispatch) -- against BOTH the raw MZ load module AND the container.  **None is found
in either.**  The init BUILDS them at runtime; the 50KB load module is smaller than the 64KB runtime
CS segment precisely because the top ~14KB of tables is init-computed.  So there is no "load the MZ,
reuse the seeds" slice: native cold boot means recovering the init that produces those tables.

**What already exists that the boot init would otherwise produce:** `build_cold_level_start_image`
reconstructs a complete, playable level-start DGROUP (all six planets) from the recovered asset
codecs + the bundle's CODE-segment constants; the asset codecs decode every container asset natively.
So the DGROUP/asset half is done -- what the bundle still supplies is the CS constant tables the init
computes.

**The tractable method (not yet started):** the boot init is exactly what the dos_re LIFTER +
`--timer-irqs` (both landed by af4055a) are for -- literal-lift each init routine, verify it against
the interpreted original, refactor.  M3 (the AI refactor loop) then turns a passing lift into clean
recovered source.  This is a multi-session campaign, not a single slice; it should be driven route by
route from C22:000E, with the CS-table construction as the acceptance criterion (the produced tables
must byte-equal the bundle's).

Not a blocker to record-and-skip so much as a SCOPE marker: the cold-boot chain is the largest
remaining piece, and it is init-recovery via the lifter, not a data shortcut.

## 2026-07-10 (2nd attempt) — 98EB: 3717 → 47 bytes, still reverted; ONE unknown remains

With the zero-fingerprint corrected (the strip scratch is CLEARED, not rendered), the composition
gets frame 5379 from 3717 diverging bytes to **47**.  Still reverted: a fail-loud gap beats a
47-byte wrong implementation.  But the remainder is now ONE cell and its derivatives.

**The model that works** (`_game_over_continuation_98eb(mem, level_bytes, pick)`, called from 9773
when `[2358] == FFFF`; the 9921 spin takes ZERO ticks and 992F is bypassed):
1. clear the WHOLE strip (`CS:[9598]`, 0xC000 bytes — its low 0x2CD0 alias DGROUP D330..FFFF).
   Clearing only the alias leaves 72 stale save-under bytes at DS:67CC.., because records whose
   `di` sits above the alias still read live strip bytes.
2. `[BEFF] = 5` (57E6), `[2286] = 0x14` (5283 -> 532D's rank), `[98C2] = 2` (96E2 -> CB1C),
   `[22BF] = 3` (532D bookkeeping).
3. `new_game_session_init_96ee()` (score/lives/planet/A342), then `[2356] = pick + 1`.
   **`pick` is USER INPUT** — the level-select cell, living only in the VM's key table during the
   window.  The demo's one game-over picks cell 0 -> planet 1.
4. `_level_data_init_0b3e(level_bytes)`, then the PLAQUE loader's own pointers, which overwrite
   0B3E's: `[21A4] = strip_seg`, `[21A6] = 0`, `[21A8] = 0x1778` (== `len(PLAQ0.ENC)` raw),
   `[21AA] = 0x144F` (DS:144F = "plaq0.enc").
5. `[234E] = 0`, `[2350] = 0x9C`, then the C3A6-family setup tail (C3A6, 77C5, 99BF, 6176, 9BE2,
   A940, `[20A6] = 20A8`, `[A8C2] = 0`, 5F43) and finally `D305` (the plaque fire-wait, carrying
   all 402 ticks).

**THE ONE UNKNOWN.**  After the fresh level start the VM has `[234C] = 0x1A00` and `[A978] = 0x111`;
the model leaves `[234C] = 0x0D00` (whatever 4DBF's rewind left) and `[A978] = 0x110`.  ALL 47
residual bytes derive from that: `DS:234D` itself, the player's `+0x0C` screen-di projections
(2389/238D), `A278`, `26D1`, and the whole `C7B1..C800` star draw list — every one differs by exactly
`0x1A00 - 0x0D00 = 0x0D00` (== 32 * 0x68, the strip row stride) in its high byte.

So the last thing to recover is **the level-start WARM-UP scroll** (60C5 sets `[2350] = 0xEA0`, then
the A781 reverse pulls settle it to 0x9C) and what it leaves in `[234C]`/`[A978]`.  `play_native`'s
cold seed uses `234C = 0x5B00`, `A978 = 0x110` — a synthetic seed, not the warm-up's real output;
this is the same constant pair, and it may be wrong there too.  **Measure it**: trap the warm-up on
a real level start and read `[234C]`/`[A978]` at its exit, rather than assuming either value.

Repro: scratch `p98eb2.py` (the composition) + `pypy -m overkill.probes.inspect_death_windows 5379`.

## 2026-07-10 — 98EB composition attempt: REVERTED; the alias is a RENDERED high-score screen

Attempted: compose `_game_over_continuation_98eb` from owned pieces (96EE + 0B3E + C3A6-tail + D305)
plus a "file scratch" model of the strip alias (raw OKMENU.ENC then raw PLAQ0.ENC written linearly
at strip:0).  Result: frame 5379 went from a fail-loud GAP to a 7552-byte DIVERGENCE — strictly
worse honesty — so the whole composition was reverted (`git checkout`, tree back to 0 B / 1 gap).

**What the measurements established (all banked, do not re-derive):**
* Per-checkpoint attribution of the window (scratch g98eb2): 5145 = 0 B; 57E6 = 6131 B (6130 in the
  strip alias) + `[BEFF] = 5`; 50C9 = 0 B and 0 ticks; 5283 = `[2286] = 0x14`; CB1C = `[98C2] = 2`;
  the title-flow load = 4097 alias bytes + `[21A4] = strip_seg`, `[BB84] = 1`; the setup-tail step =
  209 B (96EE session + 2350→9C + 2078/2340 clears + `[21AA] = 0x144F` plaq pointers) with **zero**
  alias bytes; D305 = 158 B and ALL 402 ticks; then 0 to the boundary.
* `[21A8]` at the boundary == 0x1778 == the raw size of PLAQ0.ENC (`load_container_asset`).  The
  plaque read's DGROUP-visible effect is pointers only — its buffer is NOT the alias region.
* **CORRECTED 2026-07-10 (the first fingerprint was WRONG).**  "83.7% match to HISCORE.ENC" was
  ZERO-INFLATED: it counted zero==zero agreements.  A zero-aware check (positions where either side
  is nonzero) scores **0 / 1871**.  The truth is simpler and better: **the strip alias at the 97B2
  boundary is ENTIRELY ZERO** (11472 bytes, 0 nonzero).  The front-end screens are drawn into the
  scratch and then CLEARED before the boundary.  So 98EB's alias effect is "zero the strip alias",
  not "reproduce a rendered screen", and no glyph renderer is needed for the DGROUP compare.
  My composition diverged by 7552 bytes precisely because it WROTE raw file bytes where the VM
  leaves zeros.  Lesson: never fingerprint sparse buffers with a plain byte-equality ratio.
* The window's screen sequence (by alias writers): game-over screen (57E6) → high-score screen
  (with the table drawn) → title flow → plaque read (non-alias) → setup tail → D305 plaque wait.
* The menu PICK (level-select cell) is USER INPUT that exists only in the VM's key table during the
  window; any native 98EB needs it supplied (the demo's one game-over picks cell 0 → planet 1 →
  PLAQ0.ENC).

**Repro of the failed model:** scratch `patch98eb.py` (applies the composition), then
`pypy -m overkill.probes.inspect_death_windows` → frame 5379 = 7552 B, Cxxx+ = 7288.
**Rule reaffirmed:** a declared gap is worth more than a wrong implementation — do not land a 98EB
model until the alias bytes match, and fingerprint before modelling (the "raw file scratch" guess
cost one cycle; `alias_steps.py`'s per-checkpoint capture + a candidate-source match table settled
it in two).

## 2026-07-10 — DS:98BE liveness: my probe was broken, the question is OPEN

The lockstep gate's last 2 diverging bytes are `DS:98BE` on frames 6495 and 7595 — the two windows
where `D305` runs. `[98BE]` is `0162`'s decoded input word; D305 polls it 0xC9 times, and the demo
pump rewrites the INT9 key table between INT8 frames, so the final poll reads a table that exists
only in the VM and never in the pre-state image the native frame is handed.

I tried to justify excluding it by proving the residue DEAD (the same proof shape that retired
`215A` / `215E`: every consumer preceded, in its own frame, by an absolute write). **The probe
reported `writes 0` over 8291 frames.** That is impossible — the poll plainly writes the cell — so
the instrument is wrong, not the claim. The writer addresses were derived from a static opcode scan
(`88 26 be 98` etc.); a segment/`2E` prefix in front of the store means the real instruction pointer
is one byte earlier than the scan reports, so the trap never fires.

DO NOT exclude 98BE on the strength of that run. Redo it by finding the writer the way everything
else in this port gets found — trap `(CS, 0x9B2E)`, single-step one frame, and watch the byte change
(`probes/map_frame_window.py` has the swap-in-a-full-logger pattern). Then either:
  * the residue is dead → exclude it with the driven proof recorded, as `215A` was; or
  * it is live → the key-table SEQUENCE is a third host input (with `isr_ticks` and `level_bytes`)
    and the shadow cache must record it per window.

A `writes 0` count is a broken probe, not a discovery. Check that the instrument sees what it must
see before believing what it says about what it doesn't.

## 2026-07-06 — RESOLVED: the L2 scenery batch (0x39/0x3A/0x3B/0x3C/0x3D/0x3E/0x3F/0x8A) — ALL EIGHT native

**FIXED (2026-07-06, the one-at-a-time re-land).** Neither divergence family was in the eight
handlers themselves — both were pre-existing bugs the new handlers merely EXPOSED by making more
frames walkable:

1. **The persistent DS:250D byte** was behavior **0x35**'s sprite formula: `B3BF`'s `inc ax` is
   16-BIT, so `[2342]==0xFFFF` wraps to 0 BEFORE the `shr` — the native `(0xFFFF+1)>>1` produced
   `0x8000+0x71 = 0x8071` where the VM produces `0x71`.  (Rec 0x2504 at cache frame ~4023 is a
   0x35 riser, NOT a scenery record — the batch-of-8 mis-attributed it.)
2. **The 0x8A shot-collision miss** was a FIELD MIS-BINDING in `_postmove_bc45`'s
   `object_overlap_scan_62f6` call: it passed `scanner_draw_layer=+0x0A` / `scanner_object_type=+0x16`,
   but the ASM gates on `[bp+22]` = **+0x16** (`OFF_DRAW_LAYER == OFF_HAZARD_CLASS`) and keys the
   wide window on `[bp+20]` = **+0x14** (`OFF_OBJECT_TYPE == OFF_SCAN_FLAG`).  62F6 never reads
   +0x0A.  Every OTHER caller (the VM hook, `object_update.py`, both probes) already bound the
   canonical aliases correctly; only the behavior_walk adapter mis-mapped them.  The L2 0x8A
   scanner (+0x0A==0, +0x16==4) was the first record in any demo to discriminate the fields.

All eight handlers + both fixes land together gated on the 4s cached L2 shadow (zero divergence)
AND the full L1 demo shadow.  Lesson confirmed: batch-of-8 hides WHICH handler is wrong — but also,
a "new handler's divergence" can be an OLD bug newly exposed; attribute by inspecting the diverging
record's `+0x18` in the cache before blaming the new code.

<details><summary>original batch notes (decodes now landed; kept for the record)</summary>

Decodes (disasm-verified):
* **0x39 (8A23)**: sprite 0x6E; `i16(x) >= 0x80` (SIGNED jl) -> (x==0x80 exactly: sound 0x0B),
  dir=2, the AF60 double 2px step (2x `step_operations_for_direction(2,2)`); y > 0xC0 -> BFC7. BC45.
* **0x3A (8A55)**: sprite = `[96D2 + [233C]*2] + 0xCC`; `i16(x) >= 0x80` -> 5E1B deltas
  (PERSIST +0x2A/+0x2C) + 5E42 steer (mode = DS:2312). BC45.
* **0x3B (8A7E)**: sprite = (4D95 canned random & 3) + (0x152 on planets 0/6 else 0xA9); the RING
  cursor 20A6 advances; x += 2. BC45.
* **0x3C (8AA4)**: sprite 0xC5 waiting for x == 0xB0 EXACTLY; there: sound 0x1D, +0x18 += 1 (MORPH
  -> 0x3D), dir=7, falls into the 0x3D body SAME frame.
* **0x3D (8AC7)**: sprite = `[96D2 + [233C]*2] + 0xC5`, then the 0x33 triple-AFD8 bounce (88CF).
* **0x3E (8ADD)**: sprite 0x0E; `i16(x) >= 0xA0` -> MORPH +0x18=0x3F + the 74E2 self-retarget
  (+0x2A/+0x2C) + the 8744 steer tail SAME frame.
* **0x3F (8AF6)**: `jmp 8744` = the shared steer tail (extract from `_step_ramp_steer_29`:
  [2312]=2, 5E42 with the RAMP_29 modes, write-backs, [2312]=3, signed-Y-bounds BFC7).
* **0x8A (8C1F)**: sprite = `[233C] + 0x9D` then the SAME B2AC/B2AF tail as 0x89 (the 232C==0x1F
  BAE1 emit + the BB03 bounce) — refactor `_step_scenery_89`'s tail into a shared fn.

The two divergence families to solve when re-landing:
1. **0x8A**: frames 458/472/486/500 — the VM's record (e.g. 2814) gets KILLED by a player shot
   (HP 3->0, BFC7, score, the shot 2D1C consumed) while the native record survives — same
   positions, so the 62F6 collision disagreed on something else (candidate eligibility? the emit's
   95DA cursor shift? per-frame order?). Needs a frame-458 forensic (the cache inspection +
   write-trap recipe from the crawler debug).
2. **Persistent 1-byte** at DS:250D from frame 4024 (rec 0x2504's sprite HIGH byte, nat=0x80) —
   one of the anim-table sprite writes produced a 0x80xx sprite word: check which behavior owns
   rec 0x2504 at frame 4024 in the cache and whether the [96D2 + clock*2] index needs a mask
   (the clock cell may exceed the table).

</details>

## 2026-07-06 — RESOLVED: the BDD0 contact predicate is recovered + wired; 0x89 DONE

**FIXED (2026-07-06, same day).** The hypothesis below was correct: the shared root cause was the
missing BDD0 contact predicate. It turned out to be ALREADY RECOVERED as
`collision.player_hazard_scan_hit` (+ `is_player_hazard_scan_candidate`) — only the WIRING was missing.
`contact_at` (the AFD8/B022 caller-owned callback) was changed from no-arg to
`contact_at(mirror_dx_x, mirror_dx_y)` so it receives the step's A438/A436 probe deltas; a
`_bdd0_contact_at(mem, rec)` closure in behavior_walk adds them to the object's own X/Y, applies the
BDD0 `+0x0A==1` guard, and scans the effect pool via the recovered predicate. **0x89 re-added and now
PASSES the full demo shadow (0 divergence, 8294 frames)** — proving BDD0 correct. AFD8's own oracle gate
(verify_native_contact_step) + the contact-step unit tests stay green. **The 0x8C/0x8B ground-crawler
(below) is now re-attemptable** — it hit the same AFD8-blocked mismatch, so re-adding it with the real
`_bdd0_contact_at` predicate should close it too.

<details><summary>original hypothesis (kept for the record — now confirmed + fixed)</summary>

**The high-leverage root-cause hypothesis** (two independent behaviors now hit the SAME signature —
`DS:A430` blocked-flag vm=1/nat=0, position 1px behind, and the dependent phase/direction wrong):

* **0x8C/0x8B ground-crawler** — divergence at demo frame **3072** (over its BBED terrain-follow AFD8;
  full entry below).
* **0x89 scenery emitter** — ATTEMPTED+REVERTED 2026-07-06. It is a near-clone of the recovered 0x19
  (sprite = `DS:233C + 0x1C`; when `DS:232C==0x1F` emit a C237 child via the SAME BAE1 dir=4 helper;
  then the shared `BB03` bounce) — no terrain-follow of its own, ALL reused verified pieces. Yet the
  demo shadow FAILS at walk frame **4535**: `DS:A430` vm=01/nat=00, a bounce record's Y off by 1
  (`DS:2460` vm=88/nat=89) and its BB03 direction phase wrong (`DS:2462` vm=06/nat=02), `DS:A436`
  (AFD8 mirror_y) off by 1. Repro: re-add `step_scenery_emitter_sprite_89`/`scenery_89_should_emit`
  (scenery_behaviors.py) + `_step_scenery_89` + the `beh==0x89` dispatch (behavior_walk.py, clone of
  `_step_scenery_19`), run `verify_native_walk_demo "" 20000`.

Because 0x89 reuses the EXACT `_bb03_bounce` that 0x19/0x1A pass, and still under-blocks, the shared
`contact_probe_afd8` (AFD8) is returning `blocked=False` where the VM's AFD8 blocks — on positions the
0x19/0x1A demo frames simply never reach. AFD8's own recovered-island contract already flags the cause:
"**the BDD0 contact predicate is caller-owned** (oracle runs no-contact on a cleared pool)". Every
current AFD8 caller passes `lambda: False` for that predicate. **Recovering the real BDD0 contact
predicate is the shared unblock** for 0x8c/0x8b/0x89 (~1449 demo gap frames) AND the 0x26/latch-9 morph
(which enemies_l1.md independently flagged as needing "the BDD0 contact predicate"). NEXT high-leverage
target: thread the (now-decoded, below) BDD0 predicate through `contact_probe_afd8` in place of the
`lambda: False` stubs — then re-attempt 0x89 (trivial), then 0x8c/0x8b.

**BDD0 fully decoded (1010:BDD0..BE3B), ready to implement:** an object-overlap predicate over the
EFFECT pool. Inputs: the PROBING record's `+0x0A` and `+0x0E`, and the probe point `DS:A438`
(mirror_x) / `DS:A436` (mirror_y) that AFD8 writes as it steps.
```
if probing_record[+0x0A] == 1: return NO-contact            ; BDD0/BDD4
for each of the 0x23 effect records (base 0x23B4, stride 0x38):   ; BDD6..BE38
    if rec[+0x00]==0: continue                               ; inactive
    if rec[+0x0A]==1: continue
    if rec[+0x14]!=1: continue
    if rec[+0x16]!=4: continue                               ; type 4 only
    if not (0x82 <= rec[+0x18] <= 0x94): continue            ; behavior window
    if not (rec[+0x02]-0x10 < probe_x < rec[+0x02]+0x10): continue   ; 0x20-wide X box (di=A438)
    if not (rec[+0x04]-0x10 < probe_y < rec[+0x04]+0x10): continue   ; 0x20-tall Y box (ax=A436)
    if probing_record[+0x0E] == rec[+0x0E]: continue         ; same group -> skip
    return CONTACT (the ASM jmps 5059, the STC contact exit)
return NO-contact (clc)
```
Note the box test is STRICT ge/le -> skip (jge/jle at BE10/BE17/BE21/BE28), so contact requires the
probe strictly inside the (cand±0x10) open interval on BOTH axes. **Wiring plan:** the current
`contact_at` callback (contact_step_b022 arg, today `lambda: False`) is no-arg, but BDD0 needs the
probe point AFD8 is mid-step on. Either (a) have contact_step_b022 pass the current probe (x,y) to
`contact_at`, or (b) have the AFD8 adapter write A438/A436 before each `contact_at` call and pass a
closure `lambda: _bdd0(mem, rec)` that reads them. Verify with `verify_native_contact_step` (AFD8's
own gate) THEN the 0x89/crawler demo frames. This touches the VERIFIED contact_step_b022 interface,
so it is a focused slice on its own — recover it deliberately, not as a crawler sub-step.

</details>

### behavior 0x8C/0x8B — RESOLVED (2026-07-06, same day): recovered with the wired BDD0; zero divergence

The crawler is DONE. Re-added with `_bdd0_contact_at` threaded into its AFD8 step; the frame-3072
divergence disappeared (BDD0 was the root cause, as hypothesised). Landing it unmasked one FINAL
1-byte divergence (frame 3535, `DS:2308`): B2CD (waypoint 0x12) writes its seek-mode global
(`1`, or `2` iff planet==0/BDAC==1) which the adapter never persisted — fixed via
`WaypointFollowerStep.seek_mode_2308`. Demo shadow now PASSES at zero divergence with the whole
scenery cluster native. Historical decode below (kept for the record).

<details><summary>original blocker entry (resolved)</summary>

#### behavior 0x8C/0x8B (the BB80/BB88 ground-crawler scenery): 79-byte divergence at demo frame 3072

**Attempted + REVERTED** (behavior_walk.py + scenery_behaviors.py reverted to HEAD; the play_native
cold-wiring slice `f745f6f` is unaffected). The handler RUNS correctly enough to drop 0x8c/0x8b off
the gap list entirely, but leaves a small, stable per-frame divergence on ONE crawler record.

**Repro:** add the handler back (see the reverted diff / this session's transcript) and run
`python -m overkill.probes.verify_native_walk_demo "" 20000`. FAIL: `diverged=79`, first at walk
frame **3072**, cells `DS:2426` (crawler X, effect slot 2 @ base 0x2424, +0x02) `vm=A3/nat=A2`,
`DS:242C` (that record's sprite, +0x08) `vm=5D/nat=5E..60`, `DS:A438` (AFD8 mirror_x scratch)
`vm=A2/nat=A1`. **Y (`DS:2428`, +0x04) does NOT diverge** — the discrepancy is purely X + sprite.

**What's decoded (correct, reusable):** the two behaviors are ONE body at 1010:BB8E; 0x8C writes
`DS:A952=0xFFFF`, 0x8B writes `DS:A952=0x0001` (a sign flag). The body: (1) 1010:BBED terrain-follow
move — `probe_x = X + A278 - 0x10`, run 5073 (writes `DS:215A`), if bx==FFFF blocked; else pick
direction (0 when X>=DS:237E, else 4) and probe tile `plane[bx + A952 (- 0xD on the left path)]` via
505B/C3AA — a class-0 (open) tile ⇒ BLOCKED (no step), else step via the recovered `contact_probe_afd8`;
A430 is the blocked flag, return ZF=(A430==1). (2) sprite `= 0x61 + 4*A952 + anim + dir`, where
`anim = DS:233C` ONLY when it moved (A430==0) else 0. (3) shot gate: when `DS:2330 ∈ {0x7F,0x6B,0x57}`,
fire via 7476 (`_alloc(0x95DA,...)` + `enemy_shot_stamp_7476` + override `+8=3, +4-=8, +2-=8`). Exit
`jmp BC45` (with_drift=True). All leaf workers (5073/505B/7476/AFD8/BC45) are already recovered.

**The unresolved bug:** at frame 3072 native and VM have IDENTICAL X/Y going in, yet native ends with
`moved=True` (sprite carries the `DS:233C` anim term, +1..3) where the VM has `moved=False`
(sprite constant 0x5D = 0x61-4+0+0, i.e. blocked, dir 0), and native X ends 1px behind. Since the
pre-check inputs are identical on the first divergent frame, the mismatch must be in the AFD8 step
INPUTS (direction? contact predicate?) or in the pre-probe tile the two sides read — NOT in the
elif structure. NEEDS a per-frame trace of effect-slot-2 through BOTH the VM and the native walk at
frame 3072 (dump probe_x, 5073 bx, plane[bx], class, the chosen direction, and AFD8's blocked verdict
on each side) to isolate. Candidate: BBED may pass a REAL BDD0 contact predicate to AFD8 (the same
caller-owned predicate the 0x26 recovery needs) rather than the `lambda: False` the BB03 bounce uses.

</details>

> TECHNIQUE (2026-07-04, SUPERSEDED same day): free-run timing FAST-FORWARD is now a real primitive --
> `overkill/timing_fastforward.advance_frames_fast(cpu, waits, on_frame=...)` (verified by
> `probes/verify_timing_fastforward`). It advances a hooks-cleared raw-bytes runtime by whole `0679`
> waits, delivering the REAL installed IRQ0 ISR at the game's own wait points (the verifier's ASM-side
> semantics) -- deterministic, drift-free, and it services the `9921` sound wait too. Use it for ALL
> forward traces. The old `cs:[066B] = 1` poke is RETIRED: measured against the primitive it loses
> 314 bytes of DGROUP (music/SFX + BIOS-chain state, first diff DS:20A6) and STALLS PERMANENTLY at the
> `1010:9926` sound-active wait (BEFE only clears via the ISR), though its gameplay trajectory matches
> in the pre-stall overlap (so past poke-based STRUCTURE findings remain valid). Measured pacing: one
> gameplay LOGIC frame = ~4 waits (the `601E` counter bank incl. the A7A0 wave clock advances every
> 4th wait) -- count A7A0 transitions, not waits, when reasoning in frames.

> Status note (2026-06-19): the byte-exact frontier is effectively closed —
> oracle suite 244/244 and demo-replay 19/19 (bounded) are green. The primary driver is now
> the cold-boot endgame `/goal` brief ([`overnight_endgame_execution.md`](overnight_endgame_execution.md));
> the readability refactor (`refactor_plan.md`) is a sub-means to it. The only genuinely-open
> correctness blocker was the player-death full-demo divergence below.
>
> **Update (2026-06-28):** that player-death divergence — long the only open
> correctness blocker — and the `[95F2]`/`[95F4]` view-contact-center divergence
> are both RESOLVED by one fix: the AA46 `si>=3` no-contact branch (`AA54 JAE 0xAA44`).
> Full suite 537 passed / 23 skipped. Newly surfaced: an effect-activation
> timing / ISR-cadence phase offset (see backlog).

---

## 2026-07-05 — Cold-start full-session replay hangs at the L1→L2 transition (1010:3273 blit)

**Repro:** `python scripts/verify_cold_start_demo.py artifacts/demos/demo_cold_start_full_20260705_123645`
now clears the frame-12432 all-keys-released deadlock (fixed: `input_waits.all_keys_release_wait`,
1F8F:024B) and replays pure-ASM==hybrid in lockstep from cold boot to **frame 20639 / 22923** — then
`FRAME VERIFY TIMEOUT side=reference frame=20639 budget=120000000 at=1010:3273`.

**Analysis:** 1010:3273 is one instruction of a long UNROLLED Tandy column-blit (`lodsb` -> table
lookup at DS:1514 -> AND mask -> write both interleaved banks es:[di] / es:[di+2] -> `add di,2000h;
test di,8000h; jz; add di,80A0h` bank wrap), just below the Tandy present hook (3354). Straight-line
blit can't loop 120M steps on its own, so an OUTER transition loop is redrawing without reaching a
present/timer/retrace boundary — the reference side (no async IRQ0) can't advance whatever
IRQ/counter gates the loop. Same ROOT as the CBD5 frame-tick wait (`advance_frame_tick_wait`, DS:[54]
via INT 1Ch) and the REFERENCE_ENV_HOOKS rationale, but in the L1→L2 level-transition draw, not a
named busy-wait. Frame 20639 ≈ the last ~2000 frames = the level-complete/L2-load sequence.

**Why deferred:** this is level-transition (Scene/Spine) code, outside the current gameplay-walk
frontier; the determinism result 0→20639 is already strong and the demo replays correctly
interactively (owner-confirmed). **Pick up:** trap the outer loop enclosing 3273 at frame 20639,
find the counter/flag it waits on, and if IRQ-gated add a verifier-side advancer like
`advance_frame_tick_wait` (interactive play unaffected — it fires the real ISR). The bounded gap
run (`verify_native_walk_demo … 20000`) sidesteps it and still covers all of L1 gameplay.

## 2026-07-04 — What is the A47C scripted-input script? (PARTLY RESOLVED: it is NOT player death)

**UPDATE (resolved half):** traced the player_death demo forward recording `DS:A47C` changes + `A6B9`
executions — across the WHOLE run up to the death frame (1805), A47C stayed 0 and the arm never fired.
So the A47C script is definitively NOT player death (death = the separate `9AFF` +08 anchor counter).
The three directly-A47C-linked functions were renamed `step_death_*`/`step_game_over_*` ->
`step_a47c_*` (byte-exact, probes pass). **Residual open:** (1) what the A47C script POSITIVELY is
(boss/cutscene/scripted-event) — needs a demo that actually drives A47C nonzero (e.g. a scroll-to-
position or boss-intro capture); (2) whether the countdown leaves `step_death_countdown_9e69` /
`step_game_over_countdown_9ee4` / `step_a95c_difficulty_countdown_9e43` are reachable only via the A47C
script (they were NOT renamed pending that link). Original analysis retained below.

**Blocker (original):** the A47C-indexed scripted-input subsystem (armed at `1010:A680` -> `A6B9` `mov [A47C],1`;
dispatched by `99F6`; handlers 1=9A78, 2=9A3E, 3=9A16; counters A95A/A95C/A97A/2384) was recovered
byte-exact this session and LABELED "death"/"game-over", but that semantic label is an assumption and the
evidence points elsewhere:
- the A680 arm gate is `A480==0 AND 234E==1 AND 2350==0x0EA0` — `234E`/`2350` are the world-scroll cursor,
  so it fires at a scroll POSITION and spawns an entity (`62AA`+`7524`): a scripted level/boss event
  shape, not collision-death;
- `A47C==0` at all 6 sampled demo seeds (incl. player_death and L6_boss); `A95A==3` / `A97A`!=0 are normal
  L1/L2 resting values, not death countdowns;
- the GROUNDED player-death path is the separate `9AFF` +08 anchor counter
  (`step_death_tail_9aff`/`detect_gameplay_transition`), demo-witnessed, which never touches A47C.

**Decisive experiment (before any rename pass or before wiring 99F6 into play_native as "death"):** trace
a demo forward and record every frame where `DS:A47C` changes and whether `1010:A6B9` executes. The
player_death demo's death frame is ~1805; a naive per-instruction Python step-callback over that many
frames TIMED OUT (>2 min). Need either (a) a lighter trace sampling at a single per-frame anchor IP with
near-zero work, (b) a purpose-recorded short demo that drives A47C nonzero (a scripted level-event/
boss-intro capture), or (c) instrumenting the VM memory-write path to log writes to A47C. Outcome
determines whether to rename the `step_death_*`/`step_game_over_*` functions to their true (scripted-
input/event) meaning. Functions are byte-exact regardless — a NAMING/semantics blocker, not correctness.

---

## RESOLVED (2026-07-03) — the 519A/5A6C unlifted-backend cold-boot gaps (518C/85D5/5EF9 cleared)

> **Fixed centrally.** `519A`'s unlifted-text-backend branch now runs the backend to its RET (fixes
> `518C`/`5F06`/`5EF9`); `hooks._run_5a6c_dispatched_target` does the same for `5A6C`'s unlifted blit
> backend (fixes `61DC`/`6120`/`85D5`). Both zero-gameplay-change (non-Tandy branch only). The hooks-ON
> cold-boot now runs 60K steps with no crash (past all three gaps) to `1010:4A52`; next crash beyond
> that is the next gap. See run_status. The dated per-gap notes below are kept as provenance.

## (historical) RESOLVED (2026-07-03) — the 519A cold-boot text gap; next hooks-ON gap is 85D5

> **Fixed:** the `518C` loop now handles `519A` dispatching to an unlifted non-Tandy text backend —
> when `519A` JMPs to the backend (`s.ip != 0x5197`), `518C` runs its original bytes until they RET
> to `0x5197` (`_run_original_text_backend_until_return`) instead of raising. Gameplay's Tandy-3153
> path always returns to `0x5197`, so it's unchanged. Verified: the hooks-ON cold-boot now runs PAST
> `518C` (fires 4×) to the **next** gap. The dated analysis below is kept as provenance.
>
> **NEXT hooks-ON cold-boot gap (2026-07-03):** `85D5 expected 5A6C to return to 8628, got 1010:4199`
> (at `1010:C4DB`, ~17.9K steps). Same pattern: on cold-boot the `5A6C` cell blit dispatches to an
> unlifted backend (`0x4199`, not the Tandy `306F`). Fix analogously — when `85D5`'s `call_cell_blit`
> lands `s.ip` off `0x8628`/`0x863D`/`0x864E`, run the original blit backend until it returns. Then
> rerun and take the following gap; this iterative loop is the cold-boot witness harness.

## (historical) OPEN (2026-07-03) — the 519A text dispatch raises on the cold-boot intro/title text path

Surfaced while testing a hooks-ON cold-boot (`install_replacements=True`, fast). The lifted `518C`
NUL-text loop (`rendering/text.py`) calls `run_text_dispatch_519a` and asserts it returns to `0x5197`;
on the cold-boot intro/title text it instead returns to **`0x4277`**, so the hook raises
("519A returned to unexpected IP 4277 inside 518C text loop") and halts the boot at `1010:4277`.

Root: `519A` dispatches through the video-mode text table (`CS:[95BC]` + backend flag `DS:21A2`); the
cold-boot text is drawn in a mode/backend the lifted `519A` doesn't model (it was verified for the
gameplay HUD text path). Not a gameplay regression (all gameplay tests + demos are green) — a latent
coverage gap only reached on the cold-boot path.

**To fix (a real cold-boot enabler):** trace what handler `519A` dispatches to at cold-boot (why the
`0x4277` continuation), extend the lifted `519A`/`518C` to model that text mode, gate it produced-vs-VM
(drive the intro/title text on a fresh hooks-on boot; or a synthetic-ASM oracle for the `519A` dispatch
table). This is the first of the hooks-ON cold-boot-path gaps; fixing them one by one is the fast route
to a cold-boot witness harness (see run_status). Repro: `create_overkill_runtime(exe, game_root,
install_replacements=True)` then step — halts at `1010:4277` within ~18K steps.

## RESOLVED (2026-07-03) — the 306F blit leaf is now verified via a synthetic-ASM oracle

> **Update (2026-07-03): the blit itself is DONE via oracle path #2.** `native_video/hud_chrome.paste_panel_cell`
> is byte-exact to the original 306F opcodes, proven by `tests/test_hud_chrome.py` (assembles the exact
> 306F bytes, runs them on a `CPU8086` over synthetic cells, compares). The demo witness-poverty below is
> unchanged and still applies to the FULL render path (85D5/859E cell selection + descriptor loop), which
> stays for the cold-boot phase — but the raw blit no longer needs a demo witness. The analysis below is
> kept for the remaining cell-selection/composer work.

## OPEN (2026-07-03) — static-HUD-chrome render (859E→306F) is WITNESS-POOR in all snapshot demos

Attempted the first native leaf of the static-HUD-chrome layer (Bucket C): `paste_panel_cell`, the
pure form of the `1010:306F` Tandy PANEL-cell blit (`lodsw` rows → `lodsw` width×4 stride → per-row
`rep movsb` into the packed B800 page, `DI += 0x2000` / wrap `+0x80A0`; a raw copy, no colour mask —
disasm-accurate, transcribed instruction-by-instruction). **Reverted (unverifiable):** the whole cell
render path `859E→85D5→5A6C→306F` fires **0 times** across EVERY snapshot demo checked — L2 (150f),
`start_to_end`, `L1_start` all show `306F=0`, `859E=0`. The HUD chrome is drawn **once at
cold-boot/level-load, BEFORE the demo snapshots are taken** (which is exactly why the earlier probe
found it ~99.5% static during gameplay — it's never re-blit). So there is **no demo witness** to gate a
native `306F` blit against.

**Correction to the prior run_status plan:** the "859E fires every present via D104" claim (from a
static byte-scan) is WRONG — D104/859E are not reached during snapshot-replay gameplay. Do NOT re-derive
the plan from that.

**To actually do this slice, a future run needs one of:**
1. a **cold-boot run** (fresh runtime via the `.is_cold_start` demo path — `demo_cold_start_*` has no
   snapshot; "boot a fresh runtime and replay") that executes the level-load HUD render, then wrap/step
   `306F` there; or
2. a **synthetic `306F` ASM oracle** (run the original `306F` bytes on a controlled CPU8086+Memory with a
   small synthetic cell, compare to `paste_panel_cell`) — the AGENTS.md "synthetic fixtures + interpreted
   ASM" path for witness-poor small routines.
The `paste_panel_cell` design + the `verify_native_hud_text` handler/step patterns are recorded above and
in this session's transcript; the blit mechanics are fully understood, only the witness is missing. Also
note `306F` is a registered hook that the **lifted parents bypass** (859E/85D5/5A6C run their Python lifts
and never jump to `306F`), and it's kept (not stripped) on the frame-verifier ref side — so neither a
handler-wrap nor a ref-side step-hook observes it via the lifted gameplay path; the cold-boot path is the
real witness.

---

## RESOLVED (2026-07-03) — L3 sprite-compose: was the unmodeled OR-inverted 2F40/2ECB leaves

> **Fixed same day.** Root cause: the native compose modeled only the masked compositor leaves
> (2E6E/2F81/2FB6); the OR-inverted leaves **2F40/2ECB** (`dest_word |= ~src_word`) were not
> captured, so the objects they draw (e.g. an L3 16×16 white block) were missing → `native=0`
> where `vm=15`. Recovered `decode_or_inverted_delta` (pure, `0xF ^ src` OR delta) + an
> `or_inverted` block kind in the native sprite layer + extractor capture. `verify_playfield_compose`
> is now **39/39 on L3** (was 24/29) and stays 100% on L1/L2/L4; `verify_native_starfield_plate`
> self-compose L3 39/39 too. The dated analysis below is kept as provenance.

## (historical) OPEN (2026-07-03) — L3 sprite-compose: 5/29 playfield frames diverge (plate-independent)

Surfaced while wiring the native starfield plate (not caused by it). `verify_playfield_compose`
— `playfield = plate + composite_sprites(blocks)` vs the VM's decoded `[9598]` playfield — is
byte-exact on **L1/L2/L4** (PASS) but **CHECK on L3**: 24/29 byte-exact, **5 frames diverge**.

- **Plate-independent.** `verify_native_starfield_plate` shows the starfield plate is byte-exact
  vs the VM on all 29 L3 frames; the 5 failures are identical whether the plate is VM-captured
  (`verify_playfield_compose`) or native (`verify_native_starfield_plate` self-compose = 24/29
  too). So the defect is in the **masked-sprite composite** (`composite_sprites` /
  `decode_masked_sprite` / the `MASKED_COMPOSITORS` block capture), not the background.
- **L3-specific in the current corpus** — L1/L2/L4 full-demos compose clean. Suspect an L3 sprite
  path the block-capture models slightly wrong (a compositor variant / `row_add` / opaque-mask
  edge case, or a block whose DF/rows differ). Not a `DF`-skip frame (skipped(DF)=0).
- **Repro:** `python -m overkill.probes.verify_playfield_compose artifacts/demos/demo_play_tandy_L3_full_20260617_202520 60`
  → `byte-exact=24 fail=5`. Next step for a fresh agent: dump the 5 diverging frames' per-block
  draw list (which compositor IP / di / rows) and diff the native vs VM playfield pixels to
  localize the offending block. Low urgency (render-fidelity, not a gameplay-logic gate), but it
  caps the render self-compose gate at <100% on L3.

---

## RESOLVED (2026-07-03) — the starfield is fully recovered; only backend WIRING remains

> **Update (2026-07-03): recovery DONE, this is no longer a blocker.** The starfield is a recovered,
> verified pure system — `recovered/systems/starfield.py` + `recovered/domain/starfield.py` (move at
> `1F8F:0922/0960`), probe `verify_native_starfield.py`, tests `test_starfield.py`/`test_starfield_cold.py`.
> Do NOT re-trace or re-recover it, and ignore the "Next: recover…" tails below (they are completed).
> The `4C76` "move" address cited below is WRONG — it is absent from the code; the move is `1F8F:0922/0960`.
> The ONLY remaining starfield work is wiring the pure system into `compose_playfield_indices` for the
> standalone `--backend native` frame (Bucket C). The dated analysis below is kept as historical provenance.

## (historical, 2026-06-29) — the starfield plate blocked the native frame (`--backend native`)

The standalone native frame is `playfield = starfield plate + sprites` (+ HUD). Every native
leaf is recovered **and proven byte-exact** EXCEPT the **starfield plate** (the sparse
parallax background): sprites (`composite_sprites` / `verify_sprite_layer`), the playfield
compose (`compose_playfield_indices` / `verify_playfield_compose`, 30/30), the HUD glyph
(`native_video/hud_glyph` / `verify_hud_glyph`, 256/256), and now the **full HUD/status text
line in packed B800** (`native_video/hud_text` / `verify_native_hud_text` — the whole 5EDB
line incl. score digits, 1800/1800 across L2/L5/L3) are done. So the starfield is THE
critical-path blocker for a self-composed native frame. **HUD digit band: DONE (2026-06-29)**
— the brief's "clean fresh-session slice" (3153 glyph + B800 composition) is closed; do not
re-attempt, only fold `hud_text` into the standalone backend compose (Bucket C).

- Eluded ~30 probes: the stars are a parallax PIXEL layer — the static-buffer-scroll model
  FAILED (0/60 plates reproduced, 0 colour conflicts → stars scroll at their own rate); a
  traced star byte showed NO writer (not `wb`/`ww`, not the bulk `rep movs/stos` even after the
  bulk-op watcher fix) → the plot is via a path the watchers miss (off-screen scroll-in
  suspected) or at level-load.
- **Next (fresh approach):** a parallax-aware trace at a SCROLL frame (star displacement vs
  the cursor delta → the star scroll counter), or a level-load capture. User noted it's
  pixel-plotted. Until then, the native frame must capture the VM plate (hybrid only).

**RESOLVED (mechanism) 2026-06-30 — the starfield is deterministic + recoverable.** Found with
`dos_re` `mem.write_watchers` (fires on ALL write paths). Over one frame, 7 sites write the present
source page (`CS:[9598]`); six are sprite blocks, and **`1010:4D6F` writes 40 scattered single bytes =
the ~40-px starfield**. The prior "NO writer" was a probe gap: the plotter **skips already-occupied page
pixels** (`4D2C jne`), so a fixed watched byte is usually never written. Routines (CS=1010): **erase
`4D64`** (zeroes the 40-entry working list `DS:0xC7B1`; Tandy single-byte `es:[di]`), **plot `4D15`** (set
up by `4CED`: stream `DS:0xC6C1`, list `DS:0xC7B1`, `bp=0x4D4D`), **move `4C76`** (advances the stream
per a video-mode jump table `cs:[0x4C8A+[95BC]*2]`, Tandy=shr1, parallax tables `DS:0xC803/C807/C80F` +
wrap counter `DS:0xC818`). A star is 3 words `{row, dx, color}`; page offset = `row*0x68 +
DS:[0x234C](cursor) + dx` (base table `DS:0x9A08 = row*0x68`; page row stride `0x68`=208px; present 3354
does the Tandy bank interleave). New-star ring `DS:0x20A8..0x20C7` via ptr `DS:0x20A6` (`4D95`);
level→initial-stream `DS:0xC601[level]`. Tables are DS-relative (DS=0x25CC). **Next: recover
erase/move/plot as pure systems; verify produced-vs-VM byte-exact (step-hook `4D64/4D15/4C76`); per-level
initial stream from a level-start snapshot.** Full detail in the `overkill-starfield-render` memory.

## NOTE (2026-06-29) — §1.2 state-mirror verifiers DILUTE pure %; at the rounding edge

The Bucket C §1.2 native state-mirror verifiers (`read_X` + `X_mismatches`: CameraState DONE
`5902f25`, HudLayer/Score DONE `fdd4a38`) are **VM-facing adapter code** — they read VM memory
to compare — so each ADDS to the ASM-like mass without adding `source_pure` mass. Pure %
DILUTES (Source flat at 2982; ASM-like grows). Committed Camera + Hud brought pure % to the
rounding edge (raw ~14.45% → displayed 14.5%). A further BackgroundLayer + PresentComposition
mirror slice pushed ASM-like 17650 → 17701 → **14.4% displayed (FELL)**, so it was REVERTED per
§5 (a slice failing the metric gate is a blocker, not a shortcut).

**Implication:** done-condition #2 (build the §1.2 mirrors) conflicts SHORT-TERM with #4
(pure % must not fall) — mirrors are VM-facing infra. They pay off only when the native RUNTIME
(Bucket C producer) is built and the VM-facing adapters/hooks are DELETED (pure % then jumps).
Until then, do NOT add more standalone mirror-verifier slices (they fail the metric gate). The
metric-RAISING vein is inline→pure decision extraction (A4EA-style, `e2bd8d7`), which the
brief's own Bucket-A frontier note marks exhausted (only multi-part islands remain). Confirmed
this session by examining the two unblocked Bucket-A behaviors: `B250`'s overlap-box test is
flag-coupled at each early return (AX/BX/flags differ per exit), and `8d4f` is a waypoint read +
a trivial `+0x20` offset + mode stamp then delegations to the already-lifted `5DB2`/`bc4b`.
**CORRECTION (2026-06-29, later): `B250`'s box DECISION was recovered after all** -- the
flag-coupling is only in the staged arithmetic; the predicate `overlap_contact_box_contains`
(systems/collision.py) is pure + verified produced-vs-VM (10,767 calls, 0 div), with the hook
keeping the staged arithmetic for AX/BX/flags + cross-checking.  (The lesson again: attempt the
leaf, separate the decision from the flag mechanics.)  `8d4f` remains mostly delegation glue.  So the
gate-compliant remaining work is (a) the hard Bucket-A islands (pure-raising but multi-leaf), or
(b) the native-runtime build itself (which collapses the adapters and repays the dilution).

**Update (2026-06-29, later) — clean low-risk pure-raising veins now EXHAUSTED; do NOT re-grind:**
- inline→pure spawn templates: done (A4EA `e2bd8d7`); the rest are single-use (over-engineering).
- faithful recovery of witness-poor `_observed` lifts: 5F0D was the one clean one (`bcd_add_score`
  `332b58d`); the others (`bec5`/`9e69`/`9e98`/`bd17`/`bd0d`/`7476`/`7420`) are the hard
  death/contact/spawn frontier (attended-only — that is *why* they are observed/partial).
- Bucket-A unblocked behaviors: `B250`'s box predicate is now RECOVERED (`overlap_contact_box_contains`,
  16th producer) -- it unblocks the b24d/aed8 EFAE handlers; `8d4f` remains delegation glue.
The one vein that BOTH raises pure % AND is non-blocked is the **native-runtime build (Bucket C)**;
per-handler native slot-transforms (now that B250 is pure, b24d/aed8 are the nearest) feed it.
**Done this session (`9899c12`..`afaadf6`):** `NativeGameState` + the pure verify-mode comparison
core; and the **produced-vs-VM verify-mode** grown to **5 byte-exact producers** across the demo
corpus (`scripts/verify_native_producers.py`, the cross-demo gate): `bcd_add_score`/`advance_hud_score`
(5F0D score), `object_pool_find_free` (7573 alloc), `object_spawn_seed_8209`/`_a4ea` (8209/A4EA
spawn templates), `step_first_active_timer` (61C7 frame timers).  Each probe step-hooks the routine
on the pure-VM side and asserts the native producer matches, for every real event (hundreds/demo,
0 divergence).

**The remaining §1 gap (demand-driven):** rendering a frame standalone needs `FrameSnapshot` built
from `NativeGameState` with **no VM**, which needs the **object pool updated natively** — i.e. the
**standalone per-frame object update**: the scan/dispatch over `NativeGameState`'s pool + each
object's behavior *applied* to native state (the decisions in `systems/objects.py` are already pure;
the per-object read→decide→write **application** + the **scan/dispatch orchestration** + movement/
collision/clamps + side effects are the lifted-only parts that need standalone versions).  This is
the big coupled system (no clean single leaf) — the multi-session build, and once it produces the
pool, the standalone loop (§1.1) and full-state verify (§1.2) follow.  **Pattern to reuse:** each
new producer gets a `verify_native_*` probe added to `verify_native_producers.py`'s `PROBES`.

**Confirmed coupled by inspection (2026-06-29, why no 6th clean producer):** the behaviors are not
slot→slot — `_run_object_behavior_b73e` (and siblings) end every path in `_run_object_postmove_bc4b`
(the collision/contact tail), and the movement helper `_run_movement_direction_5db2` is a compound
target-seek (reads object Y/X vs DS:2304/2306, maps a direction nibble through DS:A348/A954 into the
slot, then dispatches a step through CS:5E0C by DS:2308 — and is verified only for the 2308==2 AF60
double-2px step).  So the object-update producer must bundle target-seek + step + the bc4b
collision/postmove tail; that's the substantial recovery, not a clean leaf.  The path in: lift the
`bc4b` postmove + the target-seek/step into native-state functions, then a per-logic-id native
dispatch over `NativeGameState`'s pool, each verified produced-vs-VM with a `verify_native_*` probe.

**Second gap — the render-side `screen_di` projection (for the native FrameSnapshot sprites):**
building `FrameSnapshot` from `NativeGameState` (no VM) also needs each sprite's `+0C` dest
(`screen_di`), which `frame_snapshot_adapter` currently *reads* from the VM.  It is computed in the
per-object draw `1010:5AC8` (the present scan `A846` loops the 8D12/32CA tables calling 5AC8 per
active slot) — **un-recovered raw ASM**.  The sprite *blit* is already recovered
(`composite_sprites`/`verify_sprite_layer`); the *projection* (object world pos + scroll/camera →
B800 di, or `FFFF` cull) is the missing piece.  **But 5AC8 is NOT a clean leaf** (corrected after
disasm): it is a draw DISPATCHER — `mov bx,ss:[bp+0x14]; add bx,cs:[95BC] x3; shl bx,1; jmp
cs:[bx+0x5AE2]` — indexing a jump table at CS:5AE2 by draw-type + the video mode (`[95BC]`), so the
projection lives in *multiple per-type/per-mode handlers* (the table targets).  Recovering it = map
the 5AE2 table, lift the Tandy handler's project-then-`composite_sprites` path to native state,
verify native di == VM `+0C` across demos.  So the render-projection gap is itself a coupled
**island** (dispatch + handler set), the same risk class as the object-update island.  **Net: both
remaining §1 gaps are coupled islands; no clean `verify_native_*` leaf remains** — the work is
genuine multi-routine recovery, for a fresh, clean-context session.

**Projection observe→derive — ATTEMPTED, needs the handler ASM (2026-06-29):** captured **410**
active-sprite `(obj_x, obj_y, screen_di, camera_x, camera_y)` samples over an L2 demo run
(`scratchpad/capture_projection.py`) and tested whether `decoded_screen − (obj − camera)` is
constant under four page geometries (B800 bank; linear width 0xA0/0x68/0x150).  **None fits** — X
has 49–95 distinct offsets and Y 37–73 across the 410 samples, for every geometry.  (The earlier
2-sample snapshot "X ≈ obj_x − 136" hint was a coincidence, not a real fit.)  So `+0C` is **not** a
simple camera-relative projection in any standard page geometry — it factors something else (a
different reference origin, per-object scaling/anchor, or a non-standard stride/page).  Observation
alone cannot crack it; the recovery requires **disassembling the chosen 5AE2 Tandy draw handler**
(map the table, follow the dispatched handler's `+0C` computation), then implement
`project_object_to_di` and verify native di == VM `+0C` across demos.

**RESOLVED (2026-06-29, `f8cae7a`) — the projection IS a clean leaf after all (go-to-the-ASM won):**
followed the dispatch (5AC8 draw-type → 5A36 video-mode → **30D2** Tandy projection) and the
projection is `di = (obj_y >> 1) + DS:99C8[obj_x]`, cull on `obj_x >= 0xE0` / column entry `FFFFh`.
The reason observe→derive failed: the **X is a table lookup** (`DS:99C8`), not arithmetic.  Recovered
as pure `native_video/projection.py:project_object_to_di`, **verified 4624/4624 byte-exact** vs the
real 30D2 (`verify_native_projection.py`), added to the cross-demo gate (6th producer, first
render-side).  The column table `DS:99C8` is already recovered — the static 0F0B startup builder
(`rendering/tandy.py`: FFFF guard band + X/window table by stride CS:[959E]).  So the render
**leaves are done** (projection + column table + `composite_sprites` blit).  Remaining render work
is **integration, not a leaf**: assemble the native FrameSnapshot sprite list from
`NativeGameState`'s pool via `project_object_to_di`, reconstructing the full slot `+0C`
(= core `+ DS:234C` scroll `+` the one-row present phase `0x68` that the present-hook extraction
sees) — a Bucket-C composition step.  **So of the two §1 gaps, the render one is now leaf-complete;
the object-update island (bc4b/target-seek dual-mode) remains the substantial recovery.**

**RESOLVED (2026-06-29, later) — the full sprite `+0C` composition (`project_object_screen_di`):**
the render-side Bucket-C composition step the projection note left ("reconstruct the full slot
`+0C` = core + DS:234C scroll") is now done + verified.  Disasm of the per-object draw handler
**35CC** settled the exact formula (the projection.py docstrings disagreed on whether DS:99C8 was
already scroll-baked): `35CC call 5A36` (→30D2 core di) → `35CF mov [bp+0C],ax` → `35D8 add
ax,ds:[234C]` → `35DC mov [bp+0C],ax`, i.e. **`+0C = (project_object_to_di(x,y,col) + DS:234C) &
0xFFFF`**, or FFFFh when 30D2 culls (→25B2).  Recovered as pure
`native_video/projection.py:project_object_screen_di` (and `build_native_sprite_layer` now composes
the full `+0C`, not the core), **verified produced-vs-VM byte-exact vs the live slot `+0C`** by
`verify_native_screen_di.py` (7th producer in the cross-demo gate): L2 2191/2191, and L1/L5/L6-boss/
player-death/mothership all 0-divergence (~17k draws).  The `+0x68` "phase" in the earlier note is
NOT part of `+0C` — it is only the present-hook *extraction* boundary artifact (frame_snapshot_adapter
extracts at the draw boundary, where `+0C` is core+234C with no phase term).  **So the native sprite
layer can now place every object's screen di from `NativeGameState` (x/y + column table + DS:234C)
with no VM read.**  Render leaves AND the render composition are done; the object-update island
(the pool *producer*) is the one remaining §1 recovery.

**DONE (2026-06-29, later still) — the native draw-list producer (`native_sprite_draws`):** the
Bucket-C "compose the FrameSnapshot sprites from recovered state" step is built + verified.
`native_video/sprite_compose.py:native_sprite_draws(game_state, column_table, scroll)` walks
`NativeGameState`'s gameplay then effect pools (witnessed-exact present order), takes active slots,
composes each via `project_object_screen_di`, drops culls → the `(sprite, screen_di)` draw list, no
VM read.  **Verified produced-vs-VM** by `verify_native_sprite_draws.py` at the A90C present-scan
return (where `+0C` is fresh): native list == the VM's gameplay+effect slot draws (`+08`/`+0C`,
active + on-screen), **L2/L5/L6-boss/player-death 200/200 0-div** (8th cross-demo producer).

**DONE (2026-06-29, later) — the COMPLETE native draw list (special view-anchor slot):**
`NativeGameState` now carries the leading `special_pool` (DS:237C, drawn first), so
`native_sprite_draws` walks (special, gameplay, effect) → the COMPLETE draw list, no VM read.
Verified the special slot follows the same `project_object_screen_di` (a normal 5AC8 draw) then
wired it through `NativeGameState.special_pool` / `read_native_game_state` / the probe's VM ref:
**L2 300/300, L5/L6-boss/player-death/mothership 250/250 0-div**.  Aliasing fact locked: the
special slot's X/Y (237E/2380) ARE the VIEW_TARGET/camera globals (a camera move drifts both
`camera` and `special_pool`).  `SPECIAL_DRAW_SLOT_BASE/_COUNT` moved to `views/object_slots.py`.
**The render side is now FULLY recovered (leaves + complete composed draw list).**  Remaining §1:
the object-update island (the per-frame pool *producer* — b73e→bc4b/AD60 tails + 5DB2 target-seek)
and, for a full native FRAME, the BLOCKED starfield plate (above).  Next native step: the
standalone-loop scaffolding consuming the verified producers, and/or the object-update recovery.

**Assessed 2026-06-29 — AD60 (shared bounds/tile tail) is NOT a clean native producer either:**
its decision (`object_bounds_tile_decision_ad60`) is already pure + hybrid-verified, but its
*application* funnels into the coupled death frontier — the out-of-bounds + tile-probe-fail paths
both call `BD17` deactivate (`_run_deactivate_bd17_observed`, the attended-only `BFC7`/`BD17`/`C054`
frontier above).  Same for the behaviors via `bc4b`.  So there is no clean produced-vs-VM leaf left
in the object-update island; its native form is the coupled application build (pure ObjectPool→
ObjectPool transforms for the dispatch + movement + bc4b/AD60→BD17 tails), gated by the death
frontier.  The clean render-producer vein is exhausted (render side fully recovered); the object-
update is the substantial coupled §1 recovery, and a full native FRAME additionally needs the
BLOCKED starfield plate.

**§8 queue refill swept (2026-06-29):** confirmed no clean unattended §1-advancing slice remains
outside the attended object-update + blocked starfield. Evidence: (a) `source_port_status` pure %
15.1%, lifted files well-collapsed (94% named record offsets, 71 pure rules) — the remaining lifted
mass is VM-boundary continuation glue, not extractable decisions; (b) the largest lifted file's
candidate decision (`game_state` 9C01's `3*ah+al` axis-dispatch index) is single-use + tangled with
its jump-table control flow = the "single-use over-engineering" cautioned against above; (c)
`hooks.py` (3203 lines, over its 1500 budget — done-condition #4) has no relocatable inline render
video-writes — its size needs hook DELETION via the native runtime, not relocation; (d) the brief's
last-named Bucket-A behavior `aed8` (logic_id=2) decomposes to a trivial substate timer-dec + the
already-recovered AEE4 step + the flag-coupled `B250` contact selector + the `AD60`→`BD17` death tail
— no clean extractable decision (its only un-pure piece is `B250`'s overlap-box test, flag-coupled at
each early return per the note above). So pure %, the
glue/hooks.py budget, AND §1.1/§1.2 all converge on the SAME gate: the native object-update runtime,
which is coupled to the attended-only BD17/bc4b death frontier. That is the demand-driven loop's
honest frontier: the next productive step needs the death-frontier recovery (a reproduction trace +
gameplay context, per §2 "skip loop_blockers items" unattended) or the starfield tooling.

**Death-tail native-build roadmap (read the code 2026-06-29 — the exact leaves a fresh session needs):**
`object_deactivation.py` shows the object-update's death tail (`BD17`/`BFC7`) is recoverable to native
ONLY by recovering this leaf set first (each gated produced-vs-VM, the proven pattern):
- `C054` (`run_object_deactivate_logic_dispatch_c054`, in collision.py) — the logic-id→selector
  dispatch; its pure classification is ALREADY extracted (checked: delegates to the pure object
  system + an adapter), so only its native *application* is needed, not a new decision.
- `C12D` + `7420` (effect-spawn tails) — pure ObjectPool spawns; the spawn *templates* are already
  recovered (`object_spawn_seed_*`), so these are the application over a free slot.
- `BD17` branches: draw_layer 4 (C054+C12D+linked-counter clear), logic_id 9 (BD7A whole-projectile-
  list clear — already lifted), the small counter decrements (lifted), and **logic_id 0xA → BD9E/AC19
  which is INTERPRETED original ASM** (the attract/transition chain — the one genuinely un-lifted
  branch; if the gameplay demos never hit logic_id 0xA, a pure BD17 can fail-loud there and still pass).
- `BFC7`: score-add (`5F0D`/`bcd_add_score` — recovered), Y-clamp (`BCB1` — recovered), `7420` linked
  effect, `C054`+`C12D`, and the `C037` obj_type dispatch (types 1/2 recovered; others fail-loud).
Then a per-logic-id native dispatch over `NativeGameState`'s pool composes them into the object-update
producer → the standalone loop. Substantial but mapped; a fresh clean-context session can execute it.

**CORRECTION (2026-06-29, later) — the object-update is NOT fully death-frontier-blocked; its MOVEMENT
half is a clean recoverable leaf.** Disproved the "no clean object-update leaf" conclusion above by
building one: the per-slot movement transform is *separable* from the global death-tail side-effects.
AD60/BD17 only set the slot's `active` word + global counters — they never touch the five movement
fields (substate +1C, direction +06, sprite +08, x +02, y +04). So each behavior's movement half is a
pure composition of already-verified systems. Shipped `object_movement_step_ae09` (object_logic_ae09 +
the AF22 step), **verified produced-vs-VM byte-exact** (L5_continue 777/777, L5_short 638/638) — 9th
producer, first object-update one. **Revised frontier:** the object-update splits into (a) per-behavior
MOVEMENT producers — clean, demo-demanded, pure-% raising, the next vein to grind (b73e/b86d/b9f0/aba3/
ab77/8d4f/b24d/aed8 movement halves, each a `verify_native_object_update_*` probe); and (b) the global
side-effects (counters/spawns/`BD17` death) — the harder attended island. Only (b) is death-frontier;
(a) is open for the unattended loop.

**Progress (2026-06-29) — 2 movement primitives now native (the bulk of (a)):** AE09's fixed-step
(`object_movement_step_ae09`) AND the SHARED target-seek (`object_target_seek_step_5db2`, the whole
5DB2 — used by b73e/b9f0/8d4f/D281/B729/B1B0). The latter recovered the CS:5E0C mode table (1->AF63
2px, 2->AF60 2px×2, 3->AEE4 8px) and composes `choose_target_seek_direction` + `step_operations_for_
direction`; **verified produced-vs-VM byte-exact** (L2 1257/1257, L6_boss 1957/1957, player_death
1721/1721, L5 240/240; 5175 calls 0-div). So target-seek movement is done for ALL seeker behaviors at
once. Remaining (a): the non-seek behaviors' slot transforms (animation/state for the non-moving
b86d/ab77/aba3/b24d; aed8's AEE4+B250 which is coupled to ADC9 x=FFFF). Remaining (b): the global
death/spawn side-effects (the attended island). Next: compose the per-logic-id native dispatch over
`NativeGameState`'s pool from these movement producers + the existing decisions.

**Behavior survey (2026-06-29) — the clean MOVEMENT producers (AE09 + 5DB2) are the harvest of this
vein; the rest need harder pieces.** Read each behavior's body: AE09 = clean fixed-step (done); the
seekers b73e/b9f0/8d4f = 5DB2 (done) + bc4b; b86d = interpreted `7476` near-call + the `5E42`
delta-steer (Bresenham) + bc4b (coupled); aed8 = AEE4 + `B250`->ADC9 (x=FFFF coupling); b9f0 = the
follower (5DB2 + its own ~7 decisions + bc4b). So the next object-update producers, in rough order of
tractability: (1) **bc4b Y-clamp** (clean, always-runs; completes the post-move Y of every behavior),
(2) **`5E42` delta-steer** (delta->direction->AF22/AF63 step; composable but has the 5EB5/5EC8 + the
move_step_error Bresenham accumulator; covers b86d's steering), (3) the **global death/spawn
side-effects** (`BD17`/`BFC7` -> counters/spawns -- the attended island), then (4) the per-logic-id
native dispatch composing them.  The two highest-frequency movement primitives are already native.

**Attempted + reverted (2026-06-29) — the full AE09 slot transform (movement + active) needs the
tile-collision path / LevelState.** Tried extending the AE09 producer with the `active` field via the
AD60 bounds decision (`object_update_ae09` = movement + AD60 -> active).  It VERIFIED for the non-tile-
probe cases (L5_continue 22/22, L5_short 21/21) but **SKIPPED the majority** (755 + 617): most AE09
objects hit AD60's **tile-probe** branch (the draw_layer-2 family), whose deactivation depends on the
under-object tile sample (`5073` offset -> `505B` class -> ADC1 check).  So a slot's `active`/death for
the tile-probe behaviors is gated on the **level tile map** — i.e. it needs a recovered **LevelState**
(the tile grid) + pure `5073`/`505B`.  Reverted the partial (skip-heavy) producer per §3; the clean
movement producer stands.  **Next substantial recovery: LevelState's tile map + the pure tile probe/
lookup** — that unblocks the per-slot active/death for AE09 and the whole tile-probe family, and is the
§1.2 ``LevelState`` mirror besides.  (The movement halves are done; this is the death/bounds half's
dependency.)

**DONE (2026-06-29, later) — the full AE09 slot transform IS complete; the revert's premise was wrong.**
The tile probe/lookup (5073/505B) were ALREADY pure-recovered (`systems/tilemap.py`); only the tile-map
INPUTS were missing.  Modeled them as `LevelTileContext` (DS:234E origin, DS:2350 row base, CS:[9592]
tile plane, DS:C3AA class table -- a LevelState seed), recovered the AD60 tile-collision composition
`object_tile_probe_deactivates_ad60` (5073 +13 row -> 505B -> class==1 -> deactivate), and shipped
`object_update_ae09` (movement + AD60 bounds/tile -> active).  **Verified produced-vs-VM byte-exact**
L5_continue 353/353, L5_short 342/342, 0-div, NO skips (tile-probe included).  So the COMPLETE AE09
slot transform is native (everything but the BD17 global counter/spawn side-effects).  **Pattern proven:
movement primitive + AD60 bounds/tile -> the next slot.**  Remaining object-update: apply this template
to the other behaviors (the seekers via 5DB2 + bc4b; the 5E42-steer b86d), and the global death/spawn
side-effects (BD17/BFC7), then the per-logic-id dispatch.

**Clean low-risk producers exhausted (2026-06-29) — remaining object-update = 2 complex primitives.**
Checked the last short behaviors: `b24d` = `5E42` steer + `B250` selector (coupled); `aba3` = a 1-field
sprite (`object_logic_aba3` ALREADY recovered + the AC81 collision tail) = marginal/re-verification.
So after AE09 (fixed-step + full transform incl. tile-collision) + 5DB2 (target-seek), the two
remaining MOVEMENT/postmove primitives are both complex multi-part recoveries, best done with fresh
context: (1) **`5E42` delta-steer** -- delta_x/y (+2A/+2C) -> direction via the `5EB5`/`5EC8` sign bits
+ the `move_step_error` (+2E) Bresenham accumulator + `A348` table -> `AF22`(DS:2312==3)/`AF63` step;
the 3rd movement primitive (covers b24d/b86d steering).  (2) **`bc4b` postmove slot transform** --
y-clamp (`clamp_postmove_y_bcb1` ✅) + x-bounds death (`BD17` -> active=0) + the collision path
(BCCB -> `AA46`/`AA71` view-window ✅ -> `BFC7` death: logic_id=1 + C037 sprite + latch); the shared
postmove for the seekers (b73e/b9f0/8d4f), composable from recovered pieces but multi-branch.  The
template (movement primitive + bounds/tile -> next slot) extends to both; then the global death/spawn
side-effects + the per-logic-id dispatch.

**BFC7 death tail RE-READ (2026-06-29) — confirmed attended, with 3 observed sub-leaf prerequisites.**
Applied the attempt-don't-declare rule to `_run_collision_death_tail_bfc7` (object_deactivation.py:156):
the "clean" final transition (logic_id=1 + C037 sprite + latch) is buried *under* the global death/spawn
machinery, and the routine CALLs three still-observed sub-leaves that must be recovered first: (a)
`_run_score_add_5f0d_observed` — **DONE (2026-06-29)**: converged onto the verified `score.bcd_add_score`
(re-verified byte-exact vs the assembled 5F0D + a full kill-heavy demo, 0 divergence); (b) `_run_linked_effect_spawn_7420_observed`
(the linked-counter spawn) — **DONE (2026-06-29)**: recovered the field-init as the pure
`object_spawn_seed_7420` (systems/objects.py) returning `LinkedEffectSpawnSeed7420` (x = DS:2378 + DS:A278;
y = min(DS:2376, 0xC0); sprite = DS:237A + 0x46; raw type at +26h; constants active=1/scan=1/hazard=5/
logic=0/latch=0/linked=FFFF/variant=0/layer=0), with the hook a thin adapter (7524 alloc + write order +
register/flag choreography).  Verified: a VM-free synthetic oracle (`test_object_spawn_seed_7420`) + the
produced-vs-VM probe `verify_native_object_spawn_seed_7420` (rare event, as predicted) — **34 spawns across
L5_continue 20 / L3 10 / L2 2 / start_to_end 1 / L4 1, 0 divergence** (L6_boss/mothership/showcase have 0,
confirming they aren't linked-counter groups).  (c) the **C054** selector — **already pure** (the classifier
`object_deactivate_dispatch_decision_c054`, systems/objects.py, with a self-verifying adapter); I mis-stated
it as pending in the 7420 note above.

**BFC7 island status corrected (2026-06-29): all 5 COMPUTATIONAL leaves are now pure.** Reading the whole
BFC7 body (object_deactivation.py:156-274) shows it is: the 0021h/DS:2356 gate; the score add (✓
`bcd_add_score`); the y-clamp (✓ `clamp_postmove_y_bcb1`); the linked-counter chain -> 7420 spawn (✓
`object_spawn_seed_7420`); the C054 selector (✓ classifier) + its C12D effect tail; and the final C037
death transition (✓ NEW `object_collision_death_transition_c037`: prev_logic_id=old, logic_id=1, latch=0,
sprite by type 1->0/2->3).  What REMAINS is pure GLUE, not transforms: **C12D** (`_run_c054_c12d_effect_
spawn_tail` — stages 7420's inputs from the slot + writes DS:A482/A842 + decrements DS:A47E around the now-
pure 7420; no extractable computation) and the **BFC7 orchestration** itself (the gate, the counter-chain
decrement, the DS:98C0->BEFF gate, the stack-scratch).  So BFC7's coastline is now shortened to its leaves;
fully composing BFC7 as one pure transform = a multi-output orchestration over the 5 pure leaves (a Bucket-C
integration).  The non-blocked pure-%-raising vein remains the **Bucket-C native runtime**.

**DONE (2026-06-29) — 5E42 delta-steer recovered (the 3rd movement primitive).**
`object_delta_steer_5e42` (systems/movement.py): signed deltas (+2C/+2A) -> Bresenham axis pick vs the
`move_step_error` accumulator (+2E) -> A348 sign bits -> direction (FFh=blocked) -> AF22/AF63 step by
DS:2312.  Verified produced-vs-VM byte-exact L2 64/64 + L6_boss 121/121 (11th producer).  So ALL three
object movement primitives are native: AE09 fixed-step, 5DB2 target-seek, 5E42 delta-steer.  The ONE
remaining movement/postmove primitive is **bc4b** (the shared seeker postmove): y-clamp ✅ + x-bounds
death (BD17 active=0) + the BCCB -> AA46/AA71 (✅ recovered) -> BFC7 collision-death (logic_id=1 + C037
sprite + latch) -- multi-branch but composable from recovered pieces.  After bc4b: the global
death/spawn side-effects (BD17/BFC7 counters/spawns/C12D effect scripts) + the per-logic-id native
dispatch over `NativeGameState`'s pool, then the standalone loop.

**bc4b assessed (2026-06-29) — the most intricate piece; the SLOT transform is composable but its
collision path has observed sub-routines (global effects to scope out).** Read the full bc4b lift
(`object_postmove.py`): the slot-affecting parts are y-clamp ✅ + the x-bounds death + the BCCB
collision (`AA46` type1 / `AA71` type2, both ✅ -> CF, gated by global_disable/+0x16/+0x18/obj_type/
DS:A8C2) -> `BFC7` death (the SLOT side = logic_id=1 + previous_logic_id + transition_latch=0 + C037
sprite for obj_type 1/2; recoverable).  BUT the collision path ALSO runs `9E69` (post-contact ->
9E98/61DC DISPLAY tail) and `62F6` (object overlap scan) -- both "observed"/interpreted, NOT pure;
they appear to be GLOBAL/other-slot effects (display, cross-object scan), so a SLOT-scoped bc4b
transform can likely scope them out (as AE09 scoped out BD17's globals) -- but that must be VERIFIED
(confirm 9E69/62F6 don't write the current slot's y/active/logic_id/sprite).  Collision inputs: the
view-contact center (DS:95F2/95F4, from the view target) + the contact window.  So bc4b is a clean
fresh-session slice IF 9E69/62F6 are confirmed slot-neutral; the gate (produced-vs-VM at bc4b RET)
will catch it either way.  This is the LAST movement/postmove primitive before the global
death/spawn side-effects + the dispatch.

**DONE (2026-06-29) — the BC4B bounds half (y + active); 9E69/62F6 CONFIRMED slot-neutral.**
Shipped `object_postmove_x_bounds_deactivates_bc4b` (the X-bounds death: precise box [-C0h, F0h)
unless DS:A47C set / wide-exempt logic id -> [-14h, F0h)) composed with the recovered
`clamp_postmove_y_bcb1` -> the BC4B slot fields y + active.  **Verified produced-vs-VM byte-exact**
L2 1498/1498, L6_boss 2257/2257, player_death 2181/2181 (5936 calls, 0-div) -- which PROVES (a) the
collision death (BFC7) sets logic_id, not active; (b) 9E69/62F6 are slot-neutral for y/active.  So the
remaining BC4B work is just the **collision-death logic_id/sprite half** (BCCB -> AA46/AA71 (recovered)
-> BFC7 transition: logic_id=1 + previous_logic_id + transition_latch=0 + C037 sprite for obj_type 1/2)
-- verify those slot fields at BC4B RET on the collision-hit objects.  After that: the global
death/spawn side-effects (counters/spawns) + the per-logic-id native dispatch.

**Collision-death half recipe (assessed 2026-06-29 — the recovered pieces are all pure; compose +
verify).** The BC4B collision-death transition fires when (read object_postmove.py 100-155):
global_disable(DS:A47C)==0 AND active AND hazard_class(+16)!=5 AND logic_id(+18) not in {0,1} AND
obj_type(+14) in {1,2} AND the contact test hits AND DS:A8C2 != 1.  The contact test: obj_type 1 ->
AA46 = `view_contact_center_from_offsets_aa46`(view center + the DS:214E[DS:2384*4] dx/dy offset, with
the si>=3 -> no-contact guard) then `view_contact_rect_test`(slot, center, half-extent 0x10); obj_type
2 -> `postmove_contact_window_test_aa71`(slot, window from DS:237E/2380 + the spans, narrowed by the
DS:A8C2 boss flag).  On a hit, BFC7's slot transition = previous_logic_id := old logic_id; logic_id :=
1; transition_latch := 0; sprite_or_state := C037[obj_type] (type 1 -> 0, type 2 -> 3).  All those
helpers are recovered pure (systems/collision.py).  OPEN to confirm when building: the exact AA46
view-center source (DS:237E/2380 vs DS:95F2/95F4) + the AA71 X-window bounds -- read
`collision_adapter.run_view_window_check_aa46` + the AA71 adapter.  Probe: at BC4B RET, verify
logic_id/previous_logic_id/transition_latch/sprite for the collision-hit objects (the gate catches any
mismatch).  This is a clean fresh-session slice; it just composes more pieces than the bounds half.

**ATTEMPTED + REVERTED (2026-06-29) — the collision-death has a SECOND source: the 62F6 overlap scan
(NOT just AA46/AA71).** Built `object_postmove_collision_death_bc4b` = the AA46/AA71 view-contact ->
BFC7 transition (logic_id=1 + previous_logic_id + latch=0 + C037 sprite), composing the recovered pure
contact tests, and probed it.  Result: **1483/1498 byte-exact, 15 fails** -- all one obj_type-1 object
(logic_id 0x1d).  Diagnostic proved the AA46/AA71 model is structurally INCOMPLETE: the failing object
(slot x=0x6c, y=0x8c) transitioned (logic_id 0x1d->1, sprite->0) but its X is 0x4B from the AA46 center
(0xb7) -- WAY outside the +/-0x10 rectangle, so AA46 correctly does not hit.  The transition came from
`62F6` (the BC4B object-OVERLAP scan, object-vs-object collision -- run after BCCB), which is
observed/interpreted, NOT a clean recovered leaf, and CANNOT be scoped out (it depends on the scan over
*other* objects).  Reverted per §3 (15-fail = red).  So the FULL BC4B collision-death needs `62F6`
recovered too (an object-vs-object overlap scan + its transition) -- that is the genuinely-hard,
attended part; the AA46/AA71 view-contact half is correct (1483) but insufficient alone.  Corrected
fact: the BC4B collision death = AA46/AA71 view-contact OR the 62F6 overlap scan; both -> BFC7-style
transition.

**62F6 internals assessed (2026-06-29) — a grid overlap scan (recoverable) -> BEC5 (observed handler).**
Read `contact_side_effects.py:_run_object_overlap_scan_62f6`: after pre-scan exemptions (inactive,
x<20h, draw_layer +16 ==0, logic_id +18 in {0,1,26h}), it scans the gameplay object table for an
active + solid (`scan_enable_or_solid` +1E) candidate sharing the current object's 8px grid cell --
`dx = y & FFF8`, `cx = x & FFF8`, with obj_type-dependent extra y/x candidate cells (type 2 adds
two more rows, and X cells unless logic_id in {78h,79h}).  On a grid match it jumps to **`BEC5`**
(`_run_collision_handler_bec5_observed`), the collision handler that performs the transition -- and
**BEC5 is observed/unlifted** (the genuinely-attended part).  So the 62F6 path = a recoverable pure
grid-overlap scan over `NativeGameState`'s pool (the cell-match decision) + the UNRECOVERED BEC5
transition handler.  Fresh-session plan: recover BEC5 (the handler), then the 62F6 scan composes the
recovered AA46/AA71 + BEC5 + the grid test into the full BC4B collision death.  This is the genuine
object-vs-object collision island -- a cross-object scan + an observed handler, the attended frontier.

**BEC5 internals assessed (2026-06-29) — a deeply multi-variant handler, NOT a quick leaf.** Read
`contact_side_effects.py:_run_collision_handler_bec5_observed`: it dispatches on the COLLIDED
candidate's logic_id (variants 07h/08h/0Ch, the sprite-0033 variant-2, the 5/6 and 7/8/0C
continuations), runs `counter_20` (+20) decrement chains gated by `BEDC` (difficulty) and `A8C2`
(boss), and branches into `BFC7` (death transition), `BD0D` (cleanup -> BD17), and `BF5F` (the A8C2
mark tail) -- and it is itself "observed"/partial ("currently verified branches").  So recovering it
is a meaty multi-variant island (the per-variant counter/death/mark machinery), not a single leaf --
the genuine attended object-vs-object collision work.  Full bc4b collision-death = AA46/AA71 (done) +
the 62F6 grid scan (recoverable) + BEC5 (this multi-variant handler) -> a fresh-session island.

**RESOLVED (2026-06-29) — the ENTIRE object-vs-object collision island is now native source.** The
"attended frontier" above fell decision-by-decision once the death tails landed: `62F6` grid overlap
(`object_grid_overlap_62f6`), the BEC5 variant dispatch (`bec5_collision_variant_family`), the BF25
damage counter chain (`collision_damage_counter_chain_bf25`), and the death/spawn tails (BFC7 +
`bcd_add_score`/`object_spawn_seed_7420`/`object_deactivate_dispatch_decision_c054`/
`object_collision_death_transition_c037`) are ALL recovered + verified (synthetic + assembled-ASM
oracles + the BEC5/62F6 hook cross-checks, with frame-verifier 0-divergence on L6_boss/L2_full).  Do
NOT re-investigate this as a blocker.  LESSON: an "attended/observed multi-variant island" is not
permanently blocked -- it unblocks as its leaf dependencies (here the tails) get recovered, then the
dispatch/decisions extract cleanly.  Remaining collision composition: folding these pure pieces into a
single native BEC5 transform is a Bucket-C runtime task, not a recovery.

## NOTE (process) — check lifted-status before "recovering" a routine

`519A` / `3153` (HUD text dispatch + Tandy glyph) were ALREADY lifted (`rendering/text.py`,
hook-registered; see `coverage.py`). Grep the hook registry for an address before
disassembling it as if un-recovered. `native_video/hud_glyph` is the NATIVE-standalone form
(index-space, proven byte-exact vs the VM tables), not a re-recovery; future dedup: unify the
glyph core (glyph+colour → 8x8 block) between the VM hook (B800) and the native form (index).

## RESOLVED (2026-06-28) — Player-death `BC4B`/`BFC7` divergence (full-demo only)
**Root cause: the AA46 `si>=3` branch** (same fix as the contact-center item in
the backlog). `AA54 JAE 0xAA44` returns no-contact for a side-selector of 3+; the
lift omitted that branch and indexed the 3-entry DS:214E table out of bounds,
fabricating an 8331 hit — the `SI asm=0003 hook=...` below was exactly that.
`demo_play_tandy_player_death` full verify now passes. Original analysis kept
below for history.

Demo: `demo_play_tandy_player_death`. Passes the **bounded** 150-frame demo-replay,
but diverges deep in the **full** run (`OVERKILL_FULL_DEMO_VERIFY=1`).

- Hook-verify: `1010:BC4B object_postmove_bc4b` call 1691 diverges at continuation
  `AA04`. `AX asm=0000 hook=0060`, `SI asm=0003 hook=00DC`, 2 memory words differ
  (`0x0073→0x00EC`, `0x005E→0x0060`), plus a nearby position-list (`9682/968C/9696`).
- **Ruled out:** the `BFC7` death tail itself. Disassembled the full `BFC7..C054`
  path and the `C037` obj_type jump table @`C042`; the lift in
  `object_deactivation.py` matches exactly. The differing words are NOT `[bp+8]`
  (0/3 in both), and `AX`/`SI` aren't touched by the handlers.
- **So the bug is elsewhere in `BC4B`'s path** — `BD17` deactivate, the
  post-contact `9E69` tail, the contact window `AA46`/`AA71`, or upstream state.
  All of `BD17`/`9E69` are still "partial/observed" lifts.
- **Next step (human/trace):** reproduce, single-step `BC4B` call 1691, bisect
  which child first makes `AX`/`SI`/the position-list diverge, then disassemble
  that child and compare. Tooling ready: capstone installed;
  `artifacts/static_runtime_bundle/memory_1mb.bin` holds the original image
  (`1010:off` → linear `0x10100+off`); `scripts/trace.py` does dual-runtime
  watch/observe/globals.

---

## Resolved (2026-06-19) — kept as a short index; full write-ups in git history / run_status.md
- **Mothership camera-Y divergence** — `9B2E` lift dropped the `[a47c]==0` guard on
  the `9C01` camera-step; nested the `[2350]` poll-gate + `9C01` inside `if
  [a47c]==0`. Added `phase_gate_a47c`/`level_progress_2350` to the snapshot globals.
- **Sidearm-trail "shaking" (mothership drag)** — same root as camera-Y.
- **`menu_interaction` demo TIMEOUT** — verifier-only limitation (async INT 1Ch
  ISR not fired, `DS:[54]` frozen). Fixed with `input_waits.advance_frame_tick_wait`
  ticking `DS:[54]` when parked in the CBD5 busy-wait. Interactive play untouched.
- **BDD0 / D434 / 33AF oracles** — all three were hook/oracle *granularity*
  mismatches, not gameplay bugs (demo-replay green throughout). BDD0: land on the
  real `5059` STC;RET stub + drain it in the child-call wrapper. D434 & 33AF:
  oracle-convention fixes (compare at the hook's actual boundary). Suite 244/244.

---

## Remaining backlog — needs attended judgment (not safe unattended)

- **RESOLVED (2026-06-28) — View-contact-center `[95F2]`/`[95F4]` divergence:**
  root cause was the AA46 `si>=3` branch (`AA54 JAE 0xAA44`).  For a side-selector
  of 3+ the original returns no-contact without touching the DS:214E offset table;
  the lift indexed it out of bounds (`DS:[214E + si*4]`, e.g. DS:215A), wrote a
  bogus DS:95F2/95F4 centre and fabricated an 8331 contact hit — which spuriously
  killed in-window effect objects (`demo_play_tandy_20260627_231013` effect:20 at
  frame 936).  Proven by disasm of AA46 + a dual-runtime trace (all AA46 inputs
  byte-identical on both sides; only the si>=3 output diverged).  Fix in
  `collision_adapter.run_view_window_check_aa46_body`.  Same fix closed the
  player-death blocker above.
- **Effect-activation timing / ISR-cadence phase offset** (surfaced 2026-06-28 once
  the AA46 fix let `demo_play_tandy_20260627_231013` replay past frame 936): the
  full verify now diverges at ~frame 960 where a group of idle effect objects
  (logic 0x80, sprite ~354) begin a bounce one frame earlier in the hooked runtime
  than in the ASM oracle (y +2, sprite +1; it momentarily reconverges at the bounce
  turning points, so it is a phase offset, not corruption).  The effects are gated
  on a per-object countdown (`+0x1C`) decremented by the `1F8F:06C9` timer ISR.
  Traced mechanism: the countdown reaches 0 on the SAME frame in both runtimes
  (f959 for effect:6); the same ISR then transitions the effect idle->moving
  (`1F8F:06DB` target_y, `072B` y, `07AC` sprite).  The hooked runtime performs
  that post-zero transition in the frame the countdown zeroed; the ASM oracle
  lands it one frame later.  So the divergence is the SUB-FRAME position of the
  ISR transition relative to the present/frame boundary, which differs because the
  hooked runtime's instruction timing differs.  `1F8F` runs as raw ASM in BOTH
  runtimes (not a hook), so no hook lift fixes it — same class as the busy-wait/
  IRQ-cadence timing work, a timing-model frontier.  Bounded verify unaffected
  (green).  Needs attended timing-model work (frame-align the PIT/ISR cadence).
  The same signature recurs in `demo_play_tandy_start_to_end_20260627_145115`
  at frame 2271 (68 fields, effect:0..16 all y+2 / sprite+1), confirming it is a
  general timing frontier rather than demo-specific.
- **Unknown object-record fields `0x10`, `0x26`, `0x36`** (map at 25/28, the honest
  floor): each is written with no lifted reader (`0x26` ← DS:237A in object_spawns,
  `0x36` ← ax in object_movement; `0x10` is never accessed). Naming needs the
  reader lifted first — can't be done honestly yet.
- **Death/deactivation frontier:** `BFC7`/`BD17`/`C054` are "partial/observed"
  lifts; completing their full branch tables is the same risk class as the
  player-death blocker above and would likely clear it.
- **Interpreted gameplay islands (refactor_plan Phase 5):** `97C8` frame body,
  menu core, `BBB2`/`BE3C`/`B2CD`/`ADC9` block loops run as raw ASM today and are
  already *correct* in both runtimes — lifting them is real reverse-engineering
  with no correctness gain, best done attended, and only after Phases 3–4.
- **Object-behavior call-tree leaves (the bounded `run_original_near_call` /
  `_run_interpreted_near_call_observed` shims)** — surfaced 2026-06-28 after the
  whole object-behavior *decision/computation* vein was lifted (ab10/ae09/aba3/abca/
  b9f0 = 7 b9f0 rules; the behaviors now delegate every clean pure rule). The
  remaining inline weight in `abca`/`b9f0`/`aed8`/`b24d` is the bounded calls into the
  leaves `5DB2`✓/`5E1B`/`5E42`/`7476`/`837A`/`859E`/`AB99`, run through the interpreter
  *on purpose* so their internal near-CALL return words match byte-for-byte. Spot
  disasm confirms these are NOT simple leaves: `837A` is a dispatcher that does an
  indirect `call ax` through a runtime handler table inside a 10-iteration loop (its
  targets can't be statically resolved); `AB99` is just `call BFC7` (the attended-only
  death frontier above). Lifting them is the same "no correctness gain, attended RE"
  class — the bounded-original approach is already correct in both runtimes. Do NOT
  re-attempt unattended. Tractable filler instead: Phase-1b coastline relocations of
  the remaining genuinely-inline render hooks out of `hooks.py`.

### Cleared from this backlog (done since the last revision)
- ~~Raw-offset drain (objects.py / contact_side_effects.py / action_spawns.py)~~ —
  **done** in refactor Phase 2a: all gameplay record access now goes through
  `ObjectSlotView`; only 3 raw record-offset hex remain (the deliberate
  `OFF_SUBSTATE_1E` semantic alias), per the dashboard.
- ~~DS-global naming (141 addresses)~~ — **partly done** in Phase 2b: the 7 cells
  genuinely *shared* across subsystems are reconciled in
  `overkill/recovered/ds_globals.py`; single-subsystem globals are intentionally
  kept local (locality aids readability), so this is closed for the shared set.

---

## PARTIALLY SUPERSEDED (2026-07-03) — the whole object scan diverges on ~2 variant-2 gameplay slots/frame

> **Update (2026-07-03): the `0x1c`/`8D4F` premise below is STALE.** `object_update_8d4f` now exists
> (`systems/objects.py`) and the native dispatch DOES handle `0x1c` (`_advance_8d4f`, `systems/object_update.py`),
> so "my driver only dispatches 0x0C/0x02/0x1D/0x14, skips 0x1c" no longer holds. Re-derive this
> divergence against the CURRENT driver before acting on it; the remaining un-dispatched scanner may be
> only `0x1e` (`B909`, a spawner). Do not re-attempt from the stale analysis; re-trace first.

`native_object_scan` (the VM-free A9E0 object pass over one contiguous 0x45-slot store, both
pointer-table loops in place) was attempted and reverted (red). The effect loop is byte-exact
(1170/1170 L2, 1723/1723 L3), but ~2 gameplay slots/frame diverge and **neither separate pools
nor the shared store fixed them**. Confirmed not a tables-overlap bug and not AED8 timer-death.

- **Symptom (stable across L2/L3):** a `logic_id=2` (AED8) gameplay slot — VM has it
  `active=0`, substate UNCHANGED (e.g. 0xfff9); my pass has it `active=1`, AED8-processed
  (substate−1, x−8). So the VM **deactivates it in the EFFECT loop as a collision candidate**
  (active→0, substate untouched), then the gameplay loop skips it; my effect-loop collision
  does **not** kill it, so my gameplay loop AED8-processes it. (Slots: L2 0x2ce4/0x3064,
  L3 0x2c3c/0x2c74.)
- **ROOT CAUSE (traced 2026-06-30, RESOLVED the mystery):** NOT an order/path bug. A trace of the
  effect-loop kills (`scratchpad/trace_effect_loop_kills.py`) shows all 17 effect-loop deactivations on
  L2 are variant-2 candidates cleared at `BF1B` -- and the SCANNER logic_ids that trigger them are
  `0x1d` (B86D, native: 15) and **`0x1c` (1) + `0x1e` (1) -- NOT native handlers**.  My driver only
  dispatches `0x0C/0x02/0x1D/0x14`, so it skips the `0x1c`/`0x1e` scanners entirely, never runs their
  BC4B/62F6 collision, and so never kills the 2 candidates -> the gameplay loop re-processes them.
- **The whole-scan is blocked on the `0x1c` and `0x1e` behaviors** (via the EFAE table at CS:EFC4,
  indexed by logic_id*2: `[0x1c]=8D4F`, `[0x1d]=B86D`, `[0x1e]=B909`).  Both are NON-trivial (deeper
  than B86D/B9F0), so this is not a quick handler slice:
  - `8D4F` (0x1c) is a **far-segment dispatch** -- `call far 1F8F:027A` (the movement is in the 1F8F
    overlay, outside the 1010 code) then `jmp BC4B`; 8D4F is itself a multi-entry table of
    `call far 1F8F:0xxx; jmp BC4B` sub-behaviors.  Recovering it means reversing the 1F8F routine(s).
  - `B909` (0x1e) is a **spawning** behavior -- sets DS:2308, calls the `B729` seek, conditionally
    calls `7476` (the formation spawn) and stamps `bp+50`, then `jmp BC4B`.
  Each needs its post-movement position for the BC4B/62F6 collision, so the movement half can't be
  skipped.  Recover each (1F8F:027A for 8D4F; B729+7476 compose for B909), verify per-slot with
  `verify_native_object_update_driver`, then rebuild the shared-store `native_object_scan`.  Lower
  priority than a fresh clean pillar (these are rare behaviors; the whole-scan's last ~2 slots/frame).
- **What IS verified + committed (do NOT re-derive):** the per-slot driver incl. collision
  death (`verify_native_object_update_driver`, sprite_deferred 0); the effect-loop in-place
  pass (`verify_native_object_pass_in_place`, L2/L3 0-div); the gameplay snapshot
  (`verify_native_object_pass`). Only the *combined whole-scan* is open.
- **Next (now precise):** recover the `0x1c` and `0x1e` object behaviors as native whole-slot
  handlers (movement + BC4B contact, like B86D/B9F0), via the EFAE/EFC4 behaviour dispatch; verify
  each per-slot with `verify_native_object_update_driver`; then rebuild the shared-store
  `native_object_scan` + `verify_native_object_scan` (the design is correct, only the missing
  scanners blocked it) and it should go byte-exact.

## 2026-07-04 — death/level-end FRAME exceeds the frame-verifier per-frame budget (replay caveat, not a bug)

Replaying `demo_play_tandy_player_death_20260618_233821` under the frame verifier TIMES OUT at
**frame 1805, IP 1010:32DB** (`FrameVerifyDivergence: FRAME VERIFY TIMEOUT ... budget=6000000`): the
death/explosion+scene FRAME runs >6M instructions. Not a recovery defect — a harness per-frame budget
limit at the transition frame. **Workaround:** witness transitions via the run-up (cap `max_frames`
just before the heavy frame). `verify_native_gameplay_transition.py` already caught the 4 DEATH-exit
frames at frames <1790. If a future slice needs to replay THROUGH a death/ending transition, raise the
`frame_budget` for that run rather than treating the timeout as a divergence.

## 2026-07-04 — lifted A940 attract branch (game_state.py ~150-154) mis-handles 98A5 > 1 (untested path)

The lifted ``run_frame_game_state_update_a940`` attract-mode branch (``DS:2356 == 5``) writes 98A5/98A3
unconditionally in the ``98A5 != 0`` arm, so for ``98A5 > 1`` it sets 98A5:=CL(0) + inc 98A3. The
ORIGINAL (driven-oracle, ``verify_native_a940_attract.py``) instead DECREMENTS 98A5 to 98A5-1 and
RESETS 98A3 to 0 (the ``1010:A9B3`` branch). This lifted bug is latent — NO gameplay demo runs 97B2
with ``2356 == 5`` (the in-game demo-playback mode), so it's never exercised in the suite. The PURE
``step_a940_attract_middle`` is correct (matches the original on all branches). If the lifted attract
branch is ever put on a witnessed path, fix it to match the pure rule (or delegate the lifted adapter
to ``step_a940_attract_middle`` + ``a940_speed_bucket``). Low priority (attract-only).

## 2026-07-07 — the 0x5A/0x5F diagonal AFD8 multi-step 1px divergence
Repro: implement F268 (0x5A: 3x AFD8, blocked->dir^=6 + 1 step) / F34D (0x5F: 4x AFD8,
dir-cycling on block) with `_afd8_step` per step and run
`python -m overkill.probes.verify_native_walk_demo demo_play_tandy_L3_full_20260617_202520`:
1-byte x divergences at frames 1366/2225 (0x5A, dir 1) and 1744/1764 (0x5F, dir 5) — native
x one MORE than the VM. Cardinal-direction records verify fine (0x56/0x57/0x58/0x4E all pass).
Suspect: the DIAGONAL B022 composition (axis1-then-axis2 with blocked accumulation) interacts
with the multi-step loop's break-at-block differently than contact_step_b022 models — drive
1010:F268 on the frame-1366 pre-state (bp=2A0C) and compare step by step.
UPDATE 2026-07-07 (investigation state): the pure contact_probe_afd8 EXACTLY matches the
ISOLATED driven F268 on frame 1366's pre-state (both: steps AC/1F -> AB/20 -> blocked at AB/21,
flip dir 7, step blocked -> BFC7 death).  But the RECORDED full-frame VM ends x=AC alive, and my
native full walk ends x=AD -- three different answers, so the discriminator is the MID-FRAME
BDD0 pool state (records dispatched before 2A0C move first; 215A verified IDENTICAL at 2A0C's
dispatch, order identical).  Next: log the BDD0 candidate scans (which record, which box) inside
rec 2A0C's step in BOTH the driven-original whole walk (scratchpad/cmp_215a_1366.py drives A9DD)
and the native walk, and diff the first differing candidate — suspect a hazard-window candidate
(beh 0x82..0x94, e.g. the 0x86/0x87 launchers) whose position or eligibility differs mid-frame.
RESOLVED 2026-07-07: NOT a diagonal-step bug -- the pure contact_probe_afd8 matched the
original exactly.  The 1px skew was the DEATH-EXIT POSTMOVE distinction: F2BA/F308/F381/F21B
exit `jmp BFC7` (no BC45 drift), while F1A6 (0x54/0x56's F194) exits `call BFC7; jmp BC45`
(the drift applies after the dying stamp).  Handlers now return died and the dispatch skips
_postmove_bc45 only for the jmp-BFC7 family.  L3 walk: zero divergence.

## 2026-07-07 — the 4CED star-list native model diverges (attempt reverted)
Repro: add _star_list_4ced (the journal's decode: undraw the old C7B1 list from the CS:[9598]
strip, rebuild via bx = [9A08+tick*2]+[234C]+xoff with the occupied-cell skip, write the strip
pixel + the FFFF-terminated list) at the pre-9B2E position in native_frame and run
verify_native_lockstep: diverged 3908 -> 5476 (WORSE, same count with/without the undraw — the
LIST VALUES are wrong, not the occupancy).  Suspects: the 9A08 row table may be CS-resident (I
read DS), the tick word's scale, the strip seg (9598 vs 9592), or the pass position vs [234C]'s
update.  Next: drive 1010:4CED on a cached frame pre-state and diff the produced C7B1 list
word-by-word against the model.
UPDATE (same day): the list ARITHMETIC IS PROVEN CORRECT -- driving the model on the frame-5
pre-state reproduces the VM's C7B1 list exactly (cell = DS:9A08[tick*2] + [234C] + xoff; the
9A08 table is DS-resident).  The flaw is the OCCUPANCY INPUT: the real 4CED runs MID-PRESENT --
tiles redrawn, sprites drawn, the old stars undrawn -- so `strip[bx] != 0` sees THAT strip, not
the frame-top strip my attempt read (stale stars/sprites -> wrong skips -> reordered lists on
frames that were otherwise clean).  Fix: the lockstep frame must compose the strip's star-pass
state natively first (compose_tile_window + object_sprite_blocks_a846 are already verified
native pieces) or replay the present order 5A7E/A846/4D64/4CED on the strip seg.  This is the
RENDER-integration slice of the lockstep campaign.

## 2026-07-08 — the 4CED star pass: the INSTRUMENT can't feed it (quantified)

Re-measured on the re-recorded (trustworthy) lockstep cache, PyPy, 8292 frames:

| native frame | exact | diverged | gapped |
|---|---|---|---|
| with `_star_list_4ced` | 1042 | 7950 | 328 |
| with the star pass DISABLED | 2733 | 5231 | 328 |

Divergence histogram (star pass off), frames affected per 256-byte region:
`DS:C7xx 4831` (the star DRAW LIST) then a long tail: `2300xx 488`, `C800xx 330`, `3300xx 293`,
`3500xx 268`, `6C/6D/56/34/A9/85/88 ~200 each`.

**So the star list alone is 4831 of the 5231 diverging frames — the single dominant item.  Fix it
and the lockstep frontier drops to ~400 frames of everything else.**

ROOT CAUSE OF THE BLOCK (traced today): `4CED` reads occupancy as `cmp es:[bx],0` with
`es = CS:[9598]` -- the **tile STRIP segment** (0x35FF in the L2 snapshot; linear 0x35FF0, i.e.
just ABOVE DGROUP's 0x25CC0..0x35CBF window).  The strip is therefore NOT in DGROUP, and
`_shadow_cache.iter_cached_frames` rebuilds a replay frame as *frame-0's full image + the rolling
DGROUP window + the tile plane* -- **the strip is frozen at frame 0**.  The gate physically cannot
hand the star pass its true input.  (The current `_star_list_4ced` reads that stale strip, which is
why enabling it ADDS ~2700 divergences: it also writes star pixels into a strip the VM has moved on
from.)

Two ways out, both legitimate:
* **(A) instrument**: extend the recorder to store the strip window per frame (dedup like the tile
  plane).  Costs cache size + a format bump (invalidates the walk caches; a PyPy re-record is now
  ~6 min, so this is affordable).  Gives ground truth to build against, incrementally.
* **(B) derive it** (the VM-less end state anyway): compose the strip natively each frame from the
  already-verified pieces -- `native_video/tile_row.compose_tile_window` (oracle-fit) + the A846
  sprite draw (`object_sprite_blocks_a846`) -- and run 4CED against that.  Needs no cache change:
  the produced `C7B1` list is compared against the VM directly, so a correct composition proves
  itself on 4831 frames at once.

**Chosen: (B), with (A) available if (B)'s first attempt needs a byte-level diff of the strip.**
Prereq to write down before coding: the strip's exact layout (stride/packing) as `5A7E`/`A7EB`
build it, and the fact that A846's compositors draw into `es = CS:[9598]` (hooks.py:2407/3119 set
exactly that) -- i.e. sprites land in the SAME strip the star pass probes.

### 2026-07-08 (same day, continued) — the strip is DERIVABLE, so (B) is verifiable per-frame

Geometry nailed down from the image: `DS:9A08` is a scanline table with a **uniform stride of
0x68 = 104 bytes**, and the strip is 4bpp packed (2 px/byte) -> **104 * 2 = 208 px**, exactly the
playfield width the 1:1 instrument already uses (`x in [0,208)`).  A star cell is
`bx = [9A08 + tick*2] + [234C] + xoff`; the ring entries carry `px` in {0x0F, 0xF0, 0x07, 0x70},
i.e. ONE nibble = one pixel (0xF0 = left pixel of the byte, 0x0F = right).  Occupancy is a whole
BYTE test (`cmp es:[bx],0`), so a star is plotted only where BOTH pixels of that byte are
background.

The decisive argument for (B) over (A): **the lockstep gate runs each frame independently from a VM
pre-state**, so a native strip that is *evolved* across frames (tile rows written at pull time,
stars drawn/undrawn) can never be reconstructed inside one replayed frame -- option (A)'s recorded
strip would be needed forever.  But the strip 4CED actually probes is *derivable state*: at that
instant it holds **tiles + sprites and no stars** (4D64 undraws the previous list immediately
before the rebuild).  Both are pure functions of DGROUP: tiles from the plane + `[2350]`/`[234E]`
(`compose_tile_window`, oracle-fit) and sprites from the object pools (`object_sprite_blocks_a846`,
byte-exact vs 7596).  So the native frame can COMPUTE occupancy from scratch every frame, with no
cache change and no cross-frame state -- and the produced `C7B1` list is then compared against the
VM's own, proving the whole composition on 4831 frames at once.

Next concrete step (the slice): a driven-oracle probe `verify_native_star_strip.py` that, on a few
cached frame pre-states, drives the ORIGINAL `4CED` and compares (a) our derived occupancy byte for
every one of the 40 ring stars against the VM's `es:[bx]`, and (b) the resulting `C7B1` list.  Get
that byte-exact FIRST (small, fast, unambiguous), then lift it into `native_frame`'s present half.
Open sub-questions for that probe to answer: the `xoff` range (observed 0x02..0x1F -- byte column or
pixel?), and whether the HUD/panel area is excluded from the star band.

### 2026-07-08 — TOOLING REGRESSION: `scripts/lindis.py` is broken by the dos_re bump

`lindis` derives each instruction's length by counting `cpu.fetch8()` calls.  dos_re commit
`a062020` ("cpu: inline modrm/displacement fetches") means step() no longer routes modrm/disp
bytes through `fetch8`, so the counter reads 1 and lindis advances ONE byte per instruction --
every listing after the first instruction is garbage (it silently mis-decodes; it does not error).
Repro: `python scripts/lindis.py artifacts/demos/demo_play_tandy_L2_full_20260617_180221/snapshot
1010 A846 A890` -> one byte per line.  Workaround used today: dump raw bytes and hand-decode.
Fix options: (a) length = IP delta when CS is unchanged and the delta is 1..15, with a small
explicit table for the control-transfer opcodes (E8/E9/EB/70-7F/E0-E3/EA/9A/C2/C3/CA/CB); or
(b) ask dos_re for a decode-only entry point.  **Until fixed, do not trust lindis listings.**

### 2026-07-08 — the star pass: ORDER CONFIRMED from the call sites (hand-decoded)

* `1010:A876`: `e8 74 a4` = **call 4CED**, placed AFTER A846's per-object sprite loop
  (`e2 eb` at A874).  So the stars are drawn at the END of the DRAW SCAN.
* `1010:A93C`: `e8 25 a4` = **call 4D64**, placed AFTER A90C's scan loop.  So the previous frame's
  stars are UNDRAWN in the PRESENT SCAN, i.e. after the blit.

Therefore, at `4CED` entry the strip contains exactly **tiles + all sprites, and no stars** -- and at
our 9B2E lockstep boundary it contains the same thing.  That is precisely the derivable state, so
the model needs no strip recording.

**Model validated (scratch, 3 snapshots):** derive the strip window as
`pack(compose_tile_window)` + `object_sprite_blocks_a846` rasterized at `di + r*0x68 + c`
(strip-space; `di` is already cursor-relative), then compare against the VM's strip window
(`[234C]` is always row-aligned: `scroll % 0x68 == 0`, so window row 0 = `scroll // 0x68`):

| snapshot | tiles only | tiles + sprites |
|---|---|---|
| L2 | 0 mismatch (empty sky) | 64 (phantom: sprites not yet in the strip at this capture point) |
| L3 | 1193 mismatch | **59** |
| L4 | 0 (empty sky) | 64 (same phantom) |

The residue is a TIMING artifact of comparing at a snapshot's capture boundary rather than at
4CED.  Do NOT step a bare `cpu.step()` loop to reach 4CED: with no PIT interrupt the game spins in
its `0679` frame-wait forever (that is why the first attempt "never reached 4CED").

**Next slice (small, now unblocked by the new `trap=` harness kwarg):**
`verify_native_star_strip.py` -- run a demo through `run_ref_step_probe(..., trap={(0x1010,0x4CED)})`,
and at each trapped entry compare (a) the derived strip window vs the VM's real strip, byte for
byte, and (b) after driving 4CED, the produced `C7B1` list.  Byte-exact there == the 4831-frame
divergence family collapses when lifted into `native_frame`'s present half.

### 2026-07-08 — next lockstep targets (after the star pass + flash decay)

State: 6532 exact / 1432 diverging / 328 gapped (8292-frame L1 demo).

* **`1010:4FF9` (the player terrain-crash predicate) is WRONG in both directions.**  Found via the
  `DS:A95C` family: with `BEDC == 0` the VM drains 2/frame, we drained 1 -- because `9CB6` is a
  fall-through CALL CHAIN of four `9E19`s (9CCB/9CCE/9CD1/9CD4) entered by difficulty
  (0 -> 9CD1 = 2 calls, 1 -> 9CCE = 3, else 4).  Fixed.  What remains: on 7 frames our `4FF9`
  says crash where the VM says none (frame 4410) and vice versa (frame 3581).  The hand-decode of
  4FF9's head matches our model (pose >= 3 -> stc; the 214E pose hitbox offset; probe + 0x0D; the
  `[215A] & 0xF > 0xA` two-column widening), so the bug is in the tail we have NOT decoded past
  `e8 28 00 / 75 1c / f7 46 04 0f ...`.  **Do this with a driven-oracle probe** (the tile-cue
  recipe): load a cached pre-state, `bp = 0x237C`, drive the original 4FF9 to its `ret`, read CF,
  and compare against `_terrain_crash_4ff9` over many frames.  Cheap, definitive.
* **The `DS:6C94..6CF6` cluster** (249 frames): entries spaced 8 bytes, and there are NO direct
  writers (`mov [6C94],..` etc. find nothing), so it is written through a pointer / `es:di`.  It is
  NOT the strip (the L1 strip segment is 0x32FF, so its window starts at `DS:D330`).  Identify it by
  trapping writes to that range on the ref VM (a `trap=` probe that watches the linear range) and
  reporting the writing CS:IP.
* Then: `33xx / 34xx / 35xx` (293 / 217 / 268 frames), `56xx` (222), `85xx` (190), `83xx` (172),
  `62xx` (171).
* Still declared gaps: the `77C5` shield body (266 frames) and the `9EE4` drain beat (62).

### 2026-07-08 — IDENTIFIED: the `DS:6Cxx/6Dxx` family is the SPRITE BUFFER (and it lives in DGROUP)

Caught the writer by running the cold-start demo to the first diverging frame (97B2 frame 4205) and
then single-stepping that one frame with a watch on `DS:6C00..6E00`:

    writer 1010:A85B   (the `call 5AC8` at A858, inside A846's per-object loop)
    es = 25CC (== DS!)   di = 6D14   ->   linear 02C9D4
    CS:[9598] strip = 32FF     CS:[95A4] page = B800     CS:[95BC] mode = 2

So **the sprite compositor blits into a DGROUP-resident buffer**, not into the tile strip
(`CS:[9598]`).  That independently confirms the star gate's finding -- the strip carries TILES only,
which is exactly why `verify_native_star_strip` passes with a tiles-only model.  The frame's
composition is therefore: tiles -> the strip; sprites -> a DGROUP buffer around `DS:6C00+`;
`5BDC` merges both into `B800`.

Consequence for the lockstep gate: that sprite buffer is INSIDE the compared DGROUP window, and the
native frame never writes it -- hence the `6C00xx 249` + `6D00xx 223` families (~470 frames).

**Next slice**: model A846's blit into DGROUP.  We already own the pieces (`object_sprite_blocks_a846`
gives per-object blocks with `di`, `pixels`, `opaque`, and the `mask` / `or_inverted` ops).  Two
things to settle FIRST, with a driven-oracle probe rather than by guessing:
1. the buffer's row stride (is it the same 0x68 as the strip?) and its extent;
2. whether `5AC8` (A846's loop) DRAWS the sprites and `5A92` (A90C's loop) ERASES them, or the
   reverse -- the values written (0x77/0x88/0xF7) look like sprite pixels, but the net per-frame
   effect must be non-zero (we observe diffs at the 9B2E boundary), so the pairing matters.
Note `object_sprite_blocks_a846` needs a SpriteDrawContext built from the asset bundle today; for an
image-only native frame the banks must be read from the image instead.

### 2026-07-08 (cont.) — the DGROUP sprite region is a SAVE-UNDER BACKING STORE

Trapping `5AC8` (A846's loop) and `5A92` (A90C's loop) on the cold-start demo at the first
diverging frame shows the real shape:

    5AC8: es=B800 di=1210 bp=237C  +16typ=3   <- the PLAYER draws straight to the visible page
    5AC8: es=25CC di=3554 bp=2654  +16typ=4   <- every other object: es == DS, di ADVANCES
    5AC8: es=25CC di=6F94 bp=25E4
    5AC8: es=25CC di=7214 bp=25AC
    5AC8: es=25CC di=7494 bp=2574
    5AC8: es=25CC di=7714 bp=24CC   (+0C == FFFF, i.e. culled, and it STILL writes)
    5A92: es=B800 di=1EA0 bp=237C            <- A90C restores: player -> page
    5A92: es=32FF di=6156 bp=2654            <- others -> the STRIP

`di` marching 0x3554 -> 0x7714 across objects is not a screen coordinate; it is a cursor into a
~16 KB DGROUP **backing store**.  So A846 SAVES the background under each sprite into DGROUP (and
draws), and A90C RESTORES it.  The bytes we see diverging (0x77/0x88/0xF7 -- terrain greys) are
saved BACKGROUND, not sprite pixels.

**Consequence, stated plainly:** the `6Cxx/6Dxx` families (~470 frames) cannot be closed by
modelling the sprite blit alone.  They require the native frame to own the PAGE composition (the
strip + B800 content the save-under copies from), because the saved bytes are a function of what is
on the page at that instant.  That is the render-integration slice -- the same work the play_native
unification needs anyway -- not a small fix.  Do NOT attempt it as a patch; scope it as its own
campaign step, oracle-first (compare the backing store byte-for-byte after A846 on real frames).

Remaining lockstep frontier after that: `33xx/34xx/35xx` (293/217/268 frames -- likely the same
backing store's lower half), `56xx` (222), `85xx` (190), `83xx` (172), `62xx` (171), the `4FF9`
predicate (7 frames), and the two declared gaps (77C5 shield body 266, 9EE4 drain 62).

### 2026-07-08 (cont.) — `4FF9` is CORRECT; the A95C symptom is an UPSTREAM (scroll) divergence

Driven-oracle check (load each cached pre-state into a hookless VM, `bp = 0x237C`, drive `4FF9` to
its `ret`, read CF; compare with `_terrain_crash_4ff9`): **agree 59 / disagree 0** over sampled
frames 3000..5200.  So the predicate itself is right and is no longer a suspect.

What the A95C frames actually show (e.g. frames 3577-3580):

    DS:23A0  pre=06  vm=06  nat=04      <- the VM ran 9E19 (sets 23A0 = 8) and then A846 decayed 2
                                           back to 6; we did NOT run 9E19, so we only decayed 6 -> 4
    DS:236E/2370/2372  vm advanced, nat == pre
    DS:234C / 234E / 2350  diverge on the same ~7 frames

`4FF9` is called at `9BCA`, i.e. AFTER the move handlers and the `A66F` scroll.  Our predicate is
fed the state our own upstream stages produced, so a small scroll/anchor difference flips the crash
verdict, which then cascades into `9E19` -> `A95C` and `23A0`.  **The real bug is in the scroll /
history-ring stages, not in the damage chain.**  Next: trap `(CS,0x9BCA)` on the ref VM and diff the
anchor `237E/2380`, `234C/234E/2350`, `215A` against the native frame's values at the same point --
the first cell that differs names the stage.  (`236E..2372` looks like the 9CD9 history ring, whose
cursor we may be advancing differently.)

### 2026-07-08 (cont.) — the 23A0 flash: CORRECTED attribution, and the real open question

Instruction-level watch on `DS:23A0` (cold-start demo, frame 3576) gives the ground truth:

    @9E31  23A0: 06 -> 08      (inside 9E19 -- runs TWICE, the two 9CB6 calls at BEDC == 0)
    @9E31  23A0: 08 -> 08
    @A85B  23A0: 08 -> 07      (the sprite draw: ONE dec per DRAWN SLOT)
    @A85B  23A0: 07 -> 06

So a frame where the player is crashing looks like `pre 6 -> set 8 -> dec 2 -> 6` (delta 0), and a
frame where it is not crashing is `6 -> dec 2 -> 4` (delta 2).  That is exactly the 216/216 split
observed, and it is NOT a parity.

**CORRECTION to the earlier commit (9e9d38f):** I attributed the dec to the compositor prologues at
`25AE / 30FF / 4227`.  Trapping those three addresses shows they NEVER EXECUTE on this path -- the
dec really happens inside the routine reached from `A858 call 5AC8` (its return address is A85B).
The *model* (one dec per drawn slot, two for the anchor's two slots) is right and measured; the
cited addresses were not.  The native `_flash_decay_a846` stays as-is.

**The remaining bug is upstream and precise:** at `9BCA` our `_terrain_crash_4ff9` returns False on
frames 3577-3580 where the VM's returns True, even though a cell-by-cell diff at that exact point
(`237E/2380/234C/234E/2350/215A/2384/A278/A47E/A33A/98BE`) shows ZERO mismatches, and a driven-oracle
check of 4FF9 on frame-top states agrees 59/59.  Therefore 4FF9 reads an input we have NOT compared.
Candidates, in order: the tile PLANE bytes (seg `[9592]` -- the replay overlays it, but check the
row the probe lands on), the class table at `DS:C3AA`, and `[215A]`'s exact sub-tile phase.
**Next probe:** at `(CS,0x9BCA)`, dump the 5073 probe's full inputs AND its computed
`tile_offset`, plus `plane[offset+0xD]` / `plane[offset+0xE]` and their class bytes, from BOTH sides.
The first differing input names the stage that corrupted it.

### 2026-07-08 (cont.) — the FULL divergence accounting (8292-frame L1 demo)

    1432 diverging frames
      1362  video memory ONLY   (save-under backing store DS:3300..9592, tile strip DS:D330..)
        70  touch a non-video cell, of which:
              7  death/respawn TRANSITION frames -- the VM runs the 9908 continuation inside the
                 window (A95A FFFF -> 3, A97A 0x57 -> 1, 2384 0x0E -> 0); the native frame returns
                 at the exit by design, so these can only close when the exit continuations land
             63  the D50E sound-channel block (BFB0/BFB1 period, BFB2/BFB8 counters, BEFE) and a
                 small DS:959B..95A0 family

**Verified along the way (do not redo):**
* 2 INT8 ticks per 9B2E frame -- confirmed by the per-frame delta of `[0054]` and `[BF00]` (+/-2,
  both mod 4).  An earlier count of "4" was an ARTIFACT of patching `CPU8086.step` class-wide, which
  counts BOTH the ref and cand CPUs.  When instrumenting, patch the ref instance only.
* All INT8 ticks are delivered while the CPU spins at `1010:0679` (the frame-wait), i.e. after the
  60A2 clock stage -- which is exactly where `_isr_effects_two_ticks` already runs them.  So the
  sound residue is a MODEL bug in the D50E interpreter, not tick placement.
* Sound queue example (frame 4821): the VM has `BEFF = 0x0D` where we have 0.  `mov [BEFF],0Dh`
  exists only at `9DE4`, inside `9DB9`, whose callers are `9A1B` and `C4B3` -- neither is the AB00
  pickup table.  That frame is a respawn frame, so the queue came from the respawn path.

**Priority now:** (1) the video model (1362 frames; also unblocks play_native's unification);
(2) the D50E channel-step bug (~63 frames -- one frame shows `ch2 +9 status` vm=0 / nat=2, i.e. our
fetch took the NOTE path where the VM took REST: check the `0x80..0x85` op dispatch and the
`>= 0xE0` duration prefix against a driven trace of D5AC); (3) the exit continuations (7 frames).

### 2026-07-08 (cont.) — the D50E INTERPRETER is exonerated; the sound residue is an upstream QUEUE difference

Driven-oracle check: load each cached pre-state into a hookless VM, drive the ORIGINAL `1010:D50E`
TWICE (the proven two ticks per frame), and diff `DS:BEFE..BFD0` against
`native_frame._sound_engine_tick_d50e` run twice on the same pre-state.

    driven-vs-model: checked=601  mismatching=0

So the bytecode interpreter (op dispatch, the >= 0xE0 duration prefix, note/rest/slide/pitch,
the BFCA effect seed, the lower-id-preempts priority) is byte-exact, and my previous suspicion
("our fetch took NOTE where the VM took REST") was WRONG -- that symptom is downstream.

Therefore the ~63 sound-cell frames differ because **a different value stood in `DS:BEFF` when the
tick ran**: some frame path queues a sound in the VM that our frame does not (or vice versa).  The
tick placement is already right (all INT8 ticks land at the `0679` frame-wait, after the 60A2 clock
stage, which is where we run them).

**Next step for this item:** capture `BEFF` immediately BEFORE the ISR ticks on both sides (native:
the existing `_AT_9BCA`-style debug hook, moved/duplicated just before `_isr_effects_two_ticks`;
VM: trap `(CS,0x0679)`) and diff.  The first frame where the queued id differs names the missing
sound-emitting path.  Note the known emitters we gap: `77C5` (shield body) and `9EE4` (drain), and
the respawn path reached via `9A1B -> 9DB9` (sound 0x0D).

### 2026-07-08 (cont.) — corrected extent + the sound residue is NOT the interpreter and NOT the queue

Two more suspects eliminated by measurement (not by reading code):

* **The queue is identical.**  Capturing `DS:BEFF`/`BEFE` at the exact moment of the tick on both
  sides (VM: trap `(CS,0x0679)`; native: a spy around `_isr_effects_two_ticks`) gives
  `frames compared = 2710, differing = 0`.  So no path queues a different sound.
* **The tick count is 2.**  Per-window ISR-entry counts (ref instance only): `{2: 8284}` with 8
  outliers (four windows of 402 ticks -- level-load stalls -- plus 0/1/7 once each), and
  `18558` of `18565` ticks fire while spinning at `0679`.

**Extent correction:** the save-under backing store runs past `0x9592` -- `DS:9598..95A1` hold pixel
bytes (0x88/0x8F/0xF7), not the CS-side segment cells they resemble.  With the video window taken as
`DS:3300..95FF` plus the strip `DS:D330..`:

    1432 diverging frames = 1373 video-memory only  +  59 touching sound cells (BFAC/BFB0/BFB2/
                                                       BFB8/BFC0/BFC2/BEFE)

So the sound residue is a small, isolated family that is neither the D50E interpreter (601/601
byte-exact vs the driven original) nor the queue nor tick placement.  The remaining hypothesis is
the ORDER of the two ticks relative to the frame's own sound-cell writes on frames where the game
starts/stops an effect in the same window (e.g. around death/respawn, where `9A1B -> 9DB9` queues
0x0D).  **Next:** trap `(CS,0x06E5)` and dump `BEFE/BFAC/BFB0/BFB2` immediately before and after
each of the two ticks on a diverging frame, and replay our two ticks over the same pre-state --
the first field that parts company names the ordering constraint.

CAVEAT for whoever picks this up: my scratch classifier had an operator-precedence bug
(`post[c] | (post[c+1] << 8) == 1`), so any "transition vs other" split quoted before this entry is
unreliable.  The video/non-video split above was re-measured and is sound.

### 2026-07-08 (cont.) — THE VIDEO MODEL, fully specified (the last 1373 frames)

Disassembly + trap evidence give the whole pipeline.  `A846` is three phases, not one:

    A846  loop over 8D12 (cx=0x22):  call 5AC8   -> SAVE-UNDER
          call 4CED  (A876)                      -> draw the stars into the strip
          loops at A8BE / A8F1 / A908: call 7596 -> DRAW the sprites into the strip
    5BDC  blit strip -> B800
    A90C  loop over 8D12 (cx=0x22) + 32CA (cx=0x24): call 5A92 -> RESTORE the saved background
          call 4D64  (A93C)                      -> undraw the stars

`5AC8` and `5A92` are jump tables indexed by `[bp+0x14]` (the DRAW TYPE, 1 or 2) plus `3 * mode`
(`CS:[95BC]`, = 2 for Tandy), i.e. `word [CS:5AE2 + (type + 6)*2]` and `[CS:5AB6 + (type + 6)*2]`:

    draw type 1 -> save 35CC   restore 34D8
    draw type 2 -> save 356C   restore 34AD   (the player's dual-slot form)

`35CC` decoded:

    call 5A36                 ; project screen_di
    mov [bp+0Ch],ax           ; store it
    cmp ax,FFFF / ret         ; culled -> nothing saved
    add ax,[234C] ; mov [bp+0Ch],ax
    mov si,ax                 ; SI = source, in the STRIP
    mov di,[bp+0Eh]           ; DI = this record's SAVE-BUFFER pointer  <-- +0x0E is NOT a link key here
    mov es,cs:[9596]          ; ES = DGROUP
    mov ds,cs:[9598]          ; DS = STRIP
    mov bx,0x60
    16 x { movsw x4 ; add si,bx }   ; 8 bytes (16 px) per row, source stride 0x68, dest packed
    mov ds,cs:[9596] ; ret

`34D8` is the mirror (16 rows, `add di,bx`), with `5A92` setting `es = CS:[9598]` (strip),
`di = [bp+0Ch]`, `si = [bp+0Eh]`.

**Net effect at our 9B2E boundary** (after A90C): the strip holds TILES ONLY (stars undrawn,
sprites restored) -- which is exactly what `verify_native_star_strip` measured -- and each record's
save buffer at `[rec+0x0E]` holds the 16x8 block of terrain that was under it THIS frame.  That
buffer is the entire remaining DGROUP divergence.

**So the native frame can close it without any page emulation:** for each record in the A846 order,
if its projected `screen_di != FFFF`, copy 16 rows x 8 bytes from the DERIVED terrain window (we
already build it byte-exact for the star pass) at `screen_di + row*0x68` into DGROUP at
`[rec+0x0E] + row*8`.  Draw type 2 does it for both slots (`+0x0C` and `+0x10`).

Verify FIRST with a driven-oracle probe (trap `(CS,0xA876)`, i.e. after the save loop, and compare
every record's saved 128 bytes against ours) before wiring it into `native_frame`.

### 2026-07-08 (cont.) — the final 61: three named families

Lockstep after the video model + the 8209 leak fix: **8231 exact / 61 diverging / 0 gapped**.

1. **~15 frames: the save-under SOURCE on row-pull frames.**  Ruled out by measurement:
   * the projection is exact -- our `sync_screen_projection` matches the VM's freshly re-projected
     `+0x0C`/`+0x10` at `A876` on **33239 records, 0 mismatches** (so it is not a cull difference);
   * the save geometry is exact (443 records verified earlier).
   Running our `_save_under_a846` on the VM's own pre-A846 state and diffing `DS:3300..9600` gives
   **40 mismatching frames out of 3001**, in BOTH directions (`vm=0F nat=00` and `vm=00 nat=77`).
   So on those frames the strip is not exactly our derived terrain stack.  They are almost certainly
   the ROW-PULL frames: A7EB writes the new band using the PRE-advance `[2350]`, while
   `_terrain_stack` renders from the POST-advance `[2350]` with the `[234E]` phase.  **Next:** at
   `(CS,0xA876)`, dump `[2350]`, `[234E]`, `[2352]` and the first mismatching row for a failing
   frame; compare against the band A7EB just wrote.
2. **~31 frames: the D50E sound-channel cells** (BEFE/BFAC/BFB0/BFB2/BFB8/BFC0/BFC2).  Already
   exonerated: the interpreter is byte-exact vs the driven original (601/601) and the queue is
   identical at the tick (2710/2710).  The remaining hypothesis is the ORDER of the two ticks
   relative to the frame's own sound writes when an effect starts/stops in the same window.
3. **7 frames: death/respawn transitions.**  The VM runs the whole `9908` continuation inside the
   window (A95A FFFF -> 3, A97A 0x57 -> 1, 2384 0x0E -> 0); the native frame returns at the exit by
   design.  These close when the exit continuations are composed into the frame.

**Fixed this pass:** 8209's "+32/+34 caller-frame leak" is not a leak -- at the `A839` call site
`bp` is still `0x237C` (the anchor record set at 9B5B), so `ss:[bp+2]`/`ss:[bp+4]` ARE the player's
x and y (trapped `(CS,0x7948)`: bp = 237C on every hit).  Passing zeros had left every cue-spawned
record with `+0x32/+0x34 = 0`; that was the entire 47-frame "per-record state" family.

### 2026-07-08 (cont.) — REJECTED: reading the ring mirror's source for above-DGROUP strip bytes

The save-under's last save-buffer family (21 frames) comes from reading strip bytes that sit ABOVE
DGROUP's 64K window, where the replayed bytes are stale.  Tempting idea: A7EB duplicates each pulled
band at `+0x5480`, so `strip[off] == strip[off - 0x5480]` and the source often IS inside DGROUP.

**It does not hold, and the gate said so.**  Wiring it (guarded on `off >= 0x5480`) gave
`8106 exact / 186 diverged` versus `8260 / 32` -- strictly worse.  Reason: only the FRESHLY PULLED
band is mirrored on any given frame; the rest of the duplicate region holds whatever older bands
were copied there at their own pull times, so the two halves are equal only for the newest band.
(An earlier, sloppier version of the same idea -- guarding on the PHYSICAL address rather than the
strip offset -- was catastrophic: 589 exact.  Guard on `off`, not on `phys`, if anyone retries.)

So the remaining 21 frames need the strip's above-DGROUP bytes to be DERIVED correctly, i.e. the
band ladder for stack rows beyond what `compose_tile_window` renders.  `_terrain_stack` renders 14
bands from `row_base - s*0x0D`; rendering more bands underflows the plane row (measured: 8096
exact).  The right move is to work out which plane row each above-DGROUP strip row actually holds --
trap `(CS,0xA876)` on a failing frame, read the VM's strip bytes at the failing offsets, and match
them against `render_tile_row` for candidate plane rows.

### 2026-07-08 (cont.) — MEASURED: the stack ladder does not extend ABOVE the visible window

Trapping `(CS,0xA876)` on the first failing frame (3982: `row_base=0x057C`, `phase=0`,
`scroll=0x4E00`, `strip_seg=0x32FF`) and matching the VM's strip row against `render_tile_row` for
every candidate plane row:

    rec=24CC dt=2 slot=0 di=47D8 row=0  ->  t = -16  (one band ABOVE the window)
    our model: stack row start+t = 0    -> band 0 = plane row 0x057C (row_base)
    the VM:    that strip row IS band 3 = plane row 0x0555 (row_base - 3*0x0D)   <-- exact match

So `compose_tile_window`'s ladder (`band s = row_base - s*0x0D`, window = `stack[16+phase ...]`) is
right for the 192 visible rows -- the star gate proves that byte-for-byte -- but it is NOT the strip's
physical order above the window.  The reason is that `[234C]` steps by `CS:[959E] = 0x68` EVERY frame
while a band is only WRITTEN every 16th frame (at the pull), so which physical strip row sits above
the window depends on how many frames have passed since the pull; the ring wraps at
`0x5480 / 0x68 = 208` rows.  Extending the ladder naively (or mirroring at -0x5480) both got refuted
by the gate.

**Do not extend the stack.**  The correct model is the ring itself: a strip row is written once per
pull at `[234C] - 0x680` with the then-current `[2350]`, and thereafter only the cursor moves.  So
the band living at physical strip row `R` is `row_base - ((R_pull_distance) * 0x0D)`, computable from
`[234C]`, `[234E]` and the pull cadence.  Derive that mapping (a small amount of algebra against the
measurement above), or -- simpler and exact -- record the strip's above-DGROUP window in the shadow
cache so the replay can read it.  These are the last 21 save-buffer frames.
