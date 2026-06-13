## 2026-06-13 Tandy loop sweep lifts

Two additional Tandy hotspots were lifted out of the interpreter:

- `1010:3389` is the interlaced clear loop that zeroes `DI`, sets `ES` from
  `CS:[95A4]`, and clears 200 rows of 0x34 words through the `2000h/80A0h`
  interlace pattern. It is the same core loop shape as `1010:30B0`.
- `1010:5C74` is the postcopy mode sweep that dispatches through the mode table
  at `CS:595A`, calls the installed `497A` or `375B` leaf, waits through the
  installed `50C9` retrace hook, bumps `CS:5901`, and loops until it reaches
  `CS:58FD` before restoring `DS` and returning.

## 2026-06-12 PC speaker timing cadence

Two later Tandy snapshots clarified the sound timing behavior:

- `artifacts/snapshot_play_tandy_20260612_151420` is a level-select/menu state
  after `D`.
- `artifacts/snapshot_play_tandy_20260612_151523` is gameplay after Space/fire
  where sound was heard but no projectile appeared.

Both snapshots have `DS:0055 == 0`, so they are not using the optional far sound
driver at `2032:0000`.  Speaker activity comes from the always-run timer helper
path inside `1010:06E5 -> D50E`.

The Space/fire snapshot was compared with the old synthetic `0679` timer model
and the new real-ISR model under the same Space input.  The sampled B800 CRC and
object-table state matched.  That means the "fire sound but no projectile"
state is not caused by enabling the timer ISR speaker path; it remains a
gameplay/input-state issue to audit separately.

The sound-length complaint did reveal a pacing mismatch.  OVERKILL programs PIT
divisor `0x4000`, so the timer ISR runs at about `72.8 Hz`.  The `0679` wait
usually consumes two ISR ticks before `CS:066B` advances, yielding an effective
game cadence of about `36.4 Hz`.  The interactive player default was still
`30 Hz`, so timer-driven sounds were stretched by roughly 20%.

`CPU8086.timer_ticks_elapsed` now records the number of real ISR ticks delivered
by the `0679` hook.  `scripts/play.py` paces gameplay by those PIT-tick units,
with default `--game-hz 36.4` and an internal pacer frequency of
`--game-hz * 2`.

## 2026-06-12 PC speaker via the original timer ISR

The PC speaker backend became audible once the timer wait hook stopped skipping
the game-side ISR work.

`1010:0679 overkill_wait_timer_tick_0679` originally modeled only the flag that
unblocks the wait loop (`CS:066B`).  That was enough for video/gameplay timing,
but it bypassed the installed INT 08h handler at `1010:06E5`, where OVERKILL
updates sound.  A live delivery test from
`artifacts/play_tandy_main_menu_20260612_132548` showed the ISR producing real
speaker hardware writes:

```text
out 43h,B6h
out 42h,<low divisor>
out 42h,<high divisor>
out 61h,03h
```

The timer hook now runs the original ISR synchronously when INT 08h points at
`1010:06E5`, delivering bounded real ISR ticks until the original `CS:066B`
wait flag advances.  If that vector is absent or different, the hook fails
fast; it no longer invents a synthetic timer tick.

One guard is needed: the original ISR chains the saved BIOS timer every fourth
tick through `JMP FAR CS:[0738]`.  The VM often has that saved vector as
`0000:0000`, so the hook stops at the known chain point after the game-side
work, restores the interrupt return frame, sends the EOI, and returns to the
wait loop.  This keeps the original sound/timer behavior without executing an
unmodeled BIOS timer body.

Validation:

```text
scripts/run_tests.py
128 passed, 0 failed
scripts/play.py --snapshot artifacts/play_tandy_main_menu_20260612_132548 --verify-frames --verify-frame-max 40
FRAME VERIFY OK frames=40
scripts/play.py --snapshot artifacts/play_tandy_edrax_orbit_combat_20260611_232258 --verify-frames --verify-frame-max 40
FRAME VERIFY OK frames=40
```

## 2026-06-12 Tandy `33AF` composition guard

`artifacts/snapshot_play_tandy_20260612_141644` exposed a gameplay rendering
regression that initially looked correlated with the PC speaker pass.  It was
not: the failing path performed no `42h/43h/61h` speaker IO before divergence.

Frame verification diverged at frame 48.  Hook bisection showed that disabling
`1010:33AF overkill_expand_tandy_list_33af` alone restored frame agreement.
Live verification then showed the composed parent hook was wrong for the
snapshot's state:

```text
entry 1010:33AF
DS=35FF ES=8502 SI=0000 DI=0000
CS:[0BD8]=0000
```

The `33AF` parent composition had been verified for the startup/header-table
case where `CS:[0BD8] != 0`.  The gameplay materialization case with
`CS:[0BD8] == 0` has different visible parent-level behavior.  Rather than
guess that second mode, the hook now self-disables and falls back to original
ASM when `0BD8 == 0`; the child `1010:33B2` block expander remains hooked, so
the original parent can still benefit from the verified block-level lift.

The investigation also tightened two asset-codec side effects:

- `1010:0615` now models its two nested `CALL 0624` operations so stack scratch
  from call/return and refill paths matches the original more closely.
- `1010:03A8` now reads its three header words through the shared `0615` helper,
  preserving the original `CS:0614` temp-byte side effect.

Validation:

```text
scripts/play.py --snapshot artifacts/snapshot_play_tandy_20260612_141644 --verify-frames --verify-frame-max 60
FRAME VERIFY OK frames=60
scripts/run_tests.py
127 passed, 0 failed
```

## 2026-06-12 PC speaker hardware path

The runtime now models the PC speaker hardware state narrowly enough for
OVERKILL:

- port `43h` tracks PIT channel 2 access mode;
- port `42h` latches channel 2 reload values, including the normal low/high
  byte programming sequence;
- port `61h` stores and reads back the speaker gate/data control bits;
- a callback publishes `(enabled, frequency)` whenever a complete divisor or
  gate change can affect the audible state.

The interactive SDL viewer consumes those callbacks through a queue and plays a
cached mono square wave at `1193182 / reload` Hz while both low speaker bits are
set.  This is intentionally a hardware/backend pass, not a guessed sound-driver
rewrite.

Evidence gap: a short run from `artifacts/play_tandy_main_menu_20260612_132548`
produces no speaker-port writes, and the loaded far driver slot at `2032:0000`
is still only:

```text
2032:0000  e8 0f 00 cb  e8 0b 00 cb  02 00 00 00  00 00 88 03
```

That matches the earlier timer finding: `1010:0679` currently models the timer
flag without running the full `1010:06E5` ISR, and the observed sound target is
not yet a real PC-speaker routine.  The next sound-specific RE step is therefore
to find the command-tail/loader path that selects a non-stub driver, then decide
whether `1010:06E5` can safely compose the verified sound tick.

## Artifact hygiene note

Older one-off closure, verify, and probe outputs that were not referenced by
tests or `play_*` captures have been pruned from `artifacts/` during
cleanup. The remaining artifact directories are the ones still used as evidence
oracles in tests and living docs.

## 2026-06-12 Tandy menu text/direct-present closures

Profiling `artifacts/play_tandy_main_menu_20260612_132548` showed that slow menu
subscreens and redefine-key screens still spent substantial time in interpreted
Tandy rendering loops after the startup/gameplay hooks were already active.

Two routines clearly belonged to the existing `tandy_rendering` island:

- `1010:306F overkill_tandy_rect_copy_306f`: raw rectangle copy for menu and
  high-score text screens.  It reads height/width from `DS:SI`, copies
  `width*4` bytes per row to `CS:[95A4]` video memory, advances rows through the
  Tandy `+2000h` interlace layout, applies the original `+80A0h` wrap, and
  preserves the balanced `PUSH CX` / `POP CX` stack scratch.  This lifts the hot
  `1010:307E..3094` row loop as one coherent parent routine.
- `1010:CDAA overkill_tandy_changed_dword_present_8rows_cdaa`: Tandy
  dirty-present cell loop.  It copies two words per row from `DS:SI` to `ES:DI`
  for eight rows, advances `SI` by `00A0h`, advances `DI` through the Tandy
  interlace layout, and continues at `1010:CE02`.

Both replacements have synthetic interpreted-ASM oracle coverage in
`tests/test_replacements.py`.  After these hooks, `1010:307E` and
`1010:CDAA` disappear from the interpreted hot list.  The remaining top loop in
that snapshot is `1F8F:0960`, now classified as a compact gameplay counter
stride helper. It lives in an overlay segment, but its behavior is per-frame
game-state update, not overlay loading or asset decoding.

Follow-up profiling of `artifacts/snapshot_play_tandy_20260612_134028` from the
redefine-keys page showed a different kind of hot loop:

```text
1010:57AB  cmp byte ptr DS:[98C3],00h
1010:57B0  jz 57AB
```

This is the redefine-key screen waiting for the game's keyboard ISR/state table
to report a key, not a rendering primitive.  After accepting a key, the screen
also waits at `1010:57DD/57E0` until `DS:[98C4 + DS:[98C3]]` clears, i.e. until
that key is released.  `scripts/play.py` treats both loops as interactive yield
points so the SDL thread can pump key events immediately instead of waiting for
the full `--frame-budget`.  No global hook was added because headless/oracle
runs should still see the original keyboard wait semantics.

The instructions/order-info overlay has a similar but separate key wait.  From
`artifacts/snapshot_play_tandy_20260612_140352`, execution is already in overlay
segment `1F8F`, not loading assets.  The hot loop is:

```text
1F8F:099B..09DF  repeated cmp byte ptr DS:[key_state],01h / branch
```

It checks the game key-state bytes at `DS:990F`, `990C`, `990D`, `98D2`,
`9911`, `9914`, `9915`, `98FD`, `98E0`, and `98C5`.  `scripts/play.py` now
recognizes this overlay wait by the `1F8F:099B` code signature and yields the UI
while all watched keys are idle.  This remains an interactive scheduling fix,
not a replacement hook: profiling/oracle runs still execute the original loop.

## 2026-06-12 Tandy startup list-driver composition

Cold-start Tandy profiling showed that the startup graphics materialization path
still paid interpreter overhead around the already-hooked Tandy block expander:

```text
1010:33AF  call 44D7          ; read one block header
1010:33B2  ...                ; Tandy block expander, already hooked
1010:450A  ret / loop to 33AF
```

`1010:44D7` reads a block header from `DS:SI`, detects the zero terminator,
updates `CS:[5B9E]` height and `CS:[5B9C]` width, emits the original header words
to `ES:DI`, and leaves flags for `33B2`'s terminator branch.  New hook
`1010:33AF overkill_expand_tandy_list_33af` composes that header reader with the
existing `33B2` implementation until the zero header reaches `1010:44AA`.

This keeps the implementation inside the existing Tandy rendering/startup
materialization island and avoids duplicating the pixel expansion logic.  The
oracle test uses a two-block list plus terminator and compares full memory.  It
also exposed one missing balanced-call scratch in `33B2`: the final nested
`344B` call leaves return word `341B` at `SP-8`, now preserved by the lower-level
helper too.

## 2026-06-12 island exhaustion signals

`scripts/audit_islands.py` now gives a repeatable closure check for the existing
OverKill-specific source-port islands.  The goal is not to prove semantic
completeness automatically; the original executable remains the oracle.  The
script instead reports whether a known island still has visible frontier signs.

An island can be treated as an exhaustion candidate only when all of these are
true for the known routines in that island:

- Registered hooks have explicit hook-verifier continuation metadata.
- Hooks have obvious oracle/regression test mentions.
- `symbols.json` no longer marks island addresses as candidate/frontier,
  unverified, fallback, next-target, or active-investigation items.
- The island module does not contain explicit seams such as
  `KNOWN_ORIGINAL`, `fail_unverified`, bounded original fallbacks, or
  unverified-path branches.
- Representative traces or frame verification do not hit unknown original-code
  paths in that island.

The current audit classifies `startup_graphics` and non-overlay `asset_codecs`
as `closed-candidate`.  Startup graphics covers the known startup
materializers:

```text
1010:33B2  Tandy block expander
1010:33DD  Tandy cell expander
1010:450C  4-plane list driver
1010:4511  4-plane block renderer
1010:4537  4-plane row helper
1010:45CB  bit expander
1010:45F6  four-pixel packer
```

The non-overlay asset-codec closure now covers:

```text
1010:0324  word-pair RLE decoder
1010:0367  linear byte RLE decoder
1010:03A8  vertical byte RLE decoder
1010:0615  packed little-endian word reader
1010:0624  packed byte reader
1010:C916  file checksum loop
1010:ECF2  LZ asset decoder
1010:ED7A  LZ back-reference copy
1010:ED97  LZ input byte helper
1010:EDE9  LZ output byte helper
```

The other existing islands still have concrete blockers rather than vague
unknowns:

- `overlay`: `254A:04D7` is still the parent loader investigation target; the
  `254A:05A1`, `254A:05D9`, and `254A:0701` overlay subloops have direct tests
  and replacements.
- `coordinates`: the module still has an explicit unverified-path seam.
- `layer_sprites`: the module still has bounded-original/fail-fast compositor
  seams and the `1010:75A6` frontier symbol.
- `tandy_rendering`: several rendering hooks need direct test mentions even
  though many are covered indirectly by higher-level behavior tests.

Use the audit as a triage lens before lifting more code: if a candidate belongs
to one of these islands and appears in the blocker list, close that local seam;
if it does not clearly belong to an existing island, leave it alone for now.

## 2026-06-12 asset-codec closure: `1010:0324` word-pair RLE

The last non-overlay `asset_codecs` audit blocker was the old
`candidate_word_pair_rle_decoder` symbol at `1010:0324`.  The decoded original
routine is:

```text
0324  mov es,[023A]
0328  mov di,[023C]
032C  call 0615       ; sentinel word -> BX
0331  call 0615       ; next word
0334  cmp ax,bx
0336  jz  0344
0338  stosw           ; literal first word
0339  call 0615
033C  stosw           ; literal second word
033D  add [0244],4
0342  jmp 0331
0344  call 0615       ; repeat count
0349  jcxz 034D
034D  jmp 02A8        ; count zero terminates
0350  call 0615       ; repeated pair word 0
0353  push ax
0354  call 0615       ; repeated pair word 1
0357  mov dx,ax
0359  pop ax
035A  stosw
035B  xchg ax,dx
035C  stosw
035D  add [0244],4
0362  xchg ax,dx
0363  loop 035A
0365  jmp 0331
```

`decode_word_pair_rle` now lives in
`overkill_port/games/overkill/asset_codecs/rle.py`, with the hook wrapper
`overkill_word_pair_rle_decoder_0324`.  The synthetic oracle test covers
literal pairs, repeated pairs, and the sentinel/count-zero exit, and compares
registers, flags, output memory, `DS:0244`, `DS:0610`, `DS:0614`, and the stack
scratch range around `SS:SP`.

While verifying this, the shared `0624` packed byte reader gained an important
flag correction: on the no-refill path the original `CMP BX,0610h` leaves
`CF=1`, and `INC word ptr [0610]` preserves that carry.  The Python helper now
models that before deciding whether to refill the 512-byte packed stream buffer.

## 2026-06-12 overlay island closure: signature compare loop

The existing-island audit found one small deterministic overlay-loader loop that
clearly belongs in `overkill_port/games/overkill/asset_codecs/overlay.py`:

```text
254A:0582  lodsb
254A:0583  cmp al,[di]
254A:0585  jz  058A
254A:0587  jmp 0640
254A:058A  inc di
254A:058B  loop 0582
254A:058D  ...
```

This is the six-byte signature check after the parent overlay/container loader
reads the header at `254A:074A`.  The lifted helper
`compare_overlay_signature_0582` preserves the two continuations:

- `254A:058D` when all bytes match.
- `254A:0640` on the first mismatch.

The larger `254A:04D7` file-open/read/seek parent is still explicitly not lifted
as a whole.  It belongs to the overlay island, but includes DOS handle state,
header math, and the surrounding far-return setup; closing more small loops
first is the safer path.

## 2026-06-11 B73E formation contact: AA46 carry-set path

The later Tandy formation-change divergence from
`artifacts/test_oracles/snapshot_play_tandy_20260611_152751` was gameplay state, not
rendering.  At frame 383 the reference killed object `BP=2814` and added score
`0030`; the hook left the object alive as logic `20h`.

The overlay path normalizer at `254A:0701` preserves the live `BP` scratch
pointer as well as `SI`/`DI`.  That matters because the surrounding loader uses
the helper's far-return path and later reads the pointer back out through the
caller frame.

The original path for that tick is:

```text
B73E -> B77B          ; substate 2, X += 4, sprite 0077 once X >= 00A0
BC4B -> BCCB
AA46 -> 8331         ; X/Y rectangle test
BCFC/BCFF -> BFC7    ; carry set means contact/death path
BD09 -> 9E69
BCAD -> 62F6         ; now early-returns because logic_id is 0001
```

The important correction is `AA46/8331`: it tests both axes.  It clears carry on
any out-of-window exit, but sets carry at `8359` when the object is inside the
rectangle.  The previous helper modeled only the X half and always cleared carry
after the second X comparison, which skipped `BFC7`.

`BC4B` now composes this carry-set contact path at the parent level: it calls
the already verified `BFC7` death/transition tail when `DS:A8C2 != 1`, runs the
observed `9E69` bookkeeping path, then continues to `62F6`.  `62F6` also has a
small but important early-return detail: after `BFC7` changes the object to
`logic_id == 0001`, the original returns immediately with the incoming `BX`
preserved; it does not advance to the empty-scan sentinel.

## 2026-06-11 B73E/BEC5 gameplay continuation

Two more `1010:B73E` gameplay stops from
`artifacts/test_oracles/snapshot_play_tandy_20260611_152751` were verified against interpreted
ASM and lifted:

- `BEC5` variant-2 collision, `BEDC=0000`, fourth counter decrement reaches
  zero.  This enters the `BFC7` death/transition tail.  The observed type-1,
  no-linked-slot path adds score through the `5F0D` packed decimal helper
  (`SS:2314` BP-relative storage), runs the Y clamp, calls the observed `C055`
  logic-20 side effect (`DS:A47E--`) on the current `0020h` branch, while the
  observed `002Bh` branch follows the same transition without decrementing the
  live counter.  In both cases it transitions object logic `20h -> 1`, saves
  previous logic in `+1A`, clears `+22`, and dispatches type 1 to sprite
  `0000`.  The later `C037 -> C048` tail exits with `BX=0002` and `FLAGS=0202h`
  before the caller resumes.
- `B7F3` after an at-target `B7BD` state.  Verified branches now include the
  `B7C9` target-reset path, substate-0 `B754` movement path, and the bounded
  `B82D` waypoint-table loop when one or more selected waypoints already match
  current X/Y.

