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
python scripts/render_cga.py artifacts/snapshot_play_start --video cga --out artifacts/test_cga.png
python scripts/render_cga.py artifacts/snapshot_play_start --video ega --out artifacts/test_ega.png
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
