# EGA screen mixing investigation

The reported artifact is broader than sprite transparency: during menu/intro
transitions two whole screens can appear partially mixed.  That makes the likely
failure mode an EGA page/present/dirty-copy problem rather than only the
2932/2824 sprite-row mask pipeline.

## What was checked

1. `1010:CCAA`, `1010:CCC4`, `1010:CCF0` dirty-copy hooks
   - These are now disabled by default for interactive non-CGA playback in
     `scripts/play.py`.
   - Their isolated tests still pass, but they sit in the same fullscreen
     transition/dirty-copy cluster and should not be trusted for EGA/Tandy live
     playback until the surrounding dispatcher/page setup is verified in context.

2. EGA present hook `1010:2750`
   - This is not a general fullscreen clear.  It copies the active EGA presented
     rectangle into the four A000 shadow planes.
   - The hook already writes explicit plane chunks at `A000+0000`, `+2000`,
     `+4000`, `+6000` and ends by restoring map mask `0Fh`.

3. Fullscreen/page-copy path around `1010:2D2D`
   - In an EGA trace, the `58DF` dispatcher selects the mode-1 callee at `2D2D`.
   - `2D2D` sets the sequencer map-mask index, clears a row, then writes the four
     planes with map masks `01h`, `02h`, `04h`, `08h` before returning to the
     retrace wait.  This means the retrace boundary after `2D2D` should see a
     coherent four-plane row/page update.

4. Fused EGA asset row driver `1010:27EB`
   - Compared the fused `27EB` path against interpreted `27EB` with the verified
     leaf hooks enabled up to the first EGA fullscreen blit/retrace.
   - CPU state and the whole 1 MiB memory image matched exactly at the boundary.

## Fix made here

The narrow `1010:291C` temp-row-copy hook still had a direct flat-memory store:

```python
mem.data[(es << 4) + out_di] = al
```

That bypasses the EGA sequencer map mask when `ES=A000h`.  If this helper is
reached with the hardware aperture active, only one shadow byte is updated and
stale bits can remain in the other planes.  The hook now detects A000h overlap
and routes the write through `Memory.wb()`, so `STOSB` honours the selected EGA
map mask exactly like the interpreter.

A regression test now compares interpreted `291C` against the hook with:

- `mem.ega_planar = True`
- `ES = A000h`
- map mask `1010b`
- pre-filled stale data in all four planes

Only planes 1 and 3 are changed, matching the ASM path.

## Current status

The project now passes:

```text
70 passed
```

The next likely place to investigate if screen mixing remains is the interpreted
mode-1 fullscreen blitter `1010:2D2D..2E20` and the transition row copier around
`1010:5C83`, because those are the routines that actually perform visible EGA
screen/page changes after the startup asset expansion.
