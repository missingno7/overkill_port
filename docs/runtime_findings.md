# Runtime findings after the second RE pass

## Checkpoint 23 — 1010:38B7 masked sprite composite, 4537 helper lift

### `1010:38B7` — masked 2-column sprite composite (now hooked)

The hottest interpreted routine in the sprite-render phase after `477E` was
lifted.  `38B7..38CF` is a `LOOP` that composites a sprite onto the destination:

```
38B7  lodsw                ; mask = DS:[SI], SI += 2
38B8  and ax, es:[di]      ; AX = mask AND dest word
38BB  or  ax, ds:[si]      ; AX |= data word = DS:[SI]
38BD  add si, 2
38C0  stosw                ; ES:[DI] = AX, DI += 2
38C1..38CA  (identical 2nd column)
38CB  add di, 0030h        ; next visible row (net DI stride 0034h)
38CE  loop 38B7            ; CX rows
38D0  (fall-through)
```

So `dest = (dest AND mask) OR data`, two words per row.  Source row layout is
`[mask0, data0, mask1, data1]` (SI += 8/row); the destination is read-modified-
written at stride `0x34`.  Exit: `CX=0`, `AX` = last word, FLAGS from the final
`add di,30h`, IP falls through to `38D0`.  Replaced by
`overkill_masked_sprite_composite_38b7`, verified bit-identical over 2000
randomised states and by a self-contained oracle test.

### `1010:4537` helpers lifted to module level

The per-call closures inside the 4537 hook (`rol8`/`ror8`/`rcl8`/`rcl16_mem`,
`pack_four_pixels`, `expand_bits`) are now module-level `_r_*` functions, defined
once and reusable.  Behaviour is unchanged (3000-state fuzz + oracle test); this
is a source-clarity lift, not a speed change.

### Where the hot routines live

`477E` and `38B7` dominate *sprite-heavy gameplay frames*; the boot-to-menu path
is dominated by the already-hooked `450C`/`4511`/`4537` 4-plane asset expansion.
So lifting `477E`/`38B7` lightens per-frame work during play rather than cold
boot.  Raw cold-boot speed in CPython is near its ceiling; PyPy remains the
high-leverage option for overall speed.

## Checkpoint 21 — profiling, 1010:477E sprite blit, EGA plane diagnostics

### `1010:477E` — fully-unrolled fixed 9x16 sprite blit (now hooked)

Reached from the `1010:5A36`/`1010:4740` table dispatcher via the
`1010:A849..A9E0` sprite loop, this is the single hottest *interpreted* routine
during sprite-heavy loading.  `477E..480D` is straight-line code, not a loop:

```
477E  mov es, cs:[9596]      ; dest segment
4783  mov ds, cs:[9598]      ; source segment
      16 x:  movsw;movsw;movsw;movsw;movsb   ; copy 9 bytes, SI+=9, DI+=9
             add si, 002Bh                   ; skip 43 -> source row stride 52
4808  mov ds, cs:[9596]      ; restore DS = dest segment
480D  ret
```

It copies a fixed 9-byte-wide by 16-row sprite from `DS:SI` (source stride 52)
into a packed `ES:DI` buffer.  Exit state (verified against interpreted ASM on a
captured `477E` entry): `SI += 0x340`, `DI += 0x90`, 144 bytes written,
`DS=ES=CS:[9596]`, FLAGS = result of the final `add si,2Bh` (the only flag-
touching op; MOVS leaves FLAGS alone).  Replaced by
`overkill_sprite_blit_9x16_477e`; source and destination always live in distinct
segments so the forward slice copy can never alias.  A `DF=1` faithful fallback
exists for completeness though only `DF=0` is ever observed.

### Loading-path profile (`scripts/profile_hotspots.py`)

A 1.5M-step CGA boot window splits roughly: interpreter 31%, decode-hooks 68%,
present 1%.  The decode-hook time is dominated by the already-verified 4-plane
expansion driver `1010:450C` and the block renderer `1010:4511` it calls; the
hottest interpreted region is the `1010:A849` dispatcher feeding `1010:477E`.
Net: boot time is now governed by the 450C/4511 expansion phase, not by any
single un-hooked leaf routine.

### EGA plane diagnostics (`scripts/diag_video.py --video ega`)

At the first EGA present (~2.34M steps, ~`1010:D013`): plane 0/1/2/3 nonzero =
1378/1461/87/95 of 8000, colour indices used = `0,2,3,8,12,14` (idx0 90.8%,
idx3 8.9%).  Multiple planes are combined (indices 3/12/14 prove it), so the
old "only plane 0 / only indices 0,1" hypothesis is wrong.  The real symptom is
that planes 2 and 3 are nearly empty at this frame, leaving a cyan-on-black
image.  Whether planes 2/3 are legitimately sparse for this title/loading frame
or under-filled upstream is the open EGA question.

## Confirmed execution landmarks

- `2376:0010` — DOS-loaded MZ entrypoint for `assets/OVERKILL.UNLZEXE.EXE` with the default PSP/load layout used by this scaffold.
- `32FF:0052` range — internal unpack/self-relocation stage still present inside the already-unLZEXE'd executable.
- `1010:95C9` — first confirmed transfer into the relocated game/runtime code after the inner bootstrap has produced the useful in-memory image.
- `1010:C916` — tight checksum loop over data read from the original `OVERKILL` file. This is now the first verified source-level replacement hook.
- `1010:CA18` / `1010:CA19` / `1010:CA1B` — VGA vertical-retrace busy wait: `in al,03DAh`, `test al,08h`, `jz`. The port layer now toggles bit 3 of `0x3DA` so this no longer deadlocks.
- `1010:45CB` / `1010:45CE` — current hot path in the 100k-step snapshot. This appears to be a self-modified bit/graphics expansion helper; it is not yet replaced.

## Main-loop status

The true game/menu main loop has **not** been reached yet. The project now gets past the file checksum and VGA retrace wait that previously blocked progress, then spends a large amount of time in a graphics/bit expansion path around `1010:45CB`.

