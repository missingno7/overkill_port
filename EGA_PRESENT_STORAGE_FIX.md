# EGA present/storage follow-up fix

The previous `EGA_PLANE_STORAGE_FIX` moved emulated EGA planes out of the
CPU-visible A000h aperture, which is the right model: CPU offsets such as
`A000:2000` are real offsets/pages, not plane selectors.

However, one lifted routine still assumed the legacy storage layout:

- `1010:2750 overkill_present_ega_frame_2750`

That hook continued to copy presented planes to flat offsets:

```text
A000:0000 + row
A000:2000 + row
A000:4000 + row
A000:6000 + row
```

After the storage move, the live EGA renderer reads from the shadow-plane store:

```text
EGA_APERTURE + plane * EGA_PLANE_STRIDE + row
```

So the presenter could run and update only stale CPU-visible bytes, while the
rendered shadow planes did not change. This matches the new symptom where the
problem area was touched, but some screen changes no longer updated at all.

## Fix

`overkill_present_ega_frame_2750` now writes directly into the new shadow-plane
store when the destination segment is `A000h`, and keeps a flat fallback for
non-A000 synthetic/oracle cases.

The test `test_present_ega_frame_2750_hook_writes_shadow_planes` was updated to
enable planar mode and assert against the real shadow-plane store, not the old
flat `A000:+2000` aliases.

## Performance follow-up

The dirty-copy hooks `CCAA`, `CCC4`, and `CCF0` were re-enabled for interactive
EGA/Tandy playback. They were previously disabled while investigating screen
mixing, but the later plane-storage aliasing fix explains that class of artifact.
Keeping those hooks disabled made menu/level-select transitions noticeably
slower.

`58DF` remains disabled for non-CGA interactive playback because that hook is
still mode-0-specific and self-disables when reached in EGA/Tandy profiling.
