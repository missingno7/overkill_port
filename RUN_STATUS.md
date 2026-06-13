# 2026-06-13 artifact cleanup checkpoint

Repository cleanup pass after the hook-integrity work.  The runtime/code
behavior was not intentionally changed.

Removed/generated-pruned material:

- old root `artifacts/snapshot_play_*` gameplay snapshots that were not regression fixtures;
- old root `artifacts/play_*` captures that were not regression fixtures;
- `artifacts/tmp_*` stop/verify scratch snapshots that were not regression fixtures;
- generated `artifacts/frame_verify/` PNG/VRAM diff dumps;
- non-test, stale `artifacts/evidence/*` probe snapshots;
- root scratch helpers `dump_at.py` and `headless_coverage.py`.

Kept durable artifacts only:

- `artifacts/test_oracles/*` used by regression tests, including promoted former root snapshots;
- evidence snapshots still referenced by regression tests;
- `artifacts/evidence/hook_verify_tandy_20260613_190326` as the current
  headless hook-verifier seed;
- `artifacts/hook_coverage_cache.json`;
- `artifacts/README.md` with the retention policy.

Validation after cleanup:

```text
python -m pytest -q
185 passed

python -m compileall -q overkill_port tests scripts
OK

python scripts/verify_hooks_headless.py --snapshot artifacts/evidence/hook_verify_tandy_20260613_190326 --verify-max 1000 --fast-ranges
OK HOOK VERIFY LIMIT REACHED verified=1000
```

Size changed from roughly 183 MB to roughly 30 MB while keeping all regression oracles.

---

## 2026-06-13 Tandy hook integrity / C054 cleanup pass

Continued from the `1010:BC4B overkill_object_postmove_bc4b` full-memory
divergence at call 3 on `artifacts\snapshot_play_tandy_20260613_190326`.

Results:

- Added `scripts/verify_hooks_headless.py`, a pygame-free live hook verifier for
  snapshot runs.  It mirrors `play.py --verify-hooks` but can run in CI/minimal
  shells and automatically disables non-CGA interactive hooks such as `1010:58DF`
  for Tandy/EGA snapshots unless explicitly requested.
- Refactored the duplicated `C054:C12D` effect-spawn tail into
  `_run_c054_c12d_effect_spawn_tail`.  The helper preserves the visible dead
  stack scratch from `PUSH BX`, `PUSH BP`, `CALL 7420`, and decrements
  `DS:A47E`, so this is cleanup only, not a behavior change.
- Removed temporary `tmp_*.py` debugging scripts from the working tree after the
  reusable headless verifier replaced them.

Verification:

```text
python -m pytest -q
# 185 passed
python scripts/verify_hooks_headless.py --snapshot artifacts/snapshot_play_tandy_20260613_190326 --verify-max 9000
# HOOK VERIFY LIMIT REACHED verified=9000, no divergence
python scripts/verify_hooks_headless.py --snapshot artifacts/snapshot_play_tandy_20260613_190326 --verify-max 10000 --fast-ranges
# HOOK VERIFY LIMIT REACHED verified=10000, no divergence
```

Note: a full-memory 10k run was attempted too, but it did not finish within the
available sandbox timeout after passing the 9k checkpoint without divergence.

## 2026-06-14 original asset source switch

Switched active runtime/test/script defaults from generated convenience files to
the original OVERKILL assets:

- executable/container: `assets\OVERKILL`
- companion splash/loader data: `assets\OVERKILL.EXE`

Removed generated assets:

- `assets\OVERKILL.UNLZEXE.EXE`
- `assets\OVERKILL.OVERLAY.BIN`

Notes:

- `assets\OVERKILL` is itself an MZ executable with the 467,649-byte overlay
  appended, so the runtime now lets the original unpack/bootstrap path produce
  the in-memory game image.
- `create_runtime()` keeps `OVERKILL.UNLZEXE.EXE` as a legacy alias only when
  that generated file is absent, mapping it to sibling `OVERKILL` so old
  snapshots/commands can still be loaded.
- The original startup path exposed two narrow BIOS/port details that the
  generated file hid: INT 10h/AH=05h active display page selection, and
  monochrome status port `03BAh` polling with bit `80h`.

Verification:

```text
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\run_tests.py
# 207 passed, 0 failed
headless Tandy original-container smoke with --verify-hooks --verify-require-metadata --verify-max 50
# HOOK VERIFY LIMIT REACHED verified=50, no divergence
```

## 2026-06-13 strict hook verifier cold-start cleanup

Followed up on `scripts\play.py --verify-hooks --verify-stop-on-diff` after
full-memory verification became the default.

Fixes:

- `HookVerifier._clone_runtime()` now copies `DOSMachine.console_input_fallback`.
  Interactive play sets this to `None`; the ASM oracle clone was accidentally
  reverting to the default Esc fallback and producing a false DOS/state diff at
  `1010:0FE4`.