For now the best practical label is:

- **runtime entrypoint after inner unpacker:** `1010:95C9`
- **current next hot routine to decode/replace:** `1010:45CB`
- **main loop:** unknown, pending faster handling of the `45CB/45CE` expansion routine and/or a more complete VGA/video output layer

## Snapshot

`scripts/make_runtime_snapshot.py` writes:

```text
artifacts/snapshot_after_bootstrap_100k/
  memory_1mb.bin
  state.json
  trace_tail.txt
```

The included snapshot was generated after 100,000 interpreted steps with hooks enabled. It captures the self-modified memory image after the inner bootstrap, data-file checksum hook, VGA retrace progression, BIOS equipment query, and several newly implemented CPU instructions.

## Checkpoint 3 additions

### Newly decoded helpers

- `1010:45CB` is a deliberate self-call wrapper. `call 45CE` pushes `45CE`, executes the body once, returns to `45CE`, executes the body a second time, and then returns to the original caller. The replacement `overkill_expand_bits_45cb` preserves this behavior by running the bit shift body twice and popping the caller return address.
- `1010:45F6` packs/interleaves bitplane bytes from `AL/AH/DL/DH` into `CL`, optionally creates a transparency mask in `CH`, remaps nibbles through the `CS:45E6` table, and restores the original `AX` via `CS:45E2`.
- `1010:0624` is the hot packed-data byte reader. It reads from a 512-byte buffer at `DS:0410`; when the pointer at `DS:0610` reaches `0610`, it refills from DOS file handle stored at `DS:0240` using `INT 21h AH=3Fh`.
- `1010:0615` is a little-endian word reader built from two calls to `0624`.

### Current startup asset path

At the 950k-step snapshot, the runtime is in the RLE/asset decoder around `1010:03A8..040C` with `DS=1010`, `ES=7000`, and the original `OVERKILL` data file open at offset `83899`. This strongly suggests the game is still expanding startup graphics/resources into an intermediate/video buffer rather than running the final menu loop.

### Best next RE target

Replace one full RLE decoder rather than only its byte reader:

- `1010:03A8..040C` — vertical byte RLE decoder, hot in the current snapshot.
- `1010:0367..039F` — related linear byte RLE decoder.
- `1010:0324..0365` — related word/pair RLE decoder.

The existing `0615/0624` hooks make those larger replacements easier because the Python code can consume the same packed stream through a shared helper and compare memory output against interpreted ASM on small synthetic streams.

## Checkpoint 4 additions

### Verified larger replacements

- `1010:03A8` — vertical byte RLE decoder.  It reads three packed header words, then decodes one vertical RLE stream per column using stride/column-count from `CS:03A4`.  The hook is tested against the original ASM with mixed literal and repeat runs.
- `1010:4537` — 4-plane row helper.  It reads four bitplanes separated by `CS:5B9C`, invokes the verified `45F6` packer and `45CB` bit expander with equivalent near-call stack effects, and writes packed words to `ES:DI`.
- `1010:4511` — nested 4-plane block renderer.  It preserves the original push/pop/LOOP structure at source level while delegating each row unit to the verified `4537` hook.

### New LZ-style decompressor layer

The next hot region is `1010:ED20..ED95`.  It looks like a 4 KiB sliding-window LZ decoder:

- `1010:ED97` reads bytes from a 1 KiB buffer at `DS:D8B8+SI`, refilling from DOS handle `CS:D666` when `SI` wraps.
- `1010:EDE9` writes one output byte to `ES:DI`, increments the output counter at `CS:EDE5/EDE7`, and advances `ES` by `0x1000` when `DI` wraps.
- `1010:ED7A` copies a back-reference from the 4 KiB ring dictionary at `CS:DCB8+BX` to output and to the current dictionary position `CS:DCB8+BP`.
- `1010:EDDA` / `CS:EE04/EE05` implements a one-byte pushback slot.

The decoder has not yet been replaced as a whole.  The smaller verified hooks should make the full replacement safer: the full hook can be written as a direct transliteration of `ED20..ED95` and use the already-tested byte reader/writer/backref helper semantics.

### Early overlay/file-block decode helper

- `254A:05BF` — small XOR decode loop over a freshly read file block: `xor [di],al; inc di; add al,ah; loop`.  This hook is tied to the current default load layout, unlike the relocated `1010:*` runtime hooks.

## Checkpoint 5 — full LZ decoder at 1010:ECF2

`1010:ECF2` is now a verified full-function replacement for the runtime LZ-style asset decoder.  The original routine starts with `PUSH ES`, zeros the output counter at `CS:EDE5/EDE7`, loads the output pointer through `LES DI, CS:[ECEE]`, clears the one-byte pushback slot at `CS:EE04`, clears the sliding dictionary at `CS:DCB8`, then decodes a bitstream of literal and back-reference tokens until the `00 00 00` terminator.  It finishes with `POP ES; RET`.

Important stack detail: `1010:ED7A` looks tempting to call as a helper, but it is not a normal helper. It is a loop body that ends with `JMP ED26`, not `RET`. Treating it as a synthetic near call leaves an extra return word on the stack and causes the final `POP ES; RET` to restore the wrong ES/IP. The final hook inlines that loop behavior.

Verified snapshot pair:

```text
before: artifacts/snapshot_before_lz_full_hook_ecf2
after:  artifacts/snapshot_after_lz_full_hook_ecf2
```

The hook decodes 51,636 bytes to `ES:DI` output space for the captured asset and advances the `OVERKILL` data-file handle from offset 463,837 to 476,125.


## Checkpoint 6 — verified startup render/RLE control hooks

This checkpoint keeps the original executable as the behavioral oracle and adds only narrow replacements that were verified against interpreted ASM on synthetic streams/snapshots.

New verified hooks:

