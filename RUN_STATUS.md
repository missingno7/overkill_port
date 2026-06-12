## 2026-06-12 PC speaker timing cadence fix

Investigated two sound-related Tandy snapshots:

- `artifacts/snapshot_play_tandy_20260612_151420`: level-select/menu state after
  pressing `D`.
- `artifacts/snapshot_play_tandy_20260612_151523`: gameplay state where Space
  produced firing sound but no visible projectile.

Findings:

- Both snapshots have the optional far sound-driver flag disabled
  (`DS:0055 == 0`), so the observed speaker writes come from the always-run
  timer helper path (`1010:06E5 -> D50E`), not the `[0055] == 1` far sound
  branch at `2032:0000`.
- Old synthetic timer versus new real-ISR timer produced the same video CRC and
  sampled object-table state after the Space input.  The "sound but no
  projectile" state therefore is not introduced by the PC speaker ISR change;
  it remains a gameplay/input-state investigation target.
- The sound-duration issue did expose a pacing mismatch: OVERKILL programs PIT
  divisor `0x4000`, so the ISR cadence is about `72.8 Hz`, and the `0679` wait
  normally releases every two ISR ticks, about `36.4 Hz`.  The interactive
  player default was still `30 Hz`, stretching timer-driven sounds by roughly
  20%.

Fix:

- `CPU8086.timer_ticks_elapsed` records how many real ISR ticks the `0679` hook
  delivered before `CS:066B` advanced.
- `scripts/play.py` now paces gameplay from PIT-tick units rather than assuming
  one synthetic frame tick.
- Default `--game-hz` is now `36.4`, matching the original effective timer
  cadence; internally the pacer runs at `--game-hz * 2` and sleeps for the
  delivered ISR-tick count.

Verification:

```text
python scripts\run_tests.py
# 141 passed, 0 failed
python scripts\play.py --snapshot artifacts\snapshot_play_tandy_20260612_151523 --verify-frames --verify-frame-max 60
# FRAME VERIFY OK frames=60
```

Note: `snapshot_play_tandy_20260612_151420` times out in the reference frame
verifier after frame 1 because it is in an input/menu wait path at `1010:D439`.

## 2026-06-12 AC97 object-slot scan lift

Absorbed the hot `1010:AC97` scan from
`artifacts/snapshot_play_tandy_20260612_192438` into
`overkill_object_slot_scan_ac97`.

Findings:

- The slowdown is a read-only gameplay object-slot loop body, not asset-codec
  work.
- It walks 35 records at `DS:23B4` with a `0038h` stride, one slot per hook
  call.
- It skips empty records and records with `+24h == 1` or `+20h == 1`.
- It performs the observed signed Y/X window checks and the `SS:[BP+14]`
  compare before advancing `BX/CX` and re-entering `AC97`.

Status:

- Hook lifted.
- Regression test added against `artifacts/evidence/ac97_stop`.

## 2026-06-12 BCB1 clamp leaf lift

Lifted the hot `1010:BCB1` clamp leaf from the BC4B post-move path.

Findings:

- The routine only clamps `SS:[BP+4]` into `0..00C0h`.
- It is a repeated leaf reached from the `BC4B` post-move path.
- The replacement returns to the `BC4E` continuation just like the original.

Status:

- Hook lifted.
- Regression test added against `artifacts/evidence/bc4b_stop`.

## 2026-06-12 BC4B post-move call-site lift

Absorbed the full hot `1010:BC4B` post-move call-site from the same gameplay
snapshot.

Findings:

- The block clamps Y, applies the X bounds, performs the BCCB contact check,
  folds the observed AA71 contact-window helper including the AAAB -> AA44
  upper tail, runs the optional BFC7 death tail, does the 9E69 bookkeeping,
  and finishes with the 62F6 overlap scan.
- The remaining 62F6 early exit for signed `SS:[BP+2] < 0x20` preserves the
  compare flags and incoming `BX`; it does not fall through to the empty-scan
  sentinel.
- The call-site was the last large interpreted block in that path.
- The hook now returns to the outer caller after completing the whole helper.

Status:

- Hook lifted.
- Regression test added against `artifacts/evidence/bc4b_stop`.

## 2026-06-12 AA71 upper contact tail lift

The same BC4B snapshot also hit the higher `1010:AA71` branch that survives
the signed X guard and then takes the `AAAB -> AA44` success tail.

Findings:

- The helper reuses the `SS:[BP+2] + 18h` compare against `DS:237E`.
- The path clears carry and returns without mutating object state.
- The remaining unobserved AA71 branches stay fail-fast.

Status:

- Lifted into the shared contact-window helper.
- Regression test added against `artifacts/evidence/next_frontier_probe_4`.

## 2026-06-12 BFC7 shared C054 call for logic 003B

`snapshot_play_tandy_20260612_223501` reached `BC4B -> 62F6 -> BEC5 third counter zero -> BFC7` with `logic_id=003Bh`.  The original trace shows this is not a new bespoke branch: `BFC7` calls the shared `C054` selector before the state transition, and `003Bh` simply falls through to the default `AX=A4E4h` selector.  `C01B` then overwrites the flags with the `DS:98C0` compare and `C027` overwrites `AX` with the original logic id.

Status:

- `BFC7` now calls the shared lifted `C054` selector instead of whitelisting only `0012h/002Bh/0031h`.
- `003Bh` completes the same death/transition tail without decrementing `DS:A47E`.
- Regression test added for the `003Bh` path with `DS:98C0 != 0`.

## 2026-06-12 BFC7 no-counter branch lift

The `BFC7` death/transition tail now covers the current observed `0012h`,
`002Bh`, and `0031h` branches from the same BC4B snapshot.

Findings:

- Those branches take the same state transition as the verified death tail.
- None of them decrement `DS:A47E`.
- The replacement now keeps that family in the observed no-counter path instead
  of failing fast.

Status:

- Lifted into the shared collision tail.
- Regression tests cover the three observed logic ids.

## 2026-06-12 BD17/C054 dispatcher lift

The same BC4B tail also reaches `1010:BD17`, whose `C054` dispatcher now
selects the observed `0000h/0013h -> A4E4h` branch and preserves the `BD5F`
stack scratch below the final return word. The newer `draw_layer=5,
logic_id=0000h` path also returns cleanly after clearing the active flag, so it
is no longer a frontier either.

## 2026-06-12 BEC5 variant 000C tail lift

The same shooting path also reached `1010:BEC5` with `variant=000Ch`.

Findings:

- The BEC5 variant table routes `0007h`, `0008h`, `000Ch`, and `0009h` to the
  shared `BFB9` tail.
- Returning to the original interpreter at `BFB9` is enough to preserve the
  live state for that branch.
- The helper now preserves that branch instead of failing fast.

Status:

- Lifted as a shared-tail dispatch.
- Regression test added for the `000Ch` variant.

## 2026-06-12 BEC5 sprite 0033 BF21 continuation

The latest snapshot also hit the `sprite=0033h` branch inside `1010:BEC5`.
That branch falls through into the shared `BF25` counter logic in the original
code instead of failing fast, and the `third counter zero` tail then continues
through the shared `BF4B -> BFC7` score/death path.

Status:

- Hook updated.
- Regression tests added for the observed sprite fallthrough and `BF4B` tail.

Findings:

- The draw-layer-4 / `logic_id=002Bh` path clears the active flag, enters the
  C054 dispatcher, and the observed `0000h`/`0013h` selector branches return
  `A4E4h` without touching `DS:A47E`.
- The stricter fail-fast only belonged to the smaller counter-decrement family,
  not to the current gameplay snapshot.
- This removes the last crash in the current BC4B/BD17 tail without widening
  the hook to a guessed general rewrite.

Status:

- Hook updated.
- Regression test added for the observed `002Ah` fallthrough.

## 2026-06-12 BFC7 002B branch lift

The same BFC7 tail now also handles the observed `logic_id=002Bh` branch
without dropping `DS:A47E`.

Findings:

- The `0020h` branch remains the one that decrements the live counter.
- The current `002Bh` branch follows the same death/transition state update,
  but skips the counter drop.
- This removes the next crash from the current snapshot without guessing at a
  broad rewrite of the whole dispatcher.

Status:

- Hook updated.
- Regression test added for the observed `002Bh` no-counter path.

---

## 2026-06-12 PC speaker timer-ISR enablement

Enabled PC speaker sound during interactive play by letting the `1010:0679`
timer-wait hook run OVERKILL's installed INT 08h handler when the vector points
to the known game ISR at `1010:06E5`.

Findings:

- The speaker backend from the previous pass was correct, but normal play still
  produced no sound because `1010:0679` only synthesized `CS:066B`.
- Delivering the real INT 08h handler from
  `artifacts/play_tandy_main_menu_20260612_132548` produced the expected
  speaker writes: PIT mode `43h=B6h`, divisor bytes through `42h`, and speaker
  enable through `61h=03h`.
- The ISR chains the old BIOS timer every fourth tick via `JMP FAR CS:[0738]`.
  In this VM the saved BIOS vector can be `0000:0000`, so the hook stops at the
  known chain point after the game-side sound/tick work and restores the
  interrupt frame locally.

Changes:

- `1010:0679 overkill_wait_timer_tick_0679` now runs the original game timer ISR
  when INT 08h is installed as `1010:06E5`, delivering bounded real ISR ticks
  until the original `CS:066B` wait flag advances.
- If the expected ISR is absent, the hook fails fast; it no longer invents a
  synthetic `066B` tick.
- Added a regression using the Tandy menu snapshot that proves the timer hook
  emits `42h/43h/61h` speaker writes and safely handles the fourth-tick BIOS
  chain path.

Verification:

```text
python scripts\run_tests.py
# 128 passed, 0 failed
python scripts\play.py --snapshot artifacts\play_tandy_main_menu_20260612_132548 --verify-frames --verify-frame-max 40
# FRAME VERIFY OK frames=40
python scripts\play.py --snapshot artifacts\play_tandy_edrax_orbit_combat_20260611_232258 --verify-frames --verify-frame-max 40
# FRAME VERIFY OK frames=40
```

---

## 2026-06-12 Tandy gameplay rendering regression fix

Investigated `artifacts/snapshot_play_tandy_20260612_141644`, where gameplay
rendering broke after the PC speaker pass.

Findings:

- The PC speaker changes were not on the failing path: a 900K-instruction probe
  from the snapshot saw `0` reads of port `61h` and `0` writes to `42h/43h/61h`.
- Frame verification diverged at frame 48.
- Hook bisection showed the regression was `1010:33AF
  overkill_expand_tandy_list_33af`, not the recent sound/backend code.
- The composed `33AF` parent hook was only verified for the startup/header-table
  mode where `CS:[0BD8] != 0`.  This gameplay materialization snapshot reaches
  `33AF` with `CS:[0BD8] == 0`, where the original parent has different visible
  behavior.

Fix:

- `1010:33AF` now conservatively self-disables and falls back to original ASM
  when `CS:[0BD8] == 0`.
- The verified child block expander `1010:33B2` remains available, so the
  original parent can still dispatch into accelerated block expansion.
- Added hook-verifier metadata for `1010:33AF`.
- Tightened packed-stream/RLE side-effect fidelity found during the audit:
  `0615 -> 0624` nested calls now leave their original stack scratch, and
  `03A8` uses the shared word reader for its header words so `CS:0614` matches
  the interpreted oracle.

Verification:

```text
python scripts\play.py --snapshot artifacts\snapshot_play_tandy_20260612_141644 --verify-frames --verify-frame-max 60
# FRAME VERIFY OK frames=60
python scripts\run_tests.py
# 127 passed, 0 failed
```

---

## 2026-06-12 PC speaker hardware/backend pass

Added a narrow PC speaker path for interactive play:

- `overkill_port/dos.py` now tracks PIT channel 2 programming through ports
  `43h/42h` and the speaker gate/data bits at port `61h`.
- `scripts/play.py` bridges speaker state changes from the VM thread to SDL via
  a queue.
- `scripts/sdl_view.py` renders those events as a cached mono square wave using
  `pygame.mixer`.
- Added a core regression for the PIT channel 2 + port `61h` callback contract.

Important finding: current Tandy snapshots and the default inner-EXE command
tail still leave the `2032:0000` sound-driver slot as a tiny return stub and do
not emit speaker port writes during a short main-menu run.  The backend is ready
for real speaker writes, but audible game sound still depends on identifying the
sound-driver selection/loading path or lifting the proven `1010:06E5` timer ISR
sound call once that target is non-stub.

Verification:

```text
python -m py_compile overkill_port\dos.py tests\test_core.py scripts\play.py scripts\sdl_view.py
python scripts\run_tests.py
# 126 passed, 0 failed
```

---

## 2026-06-12 Tandy end-screen direct-video publish

Investigated `artifacts/play_tandy_the_end_20260612_001833`, where the
interactive viewer appeared frozen after the ending instead of showing the
high-score/name-entry flow.

Findings:

- Continuing the snapshot headlessly does not crash or remain at the snapshot
  entry.  The game advances from `1010:98FA` through the retrace-delay loop.
- In the following path, video memory changes directly: a 1M-step probe changed
  10,257 bytes in `B800h`.
- The hot path is interpreted text/glyph drawing around `1010:518C -> 3153`,
  which writes to `ES=B800` without hitting the usual Tandy present, timer, or
  retrace hooks after the initial delay.
- Because `scripts/play.py` previously published frames only at known
  present/timer/retrace boundaries, this looked frozen in the viewer even though
  the VM was drawing.

Fix:

- `scripts/play.py` now checks for changed visible video memory when a long run
  reaches the no-boundary frame budget.  If video changed, it publishes a
  "direct video" frame and treats that as a UI boundary.
- `scripts/sdl_view.py` reports the direct-video count in the window caption.
- Printable SDL keydowns are also bridged into the DOS key queue after the first
  direct-video publish, so late DOS character input such as `INT 21h AH=07h`
  name entry can receive typed characters without polluting the queue during
  normal gameplay controls.
- Follow-up from `artifacts/snapshot_play_tandy_20260612_131223`: a snapshot can
  start already inside the high-score/name-entry screen before this viewer
  session has counted any direct-video publish.  The DOS-key bridge is therefore
  also enabled while the CPU is in the observed high-score editor region
  `1010:5300..5650`, with a scancode-to-ASCII fallback for common printable
  keys and control keys when SDL provides no printable `unicode`.
- Follow-up from `artifacts/snapshot_play_tandy_20260612_131602`: the saved
  state is already late in the editor/submission path (`1010:55F1`) with the
  name buffer filled (`gttrfdffgg`), the name pointer at the 10-character limit,
  and the last editor character recorded as Enter (`DS:22B4=000D`).  Continuing
  that snapshot can therefore return to the menu because the name has already
  effectively been submitted, not because the VM has a stuck Enter key.
- Follow-up from `artifacts/snapshot_play_tandy_20260612_131812`: this snapshot
  starts before the high-score screen is fully drawn (`1010:32C5`).  Profiling
  1.5M steps shows the delay is pure interpreted text/direct-video drawing:
  `1010:518C`, `1010:3153`, and callers around `1010:32C5`; no replacement
  hooks fire.  This explains the slow appearance and marks the path as a future
  direct-video/text drawing lift candidate.
- The remaining "cannot type name" issue was caused by the deterministic
  headless DOS console fallback: `INT 21h AH=07h` returned Esc when no queued
  key was available.  In interactive `scripts/play.py`, DOS console input now
  blocks instead: the handler rewinds `IP` to the `INT 21h`, raises a narrow
  `ConsoleInputWouldBlock`, and the viewer yields a UI boundary until a real key
  is queued.
- Name-entry input then exposed the real missing VM service:
  `INT 10h AH=0Eh` BIOS teletype output.  The high-score editor reaches this as
  a bell (`AL=07h`) for rejected input.  `dos.py` now accepts this narrowly by
  recording the character in the stdout log rather than trying to render BIOS
  text over the graphics screen.

Verification:

```text
python -m py_compile overkill_port\dos.py scripts\play.py scripts\sdl_view.py
python scripts\run_tests.py
# 121 passed, 0 failed
```

---

## 2026-06-12 Tandy menu/redefine screen rendering pass

Investigated `artifacts/play_tandy_main_menu_20260612_132548`, where menu
subscreens such as ordering info, instructions, and redefine-keys felt slow.

Changes:

- `scripts/sdl_view.py` no longer treats Esc as a viewer quit key.  Esc is now
  forwarded to OVERKILL like the rest of the keyboard; close the SDL window to
  exit the viewer.
- Added `1010:306F overkill_tandy_rect_copy_306f`, the raw Tandy rectangle copy
  used by menu/high-score text screens.  This is a parent-level replacement for
  the formerly hot `307E` row loop.
- Added `1010:CDAA overkill_tandy_changed_dword_present_8rows_cdaa`, the Tandy
  dirty-present sibling of the existing `CD8D` CGA/EGA-ish changed-word
  presenter.

Verification:

```text
python scripts\run_tests.py
# 123 passed, 0 failed
```

Profiling notes:

- Before `306F`, `1010:307E..3094` dominated the interpreted menu/text copy
  path.  After the hook it disappears from the interpreted hot list.
- Before `CDAA`, `1010:CDAA..CDC8` was the next Tandy dirty-present loop.  After
  the hook it also disappears from the interpreted hot list.
- The remaining top interpreted loop from this snapshot is `1F8F:0960`, a compact
  far-overlay/menu counter loop.  It is not clearly part of the Tandy rendering
  island, so it was left untouched in this pass.

Follow-up from `artifacts/snapshot_play_tandy_20260612_134028`:

- The redefine-keys page itself was not slow because of rendering.  It was
  spinning in a pure keyboard wait:
  `1010:57AB cmp byte ptr DS:[98C3],00h` / `1010:57B0 jz 57AB`.
- `scripts/play.py` now treats this redefine-key wait as an interactive yield
  boundary when `DS:[98C3]` is still zero.  The runner publishes any changed
  video, pumps the UI, and retries after a real key event.
- The same handling covers the immediately following key-release wait at
  `1010:57DD/57E0`, where the game waits for `DS:[98C4 + DS:[98C3]]` to clear.
- This is deliberately not a global replacement hook: headless profiling and
  oracle runs still see the original wait loop.  The fix only prevents the live
  viewer from burning the full `--frame-budget` between redefine-key prompts.

---

## 2026-06-12 Tandy cold-start composition pass

Cold-start profiling with Tandy mode (`scripts/profile_hotspots.py --video
tandy`) showed that the largest remaining startup overhead before the next VM
frontier was not another codec, but the interpreted Tandy startup list driver:

```text
1010:33AF -> call 44D7 header reader -> 1010:33B2 block expander
```

`33B2` was already a verified hook, but startup still interpreted hundreds of
small `44D7` header reads and hook boundaries.  Added:

- `1010:33AF overkill_expand_tandy_list_33af`, a parent-level Tandy startup
  list hook that composes the `44D7` header reader with the existing `33B2`
  block expander until the zero-header terminator jumps to `44AA`.
- Full-memory synthetic oracle coverage for a two-block list plus terminator.
- A stack-scratch correction in the existing `33B2` helper for the nested final
  `344B` call return word (`341B`).

Profiling effect before the same startup frontier:

- before: `33B2` hook called 686 times and the interpreted hot list was dominated
  by `33AF/44D7/450A`;
- after: `33AF` hook called 9 times, `33AF/44D7/33B2` disappeared from the
  interpreted hot list, and total hook invocations before the frontier dropped
  from 1,048 to 371.

The same profile then exposed unsupported 8086 opcode `98h` at `1010:0008`;
implemented narrow `CBW` support in `cpu.py` (sign-extend `AL` into `AX`, flags
unchanged).  With `CBW`, a 1M-step cold Tandy profile reaches normal
menu/gameplay-heavy code.  The remaining top non-hook loop is `1F8F:0960`, which
does not clearly belong to the current asset/rendering islands and was left
untouched.

---

## 2026-06-12 Instructions/order overlay wait

Investigated `artifacts/snapshot_play_tandy_20260612_140352`, captured from the
instructions screen after it appeared slow to load.

Finding:

- The snapshot is already inside the loaded overlay segment (`1F8F:09B7`), not in
  file IO, decompression, or startup materialization.
- Profiling 1M steps showed zero hooks and 100% interpreted time in
  `1F8F:099B..09DF`, a tight key-state wait loop.  It checks menu/action key
  bytes such as `DS:990F`, `990C`, `990D`, `98D2`, `9911`, `9914`, `9915`,
  `98FD`, `98E0`, and `98C5`.
- `scripts/play.py` now recognizes this overlay wait by code signature and
  yields the interactive UI immediately while all watched key bytes are idle.
  This is not a loader hook and not a global replacement; it only prevents the
  live viewer from burning the full frame budget while instructions/order screens
  wait for input.

Verification:

```text
python scripts\run_tests.py
# 125 passed, 0 failed
```

---

## 2026-06-12 Timeless top-level documentation pass

Refactored project-facing docs so durable guidance is separated from living
status:

- `AGENTS.md` now contains stable agent/human workflow rules: project purpose,
  proof obligations, hook mechanics, verification expectations, source-port
  islands, artifact policy, and things not to do.
- `README.md` now reads as stable onboarding: goals, non-goals, local game-file
  expectations, project layout, quick-start commands, verification workflow,
  source-port island model, and documentation map.
- `docs/design.md` now describes runtime architecture and design pressure
  without embedding old checkpoint progress or tactical next targets.

Current facts, recent commands, and next tactical targets should remain in
`RUN_STATUS.md`; durable address-level findings remain in
`docs/runtime_findings.md`.

---

## 2026-06-12 Existing-island exhaustion audit tooling

Added `scripts/audit_islands.py` to make island closure visible instead of
purely conversational.  The script groups currently registered hooks into the
already-created OverKill islands:

- asset codecs / startup materialization
- overlay loading / overlay decode / overlay directory scan
- startup graphics expansion
- coordinate/address helpers
- shared layer sprite dispatch
- Tandy-specific rendering primitives

For each island it reports hook-verifier metadata coverage, obvious
oracle/regression test mentions, `symbols.json` entries that still advertise a
candidate/frontier/unverified/fallback state, explicit module seam markers such
as bounded original fallbacks, and optional trace hits.

Useful commands:

```text
python scripts\audit_islands.py
python scripts\audit_islands.py --all-hooks
python scripts\audit_islands.py --json
python scripts\audit_islands.py --trace artifacts\some_trace.txt
```

Current audit result:

- `startup_graphics` reports `closed-candidate`: all known hooks in that island
  have verifier metadata and test mentions, and the script found no explicit
  seam markers or open symbols.
- `asset_codecs` now reports `closed-candidate`: the remaining
  `1010:0324` word-pair RLE candidate has been lifted, verified, and marked
  replaced.
- `overlay` remains open because `254A:05A1` and `254A:05D9` need direct test
  mentions and `254A:04D7` is still marked as an active parent-loader
  investigation target.
- `coordinates` remains open because the coordinate module still contains an
  explicit unverified-path seam.
- `layer_sprites` remains open because it still has bounded-original/fail-fast
  seams and an open `1010:75A6` frontier symbol.
- `tandy_rendering` remains open because several hooks lack obvious direct test
  mentions.

Important limitation: `closed-candidate` is a closure signal, not proof that no
unknown behavior exists.  It means the known source-port island has no
script-detected blockers left and should then be checked with live hook
verification and representative Tandy traces.

Hook-verifier metadata was also filled in for the existing-island hooks that now
have clear boundaries, including overlay far-return handling for `254A:0701`.
A small regression pins the far-return stop metadata behavior.

Verification:

```text
python -m py_compile scripts\audit_islands.py overkill_port\hook_verify.py
python scripts\run_tests.py
# 119 passed, 0 failed
```

---

## 2026-06-12 Asset-codec closure: 1010:0324 word-pair RLE

Closed the last audit blocker in the non-overlay `asset_codecs` island:

- `1010:0324` is a word-pair RLE decoder, sibling to the already lifted
  `1010:0367` byte-linear and `1010:03A8` vertical RLE decoders.
- The stream starts with a sentinel word read through the packed `0615` reader.
  Non-sentinel words are literal two-word pairs.  Sentinel words introduce a
  repeat count; count zero exits to the shared loader continuation at
  `1010:02A8`, and nonzero counts repeat the following two-word pair.
- The implementation lives in
  `overkill_port/games/overkill/asset_codecs/rle.py` as
  `decode_word_pair_rle`, with a thin `replacements.py` hook wrapper.
- The shared packed byte reader now preserves the original fast-path carry:
  `0624` does `CMP BX,0610h`, takes the below-buffer branch with `CF=1`, and
  the later `INC word ptr [0610]` preserves that carry.
- The oracle test covers literal, repeat, and terminator paths, including final
  registers, flags, output words, packed-stream scratch, byte count, and stack
  scratch around `SS:SP`.

Audit result after this pass:

```text
asset_codecs      closed-candidate  hooks=10
startup_graphics  closed-candidate  hooks=7
```

Verification:

```text
python scripts\run_tests.py
# 119 passed, 0 failed

python scripts\audit_islands.py --all-hooks
# asset_codecs and startup_graphics report closed-candidate
```

---

## 2026-06-12 Existing-island audit: overlay signature loop

Audited remaining candidates against the already-created OverKill islands
(`asset_codecs` and `rendering`) and intentionally avoided opening new gameplay
areas.

Lifted one clear overlay-loader subloop:

- `254A:0582` belongs to the existing `asset_codecs.overlay` island.  It is the
  bounded header/signature compare loop after the parent loader reads the
  twelve-byte overlay/container header.  The Python implementation now lives in
  `overkill_port/games/overkill/asset_codecs/overlay.py` as
  `compare_overlay_signature_0582`, with a thin hook wrapper in
  `replacements.py`.
- Continuations are preserved exactly: full match goes to `254A:058D`; first
  mismatch goes to `254A:0640`.
- Added an interpreted-ASM oracle regression covering both exits.

Audit decisions:

- `254A:04D7` is clearly overlay loading, but it is a larger file-open/read/seek
  parent.  It should not be lifted wholesale until more of its small deterministic
  loops are closed.
- `1010:B73E/BC4B/62F6/BEC5` are gameplay/contact helpers, not part of the six
  requested islands, so they were left alone.
- The remaining CGA/EGA bounded layer compositor allow-list belongs to the shared
  layer-sprite rendering island, but it is not Tandy-specific and would be a
  broad rendering sweep; left untouched in this focused pass.

Verification:

```text
python scripts\run_tests.py
# 117 passed, 0 failed
```

---

## 2026-06-11 Tandy B73E formation/contact continuation

Closed the later formation-change divergence from
`artifacts/test_oracles/snapshot_play_tandy_20260611_152751`.

- The original frame-383 path for object `BP=2814` is
  `B73E -> B77B -> BC4B -> BCCB -> AA46/8331 -> BFC7`, not a `62F6`
  overlap collision.  `AA46` sets carry when the object is inside the
  view/contact rectangle; the replacement previously checked only X and always
  cleared carry, so the object stayed alive in logic `20h`.
- `_run_view_window_check_aa46` now mirrors the full X/Y rectangle test and
  preserves the carry-set contact result.
- `_run_object_postmove_bc4b` now composes the carry-set `BCCB` path: optional
  `BFC7` death/logic-transition tail, observed `9E69` bookkeeping, then the
  normal `62F6` call.
- `_run_object_overlap_scan_62f6` now preserves `BX` on the early
  `logic_id == 0001` return, matching the original post-death scan.
- Added an interpreted-ASM regression for the exact `B77B` contact-death tick.

Verification:

```text
python scripts\run_tests.py
# 113 passed, 0 failed

python scripts\play.py --snapshot artifacts\test_oracles\snapshot_play_tandy_20260611_152751 --verify-frames --verify-frame-max 500
# FRAME VERIFY OK frames=500
```

---

## 2026-06-11 B73E/BEC5 gameplay continuation

Closed two user-reported Tandy gameplay stops from
`artifacts/test_oracles/snapshot_play_tandy_20260611_152751`:

- Shooting enemies reached `B73E -> B7BD -> BC4B -> 62F6 -> BEC5 fourth
  counter zero`.  The observed `BFC7` death/transition tail now handles the
  type-1, no-linked-slot path: score add via the `5F0D` BP/SS decimal helper,
  Y clamp, logic transition `20h -> 1`, previous logic saved in `+1A`, `+22`
  cleared, and the type-1 sprite-zero dispatch.
- Passive play reached `B73E -> B7BD -> B7F3`, then the follow-up
  `B73E -> B7BD -> B82D -> B7BD` waypoint-loop case.  The verified branches now
  cover the `B7F3 -> B7C9` target-reset path, substate-0 `B754` movement path,
  and the bounded `B82D` waypoint-table loop.