The `B7C9` branch is intentionally oracle-driven: raw branch counting suggested
that `DS:2324 == 1` preserved the old target Y, but interpreted ASM showed the
observed effect is still `target_y = (DS:2380 + 8) & FFF8h`.  Preserving the old
target caused frame-266 drift.

The `B82D` loop has one important behavior detail: selecting a different waypoint
does not move immediately.  The routine updates `+34/+32` from `DS:A842`, falls
through to the `BC4B` postmove path, and leaves movement for a later
target-mismatch tick.

## 2026-06-11 A894 layer-0 scan boundary

Gameplay from `artifacts/play_tandy_edrax_orbit_combat_20260611_214016` reached an active
layer-0 object in the `1010:A894` scan and failed at the intended call boundary:

```text
A894 ... layer-0 scan
A8BE  call 7596
A8C1  pop cx
A8C2  loop A894
A8C4  ...
```

The replacement was conceptually correct but the shared helper still had the old
fail-fast behavior.  For active/matching objects it now mirrors the original
pre-call state: `BP` and `BX` selected from `DS:32CA`, flags from the final layer
comparison, `CX` unchanged, loop `PUSH CX` visible on the stack, and `IP=A8BE`.
The real call then enters the separately verified `7596`/layer draw path.

## 2026-06-11 BEC5 collision tail: BEDC=0001 path

Manual Tandy gameplay from `artifacts/play_tandy_black_panel_20260611_192528`
reached a fail-fast collision path while shooting spawned ships:

```text
B73E -> B73E -> B7BD -> BC4B -> 62F6 -> BEC5 BEDC=0001 -> BF5E
```

This is object/gameplay behavior.  The original `1010:BEC5` bytes for the
observed variant-2 collision branch show that the `DS:BEDC == 0001` case jumps
to `1010:BF4D`, not straight to the final `RET`.  The verified tail is:

```text
BF4D  dec word ptr ss:[bp+20h]
BF50  jz  BFC7          ; still unverified
BF52  mov word ptr ss:[bp+24h],0005h
BF57  cmp word ptr ds:[A8C2h],0001h
BF5C  jz  BF5F          ; still unverified
BF5E  ret
```

The replacement now preserves that extra counter decrement, the `+24h` state
write, the final comparison flags, and the normal near-return behavior.  A
synthetic interpreted-ASM oracle test covers this complete `BEDC=0001`,
`A8C2!=0001`, nonzero-counter path.

## 2026-06-11 frame-verify regression: AA2B/EFAE dispatch boundaries

Frame verification from `artifacts/test_oracles/snapshot_play_tandy_20260611_152751` exposed a
behavior divergence at frame 34 even though local hook verifier runs had passed.
The bad frame CRC was unchanged when disabling the recent Tandy layer/draw hooks,
but disabling `1010:AA2B,1010:EFAE` restored 60-frame verification.

The issue was boundary selection.  `AA2B` and `EFAE` are dispatch stubs, not
stable behavior bodies:

```text
AA2B  mov bx,ss:[bp+16h]
AA2E  shl bx,1
AA30  jmp word ptr cs:[bx+AA36h]

EFAE  mov ax,ss:[bp+04h] ; publish Y to DS:D1FE
EFB1  mov ds:[D1FE],ax
EFB4  mov ax,ss:[bp+02h] ; publish X to DS:D200
EFB7  mov ds:[D200],ax
EFBA  mov bx,ss:[bp+18h]
EFBD  shl bx,1
EFBF  jmp word ptr cs:[bx+EFC4h]
```

They have now been backed down to dispatch-only replacements: the hooks preserve
the real register/flag/prologue side effects and leave `CS:IP` at the selected
target.  They no longer execute child gameplay routines inline.  Hook-verifier
metadata was changed accordingly (`dispatch_aa2b`, `dispatch_efae`), and synthetic
oracle tests cover both dispatch boundaries.

This is a useful rule for the next gameplay pass: parent scan wrappers can be
composed when their child routine boundaries are already verified, but gameplay
dispatch stubs should first be lifted only as dispatchers.  Concrete object
behaviors such as `B73E`, `8D4F`, `AED8`, and movement/collision helpers need
their own independent frame-level verification before being composed into a
larger gameplay tick.

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

# A90F / 5A92 present-scan lift after no-fallback policy

The no-fallback policy exposed `1010:A90F -> A91E -> 5A92` in the Tandy gameplay
snapshot `play_tandy_edrax_orbit_combat_20260611_164810`. This was not a reason to restore
a pre-call fallback; it identified another parent scan.

`1010:A90F` has the same PUSH/MOV BX,CX/SHL/MOV BP/table/active-test/CALL/POP/LOOP
shape as the already lifted `A927` scan, but it uses the overlaid object pointer
table at `DS:8D12` and finishes at `A924`. It now composes active entries through
`5A92` using a shared present-scan helper.

That exposed two real Tandy present targets:

- `1010:3542`: if `DI != FFFFh`, copies 8 rows of two words from `DS:SI` to
  `ES:DI`, adding `0064h` to `DI` after each row.
- `1010:34AD`: if entry `DI != FFFFh`, calls the verified `34C5` block copy; then
  loads `DI=SS:[BP+10]`, `SI=SS:[BP+0E]+0140h`, and tail-falls into `34C5` when
  the second destination is valid.

Both targets have interpreted-ASM oracle coverage. `A90F` has a synthetic parent
scan oracle covering `3542`, `34AD`, and early-return paths. The original crash
snapshot now advances past `A90F`; the next fail-fast marker is the more
gameplay-like `A9E0 -> AA2B` dispatch path.

---

# Fail-fast replacement policy for unknown paths

The project now treats unknown replacement paths as reverse-engineering evidence, not
as something to hide behind interpreted ASM. Conservative fallbacks in composed hooks
were removed because short-term playability is less important than exposing the next
unlifted routine. Unknown targets now raise a diagnostic `RuntimeError` with the
parent hook, dispatch chain, target IP, scan `CX`, object `BP`, and relevant object
fields.

Important consequences:

- Composed hooks must only execute verified child targets.
- If a dispatch table points to an unverified target, the hook fails fast.
- Partial scan hooks still skip inactive entries, but they no longer return to the
  original pre-call boundary when an active object needs unlifted logic.
- Runtime-patched signatures no longer silently disable hooks; they fail fast with
  the live and expected bytes.

The first newly exposed target after this policy change is `1010:A90F` reaching
`1010:A91E` from the crash snapshot `play_tandy_edrax_orbit_combat_20260611_164810`. That is
the intended next RE task, not a regression.

---

# Runtime findings after the second RE pass

## Checkpoint 31 — real Tandy 2F40 layer compositor

The crash snapshot `artifacts/play_tandy_edrax_orbit_combat_20260611_164810` showed that
the layer-1 parent hook `1010:A8C7` was not merely missing a conservative fallback:
it had exposed a real nested compositor target used by `1010:768E`, namely
`1010:2F40`.

`2F40` is a mode-2/Tandy four-word layer compositor with a different shape from
the already verified masked-copy target `2F81`.  Per row it reloads `BX=0060h`
and repeats four times:

```text
mov ax,[si]
not ax
or  es:[di],ax
add si,4
add di,2
```

Then it advances `DI` by `BX`, loops for `CX` rows, restores `DS` from
`CS:[9596]`, and returns.  The new replacement
`overkill_tandy_or_inverted_mask_2f40` preserves that exact routine boundary,
including final flags from the last `ADD DI,BX`.

`1010:768E` now treats `2F40` as a verified tail target alongside `2F81` and
`2E6E`.  `1010:A8C7` still predicts the nested `768E` target before composing a
whole scan, but the observed `2F40` case is now actually executed and oracle
verified instead of being pushed back to interpreted ASM.  Unknown nested targets
remain conservative fallback cases until they are characterized the same way.

Verification added:

- direct interpreted-ASM coverage through `768E -> 2F40`;
- full composed parent coverage for `A8C7 -> 7596 -> 768E -> 2F40`;
- replay of the crash snapshot for 50,000 instructions;
- live hook verifier on the crash snapshot for `A8C7` and `768E`;
- full suite `99 passed`.

## Checkpoint 30 — Tandy layer-1 draw pipeline composition

The `A8C7 -> 7596 -> 768E` hot path is now lifted as a verified layer-1 draw
pipeline rather than a set of loose render leaves.

`1010:7596` is only a small object-type dispatcher:

```text
7596  mov bx,ss:[bp+14h]
7599  shl bx,1
759B  jmp word ptr cs:[bx+75A0h]
```

For the hot Tandy first-level layer-1 objects, the dispatch target is
`1010:768E`.  That target is now replaced by
`overkill_tandy_layer_sprite_draw_768e`.  It reads `SS:[BP+0C]` as the
destination and returns immediately if it is `FFFF`; otherwise it loads
`ES=CS:[9598]`, chooses the source segment from `CS:[95AA]`/`CS:[95AC]` based on
`SS:[BP+08]`, looks up the source pointer through the `CS:9192` table, folds the
video mode and sprite phase `SS:[BP+12]` into the compositor table, and tail-runs
the verified Tandy compositor (`2F81` in the common path, `2E6E` also allowed).
Unknown compositor targets still tail-dispatch back to the original target.

`1010:A8C7` is now a composed parent hook for the layer-1 scan.  It keeps the
same active/layer predicate as the original code, including the `DS:BDAC`,
`DS:2350`, `SS:[BP+16]`, and `SS:[BP+0A]` checks.  For active layer-1 objects
whose `7596` target is the verified `768E` path, it preserves the original
`PUSH CX`, `CALL 7596`, `POP CX`, and `LOOP` shape while running the known child
hook directly.  If an active object points at any other `7596` target, it falls
back at the original pre-call boundary `1010:A8F1`.