- `1010:450C overkill_expand_4plane_list_450c` — folds the hot outer 4-plane block-list driver (`450C -> 44D7 -> 4511 -> 450C`) while still using the already verified block renderer. It handles both normal block headers and the zero/FFFF exit cases without inventing higher-level sprite semantics.
- `1010:0367 overkill_linear_byte_rle_decoder_0367_fast` — horizontal/linear byte-RLE decoder sibling of the existing vertical decoder. It is tested against interpreted ASM for literal runs, repeat runs, and the `80h` terminator.
- `1010:4537 overkill_expand_4plane_row_4537_fast` — optimized row renderer. It is still tested against interpreted ASM, but removes synthetic nested calls to `45F6` and `45CB` inside the hot path. Note: this mirrors the current interpreter's rotate flag behavior, including the simplified ZF/SF/PF updates implemented by `CPU8086.shift`, so tests remain oracle-relative.

New tooling:

- `overkill-port continue-snapshot ...` can resume execution from a saved snapshot directory. This avoids replaying the whole bootstrap when investigating the next hot area.
- `snapshot.load_snapshot(...)` restores CPU state, memory and simple DOS open-file bookkeeping for RE scripts.

Observed runtime state at `artifacts/snapshot_after_verified_render_rle_hooks_38600`:

```text
AX=12E8 BX=0013 CX=6357 DX=0410 SI=14DE DI=B03C BP=FFFF SP=A26E
CS:IP=1010:C71E DS=25CC ES=7000 SS=25CC FLAGS=0213
```

Interpretation: startup asset loading is now repeatedly opening entries from the `OVERKILL` container/overlay, decoding blocks through the overlay loader at `254A:0504..0640`, then dispatching through `1010:C6xx/C7xx` to render/decode the resulting assets. The real menu/main loop is still not confirmed. The next evidence-driven target is not a broad rewrite; it is either the small `1010:C713` table search and its caller context, or a tighter replacement for the still-expensive 4-plane block renderer/list path if profiling shows it remains the dominant cost.

## Checkpoint 7 — verified video-loop hooks and a guarded 41DA anomaly

This checkpoint continues the oracle-first workflow.  The new hooks are narrow control-flow or video-transfer replacements, each verified against interpreted ASM on captured snapshots before being used in normal startup execution.

New verified hooks:

- `1010:497A overkill_blit_scaled_column_block_497a` — direct replacement for the mode-0 display blit/clear routine called through the table at `CS:595A`.  Verified by stopping immediately before `497A` and comparing final CPU state plus the full 1 MiB memory image after returning to `58F1`.
- `1010:41DA overkill_linear_rows_to_work_buffer_41da` — row-copy routine selected through the `5A5A` table.  The captured zero-row/zero-width startup call is verified against interpreted ASM, including the otherwise easy-to-miss stack scratch left by `PUSH CX` when the loop is collapsed.
- `1010:5827 overkill_ega_planar_to_linear_copy_5827` — narrow hook for the hot `5827..58A4` EGA row-copy loop.  It is verified for the observed mode-0 path and intentionally hands control back to original code at `58A4` instead of replacing the later render driver.
- `1010:50C9 overkill_wait_vga_retrace_50c9` — verified replacement for the `50C9 -> C9EA` VGA retrace wait wrapper.  It still reads port `03DAh` through the runtime IO layer so `vga_status_reads`, final `AL`, and flags match the oracle.  It also preserves the internal near-call stack scratch word `C9F0`.
- `1010:58DF overkill_postcopy_blit_wait_loop_58df` — narrow mode-0 hook for the `58DF..58F8` loop.  It does not invent new renderer semantics; it repeatedly invokes the already verified `497A` and `50C9` replacements and preserves the original `PUSH/CALL/POP`, `DEC CX`, and `LOOP` effects.

Regression status:

```text
pytest -q
25 passed
```

New captured oracle snapshots:

```text
artifacts/snapshot_stop_497a_probe
artifacts/snapshot_stop_41da_probe
artifacts/snapshot_stop_5827_probe
artifacts/snapshot_stop_50c9_probe
artifacts/snapshot_stop_58df_probe
```

After these hooks, execution from checkpoint 6 reaches a new guarded diagnostic snapshot:

```text
artifacts/snapshot_suspicious_41da_header_after_video_hooks
AX=FECE BX=0000 CX=0000 DX=03D9 SI=5510 DI=3B60 BP=FECE SP=A270
CS:IP=1010:41DA DS=7000 ES=7000 SS=25CC FLAGS=0283
```

The hook refuses to execute this case because the decoded `41DA` header would mean `rows=65536` and `width_bytes=FECE` from `DS:SI=7000:550C`.  That would imply billions of byte copies and is not treated as a valid understood routine replacement.  This is now the most important correctness target: either some earlier hook/interpreter detail subtly diverged, or `41DA` has an unhandled calling convention/data convention for this path.  The real menu/game main loop is still **not confirmed**.

Recommended next step: use the suspicious snapshot as a bisect point.  Compare the data that should populate `7000:550C`, and audit the immediately preceding path `CEEB..CF03 -> 5A24/4251 -> 5A5A -> 41DA`, rather than forcing `41DA` to continue.


## Checkpoint 8 — DOS PSP heap fix and re-audit of the 41DA anomaly

The suspicious `1010:41DA` case from checkpoint 7 was re-audited before adding any new renderer guesswork.  The root cause was in the narrow DOS model, not in `41DA`: the previous `INT 21h AH=48h` allocator returned the same segment (`7000h`) for every allocation.  That made OVERKILL's work buffer, asset/source buffer, and later screen buffers alias each other.  The clear routine at `1010:526A..5282` then correctly cleared `CS:[9598]`, but because all buffers overlapped it also erased data later used as the `41DA` source header at `7000:550C`.

The allocator is now modelled closer to real DOS startup while still remaining OVERKILL-specific and deterministic:

- `DOSMachine.seed_initial_memory_block(psp_segment)` registers the initial PSP-owned memory block from `PSP` to `A000h`.
- OVERKILL's early `INT 21h AH=4Ah` resize of `ES=1000h, BX=22FFh` now succeeds, shrinking the PSP block and making the next allocatable segment `32FFh`.
- Later `INT 21h AH=48h` calls now return distinct paragraph ranges instead of aliasing every buffer.
- Snapshot metadata now persists allocator state (`next_alloc_segment`, `allocation_limit_segment`, and the allocation table), so resumed traces preserve heap layout.

