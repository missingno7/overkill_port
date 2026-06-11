# EGA colour-ghosting fix

The gameplay EGA colour trails were consistent with stale bits surviving in one
or more EGA planes.  The problem was not CGA/Tandy-specific rendering; it was
that some lifted string-copy fast paths treated A000h as a flat bytearray.

Real EGA uses the same CPU offset for four bitplanes:

- writes go to the sequencer map-mask-selected planes (03C4h index 02h),
- reads come from the graphics-controller read-map-selected plane (03CEh index 04h).

The emulator already tracked the sequencer write map mask, but did not track the
GC read map select.  Also, optimized REP MOVS/STOS helpers used direct bytearray
slice copies, bypassing the Memory.rb/wb planar routing when source or
destination touched A000h.

Fixes in this revision:

1. `Memory` now tracks `ega_read_plane` and routes EGA A000h `rb/rw` through the
   selected shadow plane.
2. DOS port tracking now handles graphics-controller ports 03CEh/03CFh for index
   04h read-map-select writes.
3. Fast REP MOVSB/MOVSW/STOSB slice paths now automatically fall back to the
   per-byte Memory path whenever the transfer touches the EGA aperture.
4. The hot 5827 mode-1 EGA copy has a safe direct plane-aware copy path, so it
   does not become unbearably slow after correctness was restored.
5. Regression tests cover selected-plane EGA reads and planar-safe REP MOVSB / STOSB.

This is intentionally a hardware-semantics fix, not a visual workaround.  It
should prevent moving sprites from leaving partial-colour ghosts caused by only
some bitplanes being refreshed.