Oracle tests cover `768E` complete, `DI=FFFF`, and unknown-target fallback paths,
plus `A8C7` complete and unknown-target fallback paths.  Live verification from
`artifacts/test_oracles/snapshot_play_tandy_20260611_152751` covered 800 real `768E` calls and
500 real `A8C7` scans with no divergence.

After this pass, the remaining Tandy first-level profile is dominated by shared
object/gameplay behavior rather than Tandy render plumbing: the `A9E0 -> AA2B`
timed object scan/update, `EFAE` object routine dispatch, and the `BC4E`/nearby
update/collision-style path.

## Checkpoint 29 — composed Tandy object scan passes

The verified Tandy render/present leaves made it possible to lift two parent scan
loops without guessing at object behavior:

- `1010:A927 overkill_scan_objects_call_5a92_a927`
- `1010:A849 overkill_scan_objects_call_5ac8_a849`

Both are descending scans over the `DS:32CA` object table.  The original loop
shape is:

```text
push cx
mov  bx,cx
shl  bx,1
mov  bp,[bx+32CA]
cmp  word ptr ss:[bp],0
jz   skip_call
call dispatcher
pop  cx
loop top
```

Previously these hooks only skipped inactive entries and stopped immediately
before the real call for the first active object.  They now execute the full scan
when the active object's dispatch target is in the verified Tandy set:

- `A927 -> 5A92 -> 34D8/34C5` for object presentation.
- `A849 -> 5AC8 -> 35CC/35AA` for object drawing.

The implementation still preserves the original stack shape: each iteration
leaves the balanced `PUSH CX` scratch below `SP`, active calls also leave the
internal return-word scratch (`A939` or `A85B`), and `LOOP` does not alter flags.
If a target outside the verified set is encountered, the hook falls back to the
old pre-call boundary (`A936` or `A858`) so the original interpreted code can
continue.

Verification added synthetic interpreted-ASM oracle tests for the complete and
fallback paths of both parent hooks.  Live verifier coverage from
`artifacts/test_oracles/snapshot_play_tandy_20260611_152751` covered 750 real `A927` scans and
760 real `A849` scans with no divergence.

After this pass, the common first-level Tandy profile no longer spends
interpreter time in the repeated `A849/A927 -> 5AC8/5A92 -> 35CC/34D8` crossing
pattern.  Remaining heat is now concentrated in shared object/gameplay paths
(`AA2B`, `EFAE`, `BC4E`/nearby) and the layer-1 draw pipeline
(`A8C7 -> 7596 -> 768E`).

## Checkpoint 28 — Tandy first-level gameplay block hooks

Profiling from `artifacts/test_oracles/snapshot_play_tandy_20260611_152751` showed the next
Tandy gameplay heat was no longer startup decode, but mode-2 object sprite/copy
blocks plus object dispatch glue.  The clean Tandy-specific blocks are now
hooked and verified:

- `1010:2F81 overkill_tandy_masked_sprite_composite_2f81`
- `1010:2E6E overkill_tandy_masked_sprite_composite_2e6e`
- `1010:34C5 overkill_tandy_strided_copy_34c5`
- `1010:35AA overkill_tandy_source_strided_copy_35aa`
- `1010:34D8 overkill_tandy_small_strided_copy_34d8`
- `1010:35CC overkill_tandy_draw_object_block_35cc`

The existing `1010:5A36` row-address dispatch hook now also folds in mode 2
(`1010:30D2`).  Mode 2 maps `SS:[BP+02]` Y through the row table at
`DS:99C8`, rejects `Y >= 00E0h` and `FFFF` row entries by returning `AX=FFFF`,
stores zero to `SS:[BP+12]`, adds `X >> 1`, and optionally decrements
`SS:[BP+24]`.  The verifier metadata for `5A36` now treats modes 0/1/2 as
caller-return hooks; unknown modes still dispatch to the original table target.

`1010:35CC` is the first larger composed Tandy draw hook in this group.  It
mirrors the original `CALL 5A36` stack scratch, uses the verified row-address
hook internally, stores `SS:[BP+0C]`, applies the work-buffer base at `DS:234C`,
loads `ES=CS:[9596]` and `DS=CS:[9598]`, then copies 16 rows of four words while
advancing `SI` by `0060h` after each row.  Its companion `1010:34D8` handles the
present-side fixed block: `DI=FFFF` returns immediately, otherwise it copies 16
rows of four words and advances `DI` by `0060h` after each row.  A live verifier
run caught and corrected an initial synthetic-test mistake around the final
`ADD DI,BX` in `34D8`.

Verification added interpreted-ASM oracle tests for all new Tandy gameplay hooks,
including DF-sensitive fixed-copy cases and the composed `35CC -> 5A36 -> 30D2`
path.  Live verification from the Tandy first-level snapshot covered 2,000 mixed
calls across `2F81/2E6E/34C5/35AA/5A36`, 500 real `34D8` calls, and 1,500 mixed
`35CC/34D8/5A36` calls with no divergence.

After these hooks, the remaining real interpreted heat in a 3M-step Tandy
first-level profile has shifted toward shared gameplay/object code:
`1010:AA2B`, `1010:EFAE`, `1010:BC4E`/`BCxx`, and smaller draw target work around
`1010:768E`.  Those should be characterized as call families before lifting; the
Tandy-specific sprite-copy plumbing is no longer the main interpreted island.

## Checkpoint 27 — Tandy default and `1010:33B2` startup expander

Tandy is now the default interactive/profile mode (`scripts/play.py` and
`scripts/profile_hotspots.py`).  It is visually equivalent to the EGA path for
the current port work and has the best observed interactive behavior.

The slow Tandy cold-start asset path was the live-patched packed-pixel expander:

```text
1010:33B2  block/list continuation
1010:33DD  per-cell source expander
1010:344B  packed-pixel helper
```

This is the Tandy analog of the EGA `4511/4537/45F6` startup-expander family.
`33DD` reads four source bytes separated by `CS:[5B9C]`, calls the `344B` packer
four times, stores the resulting visible/mask bytes in `CS:5B94..5B9B`, then
writes two visible words or four mask+visible words to `ES:DI` using `STOSW`.
`344B` uses the same `ROR`/`RCL` bit chain shape as `45F6`, but it does not apply
the EGA colour-remap table.

Added verified hooks:

- `1010:33DD overkill_expand_tandy_cell_33dd`
- `1010:33B2 overkill_expand_tandy_block_33b2`

The `33B2` hook includes a live-byte guard because this area is runtime-patched.
It handles both continuations (`1010:33AF` normal loop, `1010:44AA` terminator)
and preserves final stack scratch words from the original nested `PUSH/CALL/POP`
shape.  Synthetic oracle tests cover `33DD`, `33B2`, and the terminator branch.
The live hook verifier covered all 686 real `33B2` calls reached in the current
Tandy startup profile with no divergence.

Profiling after the hook shows `33B2` as 686 block-level calls instead of the
previous interpreted `33B2/33DD/344B` loop tree.  A follow-up cleanup removed the
internal 344B rotate-simulator path and computes the packed bytes directly;
`33B2` dropped to about `0.57s` total / `0.83ms` per block in the 6M-step Tandy
startup profile.  The same profile still later stops at the pre-existing
`Unsupported opcode 98 at 1010:0008`; disabling `1010:33B2` hits the same stop,
so that is not caused by this hook.

The SDL viewer window is also resizable/maximizable now.  The native 320x200
frame is centered at the largest integer scale that fits the current window, so
maximized windows preserve aspect ratio with black bars as needed.

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
artifacts/evidence/snapshot_after_bootstrap_100k/
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
before: artifacts/evidence/snapshot_before_lz_full_hook_ecf2
after:  artifacts/evidence/snapshot_after_lz_full_hook_ecf2
```

The hook decodes 51,636 bytes to `ES:DI` output space for the captured asset and advances the `OVERKILL` data-file handle from offset 463,837 to 476,125.


## Checkpoint 6 — verified startup render/RLE control hooks

This checkpoint keeps the original executable as the behavioral oracle and adds only narrow replacements that were verified against interpreted ASM on synthetic streams/snapshots.

New verified hooks:

- `1010:450C overkill_expand_4plane_list_450c` — folds the hot outer 4-plane block-list driver (`450C -> 44D7 -> 4511 -> 450C`) while still using the already verified block renderer. It handles both normal block headers and the zero/FFFF exit cases without inventing higher-level sprite semantics.
- `1010:0367 overkill_linear_byte_rle_decoder_0367` — horizontal/linear byte-RLE decoder sibling of the existing vertical decoder. It is tested against interpreted ASM for literal runs, repeat runs, and the `80h` terminator.
- `1010:4537 overkill_expand_4plane_row_4537` — optimized row renderer. It is still tested against interpreted ASM, but removes synthetic nested calls to `45F6` and `45CB` inside the hot path. Note: this mirrors the current interpreter's rotate flag behavior, including the simplified ZF/SF/PF updates implemented by `CPU8086.shift`, so tests remain oracle-relative.

New tooling:

- `overkill-port continue-snapshot ...` can resume execution from a saved snapshot directory. This avoids replaying the whole bootstrap when investigating the next hot area.
- `snapshot.load_snapshot(...)` restores CPU state, memory and simple DOS open-file bookkeeping for RE scripts.

Observed runtime state at `artifacts/evidence/snapshot_after_verified_render_rle_hooks_38600`:

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
artifacts/evidence/snapshot_stop_497a_probe
artifacts/evidence/snapshot_stop_41da_probe
artifacts/evidence/snapshot_stop_5827_probe
artifacts/evidence/snapshot_stop_50c9_probe
artifacts/evidence/snapshot_stop_58df_probe
```