This also uncovered the previous early-exit path: before the PSP block was seeded, startup failed at `1010:95F6` with DOS error `AX=0007` and jumped to the error printer at `1010:0871`, producing `Memory de-allocation error`.  After the fix, that path is no longer taken; the runtime reaches the checksum path, allocates multiple distinct buffers, then proceeds into repeated overlay/container entry opens through `254A:04D7..05xx`.

New regression coverage:

```text
pytest -q
28 passed
```

Added tests cover:

- `INT 21h AH=30h` DOS version return convention (`AL=major`, `AH=minor`).
- seeded PSP block shrink via `AH=4Ah` followed by distinct `AH=48h` allocations.
- CPU opcode `8F /0` (`POP r/m16`), which was reached in the cleanup/error path.

New evidence snapshots:

```text
artifacts/snapshot_stop_0871_distinct_heap
artifacts/snapshot_stop_5d20_distinct_heap
artifacts/snapshot_after_psp_heap_fix_20k
artifacts/snapshot_stop_254a_0585_after_psp
artifacts/snapshot_after_psp_heap_fix_30k
```

Current best next target is the overlay/container loader path around `254A:04D7..05FB`.  It is now hit repeatedly with distinct heap segments and real file offsets.  The next safe replacement should be a narrow verified helper for a small, deterministic sub-loop in that path, not a broad asset-loader rewrite.  The true menu/game main loop is still **not confirmed**.


## Checkpoint 9 — reprogrammed-IRQ0 timer model unblocks the main loop

Running the runtime far forward (2,000,000 steps) from checkpoint 8 showed it was **not** stuck on an unsupported instruction or a guard; instead it spun forever in a tiny busy-wait that dominated ~49% of all interpreted steps:

```text
1010:0679  cmp byte ptr cs:[066B],0
1010:067F  jz   0679
1010:0681  ret
```

Static analysis of the captured image proved `CS:066B` is touched by exactly three resident routines and nothing else:

- `1010:066C` — `inc byte ptr cs:[066B]; ret` (tick increment helper)
- `1010:0672` — `mov byte ptr cs:[066B],0; ret` (clear before waiting)
- `1010:0679` — the wait loop above

The increment helper is called only from the game's **reprogrammed IRQ0 / INT 08h handler**:

- `1010:0682` installs the timer once (`cmp word [0052],1`).
- `1010:068A` saves the old INT 08h vector to `CS:0738/073A`, reprograms the 8253 PIT (`out 43h,36h`; divisor `0x4000` ≈ 72.8 Hz), and points INT 08h at `1010:06E5` via `AH=2508h`.
- `1010:06E5` is the ISR: loads `DS` from `CS:9596`, optionally far-calls sound at `2032:0000` when `[0055]&1`, calls `1010:D50E`, bumps `066B` through `066C` on alternating sub-ticks, advances `[0054] mod 4`, sends EOI to port `20h`, and chains the original BIOS INT 08h every fourth tick.
- `1010:06BC` is the matching uninstall.

This interpreter delivers no asynchronous hardware interrupts, so the ISR never runs and `066B` stays `0` forever.  The waits are the per-frame timing of the main loop (callers `981A/D025/D340/D41F`, each paired with a `0672` clear at `97B2/D007/D318/D406`).

Following the same narrow, oracle-first approach used for the VGA-retrace wait (`50C9` / port `03DAh`), the fix is a single verified replacement hook:

- `1010:0679 overkill_wait_timer_tick_0679` — models exactly one elapsed tick (`066B` `0 -> 1`, one ISR `inc`) and then reproduces the final, exiting loop iteration (`cmp`/`jz`-not-taken/`ret`).  Because `066B` has no other consumer, this is sufficient without speculatively emulating the whole IRQ0/sound ISR chain.

The hook is verified against interpreted ASM (`test_wait_timer_tick_0679_hook_matches_interpreted_asm`, both the `0 -> 1` modelled-tick path and the already-non-zero path); `pytest -q` is now `29 passed`.

With the hook active, the runtime advances out of the spin and into real per-frame output for the first time:

```text
artifacts/snapshot_probe_frontier_2m       (before: stuck spinning at 1010:0679)
artifacts/snapshot_after_timer_hook_2m     (after:  CS:IP=1010:4496, ES=B800)
```

It now executes masked sprite compositing (`lodsw; and ax,es:[di]; or ax,ds:[si]; stosw; add di,30h`) with `ES=B800` (video memory) and dispatches through the render chain `1010:A8F4 -> D010 -> 5BDC` reading the `CS:95BC` video-mode selector.  The new frontier is this `1010:D0xx` render/logic dispatch region.  The true menu/game main loop is now **very likely reached** (per-frame timing + video writes), but the next evidence-driven step is to profile this new region and lift one hot routine there, not to assume it.


## Checkpoint 10 — main loop confirmed; frame-present blit lifted

Profiling after the timer unblock (2,000,000 steps) showed the runtime in a healthy, advancing main loop (no single address dominating like the old spin).  The hottest interpreted loop was the per-frame screen present.

The presenter is `1010:5BDC`: it reads the video mode `CS:[95BC]`, `shl bx,1`, and `jmp cs:[bx+5BE8]` (a video-mode jump table).  For mode 0 the target is `1010:447B`:

```text
447B  mov si, ds:[234C]      ; work-buffer source cursor
447F  mov es, cs:[95A4]      ; destination segment  (confirmed = B800h)
4484  mov ds, cs:[9598]      ; source segment       (decoded work buffer)
4489  mov bx,1Ah / di,A0h / bp,C0h
4492  mov cx,bx; rep movsw; sub di,34h; add di,2000h;
      test di,4000h; jz +; add di,C050h; dec bp; jnz 4492   ; 192 rows x 26 words
44AA  mov ds, cs:[9596]; ret
```