Important correction while verifying: the `B7C9` target reset always produces
the observed target Y from `DS:2380 + 8` before alignment; a branch-counting
guess that preserved the old target caused frame-266 divergence.

Verification:

```text
python scripts\run_tests.py
# 111 passed, 0 failed

python scripts\play.py --snapshot artifacts\test_oracles\snapshot_play_tandy_20260611_152751 --verify-frames --verify-frame-max 300
# FRAME VERIFY OK frames=300
```

The key correction for the waypoint loop: `B82D` does not move immediately after
selecting a different waypoint.  It updates `+34/+32` from the table and falls
through to `BC4B`; movement happens on a later target-mismatch tick.

---

## 2026-06-11 Tandy layer-0 scan fix: A894 stops at CALL A8BE

User-reported gameplay from `artifacts/play_tandy_edrax_orbit_combat_20260611_214016`
hit the layer-0 draw scan with an active layer-0 object:

```text
1010:A894: partial scan reached unlifted CALL at A8BE
BP=2884 active=0001 layer=0000 type=0001 draw_layer=0005
```

This was a boundary bug in the shared partial-scan helper.  The `1010:A894`
hook is supposed to skip non-calling iterations and stop immediately before the
real `CALL` for the first drawable object.  Instead, `_scan_loop_until_callable`
still used the older fail-fast behavior.

Fix:

- `_scan_loop_until_callable` now preserves the loop `PUSH CX` scratch and leaves
  `CS:IP` at the real call instruction (`1010:A8BE` for `A894`).
- Added a synthetic interpreted-ASM oracle test for the active layer-0 path,
  comparing the original bytes through `A8BE` against the hook state.

Verification:

```text
python scripts\run_tests.py
# 108 passed, 0 failed

python scripts\play.py --snapshot artifacts\play_tandy_edrax_orbit_combat_20260611_214016 --verify-frames --verify-frame-max 60
# FRAME VERIFY OK frames=60
```

---

## 2026-06-11 Tandy gameplay crash fix: BEC5 BEDC=0001 collision tail

User-reported manual gameplay from
`artifacts/play_tandy_black_panel_20260611_192528` crashed while shooting spawned
ships:

```text
B73E -> B73E -> B7BD -> BC4B -> 62F6 -> BEC5 BEDC=0001 -> BF5E
```

The branch was real gameplay execution, not a renderer path.  Re-reading the
original bytes showed that `DS:BEDC == 0001` does not return immediately: it
jumps into the tail at `1010:BF4D`, decrements `SS:[BP+20]` once more, writes
`SS:[BP+24]=0005`, compares `DS:A8C2` with `0001`, and then returns at
`1010:BF5E` when `A8C2 != 0001`.

Fix:

- `1010:BEC5` observed variant-2 collision helper now implements the verified
  `BEDC=0001` tail instead of fail-fasting or returning early.
- The remaining zero-counter and `A8C2=0001` branches stay fail-fast with
  concrete target addresses.
- Added a synthetic interpreted-ASM oracle test for the `BEDC=0001` tail.

Verification:

```text
python scripts\run_tests.py
# 107 passed, 0 failed

python scripts\play.py --snapshot artifacts\test_oracles\snapshot_play_tandy_20260611_152751 --verify-frames --verify-frame-max 60
# FRAME VERIFY OK frames=60

python scripts\play.py --snapshot artifacts\play_tandy_black_panel_20260611_192528 --verify-frames --verify-frame-max 60
# FRAME VERIFY OK frames=60
```

---

## 2026-06-11 frame-verify regression fix: AA2B/EFAE back to dispatch-only

User-reported frame verification diverged at frame 34 from
`artifacts/test_oracles/snapshot_play_tandy_20260611_152751`:

```text
python scripts\play.py --snapshot artifacts\test_oracles\snapshot_play_tandy_20260611_152751 --verify-frames --verify-frame-max 60
```

Bisecting with `OVERKILL_DISABLE_HOOKS` showed:

- Disabling all non-frame hooks passes 60 frames.
- Disabling only the recent layer/draw hooks did not change the bad CRC.
- Disabling `1010:AA2B,1010:EFAE` alone restores 60-frame verification.

Root cause: `AA2B` and `EFAE` had crossed from dispatch-stub replacements into
inline gameplay behavior execution. Synthetic/local verifier boundaries did not
catch the later frame-level drift.

Fix:

- `1010:AA2B overkill_object_logic_dispatch_aa2b` is now dispatch-only: it
  mirrors `mov bx,ss:[bp+16]; shl bx,1; jmp cs:[bx+AA36]`.
- `1010:EFAE overkill_object_family_dispatch_efae` is now dispatch-only after
  preserving the real prologue writes to `DS:D1FE` and `DS:D200`, then jumps
  through `CS:EFC4`.
- Hook verifier metadata now stops at the selected dispatch target for both
  hooks, not at the caller return.
- Added synthetic ASM oracle coverage for both dispatch boundaries.
- `scripts/run_tests.py` now provides a tiny `pytest.raises` shim when pytest is
  unavailable, keeping the local pytest-free runner usable.

Verification:

```text
python scripts\play.py --snapshot artifacts\test_oracles\snapshot_play_tandy_20260611_152751 --verify-frames --verify-frame-max 60
# FRAME VERIFY OK frames=60

python scripts\run_tests.py
# 106 passed, 0 failed
```

---

## 2026-06-11 island-closure continuation: movement/collision/draw/layer frontier

Continued the fail-fast “close the island before expanding” pass from the previous
object-logic frontier.  The run no longer stops at `5DB2`; the currently opened
Tandy/object island now includes movement, the observed collision branch, more
first-level object logic, and several adjacent Tandy draw/layer targets.

New structural lifts in this pass:

- `1010:5DB2`: target-seeking movement/direction helper, including observed
  `AF60` double 2-pixel step and `AEE4` 8-pixel step modes.
- `1010:8D4F`: observed `logic_id=1Fh` waypoint/target-patrol branch through the
  far-call waypoint reader and `5DB2`.
- `1010:BEC5` observed branch: collision with a `+18h == 0002` object now
  deactivates the collided slot and updates the moving object's `+20h/+24h` state
  instead of stopping at the collision handler.
- `1010:AB10`: first-level AA2B target that updates object sprite/position from
  the `A40C/A414` tables.
- `1010:AED8`: observed `logic_id=2` movement/tile-probe branch, including the
  `AEE4 -> B250 -> AD5A -> 5073/505B` path and the observed out-of-bounds
  deactivation through `BD17`.
- `1010:356C`, `1010:3657`: additional Tandy draw targets reached by the composed
  `A849/A861 -> 5AC8` draw scans.
- `1010:A861`: overlaid `8D12` draw scan now composes verified `5AC8` Tandy draw
  targets instead of stopping before the call.
- `1010:7746` and `1010:2FB6`: compact layer draw setup and its two-word masked
  Tandy compositor, reached by `A87C`.
- `1010:A87C`: active-object scan over `8D12` now composes the verified `7746`
  compact layer draw path.

Current intentional frontier from `artifacts/play_tandy_edrax_orbit_combat_20260611_164810`:

```text
1010:A8C7 -> 7596 -> 75A6
```

This is useful new information: the already-opened layer pipeline now reaches the
`75A6` split/two-destination layer draw helper.  It should be lifted next rather
than adding a fallback.

Verification:

```text
python -m pytest -q                         # 103 passed
python -m compileall -q overkill_port scripts tests
python - <<'PY'                              # symbols.json parses
import json; json.load(open('symbols.json'))
PY
```

---

## 2026-06-11 fail-fast object logic frontier

The fail-fast no-fallback pass continued past the previous stop at
`1010:A9E0 -> AA01 -> AA2B`.

New structural lifts:

- `1010:A9E0`: object-logic scan over `DS:32CA`, including `DS:2340` counter side effect.
- `1010:AA10`: object-logic scan over `DS:8D12`.
- `1010:AA2B`: first-level object logic dispatch by `SS:[BP+16]` / `CS:AA36`.
- `1010:EFAE`: second-level object family dispatch by `SS:[BP+18]` / `CS:EFC4`.
- `1010:B73E`: observed `logic_id=20h` branch lifted to the next concrete helper.

Current intentional frontier from `artifacts/play_tandy_edrax_orbit_combat_20260611_164810`:

```text
1010:A9E0 -> AA2B -> EFAE -> B73E -> B85C -> B729 -> 5DB2
```

Verification:

```text
python -m pytest -q                         # 102 passed
python -m compileall -q overkill_port scripts tests
python - <<'PY'                              # symbols.json parses
import json; json.load(open('symbols.json'))
PY
```

Next best RE target: `1010:5DB2`, the movement/direction helper that compares the
object position against `DS:2304/2306`, writes `DS:A954` / `DS:230A`, XLATs through
`DS:A348`, and then dispatches via `CS:5E0C` according to `DS:2308`.

---
# Checkpoint: A90F/5A92 present-scan lift (fail-fast follow-up)

Continuing from the no-fallback run, the first exposed target was not worked around.
`1010:A90F` has now been lifted as a real parent present scan over the `DS:8D12`
object table. Active entries compose through `5A92` when their Tandy present target
is verified.

New verified present targets discovered from this path:

- `1010:3542` — 8-row/two-word Tandy present copy with `DI += 0064h`.
- `1010:34AD` — split present copy: optional first `34C5`, then
  `SS:[BP+10]` / `SS:[BP+0E]+0140h` tail into `34C5`.

`A927` now uses the same shared present-scan helper, so both `32CA` and `8D12`
present scans compose known `5A92` targets and fail fast on truly unknown ones.

Validation:

- `python -m pytest -q` -> 102 passed.
- `python -m compileall -q overkill_port scripts tests` -> passed.
- `symbols.json` parses.
- Replaying `artifacts/play_tandy_edrax_orbit_combat_20260611_164810` now gets past the
  previous `A90F -> A91E -> 5A92` stop and past the newly discovered `3542`/`34AD`
  present targets. The next intentional fail-fast target is now
  `1010:A9E0 -> AA01 -> AA2B`, object `BP=2734`, `CX=0011`, `type=0001`,
  `draw_layer=0004`, `sprite=007A`.

Next RE target:

- Reverse/lift the `1010:A9E0 -> AA01 -> AA2B` object/gameplay dispatch path.

---

# Checkpoint: fail-fast replacement policy (no ASM fallback masking)

This pass removes the conservative unknown-target fallbacks from composed replacement hooks.
The project goal is reverse engineering, not short-term playability, so unknown dispatch
paths now raise a diagnostic `RuntimeError` instead of returning to the interpreted ASM
pre-call boundary. Runtime-patched hook signatures also fail fast instead of silently
unregistering the hook and continuing through the original bytes.

Changed behavior:

- `1010:A849` now raises on unverified `A849 -> 5AC8 -> target` paths instead of
  stopping at `A858`.
- `1010:A927` now raises on unverified `A927 -> 5A92 -> target` paths instead of
  stopping at `A936`.
- `1010:A8C7` now raises on unverified `A8C7 -> 7596` or nested
  `A8C7 -> 7596 -> 768E -> target` paths instead of stopping at `A8F1`.
- `1010:768E` now raises on unknown Tandy sprite compositor targets instead of
  tail-dispatching to original code.
- Partial scan hooks using `_scan_loop_until_callable` now raise when they reach an
  active object requiring an unlifted call. They still complete skip-only scans.
- `5A36` and shared `5A00/5A24` coordinate dispatch helpers now raise on unverified
  video modes rather than jumping into original target code.

Validation:

- `python -m pytest -q` -> 99 passed.
- `python -m compileall -q overkill_port scripts tests` -> passed.
- `symbols.json` parses.
- Continuing `artifacts/play_tandy_edrax_orbit_combat_20260611_164810` now intentionally stops
  after 3 instructions at the next unknown RE target:
  `1010:A90F` partial scan reached unlifted call `A91E` with object `BP=2CAC`,
  `CX=0007`, `type=0000`, `sprite=0032`, `di=537A`, `present_si=9418`.

Next RE target exposed by fail-fast policy:

- Reverse/lift the `1010:A90F -> A91E -> 5A92` present/object scan path instead of
  allowing the old skip hook to fall back into ASM.

---

# Run status — checkpoint 31

Validated on `assets/OVERKILL.UNLZEXE.EXE`. Crash regression snapshot:
`artifacts/play_tandy_edrax_orbit_combat_20260611_164810`.

This pass fixes the gameplay crash at `1010:A8C7` without treating `2F40` as an
unknown fallback case.  The deeper issue was that `1010:768E` is a
setup/tail-dispatch helper, and the crash snapshot exercised a real Tandy
compositor target that had not yet been lifted:

- `1010:2F40 overkill_tandy_or_inverted_mask_2f40`

## Tandy compositor target 2F40

`2F40` is a four-word, 16-row Tandy layer compositor.  It is not the same masked
copy shape as `2F81`: each row consumes four source cells as
`MOV AX,[SI]; NOT AX; OR ES:[DI],AX; ADD SI,4; ADD DI,2`, then advances the
destination by `0060h`.  In game terms this is an inverted-mask OR pass used by
some layer sprites.

The new hook preserves the original `BX=0060h`, `CX` loop, `SI`/`DI` advancement,
final flags from the last row `ADD DI,BX`, `DS=CS:[9596]` restoration, and `RET`
behavior.  `768E` and the composed `A8C7` scan now treat `2F40` as a verified
child target alongside `2F81` and `2E6E`.

`A8C7` still predicts the nested `768E` compositor before composing the scan, but
that fallback is now only for genuinely unverified nested targets; the observed
`2F40` path is executed and verified rather than skipped.

## Verification

- Crash snapshot replay from `play_tandy_edrax_orbit_combat_20260611_164810`: 50,000
  instructions without the old `768E layer draw returned to unexpected IP 2F40`
  crash.
- Synthetic interpreted-ASM oracle now covers `768E -> 2F40`.
- Synthetic `A8C7` parent-scan oracle now covers full composition through
  `7596 -> 768E -> 2F40`.
- Live verifier from the crash snapshot:
  - `A8C7`: 20 real calls, no divergence.
  - `768E`: 1 real nested `2F40` call in the replay window, no divergence.
- Full test suite: `99 passed`.
- `py_compile`: passed.

---

# Run status — checkpoint 30

Validated on `assets/OVERKILL.UNLZEXE.EXE`. Current Tandy gameplay snapshot:
`artifacts/test_oracles/snapshot_play_tandy_20260611_152751`.

This pass moved one level higher in the Tandy layer-1 draw pipeline:

- `1010:768E overkill_tandy_layer_sprite_draw_768e`
- `1010:A8C7 overkill_scan_layer1_draw_a8c7`

## Layer-1 draw composition

`1010:7596` is a small object-type dispatcher.  Its hot Tandy layer-1 path
dispatches object type 1 to `1010:768E`, which sets up the source segment/table,
destination pointer, mode/phase compositor table, row count, and then tail-jumps
to the verified Tandy sprite compositor (`1010:2F81` in the current snapshot).

`768E` is now a verified setup/tail-dispatch helper.  It handles:

- `DI=FFFF` early return.
- Known compositor targets `2F81` and `2E6E` by running verified children.
- Unknown compositor targets by tail-dispatching back to the original target.

`A8C7` now composes the layer-1 scan when the active object's `7596` target is
the verified `768E` path.  It preserves the original layer filter, `PUSH CX`,
`CALL 7596`, `POP CX`, and `LOOP` behavior.  If an active object dispatches to an
unverified `7596` target, the hook falls back before the original call at
`1010:A8F1`.

## Verification

- Added interpreted-ASM oracle tests for `768E` complete, early-return, and
  fallback paths.
- Added interpreted-ASM oracle tests for `A8C7` complete and fallback paths.
- Live hook verifier from `snapshot_play_tandy_20260611_152751` covered:
  - `768E`: 800 real calls, no divergence.
  - `A8C7`: 500 real layer-1 scan calls, no divergence.

## Current profile shape

The layer-1 pipeline no longer appears as repeated interpreted
`A8C7 -> 7596 -> 768E -> 2F81` crossings in the common Tandy path.  The remaining
hot interpreted work is now strongly concentrated in shared object/gameplay code:

- `1010:A9E0 -> AA2B`
- `1010:EFAE` object routine dispatch
- `1010:BC4E` / nearby shared update/collision-style logic

Those should be treated as gameplay/object reconstruction targets rather than
rendering helpers.

---

# Run status — checkpoint 29

Validated on `assets/OVERKILL.UNLZEXE.EXE`. Current Tandy gameplay snapshot:
`artifacts/test_oracles/snapshot_play_tandy_20260611_152751`.

This pass composed two verified small-hook clusters into full object scan passes
for the common Tandy first-level object table.

## Composed object scan hooks

Updated:

- `1010:A927 overkill_scan_objects_call_5a92_a927`
- `1010:A849 overkill_scan_objects_call_5ac8_a849`

Both routines still preserve the old conservative behavior when they encounter
an unverified dispatch target: they stop at the original pre-call boundary
(`A936` for `A927`, `A858` for `A849`).  When all active objects dispatch to the
verified Tandy targets, they now run the whole scan loop and return at the loop
exit (`A93C` / `A85E`).

The composed paths reuse the already verified smaller operations:

- `A927 -> 5A92 -> 34D8/34C5`
- `A849 -> 5AC8 -> 35CC/35AA`

They preserve the original `PUSH CX`, `CALL`, `POP CX`, `LOOP` stack scratch and
flag behavior instead of inventing a higher-level object API.

## Verification

- Added interpreted-ASM oracle tests for complete and fallback paths of both
  composed scan hooks.
- Live hook verifier from `snapshot_play_tandy_20260611_152751` covered:
  - `A927`: 750 real full-scan calls, no divergence.
  - `A849`: 760 real full-scan calls, no divergence.

## Current profile shape

With both 32CA scan passes composed, a 3M-step Tandy first-level profile drops
the repeated `A849/A927 -> 5AC8/5A92 -> 35CC/34D8` interpreter crossings.  The
remaining hot interpreted areas are now mostly shared behavior:

- `1010:AA2B` / `EFAE` object dispatch/update paths.
- `1010:BC4E` and nearby shared gameplay code.
- `1010:A8C7 -> 7596 -> 768E` layer-1 draw pipeline.

These are the next good characterization targets, with preference for lifting a
whole pipeline once the boundary is proven.

---

# Run status — checkpoint 28

Validated on `assets/OVERKILL.UNLZEXE.EXE`. Current Tandy gameplay snapshot:
`artifacts/test_oracles/snapshot_play_tandy_20260611_152751`.

This pass continued from the Tandy first-level snapshot and lifted the next
highest-impact verified Tandy gameplay blocks, favoring parent/block-level hooks
over tiny leaves.

## Tandy gameplay hooks

Added verified hooks:

- `1010:2F81 overkill_tandy_masked_sprite_composite_2f81`
- `1010:2E6E overkill_tandy_masked_sprite_composite_2e6e`
- `1010:34C5 overkill_tandy_strided_copy_34c5`
- `1010:35AA overkill_tandy_source_strided_copy_35aa`
- `1010:34D8 overkill_tandy_small_strided_copy_34d8`
- `1010:35CC overkill_tandy_draw_object_block_35cc`