- `1010:450C` verifier metadata now treats the lifted routine as the whole
  4-plane list parent ending at `44AA`, not as a single-block loopback to
  `450C`.
- `1010:450C` now preserves the dead-stack scratch word left by the original
  `CALL 44D7` / `RET` path (`SS:SP-2 = 450F`), which full-memory verification
  observes.
- Added verifier metadata for already-understood helpers `41A6`, `41DA`,
  `50C9`, and `58DF`.
- `1010:58DF` now self-disables for non-CGA modes before touching stack,
  registers, or memory.  The previous guard happened after setup side effects,
  which made raw Tandy all-hooks verification diverge.

Verification:

```text
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\run_tests.py
# 185 passed, 0 failed
headless Tandy cold start with command_tail=(0D,02), --verify-hooks, --verify-require-metadata, --verify-max 500
# HOOK VERIFY LIMIT REACHED verified=500, no divergence
```

## 2026-06-13 hook verifier full-state default

Changed live hook verification so full memory comparison is the default instead
of an opt-in mode.  The old named-range verifier can still be requested with
`--verify-fast-ranges` for profiling/debug sessions, but normal
`--verify-hooks` should now catch object/gameplay state divergence immediately
even when the changed byte is not in CS/video/stack helper ranges.

Also broadened DOS/BIOS/runtime-side comparisons to include allocator state,
open file metadata/data, keyboard queues, text output, video/timer counters, and
speaker/port tracking.

Verification:

```text
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\run_tests.py
# 185 passed, 0 failed
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m overkill_port.cli continue-snapshot assets\OVERKILL.UNLZEXE.EXE artifacts\snapshot_play_tandy_20260613_181804 --game-root assets --steps 50000 --verify-hook 1010:BC45 --verify-hook 1010:BC4B --verify-stop-on-diff --verify-max 20 --out-dir artifacts\tmp_verify_full_memory_smoke
# HOOK VERIFY LIMIT REACHED verified=20, no divergence
```

## 2026-06-13 BEC5 second-counter collision tail fix

Investigated `artifacts\snapshot_play_tandy_20260613_181804`, where enemies
appeared to survive longer than the reference.

Findings:

- Frame verification diverged at frame 42.
- The first gameplay-state difference was `DS:2078`: reference decremented the
  linked counter from `03` to `02`, while the candidate left it at `03`.
- A watchpoint showed the reference write happened at original `1010:BFFE`,
  inside the shared `BFC7` death/transition tail.
- The lifted `BEC5` variant-2, `BEDC=0` path handled the `BF46` "second counter
  zero" branch by leaving `IP=BF46`.  That is not safe inside the composed
  `BC45/BC4B` parent path because the parent unwinds and overwrites the
  continuation.  The original `BF46` branch jumps to `BFC7`, so the lift must
  run the BFC7 tail inline.

Fix:

- `BEC5` now routes the observed second-counter-zero path into the shared BFC7
  tail, matching `BF46 -> BFC7`.
- Added a focused regression for the exact linked-counter decrement at
  `DS:2078`.
- Hook verification now defaults to full-memory comparison, so object/counter
  state is checked even when it lives outside the old named ranges.

Verification:

```text
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\run_tests.py
# 184 passed, 0 failed
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\play.py --snapshot artifacts\snapshot_play_tandy_20260613_181804 --verify-frames --verify-frame-max 60 --verify-frame-source both
# FRAME VERIFY OK frames=60
```

## 2026-06-13 interactive Tandy timer ordering guard

Investigated a hidden level-start issue where the initial enemy sequence played
but the next level phase did not appear to continue in interactive Tandy play.

Findings:

- Long Tandy frame verification from
  `artifacts\test_oracles\snapshot_play_tandy_20260611_152751` stayed clean
  through 500 frames, so the deterministic hooked runtime still matches the ASM
  frame oracle at that level-start snapshot.
- The interactive SDL path had one extra source of timer mutation that the frame
  verifier does not exercise: `present_hook` could call
  `AsyncTimerIrqDriver.poll()` before the normal `1010:0679` frame wait.  If that
  IRQ advanced `CS:[066B]`, the later `0679` hook could return immediately
  instead of delivering the expected frame ISR work at the timer boundary.

Fix:

- Removed async IRQ polling from the presenter boundary.  Async IRQs still run
  in explicit retrace/menu/input wait loops where there is no normal `0679`
  frame wait to service sound.
- After every `0679` timer boundary, re-anchor the async IRQ scheduler by one
  full OVERKILL frame (`2` PIT ticks) instead of using the raw number of ISR
  ticks that happened to run inside that hook.

Verification:

```text
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\run_tests.py
# 171 passed, 0 failed
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\play.py --snapshot artifacts\test_oracles\snapshot_play_tandy_20260611_152751 --verify-frames --verify-frame-max 300 --verify-frame-source both
# FRAME VERIFY OK frames=300
```