This is the actual present to `B800h` video memory, confirming the game is rendering real frames.  It is replaced by `1010:447B overkill_present_frame_blit_447b`, which mirrors the interpreter helpers in instruction order and is verified against interpreted ASM by full 1 MiB memory + CPU-snapshot equality on a synthetic work buffer (`test_present_frame_blit_447b_hook_matches_interpreted_asm`).  `pytest -q` is now `30 passed`.

Captured oracle/evidence snapshots:

```text
artifacts/snapshot_stop_447f_probe          (entry-path trace into the blit)
artifacts/snapshot_probe_frontier2_8m       (8M-step frontier: still advancing, CS:IP=1010:A930)
```

With the blit collapsed, the `4492` loop disappears from the profile and the runtime reaches further per fixed step budget (2M steps now end at `1010:A84A`).  The next hot interpreted loops, and the recommended next lift targets, are:

- `1010:CCAA` — dirty-word detect-and-copy: `mov cx,8; (mov ax,es:[si]; cmp ax,es:[di]; jz +; mov dl,1; mov es:[di],ax; add di,50h; add si,50h; loop)`.  Compares a back buffer against the front buffer column-wise (stride `50h`) and copies changed words, setting a dirty flag.  Lift the full enclosing column loop, not just this inner 8-word unit.
- `1010:41A6` — variable-width interlaced region blit: `push cx; mov cx,bp; rep movsb; sub di,bp; add di,2000h; test di,4000h; jz +; add di,C050h; pop cx; loop`.  Same scanline-addressing family as `447B`/`41DA`, but `bp` (= width*2) bytes per row over `cx` rows.

The true menu/game main loop is now considered **reached** (per-frame IRQ0 timing + `B800h` frame present running in a stable cycle).  Remaining work shifts from "reach the loop" to "lift the per-frame render/update routines one at a time," each verified against interpreted ASM.


## Checkpoint 11 — visible CGA output and an interactive front-end

The unpacked executable runs in CGA mode (`CS:[95BC]=0`), matching the real
`OVERKILL.UNLZEXE.EXE` in DOSBox, which goes straight to CGA (the CGA/EGA/Tandy
mode menu belongs to the outer launcher, not this inner module).  A raw screen
grab of `B800h` shown as text mode is meaningless CP437 glyphs; decoded as the
standard CGA 320x200 4-colour interlaced layout it is a real frame.

`scripts/render_cga.py` (dependency-free, standard-library `zlib` PNG writer)
decodes `B800h` and confirms the emulator is producing a genuine OVERKILL screen:
the outfitting/shop screen — player ship in a starfield with the
`WEAPON/MISSILES/DRONE/GADGETS/UPGRADES` HUD, score readout, and a cycling item
name.  Evidence:

```text
artifacts/frame_2m_pal1h.png   (item "Fire Nose")
artifacts/frame_8m_pal1h.png   (item "Drone >2<")
```

That two snapshots show different item names confirms the runtime is animating
real game state in its main loop, not a static buffer.

Groundwork for interactive control:

- `DOSMachine.key_queue` plus an updated `INT 16h` (AH=00 blocking read, AH=01
  check) consume queued BIOS keystrokes (`scan<<8 | ascii`).  When the queue is
  empty the previous deterministic headless behaviour is preserved (AH=01 -> no
  key, AH=00 -> Esc), so existing traces/snapshots are unaffected.  Covered by
  `test_int16_keyboard_queue_and_headless_fallback`.
- `scripts/play.py` is a first Tk-based live viewer: it steps the runtime per
  frame, renders `B800h`, and feeds key presses (arrows/Enter/Esc/Space/Tab plus
  printable ASCII) into `key_queue`.  On any interpreter exception it freezes on
  the last good frame and shows the failing `CS:IP` in the title bar, which is
  the intended "run -> observe -> iterate on the crash" debug loop.

`pytest -q` is now `31 passed`.  Next: drive the shop/menu interactively to find
the first input-dependent code paths (and likely the first new unsupported
opcodes / unhandled INTs), then lift the remaining hot render routines
(`1010:CCAA`, `1010:41A6`).


## Checkpoint 12 — real-time viewer pacing and hardware-faithful keyboard input

The first interactive viewer ran the game far too fast (no real-time pacing,
because the timer-tick hook returns instantly) and displayed only ~1 fps (the
per-pixel pure-Python PPM build was the bottleneck), and key presses did nothing.

Diagnosis of input: OVERKILL does **not** read the keyboard through BIOS
`INT 16h` (only two `INT 16h` sites exist, a "press any key" helper).  It installs
its own **IRQ1/INT 09h handler** at `1010:4ED2` that reads scan codes from port
`60h`, acks via port `61h`, and maintains a key-state table at `DS:98C4` (indexed
by scan code; `1` = pressed) plus the last scan code at `DS:98C3`, ending with a
specific EOI (`0x61`) to port `20h`.  The game polls that table.

The previous `INT 21h AH=25h/35h` were no-ops, so the IVT was empty and the
installed handler address was unknown.  Making them honour the real IVT shows the
game installs `INT 08h -> 1010:06E5` (the timer ISR from checkpoint 9) and
`INT 09h -> 1010:4ED2` (keyboard).  Input is now delivered exactly like hardware:
present the scan code on port `60h` and invoke the installed `INT 09h` handler so
the game's own ISR updates its own table -- no key semantics are reimplemented.

Changes:

- CPU: implemented `IRET` (`0xCF`), reached for the first time when an ISR
  returns (`test_iret_restores_cs_ip_and_flags`).
- DOS: `INT 21h AH=25h/35h` write/read the real IVT
  (`test_set_get_interrupt_vector_roundtrip`); port `60h` reads return the
  presented scan code (`DOSMachine.current_scancode`).