Also folded the Tandy mode-2 row-address target `1010:30D2` into the existing
`1010:5A36` dispatch hook, so mode 0/1/2 now return at the caller boundary while
unknown modes still dispatch to the original table target.

`35CC` is deliberately a composed parent hook: it calls the verified `5A36`
row-address replacement internally, mirrors the original `CALL 5A36` stack
scratch, then performs the Tandy source-strided copy as one routine.

## Verification

- Added interpreted-ASM oracle tests for all new Tandy gameplay hooks, including
  the composed `35CC -> 5A36 -> 30D2` path.
- Live hook verifier from `snapshot_play_tandy_20260611_152751` covered:
  - `2F81/2E6E/34C5/35AA/5A36`: 2,000 mixed real calls, no divergence.
  - `34D8`: 500 real calls, no divergence.
  - `35CC/34D8/5A36`: 1,500 mixed real calls, no divergence.

## Current profile shape

`python scripts/profile_hotspots.py 3000000 --video tandy --snapshot artifacts\test_oracles\snapshot_play_tandy_20260611_152751 --top 35`
now shows the Tandy-specific sprite/copy work as hooks. The remaining real
interpreted heat has shifted toward shared object/gameplay logic:

- `1010:AA2B` dispatch/helper path
- `1010:EFAE` object routine dispatcher
- `1010:BC4E` / `BCxx` shared gameplay paths
- smaller draw target work around `1010:768E`

Those are the next best candidates, but they should be lifted only after their
entry/exit contracts and call families are characterized.

---

# Run status — checkpoint 27

Validated on `assets/OVERKILL.UNLZEXE.EXE`.  Local pytest-free runner:
`86 passed, 0 failed`.

This pass switches the interactive/profiling default video mode to Tandy and
adds verified Tandy startup-expander hooks for the slow packed-pixel asset path.

## Tandy default

- `scripts/play.py` now defaults to `--video tandy`.
- `scripts/profile_hotspots.py` now defaults to `--video tandy`.
- `README.md` now documents Tandy as the default interactive path.

## Tandy startup-expander hooks

Profiling showed Tandy startup was spending most of its time in the live-patched
`1010:33B2 -> 33DD -> 344B` packed-pixel block renderer.  This is the Tandy
analog of the already-hooked EGA `4511/4537/45F6` startup expander.

Added:

- `1010:33DD overkill_expand_tandy_cell_33dd`
- `1010:33B2 overkill_expand_tandy_block_33b2`

The `33B2` hook is guarded by live-byte signature because this code region is
runtime-patched.  It preserves the original normal continuation (`1010:33AF`),
terminator branch (`1010:44AA`), `SI`/`DI`/`CX` loop effects, flags, output
writes, and final stack scratch words from the original call frame.

## Verification

- Added interpreted-ASM oracle tests for `33DD`, `33B2`, and the `33B2` zero/
  terminator branch.
- Added hook-verifier continuation metadata for `1010:33B2` and `1010:33DD`.
- Live differential verification covered all 686 real `1010:33B2` calls reached
  in the current Tandy startup profile with no divergence.
- Full local test runner: `86 passed, 0 failed`.

## Profiling note

`python scripts/profile_hotspots.py 6000000 --video tandy --top 10` now shows
`1010:33B2` as 686 block-level hook calls instead of the previous interpreted
`33B2/33DD/344B` loop tree.  After replacing the internal 344B rotate simulation
with direct bit packing, `33B2` is about `0.57s` total / `0.83ms` per block in
the same profile.  The run still stops later at the pre-existing
`Unsupported opcode 98 at 1010:0008`; a control run with `1010:33B2` disabled
hits the same stop, so it is not caused by the new hook.

## Viewer polish

The SDL viewer window is now resizable/maximizable.  Frames are centered at the
largest integer scale that fits the current window, preserving the 320x200 aspect
ratio with black bars as needed.

---

# Run status — checkpoint 26

Validated on `assets/OVERKILL.UNLZEXE.EXE`.  `65 passed` *at this checkpoint*.

> **Note:** this checkpoint is not the latest state.  Work after checkpoint 26
> (EGA planar-correctness fixes, the masked-sprite/perf pass, the replacements.py
> hook de-duplication, and the 2026-06-11 EGA gameplay-profiling passes that added
> the verified `1D1B` and wide `13E7` bit-spread composite hooks — together ~17%
> then a further ~33% faster in-level play) is recorded in
> [`docs/runtime_findings.md`](docs/runtime_findings.md); the full suite is now
> `82 passed`.

This pass continued profiling the slow planet/difficulty selection screen that is
shown after pressing SPACE in the main menu.  The earlier menu hooks helped, but
profiling showed that this screen was now dominated by overlaid masked-sprite
compositors and object dispatch stubs rather than asset decompression.

## Performance finding

After re-enabling the dirty-copy hooks and adding the previous `4D15` fix, the
next hot interpreted path was the overlaid masked sprite drawing code around
`1010:3EFB`.  This routine is used heavily by the selection highlight/sprite
redraw path and performs many `RCR`/`SHR` chains per row.

The addresses around `3EE1`/`3EFC` are reused by overlays, so hooks in that area
must verify the resident bytes before applying.  A non-guarded row-copy hook can
accidentally intercept a different overlaid compositor body.

## Fixes / hooks

- Added `1010:3E12 overkill_masked_sprite_composite_3e12`, collapsing the hot
  two-shift masked CGA sprite compositor used by the level-selection redraw.
- Added guarded strided-row-copy hooks for `1010:3EE1` and `1010:3EFC`.  These
  only run when the exact row-copy bytes are resident; otherwise they fall back
  to the interpreter for the current overlaid instruction.
- Added `1010:3EFB overkill_masked_sprite_composite_3efb`, collapsing the
  overlaid six-shift masked sprite compositor that became the dominant interpreted
  loop on the selection screen.
- Added fast dispatch hooks for `1010:5AC8` and `1010:5A92`, removing repeated
  interpreted mode/subtype dispatch overhead before the existing draw/present
  hooks take over.
- Added `1010:AA44 overkill_clc_ret_aa44` for the tiny hot success helper.
- Kept the earlier live-player hook policy change: dirty-copy hooks are enabled
  in interactive CGA, while the mode-0-only `58DF` hook remains disabled for
  non-CGA modes.

## Verification

Added oracle tests comparing the new hooks against interpreted ASM snippets:

- `test_masked_sprite_composite_3e12_hook_matches_interpreted_asm`
- `test_strided_row_copy_3ee1_and_3efc_hooks_match_interpreted_asm`
- `test_masked_sprite_composite_3efb_hook_matches_interpreted_asm`
- `test_dispatch_5ac8_and_5a92_hooks_match_interpreted_asm`
- `test_clc_ret_aa44_hook_matches_interpreted_asm`

Full result:

```text
65 passed in 2.95s
```

A 1.5M-step CGA profile now reaches further into the menu/gameplay rendering
path within the same step budget.  `1010:3EFB`, `1010:5AC8`, `1010:5A92`, and
`1010:AA44` are now replacement hooks instead of interpreted hot loops.

---

# Current run status — checkpoint 25

Validated on `assets/OVERKILL.UNLZEXE.EXE`.  `56 passed`.

This pass targeted the very slow menu/planet-selection renderer path shown by
profiling the live CGA menu loop after startup.

## Performance finding

With the interactive-safe hook set from checkpoint 24, the hottest interpreted
routine on this screen was `1010:4D15`: the presence/stamp-list helper used by
the menu/planet-selection object/cell bookkeeping.  A 5M-step profile from the
menu loop showed `4D15..4D61` dominating the interpreted address list before the
existing hook was allowed in the live player.

After enabling the fixed hook, `4D15` disappears from the interpreted hotspot
list.  The next interpreted hotspots are now `1010:017E` (keyboard poll bit
loop), `1010:CCAD..CCC0` (dirty-copy mode-1 body when the still-disabled dirty
hooks are off), and `1010:3E12..3E4E`.

## Fixes / hooks

- Reworked `1010:4D15 overkill_presence_stamp_list_4d15` into a faster local-loop
  hook instead of using CPU helper calls for every small operation.
- Fixed an uncovered mode-0 accuracy bug in the older `4D15` hook: the original
  `JNE 4D59` path stamps only the base cell and appends it to `DS:DI`; the stacked
  `+1A/+34/+4E` stores are mode-1 `JMP BP` paths only.
- Removed `4D15` from the interactive disabled-hook set after adding regression
  coverage for the mode-0 and final-skip paths.
- Removed `41A6` from the interactive disabled-hook set as well; it is already
  covered by an interpreted-ASM oracle test and is now the active fast path for
  the variable-width interlaced menu/screen blit.

## Verification

Added `test_presence_stamp_list_4d15_final_skip_and_mode0_flags_match_asm` to
cover the previously missing paths.  Full result:

```text
56 passed in 2.65s
```

---

# Current run status — checkpoint 24

Validated on `assets/OVERKILL.UNLZEXE.EXE`.  `55 passed`.

This pass fixes the accuracy regression in the fast 4-plane row expander and
continues the loading/sprite-phase lift where profiling showed the highest
remaining interpreted-instruction density.

## Accuracy fix

- **Fixed `1010:4537` fast row expander final `DX`.**  The optimized
  `_row_4537_core` incorrectly left `DX` as the entry value.  The original ASM
  loads `DL`/`DH` from plane 2/3 and then calls `45F6` four times; each call
  rotates the plane bytes by two bits, so after four calls the bytes return to
  their loaded values.  The hook now exits with `DX = (loaded_DH << 8) | loaded_DL`.
- Reconfirmed the 4537/4511 oracle tests and fuzz tests, then the full suite.

