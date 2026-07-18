# Campaign: CPUless app unification (mirror `lemmings_port`)

> Opened 2026-07-18. **Equivalence tier: byte-exact** (the CPUless graph must reproduce the VM's
> DGROUP frame-for-frame, exactly as the demo-lockstep gate already proves for gameplay).
> **Reference implementation: `D:\Games\DOS\dos_recosystem\lemmings_port`** — it already reached the
> full-CPUless milestone; follow its structure, don't reinvent.

## The goal (owner, 2026-07-18)

`play_native` should be the ENTIRE game, CPUless: boot → title/menu → level load → gameplay → ending,
running with **no CPU carrier at runtime** (a hard import wall). The hand-recovered gameplay
(`native_frame.advance_gameplay_frame_97b2`) becomes a **native override**; the **generated CPUless
corpus fills every other gap** (boot, menu, front-end, transitions). One composed call graph:
`impl = manual_override.get(addr, generated[addr])`, generated is the DEFAULT, the manual override is a
drop-in at the SAME identity (kept honest by a differential test), never a separate carrier world.

This is the "app unification" open item. Today `play_native` runs gameplay natively but the front-end
stages are fail-loud GAPs (see `native_app.describe_gaps`). We fill them with lifted CPUless methods.

## ADR-2 — the override seam is COARSE (owner-confirmed 2026-07-18)

The manual readable port and the generated corpus are **two different decompositions**: the generated
corpus is keyed by machine address (`func_<cs>_<ip>`, shaped like the call graph); the manual code is
organized by GAME SEMANTICS (`native_frame`, `domain/`, `systems/`, object-record views) and verified
by whole-DGROUP frame lockstep, not per-function. Therefore **manual overrides land at clean ABI /
semantic boundaries, never per-machine-address**:

- the **gameplay frame boundary (`97B2`/`9B2E`) is the primary seam** — gameplay is ONE coarse manual
  override (`native_frame`), everything outside it (boot, menu, front-end, transitions) is generated;
- fine-grained `sys.modules` aliasing (lemmings `native/loader.py`) is reserved for hot LEAF functions
  (performance), not for re-expressing the semantic port as address chunks — doing that would re-shred
  the readable code and pit two decompositions against the same DGROUP.

**"Manual patches generated" = a readable REPLACEMENT that grows at coarse boundaries, with the
generated version retained as its differential oracle** (byte-exact drop-in; a changed observable is a
broken override). Every layer keeps a byte-exact oracle: generated vs VM (`verify_cpuless`), override
vs generated (drop-in differential), whole run vs VM (lockstep). Caveats kept honest: "generated fills
the gaps" = the PROMOTED gaps (frontier still fails loud); "cold boot" = from a data-only boot image
(VM-free), not necessarily re-running LZEXE natively.

## The blueprint (mapped from lemmings → overkill)

| lemmings | overkill | role |
|---|---|---|
| `lemmings/recovered/func_XXXX.py` (committed) | `overkill/cpuless_recovered/` (UN-IGNORE + commit) | generated CPUless corpus — the DEFAULT impls |
| `lemmings/native/overrides/` + `native/loader.py` | `overkill/native/overrides/` + `native/loader.py` | hand-written drop-in overrides, `sys.modules` aliased under the recovered name BEFORE the root import |
| `lemmings/runtime.py` | `overkill/cpuless_runtime.py` | game-specific platform wiring (video type from the command tail, boot keys, INT quirks) |
| `dos_re.lift.platform.CPUlessPlatformRuntime` | (same, from dos_re) | the device model host: `intr`/`inp`/`outp`, fail-loud on unimplemented |
| `scripts/play_cpuless.py` | `scripts/play_cpuless.py` | standalone runner: roots → recovered graph → platform, with a hard import guard |
| `scripts/build_vmless_boot_image.py` → `generated/vmless_boot/{state.json,memory_1mb.bin}` | `scripts/build_cpuless_boot_image.py` → `generated/cpuless_boot/` | the data-only boot image (historical mem + device state), EXE-free, generated once via the VM |
| `scripts/lint_cpuless_independence.py`, `check_cpuless_runtime.py` | same | STATIC import-graph wall + DYNAMIC no-carrier check |
| `tests/test_cpuless_standalone.py` | same | the gate |

**FORBIDDEN at runtime** (the import wall, from lemmings): `dos_re.cpu`, `dos_re.cpu386`,
`dos_re.lift.install`, `dos_re.lift.runtime`, `overkill/cpuless_adapters` (the CPU-ABI adapters stay
gitignored — they are verification shims, never runtime source), `dos_re.runtime`.

## The critical-path finding (the through-line)

The front-end/menu closure `1010:CC04` is **23 of 27 functions already CPUless**; it needs only a
**video** platform shim (INT 10h + video ports), and its ONLY blockers are `CC04`'s cascade on the
**three tail-dispatch functions** `CC4F`/`CCC4`/`CDA7`. So **the tail-dispatch capability (dos_re) is
the exact unblock for a fully-CPUless native menu.** Boot bootstrap `254A:04D7` is 2 fns (INT 21h).
`level_select D390` is 70/77 CPUless but needs DOS file-I/O (INT 21h ×14, 13h, 67h).

## Slices (ordered; one verified commit each)

1. **[DONE 2026-07-18, e5fed92] Foundation** — un-ignored + committed `overkill/cpuless_recovered/`
   (561 fns, walls HOLD) + README + this campaign doc. The runtime-source substrate.
2. **Runner skeleton** — *2a [DONE 2026-07-18, 0ded6f3]:* `overkill/cpuless_host.py` —
   `run_recovered(key, mem, plat)` imports the committed corpus + runs the composed graph;
   `FailLoudPlatform`; `load_recovered` fail-loud on the frontier. Gated by `tests/test_cpuless_host.py`
   (corpus is a closed importable package; composition over a flat image; fail-loud). *2b [next]:*
   `scripts/play_cpuless.py` (the import-guard wall + main loop) + `scripts/build_cpuless_boot_image.py`
   (data-only boot image) + `overkill/native/loader.py`; boot a tiny root standalone, byte-exact vs VM.
3. **Video platform shim** — `CPUlessPlatformRuntime` video (INT 10h + ports) on the host framebuffer.
4. **Tail-dispatch capability (dos_re)** — unblock `CC4F/CCC4/CDA7/CC04`; menu closure → 100% CPUless.
5. **Wire the menu** — boot → title/menu in a native window.
6. **DOS file-I/O shim + `D390`** — new-game → level load.
7. **Gameplay as a native override** — express `native_frame` at the frame root; compose. → full game.
8. **Walls green + retire** — static+dynamic no-carrier checks pass on the whole run.

## Front-end platform surface (SCOPED 2026-07-18, ready for the video-shim slice)

The `CC04` menu closure's exact platform surface (from the committed recovered modules):
- **INT 10h AH=0Bh** (set CGA palette; `4F57` calls it with `BH=01, BL=00`). Its full register return
  is CONSUMED downstream, so the shim must be VM-FAITHFUL, not a no-op. dos_re's handler is
  `dos.py:int10` (the `ah == 0x0B` branch = palette/DAC control).
- **CGA/Tandy port writes** `0x3D8` (mode control), `0x3D9` (color select), + a computed port in the
  `0x3D0–0x3DF` block. WRITE-ONLY registers — no DGROUP effect (the host renderer owns the display),
  so the shim RECORDS them for the renderer.
- **`in 0x3DA`** retrace polling (the front-end paces on it, not the timer) — a wait-loop input.