- New `overkill_port/interrupts.py`: `deliver_interrupt(rt, num)` performs the
  hardware entry sequence (push FLAGS/CS/IP, clear IF/TF, jump via the IVT) and
  runs the interpreter to the matching `iret`; `deliver_scancode(rt, code)`
  presents a scan code and fires `INT 09h`
  (`test_deliver_interrupt_runs_isr_to_iret`).  Verified live: delivering Enter
  make/break and Up make toggles `25CC:98C4[1C]` / `[48]` and the CPU resumes
  cleanly at its prior `CS:IP`.

Viewer (`scripts/play.py`) rewritten:

- runs exactly one game frame per display update (synced to the `1010:447B`
  present hook) so no frames are skipped;
- paces to real time (`--fps`, default 30);
- renders via `render_cga.render_ppm`, a 256-entry lookup-table decoder that is
  pixel-identical to the reference renderer but fast enough to stay interactive;
- delivers key presses/releases through the `INT 09h` path (arrows/Enter/Esc/
  Space/Tab/letters/digits -> XT scan codes);
- on any interpreter exception it freezes on the crash frame and shows the
  failing `CS:IP` for iteration.

`pytest -q` is now `34 passed`.  Next: drive the shop/gameplay interactively to
surface the first input-dependent paths and any new unsupported opcodes, and lift
the remaining hot render routines (`1010:CCAA`, `1010:41A6`).


## Checkpoint 13 — threaded viewer and the real control map

First interactive run: the game ran and responded, but pressing a control key
"froze" the window for a couple of seconds.  Headless reproduction showed it is
**not** a hang -- pressing a key makes the game decode/load the next screen, a
~1M-instruction burst dominated by `1010:017E` that presents almost no frames
during the load.  The viewer ran the interpreter synchronously inside the Tk
callback, so that burst blocked the UI thread.

Fixes:

- `scripts/play.py` now runs the interpreter on a **background thread**; the Tk
  main thread only snapshots memory (a single `bytearray->bytes` copy, atomic
  under the GIL) and renders.  Long loads no longer block the UI.  Frame presents
  are paced to real time; key events flow through a deque the emulator drains at
  frame boundaries.  On an interpreter exception (or a no-frame stall past the
  budget) the title bar reports the failing/`stall` `CS:IP`.

Control map discovery: `1010:017E` is the per-frame control poller.  It reads 8
scancodes from `DS:213E` (or `DS:2146` when `DS:[0010]==2`), looks each up in the
INT 9 key-state table at `DS:98C4`, and packs the pressed bits into the button
field `DS:98BE`.  The active table `DS:213E` is
`[00, 00, Z(2C), Space(39), Q(10), A(1E), O(18), P(19)]` -- OVERKILL uses the
classic **Q/A/O/P to move + Z/Space to fire**, not the arrow keys.  This both
confirms the INT 9 input path reaches the game's own polling and explains why
arrows did nothing.  The viewer already maps letters/Space to the right scan
codes, so these controls work today.

The interpreter (pure Python) is the speed bottleneck, not the display; the lever
for higher in-game speed is to keep lifting hot loops into verified hooks
(`1010:CCAA`, `1010:41A6`, and the `1010:017E`/loader paths), not to change the
rendering backend.  `pytest -q` remains `34 passed`.


## Checkpoint 14 — frame-accurate input and a ~2x faster interpreter

Two issues from interactive play: a single tap on the menu's FIRE key did
nothing, and the interpreter was slow.

Input: the game polls its key-state table once per frame (`1010:017E`).  The
viewer delivered a make on key-down and a break on key-up and applied the whole
queue at the start of a frame, so a quick tap set then cleared the key before the
frame's poll -- the press was lost.  New `overkill_port/keyboard.py`
(`KeyDispatcher`) delivers a make immediately and **defers the matching break
until the key has been held for at least one full frame**, so every tap is
observed; it also collapses OS auto-repeat.  Unit-tested
(`test_key_dispatcher_*`).  Note OVERKILL's menu, like the original in DOSBox, is
intentionally brief and finicky -- holding FIRE is the reliable way in.

Performance: profiling showed the cost was per-instruction Python overhead, not
the display (numpy would not help -- scalar `bytearray` indexing beats a numpy
array, and the decode is branchy).  Three behaviour-preserving changes, each
guarded by the regression suite:

- `decode_rm_operand` previously defined its `RegOperand`/`MemOperand` classes
  *inside the function*, so `__build_class__` ran ~200k times per 400k
  instructions.  The operand classes are now module-level (`_RegOperand` /
  `_MemOperand`, `__slots__`).
- `Memory.rb/rw/wb/ww` inline the 20-bit address calculation and drop the
  `linear()` + `check()` + `*_phys()` call chain (word accesses now wrap at the
  1 MB boundary like hardware instead of raising).
- `set_add_flags` / `set_sub_flags` / `set_logic_flags` compute the whole FLAGS
  word in a single assignment instead of 5-6 `set_flag()` calls each, and parity
  is a 256-entry table.

Result: raw interpreter throughput rose from ~76k to ~345k instructions/second on
the post-bootstrap workload (the `pytest` suite time roughly halved, 3.0s ->
1.5s) with identical behaviour (`36 passed`).  The remaining hot spot is the
`execute_opcode` if-chain (~37%); converting it to an opcode dispatch table is the
next, larger, perf lever and is deferred until it is worth the refactor risk.


## Checkpoint 15 — real-time pacing and the startup cost

Interactive play felt like "turbo with frameskip": the game ran much faster than
DOSBox while the display only updated a few times a second.  Measurements:

- the game does **exactly one `1010:0679` timer wait per rendered frame** across
  the title, menu, demo and gameplay (no `INT 1Ah` / port-timer use), ~9434
  interpreted instructions per frame;
- steady state ran at ~50 frames/second unpaced -- faster than the original's
  ~36 -- because the timer-tick hook returns instantly (the game's clock was
  free-running at interpreter speed);
- the background emulator thread, never sleeping, also starved the Tk thread of
  the GIL, so the display crawled at a few fps while the game raced ahead.