## Loading / sprite-phase performance lifts

- **New overlaid object-scan skip hooks** for the hot repeated loops around
  `A849`, `A861`, `A87C`, `A894`, `A8C7`, `A90F`, `A927`, `A9E0`, and `AA10`.
  These loops mostly scan inactive object slots during loading/render setup.
  The hooks consume skip-only iterations in Python and stop immediately before
  the original CALL when an active/matching object needs the existing ASM logic.
  Stack scratch from the balanced `PUSH CX`/`POP CX` pair is preserved.
- **New `1010:3849` hook** for the 4-column masked sprite composite loop, the
  wider sibling of the existing `38B7` hook.  It composites four mask/data word
  pairs per row and restores `DS` from `CS:[9596]` before returning.
- **New `1010:469F` hook** for the plain 9-byte × 16-row sprite copy loop.
- **New `1010:4D6F` hook** for the presence-list clear loop.

## Verification

Added self-contained oracle tests for the newly risky lifts:

- `test_masked_sprite_composite_3849_hook_matches_interpreted_asm`
- `test_sprite_copy_469f_hook_matches_interpreted_asm`
- `test_overlay_scan_a849_skips_inactive_entries_like_asm`
- `test_overlay_scan_a9e0_counter_and_skip_match_asm`

Full result:

```text
55 passed in 2.50s
```

## Profiling note

A 1.5M-step CGA profile after the new hooks reaches further into the sprite/game
phase within the same interpreted-step budget, so wall-clock numbers are not a
clean apples-to-apples boot benchmark.  The previous `A849`/`A8C7`/`A9E0` scan
addresses disappear from the interpreted-instruction top list; the next visible
hotspots are now the small bit loop at `017E`, the `CD8D` region, and far-call
code at `1F8F:0960`.

---

# Current run status — checkpoint 23

Validated on `assets/OVERKILL.UNLZEXE.EXE`.  `49 passed`.

This pass continues the source-port lift of hot routines (the core methodology),
applies the renderer-helper cleanup that was prototyped but not committed last
round, and keeps the focus on performance-relevant code.  CGA and Tandy
correctness preserved; no gameplay logic rewritten.

## What changed

- **New `1010:38B7` hook `overkill_masked_sprite_composite_38b7`.**  Profiling
  after the 477E lift showed this is now the hottest interpreted routine in the
  sprite-render phase (~15k samples per loop-body address).  It is the classic
  masked sprite composite `dest = (dest AND mask) OR data`, two 16-bit columns
  per row over `CX` rows: source row `[mask0,data0,mask1,data1]` (SI += 8/row),
  destination stride `0x34`, read-modify-write of the destination, exit to
  `38D0` with `CX=0` and FLAGS from the final `add di,30h`.  Lifted into a
  verified Python hook (DF-aware, `CX==0 -> 65536` handled).  New self-contained
  oracle test `test_masked_sprite_composite_38b7_hook_matches_interpreted_asm`
  plus a 2000-state differential fuzz: bit-identical to the interpreted loop.

- **`1010:4537` renderer helpers lifted to module level.**  The four per-call
  closures (`rol8`/`ror8`/`rcl8`/`rcl16_mem`) and the `pack_four_pixels` /
  `expand_bits` bodies are now module-level `_r_*` functions instead of being
  rebuilt on every call.  This makes the lifted source clearer and reusable —
  exactly the direction the source port wants — and is verified bit-identical to
  the previous implementation by a 3000-state fuzz and the existing 4537 oracle
  test.  (Note: this did not measurably change raw CPython speed; it was applied
  for source-port clarity and because it is correct, not for a speed number.)

## Impact of the sprite-render lifts (477E + 38B7)

Measured over a 2.5M-step window that reaches the sprite phase: `38B7` fires
~1,089 times and `477E` ~866 times, together removing ~292k interpreted
instructions (each call replaces 90-190 one-at-a-time Python opcode dispatches
with a single hook).  These routines dominate *sprite-heavy gameplay frames*
rather than the boot-to-menu path (which is bound by the already-hooked
`450C`/`4511`/`4537` asset expansion), so the benefit shows up as lighter
per-frame work during play, not as a faster cold boot.

## Honest note on raw boot speed

As measured last checkpoint, no safe micro-optimisation to the CPython
interpreter core moves cold-boot time meaningfully; the high-leverage lever for
overall speed remains running under PyPy (10-50x on this kind of dispatch loop,
zero code change, current path stays as fallback).  The per-routine lifts above
are still worthwhile: they advance the reverse-engineered source port *and* cut
real interpreted work in the hot rendering phase.

## EGA

Unchanged this pass (still the cyan/black plane-2/3-under-fill described in
checkpoint 22).  The diagnosis stands: not a palette problem; planes 2/3 are
under-filled upstream of the verified present/expansion hooks.  A fix needs EGA
planar-memory modelling and/or a corrected EGA source decode, deliberately
deferred to avoid destabilising the working CGA/Tandy modes.  Track it with
`python scripts/diag_video.py --video ega`.

---

# Current run status — checkpoint 22

Validated on `assets/OVERKILL.UNLZEXE.EXE`.  This pass dug into the two open
complaints — "EGA still black/blue" and "performance still poor" — and reports
measured, evidence-based conclusions rather than speculative fixes.  `48 passed`.

## EGA: root cause narrowed (planar plane-fill, not palette)

`scripts/diag_video.py --video ega` now also reports EGA register activity.
Captured across the first several EGA presents:

- plane nonzero bytes stay lopsided every frame: plane0/1 ~1380-1500, but
  plane2/3 ~60-105 (persistent, not just the title frame);
- colour indices in use do grow over frames (up to `0,1,3,4,7,8,9,12,14,15`),
  so the output is not literally two colours — it is dominated by index 0
  (black, ~91%) and index 3 (cyan, ~9%), which reads as "black/blue";
- sequencer map-mask writes (`OUT 03C5h,01/02/04/08h`) are *balanced* across all
  four planes, and there are **zero** attribute-controller (`03C0h`) palette
  writes.

Interpretation: the palette is the fixed default (so colour *mapping* is not the
bug), and all four planes are addressed, yet planes 2 and 3 end up almost empty.
The verified `1010:4537` 4-plane row expander is bit-identical to the original
ASM (re-confirmed this pass by a 3000-state differential fuzz), so the missing
plane-2/3 data is **upstream** of the present/expansion hooks: either the source
bytes fed into the EGA decode, or an EGA-specific decode path, are not
delivering the high planes.  A real fix most likely needs the memory model to
represent EGA planar writes (map-mask routing into the four `A000` shadow
planes) and/or a corrected EGA source-decode — a sizeable feature that is
deliberately **not** attempted here so the working CGA and Tandy modes stay
untouched.  Use `diag_video.py --video ega` to track this as the EGA work
continues.

## Performance: measured ceiling, no free safe win

Clean A/B micro-benchmarks (1.5M boot steps, no profiler overhead) this pass:

- hoisting `4537`'s six per-call closures to module level: ~19.0s vs ~19.6s
  (no improvement — closure creation was not the bottleneck);
- guarding the interpreter's per-instruction disassembly f-strings behind
  `trace_enabled`: ~18.7s vs ~19.0s (within noise).

So the verified micro-optimisations that looked promising do **not** move the
needle and were not applied (to avoid churn/risk).  The interpreter is near its
CPython per-instruction ceiling (~80-140k interpreted-steps/sec) and the loading
path is bound by pure-Python pixel expansion (`450C`/`4511`/`4537`), which is
already a verified hook.  Realistic high-impact options, in order of
safety/leverage:

1. **Run under PyPy** — an interpreter dispatch loop like this typically gets
   10-50x for free with no code change; the current CPython path stays as the
   fallback.  This is the recommended lever for "performance is poor".
2. Skip the one-time ~11-15s asset-decode bootstrap during development with
   `python scripts/play.py --snapshot <dir>` (already supported).
3. Longer term: a dispatch-table interpreter core, or numpy/C vectorisation of
   the 4-plane expansion — both higher risk and deferred per the project's
   correctness-first rules.

The checkpoint-21 changes (the verified `1010:477E` sprite-blit hook, the dead
`prefixes` cleanup, the profiler, and the diagnostics) remain in place.

---

# Current run status — checkpoint 21

Validated on `assets/OVERKILL.UNLZEXE.EXE`.

Focus of this pass: profiling the asset-heavy loading path, one safe new
performance hook, and EGA/Tandy diagnostics.  CGA and Tandy correctness are
preserved; no gameplay logic was rewritten.

## What changed

- **New profiler `scripts/profile_hotspots.py`** (rewritten).  It samples the
  executed CS:IP every step and wraps every registered hook with a timing/
  counting shim, then prints a wall-clock breakdown of interpreter vs
  decode-hook vs present/graphics-hook time, the hottest CS:IP addresses, and
  the hooks ranked by cumulative time.  Counters live in the script, so the
  interpreter core stays clean.

      python scripts/profile_hotspots.py 3000000 --top 25
      python scripts/profile_hotspots.py 1500000 --video tandy

- **New `1010:477E` hook `overkill_sprite_blit_9x16_477e`.**  Profiling showed
  the single hottest *interpreted* routine during sprite-heavy loading is the
  fully-unrolled fixed-geometry blit at `1010:477E..480D`: it copies a 9-byte
  wide by 16-row sprite from `DS:SI` (source stride 52) into a packed `ES:DI`
  buffer, with `ES`/source-`DS` loaded from `CS:[9596]`/`CS:[9598]` and `DS`
  restored to `CS:[9596]` on exit.  The hook reproduces that exactly (registers,
  flags from the final `add si,2Bh`, the 144 copied bytes, near RET) and is
  verified against interpreted ASM for both `DF=0` and the `DF=1` fallback in
  `tests/test_replacements.py::test_sprite_blit_477e_hook_matches_interpreted_asm`.