**Verification approach (mandatory — this repo's bar is verified slices):** a faithful shim cannot CALL
dos_re's BIOS (that is the carrier). It must PORT the behavior carrier-free and verify byte-exact
against dos_re's `int10`/port handling as an OFFLINE ORACLE. So the first video-shim slice is a harness
that runs a promoted front-end fn (e.g. `4F57`) BOTH via the VM oracle and via `run_recovered` +
`OverkillPlatform`, and diffs — then `OverkillPlatform` (a carrier-free `FailLoudPlatform` subclass in
`cpuless_runtime.py`) is grown to make it pass, one INT/port at a time. NOTE: the retrace `in 0x3DA` is
front-end tier = SCREEN-EXACT (a retrace-ready toggle is faithful enough); the INT 10h palette return is
what must be byte-faithful.

## next — the FRONT-END (the remaining half; gameplay is done + playable standalone)

The standalone runner PLAYS gameplay carrier-free (`scripts/play_cpuless.py`). The remaining work is
boot → title/menu → level-load, which converges on two enablers (neither a quick win, both needed for a
visible native menu):
- (a) ▶ **IN PROGRESS — the video platform shim**: `OverkillPlatform` has the CGA/Tandy ports + INT 10h
  AH=0Bh (oracle-verified). Grow it (more INT 10h AH values / INT 16h) as running the menu reveals what
  it reaches — each one ported byte-faithfully against the dos_re `int10` oracle.
- (b) ✅ **DONE (2026-07-18)** — the **tail-dispatch capability** (contributed to dos_re): `CC04` and all
  its blockers `CC4F/CCC4/CDA7` are now promoted; the menu closure is fully CPUless.
**RAN `CC04` standalone (2026-07-18)** over the boot image via `run_recovered + OverkillPlatform` under
the wall. It got past the platform (no video effect reached yet) and failed loud on the NEXT precise
blocker:

> `UnknownDispatchTarget: dynamic dispatch to dyn 1010:CCC4: no recovered implementation`

**Diagnosis — the frameless arms are promoted but NOT DISPATCHABLE.** `tools/cpuless_promote.py` (~line
636) excludes a callee from the DISPATCH registry when `c.sp_output` (`reason = "sp-output" # needs sp
threading`); the frameless tail-dispatch arms are precisely `sp_output=True` by construction, so they
never enter the registry and `_dyn` cannot resolve them. Note the asymmetry: the HANDLERS (IRET) path
immediately above DOES admit sp-varying functions ("the invoking site pops the frame at the MERGED
runtime sp, so even an sp-varying ISR is exact") — and `dyn_exec` already merges the callee's outputs,
so sp threading does work mechanically.

**RESOLVED (2026-07-18, dos_re `2679213`).** Investigation showed sp threading ALREADY exists end to
end — the emitted dyn site passes `sp` into the bundle, `dyn_exec` merges the callee's outputs over it,
and the site reads `sp = _do['sp']` back — so an `sp_output` callee is precisely the case where sp IS
communicated. The exclusion was stale, not protective. The rule is now stated as the property it
actually is: **eligible iff the callee's sp effect is COMMUNICATED** — zero, or returned via
`sp_output`; still excluded when `sp_delta != 0 and not sp_output` (shifts sp without returning it, so
`merged['sp']` is the stale input) or `ret_pop` / non-near `ret_kind`. Applied to promoted functions and
overrides alike. No regressions (L1 48 PASS/0 DIVERGED, wall holds, dos_re 707).

### NEXT FINDING: a tail-dispatch LOOP recurses (composition models a tail JMP as a nested call)

With the arms dispatchable, `CC04` runs further and now hits **`RecursionError`**: `func_1010_ccc4` ↔
`func_1010_cda7` mutually recurse (~37 frames each). They are alternate entries into the SAME shared
CGA/Tandy blitter that tail-jump to each other.

**Root cause is structural, and PRE-EXISTS this work** (it applies to the framed variant equally — the
frameless capability only made more such functions reachable): a machine `jmp` is a TAIL transfer that
REUSES the frame (iteration), but the composed model emits it as a nested `_dyn` CALL, so a tail-dispatch
loop grows the Python stack instead of iterating. Proper handling needs a **trampoline**: a tail dispatch
should return a "continue at X" signal that the dispatcher's own loop re-enters, rather than nesting.

**DIAGNOSED (2026-07-18) — it is a GENUINE loop, not a state artifact.** Instrumented `dyn_exec` and
traced 173 dispatches before the limit: **all 173 register bundles are DISTINCT**, `cx` counts down
(15 → 14 …) and `sp` drifts — the state advances every hop. So it is real iteration (a blitter looping
over rows), and the composition is what breaks, not the input state.

**ROOT CAUSE, precisely:** `CCC4`'s dispatch site `CC9E` resolves to **`1010:CCC4` — its own entry**.
The routine re-enters itself through a computed `jmp`; on the machine that is a LOOP (the frame is
reused), but the emitter models every dyn transfer as a NESTED `_dyn` CALL, so it recurses. Confirmed
internal: `CC9E → CCC4` has `INTERNAL=True` against CCC4's own scanned instruction set.

### THE FIX — internal dispatch becomes a BLOCK GOTO (not a trampoline)

> A dyn tail dispatch whose observed targets ALL lie within the function's own scanned instruction set
> is INTERNAL control flow: emit a computed block goto (`bb = <target block>; continue`) instead of a
> nested `_dyn` call, with a fail-loud `else` for any unobserved target.

The emitter ALREADY emits each function as a block state machine (`bb = N; continue`) and already
computes the runtime target (`_dt`); it simply never uses that path for COMPUTED jumps — even `4E26`'s
purely intra-function goto currently round-trips through `_dyn`. Why this beats a trampoline:
semantically exact (a jmp inside the routine IS a goto — modelling it as a call was the error); zero
stack growth so internal loops iterate freely; NO ABI/contract/caller changes (a trampoline needs a tail
token threaded through every call site); generic across ports; fail-loud preserved.
*Implementation subtlety:* the target must be a BLOCK HEAD for `bb = idx`, so the emitter must SPLIT a
block when a dispatch lands mid-block (usually already a CFG boundary, but must be enforced).

*Scope:* this fixes the self-loop and all intra-routine cases. `CCC4 ↔ CDA7` cross-dispatch is NOT
internal to either scan (overlapping-but-distinct scans sharing 49 of CDA7's 62 instructions) — if
recursion persists after the fix, the follow-on is to treat such overlapping scans as ONE routine with
ALTERNATE ENTRIES, for which the DISPATCH tuple already carries an `_entry_ip` slot.

Then wire it into `play_cpuless`, composing generated front-end + the native gameplay override.
- SCOPING: do NOT run the boot bootstrap `254A:04D7` standalone (11 INT 21h C-startup calls — the boot
  image bypasses exactly that DOS surface).
- later: `overkill/native/loader.py` (fine sys.modules aliasing for hot-leaf overrides, per ADR-2).

## Status log (newest first)
- **2026-07-18** **MENU UNBLOCKED (4027159 + dos_re f771908):** contributed the **FRAMELESS stack-arg
  TAIL DISPATCH** capability to dos_re — the dispatcher pushes args and tail-jumps with no bp frame, so
  the framed-switch capability refused it; it now composes via a **runtime sp output** (the arm, resolved
  through `_dyn`, returns its actual sp). **561→591/626 promotable (+30); the tail-dispatch frontier is
  ELIMINATED (16→0); cascade 33→19. ALL menu functions promoted — `CC4F/CCC4/CDA7` and `CC04` (the menu
  loop itself)**, plus nested `5827/587E` and intra-function gotos `4E26/AEBF`. 30 new corpus modules,
  ZERO existing changed (purely additive). Walls HOLD; suite 1433.
  *Verification, honestly:* the capability is proven BYTE-FOR-BYTE vs the interpreter by a synthetic
  differential in dos_re; no regressions (L1 48 PASS/0 DIVERGED, cold-start 54 PASS/0 DIVERGED); but the
  30 newly-promoted fns are **not yet demo-verified at real states** — no demo reaches the menu blitters,
  so they get their byte-exact proof once the menu actually runs.
  *Also arrived upstream:* a dos_re **CPUless OVERRIDE mechanism** (`tests/test_cpuless_override.py`,
  `tools/cpuless_promote.py`) — directly relevant to ADR-2's manual-override half; evaluate it before
  hand-rolling `overkill/native/loader.py`.
- **2026-07-18** dos_re bumped 14fafab→6825851 (a3a9e58): FRAMED tail-dispatch + retf-N + leave-fusion +
  capture↔close fixpoint; corpus regenerated (243 modules), walls HOLD, suites green. **Did NOT unblock
  the menu:** OVERKILL's tail-dispatch fns are the FRAMELESS stack-arg variant (no bp frame), which the
  FRAMED capability correctly refuses. The frameless variant needs ARM COMPOSITION (resolve each arm
  from dyn-evidence, prove it pops the pushed d bytes before ret) — deeper than the arm-agnostic framed
  case. **Menu fork: (a) contribute frameless tail-dispatch to dos_re (generic, deep; coordinate — dos_re
  is active here, `abi-recovered` branch), or (b) native overrides for the 3 menu blitters CC4F/CCC4/CDA7
  (per ADR-2, fine-grained; but these are the CGA/Tandy blitters the native port replaces anyway).**
- **2026-07-18** slice 3b DONE (e3e36a2): `OverkillPlatform.intr(INT 10h AH=0Bh)` ported + verified
  BYTE-FAITHFUL against the dos_re `int10` oracle (a no-op there; the colour goes via the 3D9h port);
  unported AH values fail loud. Reusable oracle harness (`test_overkill_platform_int10.py`) grows the
  platform one INT/AH at a time. **Demonstrated:** the front-end fn `4F57` (closure = 2 fns, both
  promoted, only INT 10h) now RUNS STANDALONE under the wall via `run_recovered + OverkillPlatform`,
  carrier-free — the first generated FRONT-END code in the standalone runtime. (It took a trivial path
  with synthetic zero regs; exercising the real video branch + a byte-exact vs-VM diff needs 4F57's
  captured entry state from a live front-end call — next.)
- **2026-07-18** slice 3a DONE (12a88a9): started the device model — `OverkillPlatform` (video-port
  half: CGA/Tandy write-only registers recorded, 3DAh retrace toggle; INT 10h + rest fail loud) + the
  front-end platform surface SCOPED. `tests/test_overkill_platform.py` (3). **next slice 3b: the INT 10h
  AH=0Bh byte-faithful port + a VM-oracle diff harness (run `4F57` via VM vs run_recovered+platform).**
- **2026-07-18** slice 2b-2 DONE (e152d54): **`scripts/play_cpuless.py` — the standalone runner PLAYS
  gameplay** carrier-free with the wall armed (`--frames 5` renders 5 frames, exit 0, zero carrier).
  Thin wall-armed wrapper over play_native (proven carrier-free). `tests/test_play_cpuless.py`
  (artifact-gated subprocess). GAMEPLAY HALF DONE; remaining = front-end.
- **2026-07-18** slice 2b-1b DONE (f2a1cbb): **gameplay EXECUTES carrier-free** — 5 real
  `advance_gameplay_frame_97b2` frames over a demo image under the armed wall, zero carrier modules.
  The unified CPUless runtime PLAYS with no interpreter. `overkill/cpuless_runtime.py` holds the
  carrier-free host inputs (`level_assets_for` via pure `asset_codecs`; the probe's copy was entangled
  with the VM import). Gameplay stage is artifact-gated (skips without game data).
- **2026-07-18** slice 2b-1 DONE (f22e9f6): the import WALL — `install_import_guard()` +
  `scripts/check_cpuless_wall.py` (dynamic subprocess) prove BOTH the manual gameplay layer and the
  generated corpus run carrier-free; ADR-2 (coarse override seam) recorded. `tests/test_cpuless_wall.py`
  (4 pass).
- **2026-07-18** slice 2a DONE (0ded6f3): `overkill/cpuless_host.py` `run_recovered` runs the committed
  corpus over a flat image (frame clock proven); `tests/test_cpuless_host.py` gates completeness +
  composition + fail-loud (5 pass).
- **2026-07-18** slice 1 DONE (e5fed92): corpus committed as runtime source; campaign opened; blueprint
  mapped from lemmings; corpus regenerated (561/626, walls HOLD).

## 2026-07-18 — THE MENU LOOP RUNS AND RENDERS, CPUless

`1010:CC04` (the front-end/menu loop) now **runs to completion standalone** under the armed wall via
`run_recovered + OverkillPlatform`, and **writes 494 blocks into video memory (0xB8000)** — it draws
the menu. Carrier-free throughout; no platform effect was even reached (the drawing is direct video-
memory writes, which is why the port shim saw nothing).

The unblock was `cpuless_host.run_deep()`: the cross-function tail-dispatch cycle
(`312D→30B4→3103→306F→CCC4→CDA7`) is emitted as nested `_dyn` calls, so a BOUNDED blit loop grew the
Python stack. Running it on a 64MB-stack thread with a raised recursion limit completes it. **This is a
deliberate RUNTIME ACCOMMODATION, not the fix** — the correct repair remains: intra-routine dispatch as
a block goto (landed upstream as `_LOCAL`/arm absorption) plus a TRAMPOLINE for cross-routine tail
cycles. Recorded so it is never mistaken for a solution.

**Next:** present that rendered video memory through play_native's renderer to get a VISIBLE native
menu, then drive input into it.

## 2026-07-18 — `play_cpuless --menu`: the CPUless FRONT-END is on screen

`scripts/play_cpuless.py --menu` runs the front-end root `1010:CC04` from the GENERATED corpus over the
data-only boot image under the armed wall, then presents what it drew into B800 through the native Tandy
renderer (`decode_tandy_b800_indices` -> `PygameDisplay`). 18556 lit pixels, no CPU, no interpreter.
Gated by `tests/test_play_cpuless_menu.py` (headless, artifact-gated on the boot image).

**Both halves of the unification now RUN:** gameplay via the manual override (`--frames`), the front-end
via the generated corpus (`--menu`). What remains to join them into one cold-booting app: drive INPUT
into the menu (it currently runs to completion and returns rather than waiting on keys), then follow the
menu's own exit into level-load + gameplay.

## 2026-07-18 — the CPUless front-end is INTERACTIVE

`--menu` now feeds the host keyboard into the image's OWN INT9 key-state table (`DS:0x98C4 + scancode`,
1 = pressed) — the same table the gameplay runner writes, and the one the recovered front-end polls, so
this is real input rather than a side channel. Measured response (all CPUless, no carrier):

| key | ax | bx | lit px | screen |
|---|---|---|---|---|
| none / Esc / Enter / '1' / 'p' / 'i' | 0x0009 | 0x0019 | 18556 | idle baseline |
| **Space** (select/fire) | **0x0000** | 0x0004 | 16827 | **DIFFERS** |

So the menu genuinely acts on Space and reports a selection (`ax` 9 → 0); `run_menu` exits on that and
names level-load as the next stage.

**Remaining for one cold-booting app — the JOIN:** follow that selection into `D390` level-select /
level-load (needs the DOS file-I/O shim: INT 21h ×14, 13h, 67h) and hand off to the gameplay override.

## 2026-07-18 — THE JOIN: front-end → selection → gameplay, in one CPUless process

`play_cpuless.py --menu --play` now runs the whole chain:

```
[cpuless] front-end 1010:CC04 drew 18556 lit pixels -- NO CPU, NO interpreter
[cpuless] front-end SELECTED (ax=0, bx=0x0004) -- level 1, difficulty 1
[cpuless] -> handing off to the gameplay half (manual override)
native: cold level 1 -- planet 1, difficulty 0, lives 3 ... no VM
--frames self-test: 60 gameplay frames, 60 drawn
```

boot image → **generated front-end** → selection → **manual gameplay override**, all under the armed
wall. Gated by `tests/test_play_cpuless_menu.py::test_cpuless_chain_menu_to_gameplay`.

**Design note (ADR-2 in action):** level-load is deliberately the MANUAL side — play_native cold-starts
a level from the decoded container with NO INT 21h. The generated `D390` level-select would additionally
need the DOS file-I/O shim (INT 21h ×23, 67h ×3, 13h) *and* the `065C` sp-as-data capability, and it
buys nothing while a verified manual level-start exists. This is exactly "the generated corpus fills
what we lack manual code for".

### What still separates this from a true COLD boot
1. The front-end starts from a **data-only boot image** (post-C-startup). A from-EXE boot would need the
   DOS surface that image bypasses (`254A:04D7` = 11 INT 21h C-startup calls).
2. The menu's action code (`bx`) is not yet decoded into its branches (start / instructions / ordering /
   attract) — we act on "a selection happened", not on WHICH.
3. `run_deep` is still a runtime accommodation for cross-routine tail cycles, not the trampoline fix.

## 2026-07-18 — CORRECTION + a real cross-validation

**Correction.** The previous entry claimed the front-end "SELECTED" a level on `ax=0`. That was wrong,
and the repo's own front-end analysis caught it: run_status 2026-07-13 records the CC04 loop as
*compose grid (CE97) → recipe reveal (CE5F+CC4F ×3) → repeat*, with **"nz 16827 at +5 == the VM's early
frame"** — exactly the pixel count attributed to a "selection". Verified directly: the `ax=0` frame is
**byte-identical to `compose_blueprint(mem, 5)`**, the blueprint intro at 5 cells revealed. It is a
FIRE-key break out of the attract/blueprint cycle, not a decoded menu choice. The level/difficulty
printed alongside it were the image's boot defaults (`0xBEDA`/`0xBEDC` are never written by the loop).
`play_cpuless` now says what is actually true, and the chain test asserts the corrected wording.

**The real result this uncovered — an independent CROSS-VALIDATION.** Two recoveries that share no code
agree byte-for-byte on the same screen:
- the GENERATED corpus (`1010:CC04` under the CPUless wall, drawing into B800), and
- the HAND-RECOVERED composer (`native_video.blueprint.compose_blueprint`, reading the game's own
  `DS:BD54` recipe, separately verified against the VM with zero under-draw).

That is evidence for BOTH directions at once: the lifted front-end reproduces what the VM draws, and the
manual composer models the same machine behaviour. Gated by
`tests/test_cpuless_frontend_matches_native.py`.

**Still open (unchanged):** the menu's `bx` branch codes are undecoded, so we act on "the loop exited",
not on WHICH menu action; level-load remains the manual side; `run_deep` remains an accommodation.

## 2026-07-18 — FINDING: the env-wait frontier is not wired into our pipeline

Investigating why the front-end loop is IDEMPOTENT (same frame + same ax/bx every iteration; no tick we
tried — `DS:2324`, the 5F61 frame clock, the BIOS tick `0040:006C` — advances it) surfaced a correctness
problem that matters more than the animation:

**`1010:0679` and `1010:50C9` are PROMOTED into the committed corpus, although
`artifacts/lift_keep_interpreted.txt` declares them the ENV-WAIT FRONTIER** — async spin-waits
(`0679` = the gameplay frame timer wait; `50C9` = the front-end CRT retrace wait) where the recorded
recovery fact says a plain lift *"freezes an iteration count that is really timing-dependent -- liftverify
proves it DIVERGES against the interpreted oracle (2026-07-17e: 1010:0679 flagged DIVERGED)"*.
`scripts/probe_vmless_cpuless.py` passes `--boundary-heads` but **never passes the keep-interpreted
facts**, so the declared frontier is silently lifted. Neither function appears in the demo differential,
so our gates never verified them either.

The promoter already has the prescribed mechanism: `--boundary-heads` (tier 13) turns the head into an
emitted `plat.boundary` observer — exactly what the env-wait note asks for ("modelled as an explicit
scheduler-yield boundary in the standalone runtime").

**Measured cost of applying it naively** (both addresses appended to the boundary-head facts):
promotable **591 → 568 (−23)**, `contains-call` cascade **19 → 41**, `50C9` correctly becomes a boundary
— but **`0679` stays promoted** (the head likely has to be the inner spin site, not the entry). So it
half-fixes the problem while costing real coverage, and to be coherent the standalone runtime must also
IMPLEMENT `plat.boundary` (advance the host's time base and resume), which does not exist yet.

**Deliberately NOT applied** — reverted to 591/626. This is a proper slice, not a one-line flag:
1. implement `plat.boundary` in `OverkillPlatform` (the scheduler yield: advance the tick/retrace, resume);
2. declare the env-wait heads at the correct sites (verify `0679` actually leaves the promoted set);
3. re-verify the differential + the demo lockstep, then accept the coverage change knowingly.

This is also the likely reason the front-end cannot animate: its pacing wait is a frozen lift rather
than a yield the host services.

## 2026-07-18 — VERIFICATION COVERAGE measured: 16.2% of the promoted corpus is proven

New standing mechanism (`verify_cpuless.py --ledger` + `scripts/cpuless_verification_coverage.py`).
Promotion is STRUCTURAL; correctness is a per-function differential that only reaches what a demo runs.
Unioned over both demo ledgers:

| | |
|---|---|
| promoted | 591 |
| verified PASS (byte-exact, real states) | **96** |
| DIVERGED | 0 |
| INCONCLUSIVE | 18 |
| **NEVER EXERCISED** | **477** |
| **proven fraction** | **16.2%** |

One ledger alone reads 8.1%; adding the second demo doubled it. **So the lever on the unproven surface
is DEMO BREADTH, not more promotion** — every new promotion without a demo that reaches it grows the
unproven surface rather than shrinking it. This is the figure to quote for correctness; "591/626
promoted, walls HOLD" is a structural claim and says nothing about these 477.

### CORRECTION (2026-07-18m) — the `--observed` regression is NOT a coverage shortfall

The 18k entry above explained the `--observed` regression as thin coverage and predicted that
unioning demos would fix it. **Measured, and the prediction was wrong.** Adding the attract demo
(11257 boundaries, the single biggest contributor at +539 addresses) and a gameplay demo took address
coverage from 36% to 59% — and produced a **byte-identical census**:

| evidence | coverage | promotable | contains-call |
|---|---|---|---|
| none | — | 591 | 20 |
| spine demo | 36% | 571 | 40 |
| spine + attract + gameplay | **59%** | **571** | **40** |

**The real mechanism: dead-exit marking is SUBTRACTIVE.** 168 functions have EVERY `ret` unexecuted
across the union, so each loses its exit ABI. Where a function's only live exit is a platform effect
that is the intended win — but where the marking removes ABI a caller depended on, the caller refuses
`contains-call` and the loss cascades. Net **20 lost, 0 gained**, and every one of the 20 refused
TRANSITIVELY: `D007` (the attract machine) and `CBE8` (the front end) are among them despite their own
entry and return both demonstrably executing, and their own would-be stub-target lists being empty.

More demos of the same kind cannot repair it: the `1F8F` sound-driver segment shows only **18**
executed addresses across all three recordings, so its functions stay all-exits-dead regardless of how
much gameplay is recorded.

So `--observed` stays out of the pipeline for a sharper reason than "not enough demos": a dead exit
must not be able to strip an ABI that a LIVE caller still depends on. That is the fix, and it is a
dos_re-level change, not a coverage exercise.

**Kept as negative evidence, deliberately:** the falsified hypothesis is recorded in the tool's own
module docstring next to the numbers that killed it, because "union more demos" is the obvious next
move and someone will otherwise spend a day on it. This is the second time this campaign that a
plausible coverage story survived one measurement and died on the second — the first being the
promotion count that looked like progress while growing the UNPROVEN surface.


## 2026-07-18n — THE STITCH WAS UNSOUND: both skyroads bypass paths were present here

Owner relayed skyroads_port's hard-won pitfalls. The first one describes `overkill/cpuless_overrides.py`
exactly, so it was checked rather than assumed — and **both bypasses were real in the code shipped
earlier this session**. Two failing tests were written first, then the fix.

| bypass | why the shadow misses it |
|---|---|
| a caller that ALREADY imported the callee | `from ...func_1010_0679 import func_1010_0679` binds a DIRECT reference; a later `sys.modules` shadow cannot reach it |
| a WARMED dynamic-dispatch cache | `_dyncall._cache` memoizes `(kind, key) -> callable` on first use, so indirect transfers keep serving the generated body |

Both are SILENT — the override simply never runs and nothing reports it, which is the worst failure
mode a verification seam can have. The old tests passed only because they imported the corpus AFTER
installing, i.e. they tested the favourable order and nothing else.

Fixed: `install_overrides` now retro-patches every already-imported corpus module holding the name,
and clears `_dyncall`'s cache; `uninstall_overrides` restores the retro-patched bindings (otherwise a
torn-down override lives on in the callers it was patched into). Tests assert installation-order
independence in both directions. Suite 1454.

**A bug the fix itself introduced, caught by an existing test:** the first retro-patch was too broad
and rebound the ORACLE copy (`...__generated`, the alias `generated()` loads so an override can
delegate to the autolifted body). That would have made the differential compare the override against
ITSELF while still passing. `test_generated_stays_reachable_as_its_own_oracle` caught it immediately —
a good argument for keeping the oracle assertion even though it looks tautological.

**The module docstring carried a now-false claim** ("dynamic transfers ... the same shadow serves those
too -- no separate patch needed") and has been corrected in place, with the skyroads provenance noted.

### The other pitfalls, checked against this port

* **"Do not trust function-entry counters"** — never built any here; the equivalent trap was
  `--observed`, where a plausible coverage story survived one measurement and died on the second
  (2026-07-18m). Same lesson, different instrument.
* **"Virtual time is part of the contract"** — already the recorded blocker on any island: the
  measured-cost requirement is why no `C679`/`5559` body was written, and the `island` virtual-time
  kind is documented as NOT gate-admissible.
* **"Compare only observable outputs"** — the `1010:0679` override delegates to the generated body
  precisely so the returned flags/cost are the generated ones and cannot drift into a private notion
  of "result".
* **"Attach replacements only at real joints"** — matches the measured result that four correct
  islands promote MORE than ten (2026-07-18g), and that host-created flow (`--no-title`, `--level`,
  the `_run_title_menu` loops) is FLOW the skeleton supersedes rather than something to re-sew.
* **"A passing local island is not proof of the whole path"** — the standing claim here stays narrow:
  the boot root runs on `DOSMachine` for THIS image; the cold-start differential over the two spine
  demos remains the authority and has NOT been run, because `96C8` is still unpromoted.


## 2026-07-18l — the ATTRACT demo, and the NON-LOCAL-EXIT design (ready to implement)

Owner supplied a second spine demo, `artifacts/demos/demo_play_tandy_20260718_135013`: **11257
boundaries, ZERO events** — a do-nothing run from the same `1010:58F4` start, waiting through the grid
intro and the gameplay demonstration until the attract cycle looped back. It covers exactly what the
first spine demo SKIPPED (that one pressed SPACE at b=466), so the two are complementary and together
they are the cold-start path end to end. Union trace running.

### The non-local-exit capability — where it goes in `emit_cpuless`, and the precedent to mirror

The frontier (`065C` refused `sp-as-data`, blocking `96C8` = the game's top level) is a C-runtime
fatal-abort longjmp. `emit_cpuless` ALREADY has the right shape for this in its RUNTIME-DEAD EXIT
handling, which is the model to copy: a dead exit is *terminal but constrains nothing*, emitting
`raise RuntimeError('CPUless: runtime-dead exit ... reached -- frontier witness')` instead of a return.
A longjmp is the same idea with a real cause — it IS terminal for this function, and its "return" goes
to another stack, so it must not constrain this function's exit ABI either.

Four sites, all located this pass:

1. **Recognizer** — add `_is_nonlocal_exit(scan, i)` next to `_is_bootstrap_ss_switch` (~line 1396),
   written just as tightly: `mov sp, m16` (op `0x8B`, reg field = 4, modrm = memory) where every
   forward path reaches a `ret`/`retf` with no intervening push/pop/call. Tight recognition is the
   whole point of the precedent — it must not admit an arbitrary SP write elsewhere in the program.
2. **Refusal** — in the instruction scan (~line 1053), `continue` instead of
   `raise Refusal("sp-as-data")` when the recognizer fires, collecting the IPs.
3. **Exit ABI** — in `_check_stack_depths` (~line 1508), treat a `ret` reached only via a non-local
   exit exactly like `i.ip in dead_exits`: `continue`, recording no exit depth or `ret_pop`.
4. **Emission** — in the block emitter (~line 2000), intercept the recognized instruction and emit a
   structured `NonLocalExit` raise, terminating the block (mirroring the dead-exit branch).

The raise is not a cop-out: a longjmp really is a non-local transfer, and a Python exception is its
natural model — it unwinds the interpreter stack the same way the original unwinds the machine stack.
The recovered program root (or a future setjmp site) catches it. This is general: every DOS C runtime
has a fatal-error path of this shape, so it is a dos_re capability, not an OVERKILL patch.

**Deliberately not started at the end of a long session** — it is a four-site change in a 2000-line
emitter, and a half-applied edit there is worse than none. The sites and the precedent are recorded
so the next pass implements directly rather than re-deriving.


## 2026-07-18k — THE SPINE DEMO + a NEGATIVE result: `--observed` on one demo REGRESSES promotion

Owner supplied the spine demo `artifacts/demos/demo_play_tandy_20260718_134524` — recording started at
the first visible frame, then intro -> menu -> level select -> first level. 946 boundaries, 24 events.
Its start state is `CS:IP = 1010:58F4`, which is exactly the ground-truth timeline's "boot + intro
setup" address, and the event list reads as the spine: SPACE at b=466 (skip attract), `m` x4 at
b=602..644 (menu), SPACE at b=651 (select), ENTER at b=717, SPACE at b=750/871. This is the
authoritative path the CPUless build has to reproduce.

**New instrument: `scripts/capture_observed_trace.py`.** Replays a demo through the pure-VM oracle and
records which addresses actually execute, for `cpuless_promote --observed` (a never-executed near CALL
becomes a fail-loud stub; a never-executed `ret` becomes a DEAD EXIT that does not constrain the exit
ABI). It TRAPS only the addresses `--observed` can act on — every function entry and every return site
— because the schema never asks about anything else; a full per-instruction callback over a spine demo
would be tens of millions of Python calls for the same information.

Spine demo: `FRAME VERIFY OK frames=951`, **425 of 1192 trapped addresses executed (36%)**.

**FOURTH unwired capability — and this one is unwired for a REASON.** `probe_vmless_cpuless.py` passes
`--observed` to no stage (its two mentions are comments). Measured before wiring it, on a scratch
census, and it made things WORSE:

| | promotable | contains-call |
|---|---|---|
| today (no `--observed`) | 591 | 20 |
| `--observed` = spine demo alone | **571** | **40** |

At 36% address coverage, a single demo marks far too much as dead: a path this demo skipped is NOT a
dead path. This is the "demo breadth is the lever" lesson from 2026-07-18 resurfacing in a new place —
and it is the reason to measure a capability on scratch before wiring it into the pipeline, rather
than assuming an unpassed flag is simply an oversight. Three unwired capabilities this campaign were
real bugs (`--boundary-heads` facts, the corrupting probe, `--desmc`); the fourth is a trap.

The tool therefore takes `--demo` REPEATABLY and unions the evidence, with the measured regression
recorded in its own `--help` so nobody wires it up from a single demo. `--observed` stays OUT of the
pipeline until the union covers enough of the corpus to justify it.

**Frontier unchanged and still ordered:** `1010:96C8` (the game's top level) has no recovered module;
its chain bottoms out at `1010:065C` refused `sp-as-data`, the C-runtime fatal-abort longjmp
(`mov sp, cs:[0242]` then `ret`, returning on the restored stack). `--observed` was investigated as a
possible way to make that abort path a dead exit instead of a refusal; the instruction-level
`sp-as-data` check runs BEFORE the dead-exit logic, so dead-path evidence alone would not clear it
regardless. The general dos_re fix (model the non-local exit as a structured exception, or skip ABI
checks on provably-dead paths) remains the next capability slice.


## 2026-07-18j — FRONTIER 1 CLEARED: the boot root RUNS. Frontier 2 = a longjmp the lifter can't model

Cold-boot forward, second iteration. Frontier 1 was `INT 21h AH=3Dh` (open file) at
`func_254a_04d7.py:78`. **Repaired by DELETING port code, not writing any:** swapped the hand-rolled
`OverkillPlatform` for the framework's `dos_re.lift.platform.CPUlessPlatformRuntime`, which owns a
`DOSMachine` (pure hardware, no instruction execution) and services INT 21h/10h and ports over the
game's own files.

    BOOT ROOT RAN TO COMPLETION: {'ax': 2, 'bx': 5, 'ds': 0x254A, ...}

`bx = 5` is the DOS file handle — dos_re's lowest-free-handle allocator, the exact detail its source
documents as learned from a real per-handle-table overrun. Not one line of INT 21h was written in the
port. This is the standing rule paying out twice in two passes: first "fewer islands promote more",
now "the general machinery already had it".

**Frontier 2, in execution order:** `1010:96C8` — the game's top level — has no recovered module. Its
blocker chain bottoms out at `1010:065C`, refused **`sp-as-data`**. Decoded:

    065C: mov bx, cs:[0240]    ; the file handle
          mov ah, 3Eh          ; DOS CLOSE FILE
          int 21h
          jnb 066A             ; ok -> ret
          jmp 02B2             ; error -> the abort path
    02B2: push ax / call 065C / pop ax
          mov bx, 25CC / mov ds, bx      ; restore the data segment
          mov sp, cs:[0242]              ; <-- RESTORE A SAVED STACK POINTER
          stc
          ret                            ; returns on the RESTORED stack

That is a **C-runtime fatal-abort longjmp**: on a DOS error it unwinds to a stack pointer saved at
`cs:[0242]` and returns to whoever saved it — not to `065C`'s caller. The IR finds the function
liftable (`refusals: []`); the refusal is raised later by the CPUless emitter, where SP must be a
tracked value and here it becomes an arbitrary word from memory.

**THE GENERAL FIX (dos_re, not a local patch).** This shape is not an OVERKILL quirk — every DOS C
runtime has a fatal-error path that restores a saved SP and returns. Refusing it costs the whole
function, and here transitively the entire game main loop. A non-local exit maps naturally onto a
**structured Python exception**: emit "restore SP from memory, then ret" as a raised
`NonLocalExit`-style witness carrying the saved-SP cell, caught at the recovered program root (or at a
matching setjmp site), instead of trying to model an unknowable stack pointer. That keeps the emitted
code honest — the abort really is non-local — and turns a hard refusal into a modelled control-flow
edge for every future game.

Deliberately NOT attempted as a local workaround (declaring `065C` an override would hide a general
autolifter limitation behind a port-specific island, and it is the third such limitation this
campaign has found: unconsumed boundary-head facts, the corrupting IP-delta probe, now this).


## 2026-07-18i — METHOD CHANGE: cold-boot forward, first divergence IS the frontier

Adopting the owner's method: grow ONE continuous oracle-proven path from startup rather than a
collection of locally passing islands. The work order stops being ours to choose — boot the recovered
program, let it run until it hits something the port has not supplied, repair that seam, rerun from
the beginning, and the next first-failure is the next task.

This is a direct correction to how the last few passes worked. Call-graph analysis produced a real
result (the promotion cascade, the probe bug) but also two wrong turns a cold boot could not have
made: naming `0B3E` as the DOS-I/O seam when it performs no DOS I/O at all, and a ten-function island
set where four were needed and six were ordinary game code.

**New instrument: `scripts/coldboot_frontier.py`.** Runs the corpus from the boot root under the armed
wall and reports the first thing it cannot do. `FailLoudPlatform` raises and NAMES the missing
service, and the recovered corpus never falls back to a VM — so the exception IS the output: a
precise, ordered statement of what the port owes next.

**FIRST RESULT — and the boot root was never the problem.** `254A:04D7` (the C-startup bootstrap, the
first game code a cold boot runs) is ALREADY PROMOTED, along with `0582/05A1/05BF/05D9` and
`1F8F:01AD`/`1F8F:0980`. An earlier scoping note in this campaign said "do NOT run the boot bootstrap
standalone (11 INT 21h C-startup calls)"; under the new method that avoidance was exactly backwards,
and running it is what produced a usable frontier in one command:

    FRONTIER: CpuStandaloneWitness
      INT 0x21 reached with no host platform implementation
      in recovered code: func_254a_04d7.py:78

The site is `ax = 0x3D02` -> **INT 21h AH=3Dh AL=02h, OPEN FILE**, filename ASCIIZ at `DS:[0740]`.
The very first DOS call of the cold boot opens the asset container.

**THE REPAIR — reuse dos_re's DOS model, do not hand-roll INT 21h.** `dos_re/dos.py` already has a
real DOS file service including details that were learned the hard way (`_alloc_handle` reuses the
LOWEST free handle, because a monotonic counter makes a game that indexes a fixed-size per-handle
table overrun it — a documented Ancient Empires bug). VERIFIED this pass: **`dos_re.dos` imports
clean under the CPUless wall**, so the port can use it directly. skyroads_port already cold-boots
through `dos_re.lift.platform.CPUlessPlatformRuntime` over `DOSMachine`, which is the same answer
arrived at independently.

So the next slice is NOT "write INT 21h handlers in OverkillPlatform" — it is to back the platform
with dos_re's DOS machine (serving the real `assets/OVERKILL` bytes, which are the original file, so
faithful rather than approximated), rerun `coldboot_frontier.py`, and let the frontier move to
whatever the second gap turns out to be. Every INT 21h handler hand-written in the port would be
DOS recreated unnecessarily, against the standing rule.


## 2026-07-18h — THE JOINT WASN'T REAL: the IP-delta probe was corrupting the code it measured

Followed the skin/skeleton question "is `0248` actually a joint, or did the decoder just fail to see
bone there?" all the way down. It was not a joint. It was a **dos_re bug**, now fixed upstream
(dos_re `612cb2f`).

**The chain of reasoning, because the wrong turns are instructive:**
1. `0248` refused `decoder-mismatch` at three sites, each reporting `interpreter-delta=3` against
   static lengths of 5, 2 and 2. A CONSTANT 3 across three different instructions is the tell.
2. Hypothesis: self-modifying code, fix = `--desmc`. **Falsified** — the bytes are identical in all
   three snapshots (frontend, static bundle, and the census's own L1 demo snapshot).
3. Hypothesis: the probe is broken. Probing those addresses directly gave the CORRECT 2/5/2, so it
   did not reproduce in isolation — but it reproduced exactly inside the real scan.
4. Instrumented the scan to dump the clone's memory AT PROBE TIME: the region read
   `3D FF 3D FF ...`. `3D` is `cmp ax,imm16` — **three bytes**. There was the constant 3.

**The bug:** the probe executes each candidate instruction for real, at a forced IP, with whatever
registers the previous probe step left behind. The registers are meaningless (only the LENGTH is
wanted) but the execution is not — a store with an unrelated base writes to a real address, and when
that lands in the CODE SEGMENT every later probe decodes the overwritten bytes. `decoder-mismatch` is
a FATAL refusal, so a stray write inside a diagnostic silently condemned a real function.

**How far it cascaded:** `0248` blocked `C679`, which blocked `4DBF`, which blocked `9B2E` — the
callee the top-level frame loop composes its boundary head through. So a probe artifact was
transitively why OVERKILL's entire main loop could not be promoted. This is the third capability-level
problem this campaign found by asking "why is this refused?" instead of working around the refusal.

**The fix** (`dos_re/lift/probe.py`, the single shared `make_ip_delta_probe`): restore the code
segment after every step — slice compare + assign, so the no-write case costs one memcmp. `liftgen`
and `irgen` had INDEPENDENT copies of the buggy probe; both now delegate. Registers and non-code
memory are deliberately left alone: they cannot change how a later instruction decodes. 5 tests,
including one pinning the hazard with `restore=False` so the restore cannot be optimised away.

**Effect after regenerating the pipeline:**
- `0248` now lifts cleanly, and its scan grows **74 -> 175 instructions** — the corruption was
  truncating the walk as well as mismeasuring it;
- `C679` (136 insts) and `5559` (248 insts) are now **LIFTABLE**, so neither needs a hand-written
  body: the island set loses its two large game functions;
- `ir-not-liftable` 4 -> 3; the committed corpus regenerated **byte-identical** (591 promotable), so
  the fix changed no emitted code, only what the frontier says is possible.

**Where the frontier now honestly sits.** `0248`'s remaining blockers are the genuine DOS surface:
`0615`/`0624`/`065C` and the far call **`254A:04D7`** (the C-startup bootstrap, 11 INT 21h calls) —
the same DOS surface a from-EXE cold boot needs. So the island set is converging on exactly what a
VM-less port must own, with no game logic in it.

**NOT yet working:** seeding `254A:04D7` as an override did not unblock (`594` promotable, slightly
worse than seeding the two near primitives alone at `595`), so the FAR-call override contract is
mis-specified — `ret_kind`/key-format for a far callee needs checking against `_read_overrides`
before the next attempt. That is the next concrete step, ahead of writing any body.


## 2026-07-18g — CORRECTION + MINIMISATION: the island set is FOUR, not ten (fewer islands promote MORE)

The 2026-07-18f entry claimed the ten seeded functions were "every one an INT 21h / INT 10h function,
i.e. exactly the surface a VM-less port must own". **That was wrong**, and checking the IR before
writing bodies caught it. Only FOUR of the ten perform any interrupt:

| addr | insts | ints | what it actually is |
|---|---|---|---|
| `1010:065C` | 14 | 21h | **DOS CLOSE FILE** — `mov bx,cs:[0240]; mov ah,3Eh; int 21h` |
| `1010:0624` | 27 | 21h | **buffered byte READ** — refills a 512-byte buffer at `DS:0410` via `AH=3Fh`, returns the next byte, bumps the pointer `[0610]` |
| `1010:C679` | 136 | 10h, 21h | game code containing DOS+video calls (far-calls `254A:04D7`, `1F8F:01AD`) |
| `1010:5559` | 248 | 10h, 21h | game code containing DOS+video calls (3 far calls) |

The other six are ORDINARY GAME CODE with `ints: []` that merely *call* those primitives:
`0615` (read a 16-bit LE word = two `0624` calls), `0324`, `0367`, `03A8` (file-format readers), and
`0011`/`0030` (JOYSTICK CALIBRATION — `0030` reads min/max and computes four centres as
`((max-min)>>1)+min`; nothing to do with DOS at all).

**Overriding them was actively harmful.** Re-measured with only the genuine platform functions seeded:

| seeded islands | promotable | top level |
|---|---|---|
| the 10 from 18f | 611 | 10/10 |
| **`065C 0624 C679 5559` (4)** | **614** | **10/10** |
| `065C 0624 0111` (3) | 596 | 0/10 |
| `065C 0624` (2) | 595 | 0/10 |

**FEWER, more correct islands promote MORE** (614 vs 611): the six non-platform functions promote
GENERATIVELY once the primitives exist, instead of being replaced by hand-written bodies. This is the
"don't override what the general machinery can handle" rule paying out in a directly measurable way,
and it is the number to defend — every function moved from island to generated is manual surface
deleted and proof standard raised.

**Why it does not shrink below four:** `C679` is blocked by `1010:0248`, class `likely-data`
(`decoder-mismatch` x3) — bytes the decoder cannot read as code, so `C679` cannot promote
generatively; `5559` is blocked through `0011`'s chain. `0248` has no ABI in the census, so it cannot
even be contract-seeded. **Open question worth answering before writing any body:** is `C679`'s call
to `0248` runtime-DEAD? If it is, the correct fix is a recovery FACT (the pipeline's `--observed`
already turns runtime-dead near calls into fail-loud stubs), not a 136-instruction hand-written
override — and the island set would drop to `065C` + `0624` + whatever `5559` truly needs. That is
the difference between two thin, obviously-correct DOS primitives and two large hand-transcribed
game functions, so it is worth resolving FIRST.

**Status of the requested slice:** the target set is now identified and minimised, and the two small
primitives (`065C`, `0624`) are fully understood at instruction level and ready to implement. The
faithful bodies + shadow evidence + measured virtual-time contracts are NOT yet written; they are the
next slice, and deliberately not half-landed here.


### `0248` follow-up — `--desmc` is a SECOND unwired capability (lead, not yet resolved)

`1010:0248` is `observed_reachable=True` AND `class=likely-data` (`decoder-mismatch` x3). Those two
facts together are contradictory for plain data: it EXECUTES, but its static bytes do not decode as
code. That signature is runtime-patched / self-modifying code, and dos_re already handles it —
`cpuless_promote --desmc` ("promote desmc-candidate functions, reading each patched operand from live
code memory") and `liftemit --desmc` ("emit desmc-candidate functions with their runtime-patched
operands read from live code memory").

**`scripts/probe_vmless_cpuless.py` passes `--desmc` to NO stage** (`grep -c desmc` = 0). This is the
same failure mode as the boundary-head / keep-interpreted facts: a capability exists upstream and the
port's pipeline never asks for it. `scripts/audit_recovery_facts.py` catches unconsumed FACT FILES;
it does not catch an unpassed FLAG, which is a gap in the audit worth closing.

Measured: adding `--desmc` to the promote stage ALONE changes nothing (591 promotable, identical
refusals) — expected, because the smc verdicts have to come from the IR, and `liftemit` was not run
with `--desmc` either (`close_census.py` does not expose the flag at all). So the experiment to run
next is a full pipeline pass with `--desmc` threaded through the IR stages, then re-measure whether
`0248` decodes and `C679` promotes generatively.

**Why this matters to the slice:** if it works, the island set drops from four to `065C` + `0624`
(+ whatever `5559` still needs) — i.e. from two large hand-transcribed game functions plus two DOS
primitives, down to just the two thin, obviously-correct DOS primitives. That is a large enough
difference in manual surface and proof standard to settle BEFORE writing any body.


## 2026-07-18f — PROVEN BY EXPERIMENT: only the DOS/BIOS SURFACE gates the top level

Ran the promotion as a DIAGNOSTIC (no `--apply`, census to scratch, committed corpus untouched),
seeding `--overrides` with contracts for the DOS/BIOS boundary functions and nothing else. Result:

| provided | promotable | `contains-call` | `boundary-head-on-transfer` | top level |
|---|---|---|---|---|
| nothing (committed) | 591 | 19 | 10 | refused |
| `C679` | 600 | 19 | **0** | refused (`contains-call`) |
| `C679` + `065C` | 600 | 18 | 0 | refused |
| **the 10 DOS/BIOS fns** | **611** | **0** | **0** | **ALL TEN PROMOTE** |

Seeded set: `C679 065C 5559 0011 0030 0324 0367 03A8 0615 0624` — every one an INT 21h / INT 10h
function, i.e. exactly the surface a VM-less port must own by definition.

**ALL TEN top-level entries promote** (`96C5 96C8 97B2 9720 986E 989E 98D8 9908 9921 9928`), and with
them the whole flow: `CBE8` (front-end), `CC04`, `D007` (the attract scene machine), `D390` (LEVEL
SELECT), `558B` (the menu start/idle decision), `9B2E`, `4DBF`. `contains-call` goes from 19 to
**zero**. What remains is 4 `ir-not-liftable` (`0248` likely-data, `3EFC`, two far-segment entries)
and 1 `sp-as-data` (`0111`) — none of them in the top level's closure.

**THE HEADLINE: no game logic blocks the top level. Only the DOS surface does.** Every piece of
OVERKILL's own code already promotes; the frame is missing purely because the port has not yet
supplied INT 21h/INT 10h as composed callees. That reframes the remaining work from "recover more of
the game" to "own the DOS boundary properly" — which is a bounded, well-understood job, and the same
one the from-EXE cold boot needs anyway (`254A:04D7` = 11 INT 21h C-startup calls).

It also confirms the boundary-head chain end to end: providing `C679` alone eliminated
`boundary-head-on-transfer` entirely (10 -> 0), i.e. `9B2E` became a composed callee and the declared
head `97CB` composed, exactly as predicted. The refusal then MOVED to `contains-call` rather than
disappearing, which is why the intermediate runs still showed the top level refused — worth noting,
because a single refusal-bucket count would have read as "no progress" when the real blocker had
changed class.

Reproduce:

    python dos_re/tools/cpuless_promote.py --ir artifacts/recovery_ir_closed.json       --recovered-dir <scratch>/rec --adapter-dir <scratch>/adp       --import-base overkill.cpuless_recovered       --boundary-heads artifacts/lift_boundary_heads.txt       --dyn-evidence artifacts/indirect_sites.json --absorb-dispatch-arms       --overrides <scratch>/ovr_dossurface.json --census-out <scratch>/census.json

**WHAT THIS IS NOT.** The diagnostic seeded CONTRACTS with no bodies and a placeholder `island`
virtual-time. It proves the promotion graph unlocks; it proves nothing about correctness. To land it:
1. faithful bodies for the 10 DOS/BIOS functions (file I/O + the INT 10h video calls). The port
   already owns the asset side natively (`cpuless_runtime.level_assets_for`), so much of the file I/O
   is answering from decoded bytes rather than emulating DOS;
2. a MEASURED virtual-time contract per function (`static` with a counted cost, or `model`) — the
   `island` default is NOT virtual-time-exact and `cost` anchors platform effects and demo-input
   landing, so guessing here could perturb the gameplay lockstep;
3. `--overrides` wired into `scripts/probe_vmless_cpuless.py`, regenerate, then verify the frame
   against the oracle across a cold start (skyroads' `verify_cpuless.py` does exactly this: 672
   frames byte-exact).


## 2026-07-18e — THE UNLOCK IS ONE OVERRIDE AT THE DOS-I/O SEAM (`1010:0B3E`)

Traced the blocker chain behind the missing top level to its leaves, and the answer is much smaller
and much better-placed than expected.

    boundary head 1010:97CB (`call 9B2E`) composes only if 9B2E is a composed callee
      9B2E   liftable=True, 74 insts, exits=['ret'], NO refusals of its own
        blocked solely by -> 4DBF  (level re-init)
          blocked solely by -> 0B3E (per-level ASSET LOADER)
            subtree: C679, 0615, 0624, 065C (sp-as-data), 0248 (likely-data)

Simulated providing `1010:0B3E`: **the entire blocked cascade under `9B2E` clears.** So one provided
function turns `9B2E` promotable, which composes the boundary head, which lifts all ten top-level
entries (`96C5 96C8 97B2 9720 986E 989E 98D8 9908 9921 9928`) as boundary-delimited coroutines — i.e.
the corpus gains the TOP LEVEL, and with it a cold-start flow that is oracle-comparable end to end.

**And `0B3E` is exactly the right seam — it is already ours.** It is the loader whose original does
INT 21h file reads; this port has supplied the decoded bytes natively since the beginning
(`cpuless_runtime.level_assets_for`, whose docstring already says "the original's 0B3E / 0E9C loaders
do INT 21h file reads; the native port hands the decoded bytes in instead"). This is not a manual
reimplementation competing with generated code — it is the host boundary a VM-less port must own, and
the one place where "the port provides it" is the correct answer rather than a shortcut.

**NO NEW CAPABILITY NEEDED — dos_re already has the build-time seam.** `dos_re/tools/cpuless_promote.py`
takes `--overrides`: "AUTHORITATIVE OVERRIDES (the unified override-graph seam): seed each override's
callee contract so callers compose it exactly like a generated callee (impl = overrides.get(addr,
generated[addr]))". Each entry declares a `CalleeContract` plus a VIRTUAL-TIME contract
(`static` / `model` = exact, `island` = one dispatch step, not virtual-time-exact and the default).
skyroads_port consumes the same mechanism through `skyroads/recovered_overrides/func_CCCC_IIII.py`
+ `_override_keys()`. So this is the general DOS_RE 2.0 shape, already used by a sibling port.

**IMPORTANT DISTINCTION this pass clarified:** THE STITCH (`cpuless_overrides.py`, runtime
`sys.modules` shadowing) can NOT unblock promotion — it substitutes a body at run time, while the
emitter refuses `9B2E` at BUILD time because no `func_1010_0b3e` module exists at all. The two seams
are complementary: `--overrides` makes the frame COMPOSE around port-provided code; the stitch
replaces an already-generated body at run time. `0B3E` needs the former.

**Virtual time is the open risk.** A hand-supplied `0B3E` is not instruction-exact, so it must declare
its contract honestly. `island` (the default) is NOT virtual-time-exact, and cost accumulates into
the caller's `_cost`, which anchors platform effects and where demo input lands — so an `island`
declaration here could perturb the gameplay lockstep. Preferred: `static` with a measured
per-invocation instruction count, or `model`. MEASURE IT AGAINST THE VM BEFORE DECLARING; a guessed
cost is exactly the kind of quiet approximation this project forbids.


### CORRECTION (same pass) — the seam is `1010:C679`, not `1010:0B3E`

The entry directly below named `0B3E` as the DOS-I/O seam. Checked it instead of trusting it, and it
was wrong on the load-bearing detail: **`0B3E` has `ints: []`** — it performs no INT 21h at all. It
calls `4E75` (already auto-cpuless) and `C679`. The DOS/BIOS boundary is `C679`:
`ints: ['10','21']` — file I/O *and* video — with `0615`/`0624`/`065C` (the INT 21h primitives,
`065C` self-recursive and refused `sp-as-data`) below it.

A proper FIXPOINT over the census call graph (a node promotes when every callee promotes and it has
no own shape refusal) settles which seam to use:

| provided | `0B3E` | `4DBF` | `9B2E` | total promotable |
|---|---|---|---|---|
| nothing | no | no | no | 591 |
| **`1010:C679`** | **yes** | **yes** | **yes** | **601** |
| `1010:0B3E` | yes | yes | yes | 594 |

**`C679` alone promotes the whole chain**, and it is the strictly better seam: the manual surface is
one function instead of a subtree, and ten more functions stay GENERATED (601 vs 594). It is also the
semantically correct boundary — INT 21h + INT 10h is precisely what a VM-less port must own, whereas
`0B3E` is ordinary game code that happens to sit above it. Overriding `0B3E` would have swallowed
`C679`'s video path as collateral.

Method note worth keeping: the first walk OVERSTATED what stayed blocked, because it counted any
callee not already promoted — including ones whose blockage clears once the seam is provided. Only
the fixpoint answers the question. Two of this session's wrong turns came from reading a
one-pass reachability walk as if it were a fixpoint.

**Remaining work before this can land** (deliberately not rushed):
1. a faithful `C679` body — 12 callees, `exits: ['jmp_ind','ret']`, so the indirect exit needs
   modelling, not hand-waving;
2. its `CalleeContract` (ret_kind/ret_pop/sp_delta) read off the census ABI;
3. a MEASURED virtual-time contract (`static` with a counted per-invocation cost, or `model`).
   The default `island` kind is NOT virtual-time-exact, and `cost` accumulates into the caller's
   `_cost`, which anchors platform effects and demo-input landing — an unmeasured cost here could
   perturb the gameplay lockstep, which is the one gate that must not be weakened;
4. wire `--overrides` into `scripts/probe_vmless_cpuless.py`, regenerate, and confirm the ten
   top-level entries stop refusing `boundary-head-on-transfer`.


## 2026-07-18d — ROOT CAUSE: the corpus has NO TOP LEVEL, because the lifter refuses `no-exit` regions

Owner report: "play_cpuless starts from a not-correct intro animation instead of the real starting
point and many things are incorrectly connected together". Investigated instead of patched, and the
cause is structural, not sloppiness.

**THE GAME'S TOP LEVEL IS `1010:96C5`/`1010:96C8`.** From the lift census call graph it calls
`CBE8` (the front-end/menu), `D390` (level select) AND `9B2E`/`97B2` (gameplay) — i.e. it *is* the
main loop that sequences the whole game. It matches the cold-start ground-truth table, which
recorded `96C8` as the address for the long front-end phase. (The 2026-07-12 note calling `96C8` "a
front-end address I misidentified" was itself wrong — it is the sequencer.)

**Why it is not in the corpus:**

    1010:96C8  liftable=False  refusal = {'reason': 'no-exit',
                                          'detail': 'no ret/retf/iret/far-jmp reachable'}

A game main loop never returns — "no exit" is its DEFINING property, not a defect. `97B2` and
`96C5` refuse for exactly the same reason. So the lifter structurally cannot emit any top level,
for this or any other DOS game.

**That hole is the origin of the whole flow problem.** With no generated top level, something had
to supply the sequencing, so it was hand-written into the runner: `--no-title`, `--level N`,
`--instructions`, `--ordering` are flags standing in for the original's decision sequence, plus the
`_run_title_menu` / `_run_native_attract` host loops. Every screen is individually fine; the wiring
BETWEEN screens was invented rather than recovered. And `play_cpuless --menu` entered at `CC04`,
which is three levels below the real root (`96C8` -> `CBE8` -> `CC04`) and does not even import
`d007` — so it contains no attract scene machine and can never advance the flow.

**Corrections to two earlier beliefs** (both measured this pass):
- `CC04` is NOT the front-end root. `CBE8` calls it; `96C5`/`96C8` call `CBE8`.
- The env-wait `1010:0679` is NOT on the `CC04` path at all (a probe over 400 boundaries never
  reached it) — the CC04 front-end paces on RETRACE, which the platform already satisfies. `0679`
  is called by `D007` (the attract scene machine) and by `96C8`, i.e. it blocks the REAL flow, not
  the one we were entering. This also means the "env-wait is why the front-end cannot animate"
  hypothesis was aimed at the wrong path.

**Landed this pass — THE STITCH (`overkill/cpuless_overrides.py`):** the mechanism that lets the
generated corpus own the flow while manual code patches addresses inside it. Generated modules bind
callees at IMPORT time (`from ...func_1010_cc4f import func_1010_cc4f`), so there is no per-call
resolver; the only seam is the module object, and `install_overrides(plat)` shadows `sys.modules`
before the corpus loads. Dynamic transfers route through `_dyncall` -> `DISPATCH`, which imports by
module name, so the same shadow serves them too. Invariants: an override must match the generated
contract; an override naming an address the corpus lacks raises `LookupError` (the guard against a
regeneration silently orphaning a manual patch); and the generated function stays reachable via
`generated(addr)` as its differential oracle, so an override that only ADDS an effect delegates to
it. `1010:0679` is the model — it yields to the new `OverkillPlatform.boundary()` scheduler hook,
supplies the tick the absent INT 8 handler owed, then calls the generated body so the returned
flags cannot drift. 7 tests.

**THE NEXT SLICE, and it is a generic dos_re capability:** teach the lifter to emit `no-exit`
top-level regions. A region with no reachable return is a `while True:` whose only exits are the
host boundaries it yields at — which is precisely the contract `plat.boundary` now provides. Every
DOS game has one; refusing it means no port can ever get its flow from the original code, which is
the single thing standing between this port and a real cold start. Promote it upstream.

Then: enter at `96C8`, observe `[BE06]`/`[98C3]`, delete the flag-as-flow interface, and gate the
sequence against the `probe_coldstart_frontend.py` ground-truth timeline.

**SUITE BUG FOUND + FIXED THE SAME PASS (2026-07-18d) — a LEAKED IMPORT GUARD, 239 red tests.** The
suite was red at 239 failed / 1206 passed on a CLEAN tree (so not caused by this pass's work, and the
earlier "1436 green" claim did not hold). Cause: `tests/test_cpuless_frontend_matches_native.py`
called `install_import_guard()` bare. That guard replaces `builtins.__import__` PROCESS-GLOBALLY, so
from that test onward every test legitimately needing the interpreter died with a
`CpuStandaloneWitness` raised nowhere near the culprit — and since each failing test PASSES in
isolation, it presents exactly like corpus drift. That is the second time this session a pollution
bug was first misread as drift.

Fixed at three levels, weakest to strongest:
1. the test uses the scoped form;
2. dos_re gains `uninstall_import_guard()` + an `import_guard()` CONTEXT MANAGER (promoted upstream —
   every port has this hazard). Teardown reads the displaced `__import__` off an attribute of the
   installed guard rather than a side stack, so a caller restoring by hand (the older try/finally
   idiom, still used by `test_cpuless_wall`) cannot desynchronise it and nesting unwinds correctly.
   The first stack-based implementation DID desync against that existing caller and its test caught
   it — kept as `test_nested_guards_unwind_in_order`;
3. `tests/conftest.py` gains an autouse RATCHET that fails the *individual* test that leaks a guard,
   naming it, and repairs `__import__` so the rest of the session is unaffected.

Suite: **1445 passed, 0 failed, 36 skipped**.

