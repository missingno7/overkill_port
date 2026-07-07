> **SUPERSEDED (2026-07-07).** This document is a historical plan/report from an earlier phase.
> It is NOT the current direction and may contradict the present state.  The live authorities:
> [`campaigns/README.md`](campaigns/README.md) (the operating model) →
> [`campaigns/demo_lockstep.md`](campaigns/demo_lockstep.md) (THE active campaign) →
> the TOP HEADER of [`run_status.md`](run_status.md) (the current frontier).

# Performance investigation: VM/hook boundary crossings

This pass investigated the suspicion that many small leaf hooks are already fast,
but interpreted outer loops still repeatedly cross the VM/hook boundary.

## What changed

### `scripts/profile_hotspots.py`

The profiler now reports larger control-flow patterns, not only individual CS:IP
frequency:

- interpreted backward edges / tight loops,
- hook boundary crossings by predecessor address,
- hook stack words / likely call sites.

This is intended to find interpreted outer routines that repeatedly call already
hooked helpers.

### `overkill/hooks.py`

Optimized existing verified hooks rather than adding random tiny hooks:

- `overkill_masked_sprite_composite_3efb`
- `overkill_masked_sprite_composite_3e12`

Both now inline the repeated five-byte `RCR`/`SHR+RCR` chains as integer logic
instead of calling `CPU.shift` for every bit.

Also optimized:

- `overkill_ega_transparency_mask_2932`

This keeps the exact carry interactions of the original routine, including the
important detail that the first `RCL` sees the carry produced by the setup
`ADD BX,CS:[5B9C]`, not the caller's incoming carry flag.

## Verification

Current full test result:

```text
65 passed
```

## Profiling evidence

### CGA, 1,000,000 interpreted steps

After this pass:

```text
wall=16.88s, 59,259 interpreted-steps/sec
interpreter:        10.73s / 63.6%
replacement hooks:   5.16s / 30.6%
present hooks:       0.99s /  5.9%
hook invocations: 48,323
```

The optimized masked-compositor hooks are no longer dominant:

- `3EFB` was about 0.586s before; now about 0.067s in the previous post-change run.
- `3E12` was about 0.227s before; now about 0.048s in the previous post-change run.

The main CGA evidence for the user's suspicion is now the repeated render/object
call chain:

```text
A936 -> 5A92   2,768 crossings
A858 -> 5AC8   2,768 crossings
A93A -> A927   2,175 crossings
A8F5 -> A8C7   2,175 crossings
A85C -> A849   2,175 crossings
480E -> 5A36   2,175 crossings
```

The hottest interpreted tight loop in this profile is:

```text
1F8F:096F -> 1F8F:0960   7,636 iterations
```

That loop is an outer repeated update over small records:

```asm
1F8F:0960  inc word ptr ds:[si]
1F8F:0962  cmp word ptr ds:[si],00C0h
1F8F:0966  jnz 096C
1F8F:096C  add si,0006h
1F8F:096F  loop 0960
```

It is a proven hotspot, but it is not obviously part of the deterministic
asset-transformation path, so it was not hooked in this pass.

### EGA, 120,000 interpreted steps

After this pass:

```text
wall=7.63s, 15,731 interpreted-steps/sec
interpreter:         1.83s / 23.9%
replacement hooks:   5.80s / 76.1%
present hooks:       0.00s /  0.0%
hook invocations: 16,155
```

`2932` improved strongly:

```text
2932 before: about 2.549s, 7,550 calls, 337.6us/call
2932 after:  about 0.251s, 7,550 calls,  33.3us/call
```

Remaining EGA bottleneck:

```text
2824 overkill_ega_expand_temp_rows_2824: 4.747s, 4,242 calls, 1119us/call
```

The profiler now clearly shows the larger outer path to fuse next:

```text
27FB -> 2932   7,550 crossings
280A -> 280D   4,242 crossings
280D -> 2824   4,242 crossings
```

## Recommended next coherent hooks

1. Fuse the EGA asset-expansion driver around `27D9/27EB/27FA/280A` so it can
   inline `2932`, `280D`, and `2824` without thousands of VM/hook transitions.
2. Investigate the CGA object draw/present chain around the `D010/D016/D01C`
   call sites and helpers `A849/A8C7/A927/5AC8/5A92/5A36`.
3. Only consider hooking the `1F8F:0960` loop after its semantics are verified,
   because it is hot but does not look like the highest-priority deterministic
   asset pipeline target.

## 2026-06-11 next fusion pass: EGA 27EB row driver

Implemented the next recommended coherent hook instead of adding more random
leaf hooks:

- `1010:27EB overkill_ega_row_driver_27eb`
  - fuses the interpreted outer EGA mode-1 row driver;
  - directly drives the already verified `2932`, `280D`, and `2824` logic;
  - removes the repeated `27FB -> 2932`, `280A -> 280D`, and `280D -> 2824`
    VM/hook boundary crossings from the row path.

Also rewrote the core of:

- `1010:2824 overkill_ega_expand_temp_rows_2824`

The original lift was correct but still used `CPU.shift` inside the per-pixel
rotate/shift chain.  That became too expensive once `27EB` could process whole
row groups inside one hook call.  The new version performs the same plane packing
with local integer bit operations, while preserving the observable stack scratch
writes, registers, flags, memory output, and original loop exits.

Safety/correctness work:

- Added an oracle-style regression test for the broad `27EB` driver.  The oracle
  side runs the original interpreted `27EB` setup with the previously verified
  narrow hooks enabled; the test side replaces only `27EB` with the fused driver.
- Existing `2824` interpreted-ASM oracle still passes after the faster bit-pack
  rewrite.
- Full test suite: `66 passed`.

Profiling after the pass, EGA, 120,000 steps:

```text
wall=6.98s, 17,193 interpreted-steps/sec
interpreter:        2.67s / 38.3%
replacement hooks:  4.30s / 61.7%
hook invocations: 1,085
```

The previous explicit crossings are gone from the profiler output.  The new main
EGA interpreted hotspot after this pass is the mode-1 post-copy blitter path
around `1010:2D2D..2E20`, reached through the `58DF` dispatch loop:

```text
1010:2E20 -> 1010:2D8D   1,609 iterations
```

The existing `58DF` hook had only been verified for mode 0.  Now that the EGA
startup reaches that path sooner, it no longer crashes on mode 1; unsupported
modes make the hook self-disable and fall back to the original interpreted code.

Recommended next target:

- Lift the mode-1 blitter selected by `58DF` at `1010:2D2D`, because it is now the
  dominant interpreted EGA loop after the `27EB` fusion.

## 2026-06-11 visual regression fix: EGA marker branch in `2824`

The screenshot regression came from the optimized `2824` bit-pack rewrite taking
the marker branch from the older lifted hook too literally.  A direct comparison
against the original interpreted ASM shows that the branch is counter-intuitive:

```asm
cmp byte [bp],01h
je  swap_06_0c
cmp byte [bp],02h
je  skip_swap
```

So marker byte `1` swaps colours `06h` and `0Ch`; marker byte `2` preserves the
colour.  The optimized hook had this reversed.  That can visibly corrupt EGA
menu/title assets because the branch is part of the planar expansion path.

Fix applied:

- `overkill_ega_expand_temp_rows_2824` now swaps `06h`/`0Ch` only for marker byte
  `1`, matching the original ASM.
- The `2824` oracle test now includes forced marker-byte `1` and `2` cases with a
  pixel deliberately constructed as colour `06h`, so this branch cannot silently
  regress again.
- Full test suite after fix: `66 passed`.