## 2026-06-13 live frame verifier preview

Added an interactive preview mode for frame verification.

Behavior:

- `python scripts\play.py --verify-frames --verify-frame-preview` now launches
  the normal SDL viewer and publishes the candidate runtime while each frame is
  compared against the reference ASM runtime.
- Keyboard input is delivered to both runtimes before frame boundaries, so the
  verifier can be played like `--verify-hooks`.
- With live preview and the default `--verify-frame-max 60`, the verifier treats
  the run as unbounded so the window does not close almost immediately.  Pass an
  explicit `--verify-frame-max N` for a bounded live run.
- The old "open compare image on divergence" behavior is now
  `--verify-frame-preview-on-diff`.

Verification:

```text
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\run_tests.py
# 173 passed, 0 failed
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\play.py --snapshot artifacts\test_oracles\snapshot_play_tandy_20260611_152751 --verify-frames --verify-frame-max 5 --verify-frame-source both
# FRAME VERIFY OK frames=5
```

## 2026-06-13 hook verifier throughput pass

Improved `--verify-hooks` throughput without changing verifier coverage.

Follow-up after an interactive `play.py --verify-hooks --verify-stop-on-diff`
stall report:

- Headless cold-start verification reproduced a real verifier oracle problem:
  raw interpreted ASM for `1010:0679` can spin forever at the timer wait because
  the original busy-loop depends on IRQ0 advancing `CS:[066B]`.
- `HookVerifier._run_asm_to_target` now recognizes the original `0679/067F`
  timer wait and delivers the real installed OVERKILL INT 08h handler
  (`1010:06E5`) when `CS:[066B] == 0`.  This is not a synthetic fallback; it is
  the same game ISR the original wait loop is expecting.
- `scripts/play.py` now passes a verifier progress callback so the SDL status
  line shows the current hook being verified during long oracle runs.

Changes:

- `HookVerifier._clone_runtime` now copies the current memory image directly
  instead of allocating and zeroing a fresh full memory buffer before copying.
- `HookVerifier._range_diff` now uses a C-level `memoryview` equality check for
  identical ranges, and only walks bytes when a range actually diverges.
- Added a regression test proving the optimized range diff still reports a
  clean match, exact differing-byte count, and first differing address/value.

Verification:

```text
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\run_tests.py
# 171 passed, 0 failed
C:\Users\Jiri\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m overkill_port.cli snapshot assets\OVERKILL.UNLZEXE.EXE --game-root assets --steps 2000000 --verify-hooks --verify-max 1000 --out-dir artifacts\tmp_verify_hooks_cold_final
# HOOK VERIFY LIMIT REACHED verified=1000
```

Benchmark from `artifacts\snapshot_play_tandy_20260612_151523` with
`--verify-hooks --verify-max 200`:

```text
before: ~4583 ms
after:  ~574 ms
```

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

## 2026-06-13 BEC5 variant 000A owner-linked collision tail

`snapshot_play_tandy_20260613_000648` reached `BC4B -> 62F6 -> BEC5` with a
collided slot whose logic/variant field was `000Ah`.  The original does not
have a dedicated 000A handler; after the 7/8/0C/9 table and the 2/6/5 checks it
compares the current object BP with `DS:[BX+30h]`.  A match marks the collided
slot as linked to the current object, clears `DS:[BX+1Ch]`, clears
`SS:[BP+20h]` when `A8C2 != 1`, and jumps into the shared `BFC7` transition
path.

- `_run_collision_handler_bec5_observed` now models that owner-linked fallback.
- Added a regression that advances the captured snapshot to the 53rd `BC4B`
  call and compares the lifted hook against interpreted original ASM with full
  memory equality.

## 2026-06-13 refactor pass: replacements staging split

- Moved shared OVERKILL 8086-style arithmetic/string helpers out of
  `replacements.py` into `overkill_port/games/overkill/asm.py`.
- Moved the large gameplay object/postmove/collision behavior island out of
  `replacements.py` into `overkill_port/games/overkill/gameplay/object_runtime.py`.
  The address-facing hook wrappers remain in `replacements.py` and import the
  lifted game logic back, preserving the hook-registration boundary.
- Added `1010:30BA overkill_tandy_patched_row_copy_30ba`, a signature-guarded
  hook for the runtime-patched Tandy row copier that was showing up as the
  `30C3/30C4/...` unknown hotspot cluster.  The old static bytes at `30BA` are
  not stable; if the patched row-copy signature is not resident, the hook
  interprets the current original instruction instead of guessing.
- Added `1010:30B0 overkill_tandy_interlaced_clear_30b0` for the static startup
  Tandy interlaced clear routine.
