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

## next
- slice 2b: `scripts/play_cpuless.py` (import-guard wall + main loop) + `build_cpuless_boot_image.py`
  + `overkill/native/loader.py`; boot a tiny root standalone byte-exact vs the VM.

## Status log (newest first)
- **2026-07-18** slice 2a DONE (0ded6f3): `overkill/cpuless_host.py` `run_recovered` runs the committed
  corpus over a flat image (frame clock proven); `tests/test_cpuless_host.py` gates completeness +
  composition + fail-loud (5 pass).
- **2026-07-18** slice 1 DONE (e5fed92): corpus committed as runtime source; campaign opened; blueprint
  mapped from lemmings; corpus regenerated (561/626, walls HOLD).