Fix: pace the once-per-frame timer wait to real time.  A new optional
`CPU8086.timer_pacer` callback is invoked from the `0679` hook; it is left `None`
for headless/deterministic runs (so the regression suite and snapshots are
unchanged) and set by the viewer to `TimerPacer(game_hz)`.  That per-frame sleep
both throttles the game to real time and releases the GIL so the UI renders
smoothly.  Verified at ~30 fps for `--game-hz 30` (original is ~36; tunable).

Startup cost: reaching the first on-screen frame takes ~11 seconds, because the
bootstrap decodes all startup assets through the verified LZ/RLE/4-plane hooks --
each hook decodes a whole asset in a single interpreted "step", so it is heavy in
wall-clock time though few in step count.  To make iteration fast, `scripts/play.py`
gained `--snapshot DIR` (via `snapshot.load_snapshot`) to start from a saved
post-bootstrap state instantly; `artifacts/snapshot_play_start` is a fresh capture
(with the IVT populated, so keyboard input works on load).  The default path still
runs the real bootstrap and shows a "decoding startup assets" status until the
first frame.

Input: the viewer now forwards the full keyboard (a complete Tk-keysym -> XT
scan-code map), on top of the frame-accurate `KeyDispatcher` from checkpoint 14.
OVERKILL's menu is intentionally brief and cyclic (menu -> attract demo -> menu);
holding FIRE (Z or Space) across a cycle is the reliable way to start the game.

`pytest -q` remains `36 passed`.

## Checkpoint 16 — lifted remaining known render/cell-copy hot paths

This pass keeps the incremental hybrid-runtime approach: no guessed gameplay rewrite, only narrow hooks for routines whose byte-level behavior was already understood from the live runtime.

New replacements:

- `1010:41A6 overkill_variable_width_interlaced_blit_41a6` — variable-width interlaced row blit.  It preserves the original `push cx; mov cx,bp; rep movsb; sub/add/test/wrap; pop cx; loop; ret` behavior, but collapses the row loop into Python.
- `1010:CCAA / 1010:CCC4 / 1010:CCF0` — dirty detect-and-copy modes selected by the `1010:CC90` video dispatcher.  These compare back-buffer cells against front-buffer cells in ES, copy changed words/bytes, and set `DL=1` for the continuation at `CD08`.
- `1010:4D15 overkill_presence_stamp_list_4d15` — hot presence/stamp-list helper used during per-frame object/cell bookkeeping.  It maps compact list triples through the `DS:9A08` table, checks/stamps ES cells, and appends changed cell addresses to `DS:DI`, including the mode-1 stacked-cell cases selected by `BP=4D4D/4D51`.

The shared `REP MOVSB/MOVSW/STOSB` helpers now have a fast bytearray slice path for the common forward non-wrapping render-copy case, while falling back to the exact byte loop for wrapping or reverse-direction cases.

Regression coverage was expanded with interpreted-ASM oracle tests for `41A6`, `CCAA`, and `4D15`; `pytest -q` is now `39 passed`.

### 2026-06-10 interactive player regression fix: no frame skipping ahead of Tk

The first menu-pacing fix still allowed `CPU8086.run(8000)` to continue after a
`1010:447B` present hook.  If that burst contained more than one present, the
emulator could overwrite B800/video memory several frames ahead of the Tk
renderer; the UI then sampled only occasional states, making intro/menu look like
unpaced turbo mode even with `--fps 30 --game-hz 30`.

`scripts/play.py` now treats `1010:447B` as a hard frame boundary:

- the present hook performs the original blit, publishes an immutable memory
  snapshot to the UI thread, and waits until Tk consumes that exact frame;
- it then raises an internal `FramePresented` signal so the outer emulator loop
  stops the current `CPU8086.run(...)` burst immediately and pumps keyboard once
  per visible frame;
- real-time sleeping is done only at present time, not from the modeled
  `1010:0679` timer flag hook, avoiding ordering-dependent double/missed pacing.

The newest interactive-risk render hooks (`1010:41A6`, `1010:4D15`,
`1010:CCAA`, `1010:CCC4`, `1010:CCF0`) are disabled by default in `play.py`
because the live starfield/menu path showed ghosting/trailing.  They remain in
`replacements.py` for oracle tests/profiling and can be re-enabled with
`--unsafe-render-hooks`.

### 2026-06-10 interactive player regression fix 2: sync on the timer frame, not the blit

The previous fix used `1010:447B` as the hard frame boundary.  That was too
optimistic: `447B` is the mode-0 B800 blit, but it is not the full logical frame
boundary.  In the observed loop, the order is `447B` first and `1010:0679` timer
wait afterwards.  Stopping at the blit allowed the front-end to resume/pump input
before the rest of the game frame had completed, and the Tk loop still had a
fallback path that sampled live emulated memory between pending frames.

`scripts/play.py` now uses `1010:0679` as the one-frame boundary:

- `1010:447B` only performs/counts the original present blit;
- `1010:0679` performs the timer-wait replacement, publishes an immutable memory
  snapshot to Tk, waits until Tk consumes that exact snapshot, paces to
  `--game-hz`, then raises the internal `FramePresented` signal to stop the
  current CPU burst;
- the Tk loop no longer renders live memory when no pending synchronized frame is
  available, preventing partial in-between frames while the emulator is still
  mutating B800 for the next frame;
- Tk keyboard input uses `bind_all` so menu input is not lost due to focus being
  on the wrong widget.

`--fps` is now kept only as a legacy/compatibility option for existing command
lines.  Real interactive timing is controlled by `--game-hz`; using Tk's repaint
cadence as another timer created accidental double-throttling and still did not
represent DOS time correctly.

### 2026-06-10 interactive player regression fix 3: intro/menu use VGA retrace timing, not only the PIT timer

The timer-frame sync fix was still wrong for the non-gameplay screens.  Gameplay
uses the `1010:447B` full B800h blit followed by the `1010:0679` PIT/timer wait,
so pacing on `0679` makes the gameplay demo look correct.  The intro/menu and
transitions also use the verified `1010:50C9` VGA retrace wait path as a real
screen delay, and they can update B800h around that path before returning to the
normal gameplay timer loop.

