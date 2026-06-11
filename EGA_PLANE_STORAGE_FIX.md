# EGA plane storage / screen-mixing fix

The remaining EGA artifact looked like stale bitplanes during sprite motion and,
more importantly, like whole screens being mixed during transitions.  That is not
just a transparency-mask problem: it points at the emulated EGA aperture itself.

## Root cause found

The previous EGA shadow layout stored the four display planes inside the same
CPU-visible A000h aperture:

```text
A000:0000  plane 0
A000:2000  plane 1
A000:4000  plane 2
A000:6000  plane 3
```

That is convenient for rendering, but it is not how real EGA memory works.
On real EGA, `A000:2000` is still CPU offset/page `2000h` inside the currently
selected hardware plane(s).  It is **not** plane 1 at visible offset 0.

The transition/fullscreen code really does touch those high CPU offsets.  A probe
up to the bonus/menu transition reported:

```text
A000 access buckets by 8 KiB page:
  rb page 0: 672
  wb page 0: 3283784
  ww page 0: 40576
  ww page 1: 23424

example: ww page 1 at 1010:274F A000:2000 map=F read=0
```

With the old storage, those `A000:2000` accesses could overwrite the renderer's
plane-1 shadow for the visible screen.  That explains why the artifact was EGA
only, why it appeared during transitions/clears/page copies, and why it looked
like mixed screens or stale colour planes rather than a simple sprite blit bug.

## Fix

`Memory` now stores emulated EGA planes outside the 20-bit CPU-visible address
space:

```text
CPU-visible aperture: A0000h..AFFFFh
shadow storage:       100000h + plane * 10000h + offset
```

CPU reads/writes to any `A000:0000..FFFF` offset are routed through the EGA
read-map / sequencer map-mask state into that separate shadow storage.  Rendering
and CRC sampling read from the separate shadow storage, not from the CPU aperture.

This keeps real CPU offsets/pages such as `A000:2000` from aliasing visible plane
1 offset `0000`.

## Verification

Added regression tests:

- `test_ega_cpu_page_offsets_do_not_alias_visible_shadow_planes`
- `test_ega_read_map_can_read_high_cpu_offsets_without_shadow_aliasing`

Full suite:

```text
72 passed
```

Diagnostic helper added:

```bash
python scripts/probe_ega_page_offsets.py
```