- Validation: `python scripts/run_tests.py` => `161 passed, 0 failed`.
- Live verification: `scripts/play.py --verify-hook 1010:30BA --verify-stop-on-diff`
  verified 25 calls before the smoke run timeout, with `1010:30BA` averaging
  about 112.68 ASM-equivalent instructions/call.

## 2026-06-13 video-mode label audit

- Audited CGA-labelled hooks seen during Tandy gameplay.
- Confirmed `1010:5A00`, `1010:5A24`, and `1010:5A36` are shared video-mode dispatch helpers. They select CGA/EGA/Tandy behavior through `CS:[95BC]`, so their registered hook names were changed from `overkill_cga_*` to neutral coordinate names while keeping old aliases for tests/tools.
- Reclassified `1010:4D15` and `1010:4D6F` from `cga_renderer` to `layer_sprites`: these are shared presence/occupancy-list stamp/clear helpers used by Tandy gameplay too. Mode 1 has EGA-style stacked-cell handling; CGA/Tandy share the non-mode-1 base-cell path.
- Short Tandy snapshot coverage smoke now reports zero `cga_renderer` calls for the intro/dirty-cell presenter path; shared hooks show under `coordinates`, `layer_sprites`, or `tandy_renderer` as appropriate.


## 2026-06-13 - Unknown gameplay/collision hook absorption

Absorbed several hot unknown/gameplay instructions without duplicating existing logic:

- `1010:AED8 overkill_object_behavior_aed8` now hooks the observed logic-id 2/3 countdown/movement behavior and reuses a shared `AD60` bounds/tile tail.
- `1010:AD04 overkill_object_logic_branch_ad04` is only a branch selector: it returns or jumps to existing `ABxx` behavior tails, rather than reimplementing those tails.
- `1010:AC81 overkill_object_slot_scan_guard_ac81` is only the guard/setup for the already-lifted `AC97` object-slot scan and directly reuses `run_object_slot_scan_ac97`.
- `1010:AE09 overkill_object_behavior_ae09` handles the observed logic-id `0Ch` timer/3-pixel movement behavior, then reuses the same shared `AD60` tail as `AED8`.

The previous inline `AD60` implementation inside `AED8` was refactored into `_run_object_bounds_tile_tail_ad60` so new behaviors do not clone the same bounds/tile/deactivation logic.

Validation: `python scripts/run_tests.py` => `162 passed, 0 failed`; `python -m compileall -q overkill_port tests scripts`; live hook verifier samples were recorded for `AC81`, `AD04`, `AE09`, and `AED8` and added to `artifacts/hook_coverage_cache.json`.

## 2026-06-13 startup renderer table unknown absorption

- Identified the `1010:0F31/0F32/0F37` unknown startup cluster as the inner loop
  of `1010:0F0B`, a renderer coordinate/video lookup-table builder.
- Added `1010:0F0B overkill_startup_coordinate_tables_0f0b` in the renderer
  module.  The hook generates the `DS:99C8..A077` table family and reuses the
  existing `1010:0FA3` lifted helper for the fallthrough table builder, avoiding
  a second implementation of the same `0FA3` logic.
- Regression oracle `snapshot_stop_1010_0f0b_startup_tables` compares the lifted
  hook against fully interpreted ASM through continuation `1010:526A` with full
  CPU and memory equality.
- Validation: `python scripts/run_tests.py` => `163 passed, 0 failed`.
- Live verification: `scripts/play.py --video tandy --verify-hook 1010:0F0B
  --verify-stop-on-diff` verified the cold-start call with no divergence before
  the smoke timeout.
- Remaining cold-start unknowns around `32FF:0052` belong to the transient
  unpack/relocation bootstrap segment, not to a stable game island.  I did not
  hook them because the segment is dynamically loaded and not useful as a game
  module boundary.

## 2026-06-13 documentation/methodology refresh

Updated the project documentation to describe the now-established source-port
method as a reusable system rather than a pile of one-off OVERKILL fixes.

Main documentation changes:

- Added `docs/source_port_methodology.md`, the canonical playbook for the
  evidence-driven workflow:
  `observe -> classify -> choose boundary -> build ASM oracle -> implement hook -> verify -> document -> move to island`.
- Updated `AGENTS.md` with the canonical workflow, the current island-module
  layout, the staging rule for `replacements.py`, and the requirement to search
  for existing tails/helpers before implementing a new hook.
- Removed a duplicated `CPU Interpreter Rules` section from `AGENTS.md`.
- Updated `README.md` with the methodology loop, current island examples, and a
  pointer to the new methodology document.
- Updated `docs/design.md` with the current `games/overkill/` module map and the
  migration path from original ASM to staged hook to island module.
- Replaced the stale `docs/next_steps.md` bootstrap-era TODO list with current
  priorities: meaningful unknown absorption, keeping `replacements.py` as
  staging, duplicate-code prevention, intentional verification modes, and island
  documentation hygiene.

No runtime code changed in this pass.

## 2026-06-13 logic-pyramid documentation and bootstrap classification