Because `50C9` was a deterministic replacement that returned immediately, the
VM was not "leaking" state; it was faithfully fast-forwarding a hardware wait
that the interactive front-end had not treated as time.  That explains the exact
symptom: gameplay demo speed was correct, but menu/intro screens disappeared or
advanced invisibly until the demo screen was reached again.

`scripts/play.py` now treats both kinds of hardware waits as interactive
boundaries:

- `1010:0679` still paces gameplay frames through `--game-hz`;
- `1010:50C9` is wrapped and paced too (`--retrace-hz`, defaulting to
  `--game-hz`), so intro/menu/fade loops no longer run in turbo mode;
- a B800h CRC is tracked, and a new immutable snapshot is published to Tk only
  when visible memory changes, avoiding duplicate renders during static retrace
  delay loops;
- `1010:58DF` is disabled by default in `play.py`, because that lifted hook calls
  the 50C9 helper directly inside Python and would otherwise bypass the
  interactive retrace wrapper;
- `1010:447B` still publishes full gameplay blits and hands control back to the
  UI, while the subsequent `0679` performs the real sleep.

`pytest -q` remains `39 passed`.

### 2026-06-10 CPU coverage: `DAA` at `1010:5F18`

After the intro/menu retrace pacing fix, interactive play reached an overlay path
that crashed at `1010:5F18` with unsupported opcode `27h`.  This is `DAA`
(decimal adjust AL after BCD addition), used in a repeated digit-update sequence
near `1010:5F16`: `ADD AL,BL; DAA; MOV [BP],AL`, followed by further
`ADC`/`DAA` pairs for carry propagation.

This did **not** look like a random VM instruction-pointer leak after checking the
loaded snapshots: the cold EXE image has startup bytes at `1010:5F18`, but the
runtime overlay later contains `27h` at that exact address, and existing
post-bootstrap snapshots already show the `DAA` byte there.  So the correct fix is
CPU coverage, not papering over control flow.

`overkill_port.cpu.CPU8086` now implements 8086 `DAA` with AL adjustment, AF/CF
carry semantics, and SF/ZF/PF from the adjusted AL.  OF remains unchanged because
it is undefined for `DAA` on 8086 and this project avoids inventing behavior
unless the game observes it.  Focused tests cover the carry-producing BCD case
used by this path.

### 2026-06-10 EGA play mode: `/E` command tail and mode-1 presenter

The original `OVERKILL.DOC` documents `/E` as the EGA monitor selector.  The
runtime previously always booted the unpacked executable with an empty PSP command
tail and `scripts/play.py` always decoded `B800h` as CGA.  This made the stable
interactive path CGA-only even though the original binary contains separate mode
selectors.

`overkill_port.runtime.create_runtime` now accepts a `command_tail` argument and
passes it to the PSP at `PSP:80h`.  `scripts/play.py --video ega` uses the
original documented selector by passing `" /E"`; CGA remains the default path.
There is also a debug escape hatch `--dos-args` for explicitly testing another
PSP tail.

EGA's frame presenter is the mode-1 jump-table target at `1010:2750`.  Its
structure is:

```asm
2750  mov si, ds:[234C]
2754  mov es, cs:[95A4]      ; A000h in EGA mode
2759  mov ds, cs:[9598]      ; decoded work buffer
275E  mov bx,000Dh           ; 13 words = 26 bytes per plane row
2761  mov di,00A0h
2764  mov dx,03C4h / out dx,02h / inc dx
276B  mov bp,00C0h           ; 192 rows
276E  mov al,01h / out dx,al ; plane 0 map mask
2771  rep movsw
2778  shl al,1 / out dx,al   ; plane 1
277B  rep movsw
2782  shl al,1 / out dx,al   ; plane 2
2785  rep movsw
278C  shl al,1 / out dx,al   ; plane 3
278F  rep movsw
2793  add di,000Eh           ; net row stride 40 bytes
2796  dec bp / jnz 276E
2799  mov al,0Fh / out dx,al
279C  mov ds, cs:[9596]
27A1  ret
```

A flat `bytearray` cannot represent real EGA hardware bitplanes selected through
the sequencer map-mask register.  The new verified-for-purpose replacement
`1010:2750 overkill_present_ega_frame_2750` therefore stores the currently
presented frame in an explicit shadow layout inside the `A000h` aperture:

```text
A000:0000..1F3F  plane 0
A000:2000..3F3F  plane 1
A000:4000..5F3F  plane 2
A000:6000..7F3F  plane 3
```

`render_ega_ppm()` decodes those four planes as standard 320x200 16-colour EGA
RGBI output.  `scripts/play.py` switches its present hook, CRC range, and renderer
based on `--video`.  The existing CGA B800h path is unchanged.

`pytest -q` is now `43 passed`.

### 2026-06-10 EGA performance pass: lifted mode-1 row conversion helpers

The first playable EGA path was correct enough to enter the game, but startup/menu
was much slower than CGA because the mode-1 renderer spent most interpreted steps
in the 27D9..2990 EGA row conversion path.  A short EGA profile showed the hot
loops at `1010:280D`, `1010:2824`, `1010:291C`, and `1010:2932`.

Added narrow, oracle-tested replacements:

- `1010:280D overkill_ega_load_temp_rows_280d` — copies four source rows into
  CS temporary rows at `5AF4/5B1C/5B44/5B6C`, then continues at `2824`;
- `1010:2824 overkill_ega_expand_temp_rows_2824` — converts those temporary rows
  to EGA output-plane rows, applies the transparent-colour rule, copies the four
  rows to the ES output cursor, then preserves the original `27EB`/`27D9` loop
  tail;
- `1010:291C overkill_ega_temp_row_copy_291c` — copies a temporary row to the ES
  output cursor stored at `CS:5BA6`;
- `1010:2932 overkill_ega_transparency_mask_2932` — builds the 8-pixel
  transparency mask byte from four source plane bytes.

Each replacement has a synthetic interpreted-ASM oracle test comparing registers,
flags, stack scratches, and full 1 MiB memory.  `pytest -q` is now `47 passed`.
