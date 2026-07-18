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