- Added the end-goal source-port pyramid to `docs/source_port_methodology.md`,
  `docs/design.md`, `README.md`, `AGENTS.md`, and `docs/next_steps.md`:
  original binary oracle -> ASM-compatible hook/runtime -> verified lifted
  routine -> runtime object/data model -> game systems -> gameplay archetypes ->
  semantic game model -> modern/enhanced port layer.
- Clarified that current object work is mostly still layer 4: slots with
  sprite/layer/logic-id/movement/collision fields.  Player/projectile/enemy/boss
  names should emerge only after multiple verified routines support them.
- Added a `bootstrap` coverage island for the transient `32FF:*` cold-start
  unpack/self-relocation segment.  This makes the dashboard more honest: these
  instructions are no longer `unknown`, but they are also not a game-module island
  to hook prematurely.
- Added `32FF:0052 inner_unpack_relocation_bootstrap_32ff_0052` to
  `symbols.json` as `classified-do-not-hook`.
- Validation: `python scripts/run_tests.py`; `python -m compileall -q overkill_port tests scripts`.

## 2026-06-13 crystallization methodology integration

Integrated the user-supplied methodology dump into durable project docs.

Updated:

- `docs/source_port_methodology.md` with the full evidence ladder: original
  oracle, layer ownership, dependency direction, promotion rules, vertical
  slices, definitions of done, AI task framing, and hard anti-chaos rules.
- `docs/island_truth_tables.md` as the new per-island confidence/evidence index.
- `AGENTS.md` with hard layer boundaries, task framing examples, dependency
  direction, and the requirement that every semantic name remains reversible to
  original ASM evidence.
- `README.md`, `docs/design.md`, and `docs/next_steps.md` to point future work at
  the crystallization model and island truth tables.

No runtime behavior changed. Validation: `python -m compileall -q overkill_port tests scripts`; `python scripts/run_tests.py`.

## 2026-06-13 unknown/island cleanup continuation

Continued the evidence-driven cleanup after the crystallization-methodology pass.

Runtime changes:

- Added `1010:5A6C overkill_menu_cell_source_blit_dispatch_5a6c`, a shared
  source-cell video-mode dispatch stub used by the dirty-cell presenter.  It is
  classified under `layer_sprites`, not CGA/Tandy-specific rendering, because it
  only reads `CS:[95BC]` and jumps through the mode table.
- Registered/lifted `1010:AB10 overkill_object_logic_ab10` using the live
  runtime-patched byte shape.  The deactivation path through `AC22` is now
  modelled instead of fail-fast.
- Added `1010:AB77 overkill_object_behavior_ab77` as an observed object-behavior
  driver.  It deliberately reuses existing `AB4F`, `AC28`, and `AC81/AC97`
  helpers and preserves original continuations for still-unlifted tails.
- Added `1F8F:0922 overkill_gameplay_counter_tick_1f8f_0922` and the new
  `game_state` coverage island.  This routine lives in an overlay segment but is
  per-frame/game-state counter logic, not asset decoding.
- Moved the `1010:0679` timer wait implementation out of `replacements.py` into
  the sound/timer island and added the companion `1010:0672` clear-timer-flag
  hook there.
- Added `1010:511F overkill_video_page_toggle_511f`, a shared per-frame video
  page stub.  It is a no-op return in Tandy/CGA but toggles the mode-1 visible
  page state.

Classification changes:

- `1010:D007..D04C` is now classified as the main gameplay frame-loop dispatcher
  under `game_state`, not raw unknown code.
- `1010:A846/A85E/A876` and `1010:4CED..4D14` are classified as layer-sprite /
  presence-list parent frontiers.  They are not hooked yet because they should be
  composed from existing `A849/A861/A87C/4D15` helpers rather than duplicated.

Validation:

- `python -m compileall -q overkill_port tests scripts`
- `python scripts/run_tests.py` => `165 passed, 0 failed`
- `scripts/play.py --snapshot artifacts/snapshot_play_tandy_20260613_000648
  --verify-hook 1010:0672 --verify-hook 1010:0679 --verify-hook 1010:511F
  --verify-hook 1F8F:0922 --verify-hook 1010:AB77 --verify-hook 1010:AB10
  --verify-hook 1010:5A6C --verify-stop-on-diff --verify-max 250` reached the
  verifier limit with no divergence.

## 2026-06-13 layer-sprite present parent cleanup

Continued the unknown/island cleanup by absorbing the A90C/A93C/4D64 present-scan
frontier without duplicating the underlying renderer/presence loops.

Runtime changes:

- Added `1010:A90C overkill_present_object_scan_pair_a90c`, the two-table
  present parent.  It sets `CX=22h` and reuses the existing `A90F` scan over
  `DS:8D12`, then sets `CX=24h` and reuses the existing `A927` scan over
  `DS:32CA`.  If either child scan finds an active entry, the hook preserves the
  original partial continuation at the real `CALL 5A92` site.