- **Interpreter micro-cleanup in `overkill_port/cpu.py`.**  Removed a dead
  per-instruction `prefixes` list that was allocated on every `step()` but never
  read, and hoisted the segment-override prefix table to a module-level
  `_SEG_OVERRIDE` dict instead of rebuilding it per prefix byte.  No semantic
  change; the core regression suite still passes.

- **New diagnostics `scripts/diag_video.py`.**  Runs the original code to the
  first frame-present in the requested mode and reports, for EGA, the nonzero
  byte count of each of the four `A000` shadow planes and the full 16-colour
  index histogram; for Tandy/CGA the packed nibble/2bpp histogram.

      python scripts/diag_video.py --video ega
      python scripts/diag_video.py --video tandy

## Profiling finding (loading path)

In a 1.5M-step CGA boot window the wall-clock split was roughly interpreter
31% / decode-hooks 68% / present 1%.  The decode-hook time is dominated by the
already-verified 4-plane expansion driver `1010:450C`
(`overkill_expand_4plane_list_450c`) and the per-block renderer it calls,
`1010:4511`.  The hottest *interpreted* region is the `1010:A849..A9E0` sprite
dispatcher that calls `1010:477E`.  The new 477E hook removes the unrolled-MOVS
body of that dispatcher (~96 interpreted instructions per call) but, because
477E is only ~2-3% of boot steps, the headline boot time is still governed by
the 450C/4511 expansion phase.  Speeding that up further would mean optimising
the existing renderer hook rather than adding new ones, which is deferred to
keep the verified path intact.

## EGA diagnostic finding (supersedes the "only one plane" hypothesis)

`diag_video.py --video ega` at the first EGA present (reached ~2.34M steps,
stopping around `1010:D013`) reports:

- plane 0 nonzero = 1378/8000, plane 1 = 1461/8000, plane 2 = 87/8000,
  plane 3 = 95/8000;
- colour indices actually used = `0, 2, 3, 8, 12, 14` (index 0 = 90.8%,
  index 3 = 8.9%, the rest < 0.3%).

So the renderer *is* combining multiple planes (indices 3/12/14 require more
than one plane), which **refutes** the earlier "only plane 0 / only indices
0,1" theory.  The real symptom is that planes 0 and 1 carry almost all the data
while planes 2 and 3 are nearly empty, so the first presented EGA frame is
cyan(index 3)-on-black - consistent with the "black/blue" report but now
quantified.  Open question: whether planes 2/3 are legitimately sparse for this
particular (title/loading) frame or are being under-filled upstream.  Capturing
several EGA presents with `diag_video.py` is the recommended next EGA step.

## Tests

`48 passed` (was 47; one new self-contained 477E differential test).  Run with:

    python -m pytest -q

Compile check:

    python -m py_compile scripts/profile_hotspots.py scripts/diag_video.py \
        overkill_port/cpu.py overkill_port/replacements.py

## Still unknown / next

- EGA: are planes 2/3 under-filled, and where (compare several presents)?
- Loading speed is now bounded by the 450C/4511 4-plane expansion hook; any
  further win there must stay a verified transliteration.
- CGA and Tandy remain the correctness oracles and were not changed.

---

# Current run status — checkpoint 20

Validated on `assets/OVERKILL.UNLZEXE.EXE`.

Commands used in this pass:

```bash
python -m py_compile scripts/play.py scripts/render_cga.py overkill_port/runtime.py overkill_port/replacements.py
python -m pytest -q
python scripts/render_cga.py artifacts/play_tandy_edrax_orbit_combat_20260611_214016 --video cga --out artifacts/evidence/test_cga.png
python scripts/render_cga.py artifacts/play_tandy_edrax_orbit_combat_20260611_214016 --video ega --out artifacts/evidence/test_ega.png
```

Result:

- tests pass: `43 passed`,
- `create_runtime(..., command_tail=...)` can now pass a DOS PSP command tail to
  the original executable,
- `scripts/play.py` has `--video cga|ega`; `--video ega` launches the original
  code with the documented `/E` command-line selector,
- EGA mode uses the original mode-1 present path at `1010:2750`, which writes to
  `A000h` through the EGA sequencer map-mask mechanism,
- because the project memory model is a flat bytearray, the new `1010:2750`
  replacement stores the presented EGA frame in explicit shadow planes inside
  the `A000h` aperture (`+0000/+2000/+4000/+6000`),
- `scripts/render_cga.py` and `scripts/play.py` can decode that EGA shadow layout
  as 320x200 16-colour RGBI/EGA output,
- CGA remains the default and still uses the previously stabilized B800h pacing
  path.

Useful commands:

```bash
python scripts/play.py --fps 30 --game-hz 30
python scripts/play.py --video ega --fps 30 --game-hz 30
```

If intro/menu speed needs tuning independently from gameplay, use:

```bash
python scripts/play.py --video ega --fps 30 --game-hz 30 --retrace-hz 60
```

---

# Current run status — checkpoint 19

Validated on `assets/OVERKILL.UNLZEXE.EXE`.

Commands used in this pass:

```bash
python -m pytest -q
```

Result:

- tests pass: `41 passed`,
- added 8086 opcode `27h` / `DAA` to `overkill_port/cpu.py`,
- confirmed this is not simply a stray VM/IP leak: the loaded runtime overlay rewrites
  `1010:5F18` from the startup byte `C6` into a legitimate `DAA` sequence, and
  previous snapshots already contain `27` at that address,
- added focused BCD adjust tests for the score/text digit path around
  `1010:5F18`, including `DAA` carry propagation after `ADD AL,imm8`.

The intro/menu retrace pacing from checkpoint 18 remains in place.  If the player
now reaches the same path, it should no longer crash on `Unsupported opcode 27 at
1010:5F18`.

Useful command:

```bash
python scripts/play.py --fps 30 --game-hz 30
```

If intro/menu speed needs tuning independently from gameplay, use:

```bash
python scripts/play.py --fps 30 --game-hz 30 --retrace-hz 60
```

---

# Current run status — checkpoint 18

Validated on `assets/OVERKILL.UNLZEXE.EXE`.

Commands used in this pass:

```bash
python -m pytest -q
python scripts/play.py --fps 30 --game-hz 30
```

Result:

- tests pass: `39 passed`,
- the latest player no longer assumes that gameplay's `1010:0679` timer wait is
  the only timing source,
- `1010:50C9` VGA retrace waits are now paced in `scripts/play.py` as well,
  because intro/menu/transition code uses that path for visible delays,
- B800h is checksummed and Tk receives a new immutable snapshot only when the
  visible screen changed, which prevents static retrace delay loops from
  flooding the UI with duplicate frames,
- `1010:58DF` is disabled in interactive play by default so its internal direct
  calls to the 50C9 helper do not bypass the retrace pacing wrapper,
- the previous unsafe dirty/render hooks remain disabled by default:
  `1010:41A6`, `1010:4D15`, `1010:CCAA`, `1010:CCC4`, `1010:CCF0`.

Controls (`scripts/play.py`): **Q up, A down, O left, P right, Z / Space fire, Esc quit.**

Useful command:

```bash
python scripts/play.py --fps 30 --game-hz 30
```

If intro/menu is too slow or too fast, tune the VGA wait pacing separately:

```bash
python scripts/play.py --fps 30 --game-hz 30 --retrace-hz 60
```


## 2026-06-10 EGA performance update

- EGA mode now has additional verified hooks for the hot mode-1 row conversion
  path: `280D`, `2824`, `291C`, and `2932`.
- These are narrow replacements of known loops, not broad renderer guesses.
- The visible EGA output is still using the current A000 shadow-plane renderer;
  the reported blue/black menu suggests there is still more EGA palette/plane
  investigation to do, but the new hooks target the slow startup/menu path.
- Test suite: `47 passed`.

### 2026-06-10 Tandy video mode experiment

`scripts/play.py` now accepts `--video tandy` and passes the original documented
` /T` PSP command-tail selector to the game.  The live player wraps the mode-2
presenter at `1010:3354` as a frame boundary and renders the Tandy/PCjr
320x200x16 packed aperture from `B800h`.

Implemented pieces:

- `1010:3354 overkill_present_tandy_frame_3354` mirrors the original mode-2
  presenter: `52` words (`104` bytes) per row, `192` rows, starting at `00A0h`,
  with the Tandy four-bank row stepping (`+2000h`, wrap with `+80A0h`).
- `render_tandy_ppm()` decodes the Tandy layout as two 4-bit RGBI pixels per byte
  with scanlines split as `(y & 3) * 2000h + (y >> 2) * 160`.
- `scripts/render_cga.py --video tandy` can render snapshots using the same
  decoder.

The regular test suite remains green (`47 passed`).  This is intentionally an
experimental third video mode rather than a replacement for fixing the remaining
EGA plane/palette issue.

### 2026-06-10 Tandy selector fix

The first Tandy experiment passed the documented ASCII `/T` switch directly to
`OVERKILL.UNLZEXE.EXE`.  That is not what the already-unpacked inner executable
expects: its startup parser reads `PSP:82` as a compact binary video selector
(`0=CGA`, `1=EGA`, `2=Tandy`).  ASCII `/T` therefore looked like an out-of-range
selector and fell back to EGA, while `play.py` was watching the Tandy `B800h`
aperture, producing black frames.

`play.py --video ega` and `--video tandy` now pass the inner binary selector
instead:

- EGA: `bytes((0x0D, 0x01))`
- Tandy: `bytes((0x0D, 0x02))`

The `--dos-args` escape hatch remains for raw ASCII PSP-tail experiments.