After these hooks, execution from checkpoint 6 reaches a new guarded diagnostic snapshot:

```text
artifacts/evidence/snapshot_suspicious_41da_header_after_video_hooks
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
artifacts/evidence/snapshot_stop_0871_distinct_heap
artifacts/evidence/snapshot_stop_5d20_distinct_heap
artifacts/evidence/snapshot_after_psp_heap_fix_20k
artifacts/evidence/snapshot_stop_254a_0585_after_psp
artifacts/evidence/snapshot_after_psp_heap_fix_30k
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
artifacts/evidence/snapshot_probe_frontier_2m       (before: stuck spinning at 1010:0679)
artifacts/evidence/snapshot_after_timer_hook_2m     (after:  CS:IP=1010:4496, ES=B800)
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
artifacts/evidence/snapshot_stop_447f_probe          (entry-path trace into the blit)
artifacts/evidence/snapshot_probe_frontier2_8m       (8M-step frontier: still advancing, CS:IP=1010:A930)
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
artifacts/evidence/frame_2m_pal1h.png   (item "Fire Nose")
artifacts/evidence/frame_8m_pal1h.png   (item "Drone >2<")
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
post-bootstrap state instantly; the current live play snapshots are fresh captures
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

This note is historical: the later EGA shadow-plane and present/page-flip fixes
explained the observed ghosting better than those hooks.  `play.py` no longer
has an `--unsafe-render-hooks` mode.  The only interactive-mode hook suppression
left is `1010:58DF` for non-CGA, because that lifted loop is mode-0-specific.

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
presented frame in an explicit shadow layout inside the `A000h` aperture
(**superseded** — the planes were later moved out of the CPU aperture; see the
"EGA planar correctness" entry below):

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

### 2026-06-10 EGA planar correctness: read-map tracking and out-of-aperture shadow storage

This entry consolidates the EGA colour-ghosting / screen-mixing investigation that
followed the first EGA presenter.  It **supersedes the in-aperture shadow layout**
described in the "EGA play mode" entry above: emulated EGA planes are no longer
stored inside the CPU-visible `A000h` aperture.

Findings and fixes, in the order they landed:

1. Read-map tracking and planar-safe fast paths.
   `Memory` now tracks the graphics-controller read-map-select (port `03CEh/03CFh`
   index `04h`) in addition to the sequencer map mask (`03C4h` index `02h`), and
   routes `A000h` `rb/rw` through the selected shadow plane.  The optimized
   `REP MOVSB/MOVSW/STOSB` slice paths fall back to the per-byte `Memory` path
   whenever a transfer touches the EGA aperture, so they can no longer update or
   read only one plane and leave coloured sprite ghosts.

2. Out-of-aperture shadow storage.  On real EGA,
   `A000:2000` is CPU offset/page `2000h` in the *selected* plane(s), not "plane 1
   at offset 0".  The transition/fullscreen code really does touch those high CPU
   offsets, so the old in-aperture layout let them clobber the visible plane
   shadows (the "mixed screens" artifact).  Planes now live outside the 20-bit CPU
   address space at `EGA_SHADOW_BASE (0x100000) + plane * 0x10000 + offset`; CPU
   accesses to `A000:0000..FFFF` are routed through the read-map / map-mask state
   into that store, and rendering + CRC sampling read the store, not the aperture.
   Tests: `test_ega_cpu_page_offsets_do_not_alias_visible_shadow_planes`,
   `test_ega_read_map_can_read_high_cpu_offsets_without_shadow_aliasing`.
   Diagnostic: `scripts/probe_ega_page_offsets.py`.

3. Presenter + remaining flat stores.  `overkill_present_ega_frame_2750` and
   the `1010:291C` temp-row copy still wrote flat `A000:+plane*2000` / direct
   `mem.data` bytes; both now write through the shadow store / `Memory.wb()` when
   `ES=A000h` (keeping a flat fallback for non-`A000h` synthetic/oracle cases).
   With the aliasing fixed, the `CCAA`/`CCC4`/`CCF0` dirty-copy hooks were
   re-enabled for interactive EGA/Tandy playback; `1010:58DF` stays disabled for
   non-CGA because it is mode-0-specific.

4. Self-modifying-code guardrail.  The unpacked
   EXE rewrites large parts of `CS=1010h` during bootstrap, so comparing against the
   load image is misleading; the useful baseline is the first post-bootstrap video
   boundary.  Over the tested intro/menu path the EGA render routines stay stable
   after that baseline (only the inline variable at `1010:5901` changes).  As a
   guardrail the EGA render/dirty hooks (`2750`, `27EB`, `280D`, `2824`, `291C`,
   `2932`, `58DF`, `CCAA`, `CCC4`, `CCF0`) verify their entry bytes and self-disable
   (leaving `CS:IP` for the interpreter) if the game ever patches them later.
   `OVERKILL_TRACE_CODE_PATCHES=1` logs such self-disables.
   Diagnostic: `scripts/probe_ega_self_mod.py`.

`render_ega_ppm()` decodes the four shadow planes (`EGA_SHADOW_BASE` layout, with a
legacy in-aperture fallback for old byte snapshots) as standard 320x200 16-colour
RGBI output.

### 2026-06-11 EGA gameplay profiling and the 1D1B bit-spread composite hook

First profiling pass driven from a real in-level EGA snapshot
(`artifacts/play_ega_edrax_orbit_combat_20260611_123041`, ~3.9M steps in) rather than the
startup/loading path.  Tooling: `scripts/profile_hotspots.py <steps> --snapshot
<dir>` (wraps every hook with a timing shim and reports interpreted CS:IP
frequency, backward-edge loops, and hook boundary crossings).

Headline: during gameplay the **interpreter is ~86% of wall time**; replacement
hooks are ~5.7% (decode/IO) and present/frame hooks ~8.2%.  So the wins are in
fusing the remaining hot *interpreted* loops, not in adding more leaf hooks.

Top interpreted gameplay loops (2M-step sample, by backward-edge count):

| loop | iters | what it is |
|------|-------|------------|
| `1D1B→1DEB` | 4,080 | EGA bit-spread masked sprite/tile composite (hottest, ~18% of interpreted steps) |
| `29AF→29C3`, `2A9D→2AB1` | ~3,700 | interpreted tails around the already-hooked 29C6/2AB9 EGA copies |
| `13E7→1542` | 3,660 | not yet analysed |
| `2672→26FA` | 2,928 | not yet analysed |

The object-scan dispatch (`A8xx`/`5A92`/`5AC8`/`A9E0`) is already hooked and cheap
per call; it drives the EGA copy/composite variants, which is where the time goes.

`1010:1D1B` is one target of the `jmp cs:[bx]` sprite dispatcher at `1010:76E2`
(sibling of the already-hooked `1010:1AEB`).  It returns near to the object-scan
caller after restoring DS from `CS:[9596]`.  Per row it reads one mask word plus
four data words (`SI += 0Ah`), spreads each word through the original RCR/SHR bit
chains, AND-s the mask into four 3-byte chunks (word at DI, byte at DI+2; chunks
spaced 1Ah; `DI += 68h` per row), then OR-s the four data words in.

New verified hook `overkill_ega_spread_masked_composite_1d1b` replicates those
chains exactly (same primitives/order, so registers, flags and memory match) and
removes the per-instruction fetch/decode/dispatch overhead.  Correctness:

- synthetic oracle `test_ega_spread_masked_composite_1d1b_hook_matches_interpreted_asm`
  (rows 1/2/8/16/17, full register+flag+memory equality vs interpreted ASM);
- runtime differential verifier (`hook_verify.py`, `1D1B` → `near_ret`): 300
  consecutive in-game calls compared full-memory against the interpreted routine
  with zero divergence.

Performance (150 in-level frames from the snapshot, same game progress):

| config | wall | fps | interpreted steps |
|--------|------|-----|-------------------|
| 1D1B interpreted | 12.42s | 12.1 | 2,474,881 |
| 1D1B hooked | 10.27s | 14.6 | 2,029,670 |

≈ **17% faster wall / +20% fps** from this one hook; interpreter steps/sec is
unchanged, confirming the gain is from executing ~445k fewer interpreted
instructions per 150 frames.  The hook only fires in EGA (CGA/Tandy select other
jump-table targets and never reach `1D1B`), so those modes are unaffected.

Tooling note: hooks can now be disabled individually for A/B checks and bisection
via `OVERKILL_DISABLE_HOOKS=1010:1D1B[,1010:....]` (honoured by
`HookRegistry.install`).

### 2026-06-11 EGA gameplay perf #2: the wide 13E7 bit-spread composite hook

Re-profiling the same in-level EGA snapshot after the `1D1B` hook, the interpreter
is still ~83% of wall time.  Top interpreted gameplay loops by backward-edge count
(2M-step sample):

| loop | iters | what it is |
|------|-------|------------|
| `29C3→29AF` | 4,440 | un-hooked block-copy routine at `29A9` (5-byte columns, sibling of the hooked `29C6`) |
| `2AB1→2A9D` | 4,440 | sibling copy near the hooked `2AB9` |
| `1542→13E7` | 4,417 | **wide bit-spread masked composite (chosen)** |
| `26FA→2672` | 3,552 | EGA planar tile draw with per-plane `OUT 03C4h/03CEh` port writes |

Chosen: `1010:13E7`, the five-byte-wide sibling of `1D1B`.  Like `1D1B` it is a
target of the `jmp cs:[bx]` sprite dispatcher (here at `1010:7620`) and returns
near to the object-scan caller after `MOV DS,CS:[9596]`.  Differences from `1D1B`:
each chunk is word+word+byte (AX at DI, BX at DI+2, DL at DI+4) instead of
word+byte; the RCR/SHR spread chains run over the AL/AH/BL/BH/DL register chain;
the source is read with explicit `MOV r,DS:[SI+disp]` (not `LODSW`) as one mask
pair plus four data pairs, so `SI += 14h` per row; the row end is
`ADD DI,68h; ADD SI,14h` and the live flags at the near return come from that final
`ADD SI,14h`.  Four chunks per row spaced `1Ah`, 16 rows, `DI += 68h` per row.

New verified hook `overkill_ega_spread_masked_composite_wide_13e7` replicates the
chains exactly (same primitives/order) so registers/flags/memory match; only the
per-instruction dispatch overhead is removed.  Correctness:

- synthetic oracle `test_ega_spread_masked_composite_wide_13e7_hook_matches_interpreted_asm`
  (rows 1/2/8/16/17, full register+flag+memory equality vs interpreted ASM);
- runtime differential verifier (`hook_verify.py`, `13E7` → `near_ret`): 300
  consecutive in-game calls compared full-memory against the interpreted routine
  with zero divergence.

Performance (150 in-level frames from the snapshot, identical game progress;
deterministic step counts, two back-to-back runs each):

| config | wall | fps | interpreted steps |
|--------|------|-----|-------------------|
| 13E7 interpreted | ~14.2s | ~10.6 | 2,029,670 |
| 13E7 hooked | ~9.5s | ~15.7 | 1,328,476 |

≈ **33% faster wall / +48% fps** from this one hook; 701k fewer interpreted steps
(-34.5%) for the same 150 frames, steps/sec unchanged.  EGA-only (CGA/Tandy select
other jump-table targets and never reach `13E7`).

Remaining top gameplay candidates for a future single-hook pass: the un-hooked
`29A9` 5-byte block copy (`29C3→29AF`, simplest, exact sibling of `29C6`), its
`2A9D` neighbour, and the port-driven planar tile loop at `2672` (riskier because
each iteration issues `OUT 03C4h/03CEh` sequencer/GC writes that change planar
routing state).

### 2026-06-11 Viewer backend investigation: is Tk the bottleneck? (added SDL backend)

Question raised from interactive EGA play feeling like ~5 fps: is the Tk renderer
the bottleneck, and would SDL help?  Measured on the in-level EGA snapshot.

Per-frame display path (scale 2): `render_ega_ppm` builds a *scaled* RGB PPM in a
pure-Python pixel loop, it is written to a temp `.ppm` file, and a fresh
`tk.PhotoImage(file=...)` is parsed back from disk every frame.  Component costs:
render 3.1 ms, disk write 0.5 ms, PhotoImage 1.6 ms.  A NumPy decode at *native*
320x200 is 0.76 ms and is pixel-identical to `render_ega_ppm`.

Head-to-head, real `FrameSync` + emulator thread, displayed frames over 6 s:

| pipeline | fps |
|----------|-----|
| emulator only (no UI), counting visible `2750` presents | ~14 |
| async Tk (`root.after(1)` + PPM + disk + PhotoImage) | ~11 |
| async pygame (poll + NumPy + SDL surface/scale/flip) | ~12 |

**Conclusion: Tk is _not_ the primary bottleneck — the interpreter is** (~14
visible-fps ceiling on this snapshot; lower with more on-screen objects).  Both UI
pipelines sit near that ceiling, so swapping Tk→SDL is only ~10% at scale 2.  The
real lever for higher fps remains emulator hook fusion (see the 1D1B/13E7 passes).

SDL is still clearly the better viewer and is now the **only** live backend (Tk
was removed): keeping two UIs was pure accretion once `pygame`/`numpy` are accepted
runtime deps for the playable game.

- the display path is **8-9x cheaper** (scale 2: ~1.4 ms vs ~12 ms) and, unlike
  the old Tk path whose pure-Python scaled-PPM cost is O(scale²) (12 / 15 / 21 ms
  at scale 2 / 3 / 4), the SDL path renders native and GPU-scales (~1.4 / 1.8 /
  2.4 ms), so its advantage grows with window size and as the emulator gets faster;
- it removes the per-frame temp-file round-trip and `PhotoImage` allocation.

Implementation: `scripts/sdl_view.py` (`pygame` + `numpy`) holds the vectorised
`render_{ega,cga,tandy}_rgb` decoders and `run_sdl_ui`; `play.py` builds the
emulator/hooks/`FrameSync`/keyboard/pacing/F12-snapshot session and then runs
`run_sdl_ui` on the main thread.  The reference `render_*_ppm` functions in
`render_cga.py` are kept as the headless PNG-dump tool and as the decode oracle;
`tests/test_render_rgb.py` asserts the NumPy decoders are pixel-identical to them
(full-memory *and* the tight shadow-plane slice the viewer actually publishes), so
the displayed image is unchanged.  `pygame`/`numpy` are declared in
`pyproject.toml` and imported only when the viewer launches, so the interpreter
core, the PNG tool and the test suite still run without them.

### 2026-06-11 fail-fast object-logic frontier: A9E0 -> AA2B -> EFAE -> B73E -> 5DB2

After removing playable fallbacks, the next Tandy gameplay snapshot stopped at
`1010:A9E0 -> AA01 -> AA2B`.  This was not a render fallback; it is the first
real move into shared object/gameplay logic.

New lifted pieces:

- `1010:A9E0 overkill_scan_objects_call_aa2b_a9e0`: full fail-fast scan over the
  `DS:32CA` object table.  It preserves the original per-iteration increment and
  reset of `DS:2340`, checks `SS:[BP]` active state, and composes the AA2B object
  dispatch instead of stopping at the CALL boundary.
- `1010:AA10 overkill_scan_objects_call_aa2b_aa10`: same AA2B composition for the
  `DS:8D12` object table.
- `1010:AA2B overkill_object_logic_dispatch_aa2b`: first-level object logic
  dispatcher using `SS:[BP+16]` and table `CS:AA36`.
- `1010:EFAE overkill_object_family_dispatch_efae`: second-level object-family
  dispatcher.  It writes object coordinates to `DS:D1FE/D200`, then dispatches
  through `CS:EFC4` using `SS:[BP+18]`.
- `1010:B73E overkill_object_behavior_b73e`: first branch layer of the observed
  `logic_id=20h` behavior.  For the current object (`substate=FFFFh`) it selects
  the frame, reaches the `B85C -> B729` path, prepares `DS:2304/2306`, and stops
  at the concrete unlifted helper `1010:5DB2`.

The frontier is now no longer the vague `AA2B` dispatcher.  It is a specific
movement/direction helper:

```text
A9E0 -> AA2B -> EFAE -> B73E -> B85C -> B729 -> 5DB2
```

Snapshot replay now intentionally stops with full object context at `1010:5DB2`.

### 2026-06-12 AC97 object-slot scan lift

Using `artifacts/evidence/ac97_stop` from
`artifacts/snapshot_play_tandy_20260612_192438`, I traced the hot
`1010:AC97` path and confirmed it is a read-only scan over 35 object records.
The body walks `DS:23B4` in `0038h` strides, skips empty and state-gated
entries, applies the signed Y/X window checks plus the `SS:[BP+14]`
comparison, and then advances `BX/CX` before re-entering `AC97` for the next
slot.

That scan now lives in `overkill_object_slot_scan_ac97`, so the slowdown no
longer needs to run through the interpreted original loop.

### 2026-06-12 BCB1 post-move clamp lift

The same gameplay snapshot also showed `1010:BCB1` as a tiny but hot repeated
leaf inside the BC4B post-move path.  It only clamps `SS:[BP+4]` into the
inclusive `0..00C0h` range before returning to the `BC4E` continuation, so it
is now lifted into `overkill_postmove_y_clamp_bcb1`.

### 2026-06-12 BC4B post-move call-site lift

The remaining collision hotspot from the same snapshot was the `1010:BC4B`
post-move call-site itself.  The hook now absorbs the full Y clamp, X bounds,
BCCB view/contact check, the observed `AA71` contact-window helper including
the `AAAB -> AA44` upper tail, optional BFC7 death tail, `9E69` bookkeeping,
and the `62F6` overlap scan before returning to the outer caller, which removes
the last large interpreted block in that path.

One more small `62F6` detail mattered for verifier parity: the signed
`SS:[BP+2] < 0x20` early exit keeps the compare flags live and returns with the
incoming `BX` unchanged instead of advancing to the empty-scan sentinel.

### 2026-06-12 AA71 upper contact tail lift

The same BC4B snapshot also exercised the higher `AA71` branch that survives
the signed X guard and then runs the `AAAB -> AA44` success tail.  That path
reuses the `SS:[BP+2] + 18h` compare against `DS:237E`, clears carry, and
returns without mutating any object state, so it is now folded into the
contact-window helper instead of failing fast.  The remaining `A8C2==0001`
branch still stays as an explicit frontier because we have not yet captured it
in a trace.

### 2026-06-12 BD17/C054 dispatcher lift

The same out-of-bounds tail also reaches the `1010:BD17` deactivation helper.
The current `C054` compare chain now returns `A4E4h` for the observed
`0000h`/`0013h` selectors and leaves the `BD5F` call scratch below the final
return word.  Only the smaller side-effect family still touches the live-object
counter.  The newer `draw_layer=5, logic_id=0000h` branch also clears the
active flag and returns without touching `DS:A47E`, so the replacement now
tracks both observed paths instead of failing fast.

### 2026-06-13 BD17 A83E/A82A linked-effect tail

A later Tandy capture (`snapshot_play_tandy_20260613_125913`) hit the
`BC4B -> BD17` out-of-bounds branch with `draw_layer=4` and `logic_id=001Fh`.
That path does not stop after `C054`: when the selector resolves to `A83Eh`
(and the sibling `A82Ah` selector on the same tail family), the original code
stores the selector result in `DS:A482`, marks `DS:A842=A844h`, pushes the live
`BX/BP` frame, publishes source Y/X/type to `DS:2376/2378/237A`, seeds the
`C017` scratch word, and calls the shared `7420` linked-effect spawn helper.
After `7420` returns, `BD17` pops `BP` and `BX`, decrements `DS:A47E`, and
returns through `BD5F`.

The replayed oracle state at the shared continuation is:

```text
AX=0000 BX=0008 CX=0022 SI=0048
```

That matches the `1010:BD17` helper now and closes the missing post-`C054`
tail that had been returning too early.

### 2026-06-12 BFC7 shared C054 call for logic 003Bh

A later Tandy snapshot (`snapshot_play_tandy_20260612_223501`) reached the
`BC4B -> 62F6 -> BEC5 third counter zero -> BFC7` tail with
`logic_id=003Bh`.  Running the same entry through interpreted ASM showed that
`BFC7` does not special-case this id.  It still calls the shared `C054`
selector at `C018`; `003Bh` falls through the compare chain to the default
`AX=A4E4h`, then `C01B` overwrites flags with the `DS:98C0` compare and `C027`
loads `AX=003Bh` for the final state transition.  Therefore the replacement now
models the real shared `C054` call instead of maintaining a short allow-list of
no-counter logic ids.

### 2026-06-12 BFC7 no-counter branch lift

The `BFC7` death/transition tail also has current observed `logic_id=0012h`,
`002Bh`, and `0031h` branches in the same snapshot.  They take the same state
transition as the verified death tail but skip the `DS:A47E--` live-counter
decrement.  The replacement now keeps that family in the observed no-counter
path instead of failing fast.

### 2026-06-12 BEC5 variant 000Ch BFB9 tail lift

The same BEC5 collision helper has a variant table entry for `000Ch` that
shares the `BFB9` tail with the `0007h`, `0008h`, and `0009h` branches.  That
branch now returns control to the original interpreter at `BFB9` instead of
throwing, so the shared tail can continue to run with the live game state.

### 2026-06-12 BEC5 sprite 0033 BF21 continuation

The same `1010:BEC5` helper also has a `sprite=0033h` branch that just falls
through into the shared `BF25` counter logic instead of failing fast.  The
`third counter zero` path then joins the shared `BF4B -> BFC7` death/score
tail, so the replacement now lets the original tail run instead of aborting at
the sprite compare.


### 2026-06-12 — CC7F dirty-cell presenter row driver

- `1010:CC7F overkill_dirty_cell_presenter_row_cc7f` is the hot row driver
  around the already-lifted dirty-copy leaves `CCAA`/`CCF0`/`CCC4`.  It is not
  asset-codec work; it belongs to the renderer/menu dirty-cell presenter.
- The routine starts with a remaining-row count in `CX`, pushes it, converts the
  current row coordinate `DS:BD95` through `5A24`, stores the work-buffer DI in
  `DS:BD9E`, points `SI` at the shadow/front-buffer cell, clears `DL`, and
  dispatches the video-mode dirty-copy detector through the table at `CS:CCA4`.
- If `DL` remains zero, the original jumps from `CD08` to `CE07` and only
  increments `DS:BD95` before the inner `LOOP`.  If `DL` is non-zero, the
  original draws the source cell through the `5A6C` mode table, optionally waits
  for retrace, then dispatches the changed-cell present loop through `CS:CD84`.
- The hook consumes the inner `CC7F -> ... -> CE10 -> CC7F` loop internally and
  stops at `CE13`, so live verification can use a stable continuation that is
  not the hook entry itself.  CGA mode uses the existing `41A6` and `CD8D`
  hooks; Tandy mode uses the existing `306F` and `CDAA` hooks.

### 2026-06-12 — CC7F intro pacing wrapper regression

- The first `1010:CC7F` lift was register/memory-correct at the `CE13` row
  boundary, including when compared against pure interpreted ASM from the
  `snapshot_play_tandy_20260612_235139` intro dirty-cell state.
- The interactive intro still regressed visually because the fused CC7F path
  called the base `1010:50C9` retrace wait helper directly from the nested
  `CD52 -> 50C9 -> CD68` path.  In `scripts/play.py`, `50C9` is wrapped as a
  visual pacing boundary that publishes the dirty-cell transition and yields to
  the UI.  Bypassing that installed wrapper lets a large number of changed cells
  complete inside one CPU burst, so the intro looks frozen/skipped even though
  memory matches at the later verifier boundary.
- The fix is deliberately narrow: fused hooks still call most leaf replacements
  directly, but timing-sensitive nested retrace waits use the currently
  installed hook with normal near-CALL stack semantics.  If the interactive
  wrapper raises after returning to `CD68`, execution resumes in the original
  interpreted tail at `CD68`, preserving both UI pacing and correctness.

### 2026-06-13 — replacements.py staging refactor and 30BA patched row copier

`replacements.py` has been reduced back toward an address-facing hook wrapper
layer.  Shared 8086-style helper operations now live in
`overkill_port/games/overkill/asm.py`, while the large gameplay object,
post-move, collision, and object-logic branch family now lives in
`overkill_port/games/overkill/gameplay/object_runtime.py`.  The wrappers still
register exact `CS:IP` hooks in `replacements.py`; tests that import legacy
private helpers continue to work through imports from the new modules.

The cold-start coverage dashboard also exposed the `1010:30C3/30C4/...` unknown
cluster.  Inspecting live bytes showed that `1010:30BA` is runtime-patched: the
static startup clear-loop body is later replaced by a compact Tandy row copier
(`mov cx,ax; lodsw; shl ax,1; shl ax,1; mov bp,ax; ... rep movsb ... add
di,00A0h; loop`).  The new `1010:30BA overkill_tandy_patched_row_copy_30ba`
hook is therefore signature-guarded and falls back to interpreting the current
instruction if those patched bytes are not resident.  Live hook verification
from startup verified 25 calls before timeout with no divergence.

## 2026-06-13 file-I/O island closure: `254A:04D7` overlay/container parent

The overlay/container parent at `254A:04D7` has now been lifted as a small
`file_io` island rather than as another asset decoder.  It opens either the
container-list path or a direct file path depending on `CS:[073A]` bit 0, reads
12-byte container headers, computes MZ overlay-directory offsets from
`CS:[074C]/[074E]`, delegates the existing verified signature/directory/name/path
subloops, seeks to the selected payload, and returns the open DOS handle plus the
selected payload length.

The implementation lives in
`overkill_port/games/overkill/file_io/overlay_loader.py` with the hook wrapper
`overkill_overlay_container_open_entry_254a_04d7`.  Its stop metadata is a
far-return boundary, matching the original caller shape.

Verification notes:

```text
snapshot_stop_254a_04d7_overlay_parent: interpreted ASM == lifted hook
full CPU state match
full memory match
DOS file positions/open handles match
live verifier: 17 cold-start calls with no divergence before the smoke timeout
```

This supersedes the older note that `254A:04D7` was intentionally not lifted.
The codec work remains separate: `asset_codecs` covers deterministic decode and
search loops, while `file_io` now owns the parent file-open/read/seek
orchestration.


## 2026-06-13 - Unknown gameplay/collision hook absorption

Absorbed several hot unknown/gameplay instructions without duplicating existing logic:

- `1010:AED8 overkill_object_behavior_aed8` now hooks the observed logic-id 2/3 countdown/movement behavior and reuses a shared `AD60` bounds/tile tail.
- `1010:AD04 overkill_object_logic_branch_ad04` is only a branch selector: it returns or jumps to existing `ABxx` behavior tails, rather than reimplementing those tails.
- `1010:AC81 overkill_object_slot_scan_guard_ac81` is only the guard/setup for the already-lifted `AC97` object-slot scan and directly reuses `run_object_slot_scan_ac97`.
- `1010:AE09 overkill_object_behavior_ae09` handles the observed logic-id `0Ch` timer/3-pixel movement behavior, then reuses the same shared `AD60` tail as `AED8`.

The previous inline `AD60` implementation inside `AED8` was refactored into `_run_object_bounds_tile_tail_ad60` so new behaviors do not clone the same bounds/tile/deactivation logic.

Validation: `python scripts/run_tests.py` => `162 passed, 0 failed`; `python -m compileall -q overkill_port tests scripts`; live hook verifier samples were recorded for `AC81`, `AD04`, `AE09`, and `AED8` and added to `artifacts/hook_coverage_cache.json`.

## 2026-06-13 - Startup renderer table builder `1010:0F0B`

The `1010:0F31/0F32/0F37` cold-start unknown hotspot cluster is not asset or
file-I/O logic.  It is the inner loop of the startup renderer coordinate/video
lookup-table builder at `1010:0F0B`.

The lifted hook `overkill_startup_coordinate_tables_0f0b` now lives in the
renderer module with the adjacent startup table helpers.  It fills the active
renderer data-segment table family at `DS:99C8..A077`, preserves the final
mode-dispatch register side effect (`BX = CS:[95BC] << 1`), and falls through to
the existing lifted `1010:0FA3` video-offset table builder rather than cloning
that logic.

Verification notes:

```text
snapshot_stop_1010_0f0b_startup_tables: interpreted ASM == lifted hook
continuation: 1010:526A
full CPU state match
full memory match
```

This closes those startup unknowns as renderer setup, not as another codec or
file loader.

## 2026-06-13 methodology codified

The repeated hook/debug/refactor pattern has now been codified in
`docs/source_port_methodology.md`.

The durable workflow is:

```text
observe -> classify -> choose boundary -> build ASM oracle -> implement hook -> verify -> document -> move to island
```

This reflects the current successful pattern used for asset codecs, file I/O,
Tandy rendering/setup tables, gameplay object behavior, and collision tails:
start with exact-address hooks in `replacements.py`, prove them against the
original ASM, then move stable behavior into a clear module under
`overkill_port/games/overkill/` while keeping only the address wrapper in
`replacements.py`.

This documentation pass also makes duplicate-code prevention explicit: before
lifting a new hook, search for existing helpers with the same original tail,
continuation IP, field offsets, or table addresses, and factor shared behavior
instead of cloning it.

### 2026-06-13 input/menu poller and ABxx collision helpers

- `1010:0162` is the full OVERKILL input poller. It checks `DS:[0010]`:
  - `1` selects the joystick branch and switches to resident segment `15BC`.
  - `2` selects the alternate keyboard control-map table at `DS:2146`.
  - all other values use the default keyboard table at `DS:213E`.
  The hot inner bit packer remains `1010:017E`, now shared through `pack_keyboard_poll_bits_017e`.

- `1010:D445` is a small input-driven selector/counter loop, not a renderer or
  collision leaf. It has two observed modes:
  - when `DS:[98E4] == 1`, it increments `DS:[BEDC]` and wraps that counter
    back to zero after the third tick;
  - otherwise it polls `0162` and updates `DS:[BEDA]` as a 2x3 selector grid
    using bits `1`, `2`, `4`, and `8` from `DS:[98BE]`.
  The fire bit `10h` exits only when `DS:[BEDA]` is nonzero.

- `1010:AC28` is a runtime-patched tile-collision probe used by ABxx object behaviours. It is not a standalone tile decoder; it composes already-lifted helpers:
  - `1010:5073` coordinate-to-tile index
  - `1010:505B` tile id lookup
  It returns clear for no collision, can jump to `AA44` when global gates disable processing, and sets object countdown/variant fields on collision.

- `1010:AB34` is a runtime-patched motion-table coordinate helper. It uses base object `DS:237C`, caller table base `DX`, and the base object's sprite/index at `+08` to write object coordinates to `SS:[BP+2]` and `SS:[BP+4]`.

- `1010:AB4F` is a small runtime-patched scroll/sprite helper that writes `DS:[233C]+18h` to `SS:[BP+8]`.

## 2026-06-13 source-port layer pyramid and bootstrap classification

The project now documents the higher-level migration model as a logic
crystallization pyramid: original binary oracle -> ASM-compatible runtime ->
verified lifted routines -> runtime object/data model -> game systems -> gameplay
archetypes -> semantic game model -> modern/enhanced port layer.

This matches the current object work: many objects are still best described as
slot records with sprite/layer/logic-id/movement/collision fields.  Names such as
player, projectile, pickup, boss, or specific enemy archetype should be promoted
only when multiple verified lower-level routines make the identity stable.

The cold-start `32FF:*` interpreted hotspot is now classified as `bootstrap` in
coverage.  It is the transient inner unpack/self-relocation stage already noted
at `32FF:0052`; it is intentionally not treated as a source-port game island and
should not be hooked merely to make the unknown count look smaller.

## 2026-06-13 unknown cleanup: game-state, timer, and shared video stubs

Newly clarified routines:

- `1010:5A6C` is a shared source-cell video-mode dispatch stub.  It does not
  belong to CGA/Tandy-specific renderers; it simply reads `CS:[95BC]`, indexes
  the source-cell dispatch table, and jumps to the mode-specific copy routine.
- `1010:AB10` is an object logic helper using a runtime-patched live byte shape.
  It updates object-slot sprite/table fields from `DS:[2336]`/`A40C` and can
  deactivate the slot through the `AC22` tail when global counters reach 3.
- `1010:AB77` is an observed object-behavior driver.  Its implementation is
  intentionally compositional: it calls the existing lifted `AB4F`, `AC28`, and
  `AC81/AC97` helpers rather than cloning their internals.
- `1F8F:0922` is a gameplay/frame counter tick, not asset decode. It reuses the
  existing `1F8F:0960` gameplay counter stride loop. Both belong to the
  `game_state` island despite `0960` living in an overlay segment.
- `1010:0672` and `1010:0679` form the timer flag clear/wait pair around
  `CS:[066B]`.  Both now live in the sound/timer island next to the IRQ0 model.
- `1010:511F` is called by all modes but only mutates page state when
  `CS:[95BC] == 1`.  Tandy execution reaching this hook is expected and not an
  EGA/CGA leakage bug.

Classified but not yet hooked:

- `1010:D007..D04C` is the main gameplay frame-loop dispatcher.  It composes
  timer clear/wait, video page stubs, object/layer scans, rendering, input poll,
  and game-state updates.  Do not hook it until more child calls are exhausted.
- `1010:A846/A85E/A876` are parent/setup glue around existing layer-sprite scan
  hooks.  Future hook work should compose the existing scan helpers.
- `1010:4CED..4D14` is a presence-list parent around three `4D15` calls.  Future
  hook work should call/reuse `4D15`, not duplicate its presence stamping loop.

## 2026-06-13 layer-sprite present parent cleanup

- `1010:A90C` is a layer-sprite present parent, not semantic object logic.  It
  composes the existing `A90F` and `A927` scans and then clears the presence list.
  The hook deliberately preserves partial continuations at the real `5A92` call
  sites instead of absorbing the present-object dispatch body.
- `1010:A93C` is only `CALL 4D64 ; RET`.
- `1010:4D64` is only setup for `4D6F`: load the visible/work segment into `ES`,
  set `SI=C7B1h`, set `CX=28h`, then tail into the shared clear loop.
- `1010:D04D..D072` is a per-frame game-state/UI frontier reached after the
  `D007` main-frame dispatcher.  It should stay classified until its child calls
  are understood; do not fold it into object semantics prematurely.

## 2026-06-13 next unknown cleanup: intro pacing, postmove prelude, loading scroll, counters

- `1010:96C5` is an intro/menu delay loop: `CALL 50C9 ; LOOP 96C5`.  It is not
  gameplay logic.  The lifted hook must call the installed `50C9` hook, not only
  the base retrace helper, because `play.py` wraps `50C9` as an interactive
  frame publish/yield boundary.
- `1010:96C8` is the `LOOP` tail used when execution resumes after that pacing
  boundary.  It decrements `CX` and jumps back to `96C5` or continues to `96CA`;
  it does not alter flags itself.
- `1010:BC45` is a tiny prelude before the shared `BC4B` postmove/collision
  chain.  It adds `DS:[A278]` into `SS:[BP+02]`, then falls through into `BC4B`.
  It should remain a composition wrapper, not a second copy of the BC4B chain.
- `1010:4E0D` is a Tandy loading-scroll parent around the existing `A781` step.
  The original pushes `DI`/`SI`, calls `A781`, restores them, then loops on
  `DS:[2350]` and `DS:[234E]`.  The call return scratch is `4E12`; using a
  later synthetic return address causes full-memory verifier mismatches.
- `1010:61CA` is the hot inner scan over word counters at `DS:2368..2372`.
  It decrements the first non-zero counter and returns.  `1010:61C5` is only the
  setup parent that initializes `DI=2368`; many observed gameplay callers enter
  the scan directly at `61CA`.

Classified but still frontier:

- `1010:9FEA` updates object/table coordinate state and flag bytes around
  `A39E/A39F`; it needs a direct oracle before being assigned to movement versus
  object-runtime.
- `1010:5EF9` appears text/nibble rendering related.
- `1010:4D95` should be treated as a presence-list parent candidate and should
  reuse `4D15` if lifted.
- `1010:780E` is a Tandy/layer draw sub-loop candidate.
- `1010:8A7E` is object-behavior frontier and should not receive semantic enemy
  names yet.

## 2026-06-13 leftover hook cleanup: 4CED and 5EF9

- `1010:4CED` is now lifted as a small layer-sprite/presence-list parent.  It
  composes the verified `4D15` stamper three times with the original call-site
  return scratch words (`4D01`, `4D0A`, `4D10`), then writes the final `FFFFh`
  sentinel at `DS:DI` and returns.  The hook deliberately does not duplicate the
  `4D15` stamping loop.
- `1010:5EF9` is now lifted as the two-nibble HUD/text helper.  It preserves the
  original `PUSH AX` / `CALL 5F06` scratch shape, calls the existing `5F06`
  nibble-to-text helper for the high nibble, restores `AX`, and then tail-calls
  `5F06` for the low nibble.

Remaining meaningful leftovers after this pass:

- `1010:A846` is still the larger layer-sprite scan parent around the existing
  `A849`, `A861`, `4CED`, `A87C`, `A894`, and `A8C7` pieces.  It is now more
  attractive, but should be lifted only as a composition parent that preserves
  partial child continuations.
- The hot `1010:B9F0..BAxx` object-family path remains interpreted; it should be
  investigated as object-runtime behavior, not renderer cleanup.
- The very hot `1010:9921/9926` loop is a wait/spin on byte globals, not an
  obvious source-port island hook.  Treat it as pacing/state investigation
  before replacing it.