- Added `1010:A93C overkill_present_scan_clear_presence_a93c`, modelling the
  tiny `CALL 4D64 ; RET` parent.
- Added `1010:4D64 overkill_clear_presence_list_parent_4d64`, the setup parent
  for the already-lifted `4D6F` presence-list clear loop.  It sets
  `ES=CS:[9598]`, `SI=C7B1h`, and `CX=28h`, then tail-runs the existing `4D6F`
  hook.
- Classified the next `D04D..D072` per-frame state/UI cluster under
  `game_state` rather than leaving it as raw unknown.  It is still a larger
  frontier, not a safe small hook.

Validation:

- `python -m compileall -q overkill_port tests scripts`
- `python scripts/run_tests.py` => `165 passed, 0 failed`
- `1010:A90C` verified for 50 calls from `artifacts/evidence/snapshot_stop_1010_a90c`.
- `1010:A93C` verified for 10 calls from `artifacts/evidence/snapshot_stop_1010_a93c`.
- `1010:4D64` verified on its direct stop snapshot.

## 2026-06-13 next unknown cleanup: pacing loops, postmove prelude, loading scroll, counters

Continued the evidence-driven unknown cleanup after the A90C/A93C/4D64 layer-sprite pass.
The focus was small, composable hooks that remove meaningful unknown coverage without
collapsing larger orchestration boundaries or duplicating existing lifted logic.

Runtime changes:

- Added `1010:96C5 overkill_intro_retrace_delay_loop_96c5` and companion
  `1010:96C8 overkill_intro_retrace_delay_loop_tail_96c8`.  This is the
  intro/menu fixed-count `CALL 50C9 ; LOOP` delay.  The hook calls the installed
  `50C9` hook instead of the base implementation so interactive `play.py` keeps
  its visual pacing/publish boundary.
- Added `1010:BC45 overkill_object_postmove_prelude_bc45`.  This tiny collision
  prelude adds `DS:[A278]` into `SS:[BP+02]`, then reuses the shared `BC4B`
  postmove/collision chain.  The hook performs the final near return exactly like
  the interpreted fallthrough path.
- Added `1010:4E0D overkill_tandy_loading_scroll_until_4e0d`, the loading-scroll
  parent around the existing lifted `A781` step.  It preserves `SI/DI`, loops
  until `DS:[2350] <= DI` and `DS:[234E] == 0`, then stores `SI` into `DS:[A978]`.
  The nested return IP is intentionally `4E12`, matching the original stack scratch.
- Added `1010:61CA overkill_decrement_first_active_counter_scan_61ca`, the hot
  inner scan over `DS:2368..2372` word counters.  It decrements the first non-zero
  counter and returns when all are zero.  The `1010:61C5` parent remains available
  for callers that enter before loading `DI=2368`, but real hot gameplay calls
  commonly enter directly at `61CA`.

Anti-duplication notes:

- `96C5` does not inline the retrace/publish wait; it composes the installed
  `50C9` hook.
- `BC45` does not copy the postmove/collision chain; it delegates to the existing
  `BC4B` implementation.
- `4E0D` does not clone the loading-scroll step; it calls the existing lifted
  `_loading_scroll_step_a781`.
- `61CA` is the shared scan core used by the `61C5` parent and direct hot callers.

Validation:

- `python -m compileall -q overkill_port tests scripts`
- `python scripts/run_tests.py` => `167 passed, 0 failed`
- Live hook verifier coverage was checked for `1010:96C5`, `1010:BC45`,
  `1010:4E0D`, and `1010:61CA` with no divergence in the exercised snapshots.

Remaining useful frontiers:

- `1010:9FEA` appears to be an object/table coordinate update helper.  Build a
  direct oracle before naming it as movement or object-runtime logic.
- `1010:5EF9` looks like a small text/nibble rendering helper around `5F06`.
- `1010:4D95` is likely another presence-list parent and should compose `4D15`.
- `1010:780E` is a Tandy/layer draw sub-loop candidate.
- `1010:8A7E` is object-behavior frontier; do not promote to enemy/projectile
  semantics until child helpers and evidence traces converge.

## 2026-06-13 island classification sanity pass

Goal: keep the current work in the strict first/lifted-routine layer and make
island ownership match observed behavior rather than historical address names or
segment residence.

Corrections made:

- `startup_graphics.py` moved from `asset_codecs/` to `rendering/startup_graphics.py`.
  The routines there materialize renderer/startup tables and graphics buffers;
  they are not asset codecs just because they run during loading.
- `1F8F:0960` moved from overlay/asset ownership to `gameplay/game_state.py` and
  registered as `overkill_gameplay_counter_stride_loop_1f8f_0960`.  It lives in
  an overlay segment, but it updates gameplay counters, so segment residence is
  not the island classifier.
- Coverage now has separate `overlay` and `startup_graphics` dashboard islands.
- Coverage exact-address sets are tested to be non-overlapping, and every
  registered hook is tested to classify to a non-`unknown` island.
- `scripts/audit_islands.py` now uses the same `OverkillCoverageClassifier` as
  the live dashboard, so audit output and runtime coverage cannot silently drift
  apart.

Current first-layer rule reinforced:

- Keep hook names technical and evidence-based.
- Do not introduce semantic names such as concrete enemies/projectiles while we
  are still only proving runtime object-slot behavior.
- Move stable lifted behavior out of `replacements.py` into the correct island,
  but keep `replacements.py` as address-facing hook glue and compatibility
  aliases only.

Validation:

```text
python -m compileall -q overkill_port tests scripts
python scripts/run_tests.py
169 passed, 0 failed
```

Smoke coverage with dummy SDL now reports cold-start startup materialization as
`startup_graphics` instead of `asset_codecs`/`tandy_renderer`, and `overlay` is
reserved for the real `254A:*` overlay helpers.
## 2026-06-13 - Hook wrapper refactor / naming audit

- Moved asset/loading codec hook wrappers from `overkill_port/replacements.py` to
  `overkill_port/games/overkill/hook_wrappers/asset_codecs.py`.
- Kept `overkill_port.replacements` as the compatibility aggregate import that
  registers all hooks and re-exports existing test imports.
- Normalized registry labels so all 222 registered hooks include an address
  suffix.
- Removed semantic-noise `_fast` from the two asset-codec registry labels where
  it described implementation speed rather than original-game behavior.
- Added `docs/hook_naming_audit.md` with the current naming rules and next safe
  extraction targets.
- Verification: `python -m pytest -q` => 185 passed;
  `python scripts/verify_hooks_headless.py --snapshot artifacts/evidence/hook_verify_tandy_20260613_190326 --verify-max 1000 --fast-ranges` => OK.



## 2026-06-13 - Hook wrapper refactor pass 2

- Extracted shared hook-wrapper mechanics from `overkill_port/replacements.py`
  into `overkill_port/games/overkill/hook_wrappers/common.py`:
  runtime-patched-code guard plus near-CALL wrapper helpers.
- Moved text-rendering hook wrappers into
  `overkill_port/games/overkill/hook_wrappers/text.py`.
- Moved timer/PC-speaker hook wrappers into
  `overkill_port/games/overkill/hook_wrappers/sounds.py`.
- Kept `overkill_port.replacements` as the aggregate import/re-export surface so
  old tests and scripts keep working.
- Renamed misleading shared layer-sprite registry labels:
  `768E`, `75A6`, and `7746` no longer claim Tandy-only ownership.  Old
  `overkill_tandy_*` Python names remain as compatibility aliases.
- Registered hook count remains 222.
- Verification: `python -m pytest -q` => 185 passed;
  `python scripts/verify_hooks_headless.py --snapshot artifacts/evidence/hook_verify_tandy_20260613_190326 --verify-max 1000 --fast-ranges` => OK.

Next safe extraction target is still renderer wrappers, but split it carefully:
move Tandy-only wrappers separately from shared layer-sprite scan/dispatch glue.
Do not collapse object behavior names into gameplay semantics until trace evidence
proves the object role.

## 2026-06-13 — hook cleanup pass 3: duplicate pruning and label alignment

- Renamed three asset-codec wrapper functions so decorated Python names match
  the registry labels: `overkill_file_checksum_loop_c916`,
  `overkill_packed_read_byte_0624`, and `overkill_packed_read_word_le_0615`.
- Kept the older unsuffixed names as compatibility aliases exported through
  `overkill_port.replacements`.
- Replaced the stale duplicate implementation in
  `games/overkill/asset_codecs/startup_graphics.py` with a compatibility shim
  that re-exports `games/overkill/rendering/startup_graphics.py`.
- Static hook audit now reports 222 hooks and no function/registry-label
  mismatch.


## 2026-06-13 — runtime-code variant exhaustion policy

- Promoted runtime-patched code from an ad-hoc hook guard into an explicit
  `games/overkill/runtime_code.py` manifest.
- `1010:5E42` now has named live-byte variants:
  - `gameplay_object_steer_5e42` — hooked/verified movement helper observed in
    `snapshot_play_tandy_20260613_220042`.
  - `cold_display_helper_5e42_prefix` — known cold executable body at the same
    address, intentionally not valid for the movement hook.
- Removed the previous behavior where the 5E42 hook could silently run the live
  original body when bytes did not match.  Known-wrong or unknown bytes now raise
  `UnknownRuntimeCodeVariant`.
- Added optional `Memory.write_watchers` and `RuntimeCodeWriteTracer` for tracing
  who writes into runtime-code regions without enabling it in normal gameplay.
- Added `scripts/trace_runtime_code_writes.py` with `--no-hooks` and `--all-code`
  for cold-start code-materialization audits.
- Added runtime-code tests proving cold/gameplay variant distinction, unknown
  byte fail-fast behavior, and write-tracer event capture.

Validation:

```text
pytest -q
196 passed
python scripts/verify_hooks_headless.py --snapshot artifacts/snapshot_play_tandy_20260613_220042 --verify-max 300 --fast-ranges --coverage
OK HOOK VERIFY LIMIT REACHED verified=300
```

## 2026-06-13 — runtime-code staticization scaffold

- Promoted runtime-code handling from variant fail-fast only to an explicit
  staticization manifest.
- `games/overkill/runtime_code.py` now models `RuntimeCodeSlot`, accepted/rejected
  `RuntimeCodeVariant` records, and `RuntimeCodeStaticization` targets.
- `1010:5E42` is now recorded as a polyvariant code slot whose accepted gameplay
  body is staticized into
  `gameplay.object_runtime.run_runtime_patched_object_steer_5e42`.
- Added `scripts/audit_runtime_code_staticization.py`:
  - `--check` verifies that accepted runtime-code variants have static Python
    owners.
  - `--strict-installers` additionally requires writer/installer provenance and
    is intended as the final 100% exhaustion gate.
- `trace_runtime_code_writes.py --dump-final-variants` now reports the final live
  digest/variant for registered runtime-code slots after stepping.
- Added `docs/runtime_code_staticization.md` as the policy/playbook for turning
  runtime self-modifying code into named, flat source-port logic.

Important status:

- Source-port staticization gate passes for the current known slot.
- Strict installer gate intentionally still fails for `1010:5E42` until the
  cold-start writer that materializes the gameplay body is traced and named.

## 2026-06-13 — hot unknown cleanup after runtime-code staticization

- Absorbed two misleading hot/problematic interpreted regions that were not new
  runtime-patched bodies:
  - `1010:61F7` now hooks the hot `CALL 61C7; LOOP 61F7` status-counter glue.
  - `1010:5EDB` now hooks the HUD/status text block that composes `518C`, `5EF9`,
    and `5F06`.
- Corrected the old `1010:61C5` countdown hook metadata: `61C5` is inside the
  preceding CALL immediate in the materialized runtime body.  The real routine
  entry is `1010:61C7` (`MOV DI,2368h`).
- The new `61F7` hook preserves nested CALL stack scratch and leaves FLAGS from
  the final scan, matching interpreted ASM memory/state oracle checks.
- The new `5EDB` hook preserves intermediate CALL return scratch and tail-runs
  the final `5EF9` helper so the caller's original return address is consumed by
  the same boundary as the original code.
- No additional runtime-code slot was identified in this pass; these removals are
  static hot-region absorption, not self-modifying Python behavior.

Validation:

```text
python scripts/audit_runtime_code_staticization.py --check
ok; 1010:5E42 remains the only registered runtime-code slot, staticized with
installer provenance still pending

python -m pytest -q
201 passed

python scripts/verify_hooks_headless.py --snapshot artifacts/snapshot_play_tandy_20260613_220042 --verify-max 800 --fast-ranges --coverage
OK HOOK VERIFY LIMIT REACHED verified=800
```

## 2026-06-13 runtime-code census: 5E42 is bootstrap materialization, not video selection

Investigated whether the currently known runtime-patched code is actually a
video/sound/input selector that can be retired by committing to Tandy-first.

Result:

- `1010:5E42` is installed by the transient `32FF:*` inner unpack/self-relocation
  bootstrap, specifically `writer=32FF:009B`.
- The installer writes 211 bytes into `1010:5E42-5F1A`.
- CGA, EGA, and Tandy command tails all receive the same final variant:
  `gameplay_object_steer_5e42`.
- Therefore `5E42` is not a video-card, sound-card, keyboard, joystick, or
  Amstrad-joystick selector.  It is a bootstrapped gameplay/object steering body
  that is already staticized as flat Python.
- The actual video-mode choice observed in the same census is a data/config word
  in the code segment: `CS:95BC = 0000/0001/0002` for CGA/EGA/Tandy.  That can
  be lifted later into high-level Tandy configuration; it is not executable SMC.

Added `scripts/audit_runtime_code_census.py` to make this repeatable:

```bash
python scripts/audit_runtime_code_census.py --video all --steps 250000 --show-bootstrap
```

Updated the runtime-code manifest so strict installer audit now passes:

```bash
python scripts/audit_runtime_code_staticization.py --check --strict-installers
```

Validation:

```bash
python -m pytest -q
# 202 passed

python scripts/verify_hooks_headless.py --snapshot artifacts/snapshot_play_tandy_20260613_220042 --verify-max 800 --fast-ranges --coverage
# OK HOOK VERIFY LIMIT REACHED verified=800
```
